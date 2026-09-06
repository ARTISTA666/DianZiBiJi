// 实验区：RAG 实验运行/租约、证据导出与 CSV 导出。

use std::{collections::HashSet, panic::AssertUnwindSafe, time::Duration};

use futures_util::FutureExt;

use axum::{
    body::Body,
    extract::{Path, State},
    http::{header, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use super::{
    mode_requires_dataset, mode_uses_embeddings, query_project_rag_inner,
    require_compatible_embedding, require_manager, require_unblinded_access, ExperimentLogContext,
    QueryLogRow, EXPERIMENT_COLUMNS, MAX_RAG_QUERY_CHARS,
};
use crate::{
    api::auth::CurrentUser,
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    db::{EXPERIMENT_HEARTBEAT_INTERVAL_SECONDS, EXPERIMENT_LEASE_SECONDS},
    error::ApiError,
    models::{
        AIExperimentRunRead, AIExperimentRunRequest, RagDatasetRead, RagQueryRequest, UserRecord,
    },
    permissions::{require_external_ai, require_project_access},
    rag::{document_snapshot_in_transaction, graph_snapshot_in_transaction},
    AppState,
};

const EXPERIMENT_CSV_HEADER: &str = concat!(
    "\u{feff}experiment_run_id,question_index,question,mode,repetition_index,execution_order,",
    "status,query_log_id,answer,source_count,graph_hit_count,response_ms,provider,model,",
    "prompt_version,fallback_reason,sources_json,graph_context_json,usage_json,error,",
    "retrieval_config_json,embedding_model,corpus_snapshot_hash,rag_index_version,index_version,",
    "graph_schema_version,",
    "retrieval_strategy,retrieval_top_k,collection_retrieval_top_k,vector_candidate_k,graph_top_k,",
    "chunk_size,chunk_overlap,graph_min_score,retrieval_min_score\r\n"
);

pub(super) async fn run_experiment(
    State(state): State<AppState>,
    _client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Json(payload): Json<AIExperimentRunRequest>,
) -> Result<(StatusCode, Json<AIExperimentRunRead>), ApiError> {
    let project = require_project_access(&state.pool, &user, project_id).await?;
    require_external_ai(&project, state.settings.allow_sensitive_external_ai)?;
    require_manager(&state, &user, project_id).await?;
    let name = payload.name.trim();
    if name.is_empty() || name.chars().count() > 255 {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Experiment name must contain between 1 and 255 characters",
        ));
    }
    let questions = normalize_experiment_questions(payload.questions)?;
    let allowed_modes = [
        "pure_llm",
        "bm25_rag",
        "project_rag",
        "structured_query",
        "kg_enhanced_rag",
    ];
    let mut modes = Vec::new();
    for mode in payload.modes {
        if !modes.contains(&mode) {
            modes.push(mode);
        }
    }
    if modes.is_empty()
        || modes.len() > 5
        || modes
            .iter()
            .any(|mode| !allowed_modes.contains(&mode.as_str()))
    {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            format!(
                "Experiment modes must be one of: {}",
                allowed_modes.join(", ")
            ),
        ));
    }
    if !(1..=10).contains(&payload.repetitions) {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Repetitions must be between 1 and 10",
        ));
    }
    validate_expected_snapshot_bindings(
        &modes,
        payload.expected_corpus_snapshot_hash.as_deref(),
        payload.expected_graph_snapshot_hash.as_deref(),
    )?;
    let questions_hash = questions_sha256(&questions);
    let seed = payload.random_seed.unwrap_or_else(|| {
        let digest = Sha256::digest(uuid::Uuid::new_v4().as_bytes());
        i32::from_be_bytes([digest[0] & 0x7f, digest[1], digest[2], digest[3]])
    });
    let mut plan = Vec::new();
    for (question_index, question) in questions.iter().enumerate() {
        for repetition_index in 1..=payload.repetitions {
            for mode in &modes {
                plan.push(json!({
                    "question_index": question_index + 1,
                    "question": question,
                    "repetition_index": repetition_index,
                    "mode": mode
                }));
            }
        }
    }
    if payload.randomize_order {
        plan.sort_by_key(|item| {
            let material = format!(
                "{}:{}:{}:{}:{}",
                seed,
                item["question_index"],
                item["repetition_index"],
                item["mode"],
                item["question"]
            );
            Sha256::digest(material.as_bytes()).to_vec()
        });
    }
    for (index, item) in plan.iter_mut().enumerate() {
        item["execution_order"] = json!(index + 1);
    }
    let plan_hash = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&plan).map_err(ApiError::internal)?)
    );
    let mut transaction = state.pool.begin().await?;
    sqlx::query("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        .execute(&mut *transaction)
        .await?;
    lock_experiment_project(&mut transaction, project_id).await?;
    ensure_no_active_experiment(&mut transaction, project_id).await?;
    let dataset = if modes.iter().any(|mode| mode_requires_dataset(mode)) {
        let dataset = sqlx::query_as::<_, RagDatasetRead>(&format!(
            "SELECT {} FROM project_rag_datasets WHERE project_id = $1",
            super::DATASET_COLUMNS
        ))
        .bind(project_id)
        .fetch_optional(&mut *transaction)
        .await?
        .ok_or_else(|| {
            ApiError::new(
                StatusCode::CONFLICT,
                "RAG 资料库尚未初始化，请先在数据页完成资料入库",
            )
        })?;
        if modes.iter().any(|mode| mode_uses_embeddings(mode)) {
            require_compatible_embedding(&state, &dataset)?;
        }
        Some(dataset)
    } else {
        None
    };
    let active_corpus = if dataset.is_some() {
        Some(
            document_snapshot_in_transaction(
                &mut transaction,
                project_id,
                &state.settings.rag_index_version,
            )
            .await?,
        )
    } else {
        None
    };
    let active_graph = if modes
        .iter()
        .any(|mode| matches!(mode.as_str(), "structured_query" | "kg_enhanced_rag"))
    {
        Some(graph_snapshot_in_transaction(&mut transaction, project_id).await?)
    } else {
        None
    };
    if let Some(detail) = compare_experiment_snapshots(
        &modes,
        payload.expected_corpus_snapshot_hash.as_deref(),
        payload.expected_graph_snapshot_hash.as_deref(),
        active_corpus
            .as_ref()
            .map(|snapshot| snapshot.hash.as_str()),
        active_graph.as_ref().map(|snapshot| snapshot.hash.as_str()),
    ) {
        return Err(ApiError::new(StatusCode::CONFLICT, detail.to_string()));
    }
    let run_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO ai_experiment_runs (
            project_id, created_by, name, status, questions_json, modes_json,
            config_snapshot_json, summary_json, total_cases, completed_cases,
            failed_cases, created_at, completed_at
        )
        VALUES ($1, $2, $3, 'queued', $4, $5, $6, $7, $8, 0, 0, now(), NULL)
        RETURNING id
        "#,
    )
    .bind(project_id)
    .bind(user.id)
    .bind(name)
    .bind(json!(questions))
    .bind(json!(modes))
    .bind(json!({
        "embedding_model": state.settings.embedding_model,
        "generation_model": state.ai_provider.model(),
        "questions_sha256": questions_hash,
        "corpus_snapshot_hash": active_corpus.as_ref().map(|snapshot| &snapshot.hash),
        "graph_snapshot_hash": active_graph.as_ref().map(|snapshot| &snapshot.hash),
        "rag_index_version": state.settings.rag_index_version,
        "graph_schema_version": crate::rag::GRAPH_SCHEMA_VERSION,
        "experiment_protocol": {
            "repetitions": payload.repetitions,
            "randomize_order": payload.randomize_order,
            "random_seed": seed,
            "execution_plan_hash": plan_hash
        }
    }))
    .bind(json!({
        "errors": [],
        "fatal_error": null,
        "unexecuted_cases": plan.len(),
        "execution_plan": plan
    }))
    .bind(plan.len() as i32)
    .fetch_one(&mut *transaction)
    .await
    .map_err(map_experiment_write_error)?;
    transaction.commit().await?;
    let run = fetch_experiment(&state, run_id).await?;
    spawn_experiment(state.clone(), user.clone(), run_id);
    Ok((StatusCode::ACCEPTED, Json(run)))
}

pub(super) async fn list_experiments(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<Vec<AIExperimentRunRead>>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    require_unblinded_access(&state, &user, project_id).await?;
    let query = format!(
        "SELECT {EXPERIMENT_COLUMNS} FROM ai_experiment_runs WHERE project_id = $1 ORDER BY created_at DESC, id DESC LIMIT 50"
    );
    Ok(Json(
        sqlx::query_as::<_, AIExperimentRunRead>(&query)
            .bind(project_id)
            .fetch_all(&state.pool)
            .await?,
    ))
}

pub(super) async fn get_experiment(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(run_id): Path<i32>,
) -> Result<Json<AIExperimentRunRead>, ApiError> {
    let run = fetch_experiment(&state, run_id).await?;
    require_project_access(&state.pool, &user, run.project_id).await?;
    require_unblinded_access(&state, &user, run.project_id).await?;
    Ok(Json(run))
}

pub(super) async fn resume_experiment(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(run_id): Path<i32>,
) -> Result<(StatusCode, Json<AIExperimentRunRead>), ApiError> {
    let run = fetch_experiment(&state, run_id).await?;
    let project = require_project_access(&state.pool, &user, run.project_id).await?;
    require_external_ai(&project, state.settings.allow_sensitive_external_ai)?;
    require_manager(&state, &user, run.project_id).await?;
    if run.status != "interrupted" {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only interrupted experiments can resume",
        ));
    }
    if !transition_interrupted_to_queued(&state, run_id, run.project_id).await? {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Experiment is no longer interrupted or another experiment is active",
        ));
    }
    spawn_experiment(state.clone(), user.clone(), run_id);
    Ok((
        StatusCode::ACCEPTED,
        Json(fetch_experiment(&state, run_id).await?),
    ))
}

pub(super) async fn export_experiment(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(run_id): Path<i32>,
) -> Result<Response, ApiError> {
    let run = fetch_experiment(&state, run_id).await?;
    require_project_access(&state.pool, &user, run.project_id).await?;
    require_unblinded_access(&state, &user, run.project_id).await?;
    experiment_csv_response(&state, &run, &format!("rag-experiment-{run_id}.csv")).await
}

pub(super) async fn export_experiment_evidence(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(run_id): Path<i32>,
) -> Result<Response, ApiError> {
    let run = fetch_experiment(&state, run_id).await?;
    require_project_access(&state.pool, &user, run.project_id).await?;
    require_unblinded_access(&state, &user, run.project_id).await?;
    if let Some(detail) = evidence_export_status_error(&run.status) {
        return Err(ApiError::new(StatusCode::CONFLICT, detail));
    }
    let logs = sqlx::query_as::<_, QueryLogRow>(
        r#"
        SELECT id, project_id, user_id, question, answer, rag_mode,
               graph_hit_count, source_count, response_ms, conversation_id,
               graph_context_json, sources_json, provider, model_name,
               prompt_version, retrieval_config_json, usage_json,
               fallback_reason, error_message, experiment_run_id,
               experiment_case_index, experiment_repetition_index,
               experiment_execution_order, created_at
        FROM ai_query_logs WHERE experiment_run_id = $1
        ORDER BY experiment_execution_order, id
        "#,
    )
    .bind(run_id)
    .fetch_all(&state.pool)
    .await?;
    let cases = logs.into_iter().map(experiment_evidence_case).collect();
    let package = build_experiment_evidence_package(
        &json!({
            "id": run.id,
            "project_id": run.project_id,
            "created_by": run.created_by,
            "name": run.name,
            "status": run.status,
            "questions": run.questions_json,
            "modes": run.modes_json,
            "config_snapshot": run.config_snapshot_json,
            "summary": run.summary_json,
            "total_cases": run.total_cases,
            "completed_cases": run.completed_cases,
            "failed_cases": run.failed_cases,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
        }),
        cases,
    );
    let body = serde_json::to_vec_pretty(&package).map_err(ApiError::internal)?;
    let mut response = Body::from(body).into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/json; charset=utf-8"),
    );
    if let Ok(value) = HeaderValue::from_str(&format!(
        "attachment; filename=\"rag-experiment-{run_id}-evidence.json\""
    )) {
        response
            .headers_mut()
            .insert(header::CONTENT_DISPOSITION, value);
    }
    Ok(response)
}

fn evidence_export_status_error(status: &str) -> Option<&'static str> {
    match status {
        "queued" | "running" => {
            Some("Experiment evidence is unavailable until the run reaches a terminal state")
        }
        "interrupted" | "completed" | "completed_with_errors" | "failed" => None,
        _ => Some("Experiment evidence is unavailable for an unsupported run status"),
    }
}

fn experiment_evidence_case(log: QueryLogRow) -> Value {
    let failed = log.error_message.is_some();
    let citation_audit = log
        .retrieval_config_json
        .get("citation_audit")
        .cloned()
        .unwrap_or_else(|| json!({}));
    json!({
        "query_log_id": log.id,
        "question_index": log.experiment_case_index,
        "question": log.question,
        "mode": log.rag_mode,
        "repetition_index": log.experiment_repetition_index,
        "execution_order": log.experiment_execution_order,
        "status": if failed { "failed" } else { "completed" },
        "failure_scope": if failed { json!("case") } else { Value::Null },
        "failure_code": if failed { json!("query_error") } else { Value::Null },
        "answer": log.answer,
        "source_count": log.source_count,
        "graph_hit_count": log.graph_hit_count,
        "response_ms": log.response_ms,
        "provider": log.provider,
        "model": log.model_name,
        "prompt_version": log.prompt_version,
        "fallback_reason": log.fallback_reason,
        "error": log.error_message,
        "sources": log.sources_json,
        "graph_context": log.graph_context_json,
        "retrieval_config": log.retrieval_config_json,
        "usage": log.usage_json,
        "citation_audit": citation_audit,
        "created_at": log.created_at,
    })
}

fn normalize_experiment_questions(raw_questions: Vec<String>) -> Result<Vec<String>, ApiError> {
    let questions: Vec<String> = raw_questions
        .into_iter()
        .map(|question| question.trim().to_owned())
        .filter(|question| !question.is_empty())
        .collect();
    if questions.is_empty() || questions.len() > 50 {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "At least one and at most 50 questions are required",
        ));
    }
    if questions
        .iter()
        .any(|question| question.chars().count() > MAX_RAG_QUERY_CHARS)
    {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            format!("Each question cannot exceed {MAX_RAG_QUERY_CHARS} characters"),
        ));
    }
    let mut seen = HashSet::new();
    if questions.iter().any(|question| !seen.insert(question)) {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Experiment questions must not contain duplicates",
        ));
    }
    Ok(questions)
}

pub(super) fn questions_sha256(questions: &[String]) -> String {
    let bytes = serde_json::to_vec(questions).expect("question arrays are JSON serializable");
    format!("{:x}", Sha256::digest(bytes))
}

struct ExperimentRuntimeBindings<'a> {
    corpus_snapshot_hash: Option<&'a str>,
    graph_snapshot_hash: Option<&'a str>,
    index_version: &'a str,
    embedding_model: &'a str,
    generation_model: &'a str,
    graph_schema_version: &'a str,
}

fn validate_experiment_input_bindings(
    config: &Value,
    questions: &Value,
    modes: &Value,
    runtime: ExperimentRuntimeBindings<'_>,
) -> Result<(), String> {
    let questions = questions
        .as_array()
        .ok_or_else(|| "questions_json must be an array".to_owned())?
        .iter()
        .map(|question| question.as_str().map(ToOwned::to_owned))
        .collect::<Option<Vec<_>>>()
        .ok_or_else(|| "questions_json must contain only strings".to_owned())?;
    let expected_questions_hash = config
        .get("questions_sha256")
        .and_then(Value::as_str)
        .ok_or_else(|| "config_snapshot.questions_sha256 is missing".to_owned())?;
    let actual_questions_hash = questions_sha256(&questions);
    if actual_questions_hash != expected_questions_hash {
        return Err("questions_sha256 does not match the queued question set".to_owned());
    }

    for (key, current) in [
        ("rag_index_version", runtime.index_version),
        ("embedding_model", runtime.embedding_model),
        ("generation_model", runtime.generation_model),
        ("graph_schema_version", runtime.graph_schema_version),
    ] {
        let expected = config
            .get(key)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("config_snapshot.{key} is missing"))?;
        if expected != current {
            return Err(format!(
                "config_snapshot.{key} does not match the runtime value"
            ));
        }
    }

    let dataset_backed = modes
        .as_array()
        .ok_or_else(|| "modes_json must be an array".to_owned())?
        .iter()
        .map(|mode| {
            mode.as_str()
                .ok_or_else(|| "modes_json must contain only strings".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .any(mode_requires_dataset);
    let expected_corpus_hash = config.get("corpus_snapshot_hash");
    if dataset_backed {
        let expected_corpus_hash = expected_corpus_hash
            .and_then(Value::as_str)
            .ok_or_else(|| "config_snapshot.corpus_snapshot_hash is missing".to_owned())?;
        if runtime.corpus_snapshot_hash != Some(expected_corpus_hash) {
            return Err(
                "config_snapshot.corpus_snapshot_hash does not match the active corpus".to_owned(),
            );
        }
    } else if expected_corpus_hash.is_some_and(|hash| !hash.is_null()) {
        return Err("non-dataset experiments must not carry a corpus_snapshot_hash".to_owned());
    }
    let graph_backed = modes
        .as_array()
        .ok_or_else(|| "modes_json must be an array".to_owned())?
        .iter()
        .filter_map(Value::as_str)
        .any(|mode| matches!(mode, "structured_query" | "kg_enhanced_rag"));
    let expected_graph_hash = config.get("graph_snapshot_hash");
    if graph_backed {
        let expected_graph_hash = expected_graph_hash
            .and_then(Value::as_str)
            .ok_or_else(|| "config_snapshot.graph_snapshot_hash is missing".to_owned())?;
        if runtime.graph_snapshot_hash != Some(expected_graph_hash) {
            return Err(
                "config_snapshot.graph_snapshot_hash does not match the active graph".to_owned(),
            );
        }
    } else if expected_graph_hash.is_some_and(|hash| !hash.is_null()) {
        return Err("non-graph experiments must not carry a graph_snapshot_hash".to_owned());
    }
    Ok(())
}

fn validate_expected_snapshot_bindings(
    modes: &[String],
    expected_corpus_hash: Option<&str>,
    expected_graph_hash: Option<&str>,
) -> Result<(), ApiError> {
    let corpus_required = modes.iter().any(|mode| mode_requires_dataset(mode));
    let graph_required = modes
        .iter()
        .any(|mode| matches!(mode.as_str(), "structured_query" | "kg_enhanced_rag"));
    if corpus_required != expected_corpus_hash.is_some() {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            if corpus_required {
                "Dataset-backed experiments must provide expected_corpus_snapshot_hash"
            } else {
                "Non-dataset experiments must not provide expected_corpus_snapshot_hash"
            },
        ));
    }
    if graph_required != expected_graph_hash.is_some() {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            if graph_required {
                "Graph-backed experiments must provide expected_graph_snapshot_hash"
            } else {
                "Non-graph experiments must not provide expected_graph_snapshot_hash"
            },
        ));
    }
    for (name, value) in [
        ("expected_corpus_snapshot_hash", expected_corpus_hash),
        ("expected_graph_snapshot_hash", expected_graph_hash),
    ] {
        if let Some(value) = value {
            if !super::valid_snapshot_hash(value) {
                return Err(ApiError::new(
                    StatusCode::UNPROCESSABLE_ENTITY,
                    format!("{name} must be a lowercase SHA-256 hash"),
                ));
            }
        }
    }
    Ok(())
}

fn compare_experiment_snapshots(
    modes: &[String],
    expected_corpus_hash: Option<&str>,
    expected_graph_hash: Option<&str>,
    actual_corpus_hash: Option<&str>,
    actual_graph_hash: Option<&str>,
) -> Option<Value> {
    let corpus_mismatch = modes.iter().any(|mode| mode_requires_dataset(mode))
        && expected_corpus_hash != actual_corpus_hash;
    let graph_mismatch = modes
        .iter()
        .any(|mode| matches!(mode.as_str(), "structured_query" | "kg_enhanced_rag"))
        && expected_graph_hash != actual_graph_hash;
    (corpus_mismatch || graph_mismatch).then(|| {
        json!({
            "error": "experiment_snapshot_drift",
            "expected_corpus_snapshot_hash": expected_corpus_hash,
            "actual_corpus_snapshot_hash": actual_corpus_hash,
            "expected_graph_snapshot_hash": expected_graph_hash,
            "actual_graph_snapshot_hash": actual_graph_hash,
        })
    })
}

async fn validate_current_experiment_input_bindings(
    state: &AppState,
    run: &AIExperimentRunRead,
) -> Result<(), ApiError> {
    if run.total_cases == 0 {
        return Ok(());
    }
    let current_corpus_hash = if run
        .modes_json
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .any(mode_requires_dataset)
    {
        Some(
            crate::rag::document_snapshot(
                &state.pool,
                run.project_id,
                &state.settings.rag_index_version,
            )
            .await
            .map_err(|error| {
                ApiError::new(
                    StatusCode::CONFLICT,
                    format!("Experiment input binding drift detected: {}", error.detail),
                )
            })?
            .hash,
        )
    } else {
        None
    };
    let current_graph_hash = if run
        .modes_json
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .any(|mode| matches!(mode, "structured_query" | "kg_enhanced_rag"))
    {
        Some(
            crate::rag::graph_snapshot(&state.pool, run.project_id)
                .await?
                .hash,
        )
    } else {
        None
    };
    let generation_model = state.ai_provider.model();
    validate_experiment_input_bindings(
        &run.config_snapshot_json,
        &run.questions_json,
        &run.modes_json,
        ExperimentRuntimeBindings {
            corpus_snapshot_hash: current_corpus_hash.as_deref(),
            graph_snapshot_hash: current_graph_hash.as_deref(),
            index_version: &state.settings.rag_index_version,
            embedding_model: &state.settings.embedding_model,
            generation_model,
            graph_schema_version: crate::rag::GRAPH_SCHEMA_VERSION,
        },
    )
    .map_err(|detail| {
        ApiError::new(
            StatusCode::CONFLICT,
            format!("Experiment input binding drift detected: {detail}"),
        )
    })
}

fn build_experiment_evidence_package(run: &Value, mut cases: Vec<Value>) -> Value {
    let summary = run.get("summary").cloned().unwrap_or_else(|| json!({}));
    let logged_orders: HashSet<i32> = cases
        .iter()
        .filter_map(|case| case["execution_order"].as_i64())
        .filter_map(|order| i32::try_from(order).ok())
        .collect();
    if let Some(errors) = summary.get("errors").and_then(Value::as_array) {
        for error in errors {
            let Some(order) = error["execution_order"]
                .as_i64()
                .and_then(|value| i32::try_from(value).ok())
            else {
                continue;
            };
            if logged_orders.contains(&order) {
                continue;
            }
            cases.push(json!({
                "query_log_id": null,
                "question_index": error["question_index"],
                "question": error["question"],
                "mode": error["mode"],
                "repetition_index": error["repetition_index"].as_i64().unwrap_or(1),
                "execution_order": order,
                "status": "failed",
                "failure_scope": error
                    .get("failure_scope")
                    .cloned()
                    .unwrap_or_else(|| json!("case")),
                "failure_code": error
                    .get("failure_code")
                    .cloned()
                    .unwrap_or_else(|| json!("query_error")),
                "answer": null,
                "source_count": 0,
                "graph_hit_count": 0,
                "response_ms": 0,
                "provider": "system",
                "model": null,
                "prompt_version": "experiment-unlogged-failure-v1",
                "fallback_reason": null,
                "error": error["error"],
                "sources": [],
                "graph_context": [],
                "retrieval_config": {},
                "usage": {},
                "citation_audit": {},
            }));
        }
    }
    cases.sort_by_key(|case| case["execution_order"].as_i64().unwrap_or(i64::MAX));
    let config = run
        .get("config_snapshot")
        .cloned()
        .unwrap_or_else(|| json!({}));
    let protocol = config
        .get("experiment_protocol")
        .cloned()
        .unwrap_or_else(|| json!({}));
    json!({
        "schema_version": "rag-evidence-package-v1",
        "experiment": {
            "id": run["id"],
            "project_id": run["project_id"],
            "created_by": run["created_by"],
            "name": run["name"],
            "status": run["status"],
            "questions": run["questions"],
            "modes": run["modes"],
            "total_cases": run["total_cases"],
            "completed_cases": run["completed_cases"],
            "failed_cases": run["failed_cases"],
            "created_at": run["created_at"],
            "completed_at": run["completed_at"],
            "repetitions": protocol["repetitions"],
            "randomize_order": protocol["randomize_order"],
            "random_seed": protocol["random_seed"],
            "execution_plan_hash": protocol["execution_plan_hash"],
            "embedding_model": config["embedding_model"],
            "generation_model": config["generation_model"],
            "questions_sha256": config["questions_sha256"],
            "corpus_snapshot_hash": config["corpus_snapshot_hash"],
            "graph_snapshot_hash": config["graph_snapshot_hash"],
            "rag_index_version": config["rag_index_version"],
            "graph_schema_version": config["graph_schema_version"],
        },
        "config_snapshot": config,
        "summary": summary,
        "case_count": cases.len(),
        "cases": cases,
    })
}

#[cfg(test)]
mod evidence_package_tests {
    use serde_json::{json, Value};

    use super::{build_experiment_evidence_package, evidence_export_status_error};

    #[test]
    fn test_evidence_export_rejects_non_terminal_run() {
        assert!(evidence_export_status_error("queued").is_some());
        assert!(evidence_export_status_error("running").is_some());
        assert!(evidence_export_status_error("interrupted").is_none());
        assert!(evidence_export_status_error("completed").is_none());
        assert!(evidence_export_status_error("failed").is_none());
        assert!(evidence_export_status_error("unsupported").is_some());
    }

    #[test]
    fn test_evidence_package_binds_protocol_cases_and_audit() {
        let package = build_experiment_evidence_package(
            &json!({
                "id": 12,
                "project_id": 7,
                "name": "confirmatory RAG run",
                "status": "completed",
                "questions": ["问题一"],
                "modes": ["project_rag", "kg_enhanced_rag"],
                "config_snapshot": {
                    "embedding_model": "hash-v1",
                    "questions_sha256": "questions-sha",
                    "corpus_snapshot_hash": "corpus-sha",
                    "graph_snapshot_hash": "graph-sha",
                    "rag_index_version": "structured-v1",
                    "graph_schema_version": "kg-v3-numbered-list-expansion",
                    "experiment_protocol": {
                        "repetitions": 1,
                        "randomize_order": false,
                        "random_seed": 42,
                        "execution_plan_hash": "plan-sha"
                    }
                }
            }),
            vec![json!({
                "query_log_id": 99,
                "question_index": 1,
                "question": "问题一",
                "mode": "project_rag",
                "status": "completed",
                "answer": "回答 [S1]",
                "source_count": 1,
                "graph_hit_count": 0,
                "sources": [{"file_id": 3}],
                "graph_context": [],
                "retrieval_config": {"index_version": "structured-v1"},
                "citation_audit": {"passed": true, "citation_count": 1}
            })],
        );

        assert_eq!(package["schema_version"], "rag-evidence-package-v1");
        assert_eq!(package["experiment"]["repetitions"], 1);
        assert_eq!(package["experiment"]["randomize_order"], false);
        assert_eq!(package["experiment"]["execution_plan_hash"], "plan-sha");
        assert_eq!(package["experiment"]["questions_sha256"], "questions-sha");
        assert_eq!(package["experiment"]["corpus_snapshot_hash"], "corpus-sha");
        assert_eq!(package["experiment"]["graph_snapshot_hash"], "graph-sha");
        assert_eq!(package["experiment"]["rag_index_version"], "structured-v1");
        assert_eq!(
            package["experiment"]["graph_schema_version"],
            "kg-v3-numbered-list-expansion"
        );
        assert_eq!(package["cases"][0]["query_log_id"], 99);
        assert_eq!(package["cases"][0]["citation_audit"]["passed"], true);
        assert_eq!(
            package["cases"][0]["retrieval_config"]["index_version"],
            "structured-v1"
        );
        assert_eq!(package["cases"][0]["source_count"], 1);
        assert_eq!(package["cases"][0]["graph_hit_count"], 0);
    }

    #[test]
    fn test_evidence_package_preserves_unlogged_failures() {
        let package = build_experiment_evidence_package(
            &json!({
                "id": 12,
                "project_id": 7,
                "status": "completed_with_errors",
                "questions": [],
                "modes": [],
                "summary": {
                    "errors": [{
                        "question_index": 2,
                        "question": "失败问题",
                        "mode": "kg_enhanced_rag",
                        "repetition_index": 1,
                        "execution_order": 2,
                        "error": "timeout"
                    }]
                },
                "config_snapshot": {}
            }),
            vec![],
        );

        assert_eq!(package["case_count"], 1);
        assert_eq!(package["cases"][0]["status"], "failed");
        assert_eq!(package["cases"][0]["error"], "timeout");
        assert_eq!(package["cases"][0]["query_log_id"], Value::Null);
        assert_eq!(
            package["cases"][0]["prompt_version"],
            "experiment-unlogged-failure-v1"
        );
        assert_eq!(package["cases"][0]["source_count"], 0);
        assert_eq!(package["cases"][0]["graph_hit_count"], 0);
    }

    #[test]
    fn test_evidence_package_does_not_duplicate_logged_failures() {
        let package = build_experiment_evidence_package(
            &json!({
                "id": 12,
                "project_id": 7,
                "status": "completed_with_errors",
                "summary": {
                    "errors": [{
                        "question_index": 1,
                        "question": "失败问题",
                        "mode": "project_rag",
                        "repetition_index": 1,
                        "execution_order": 1,
                        "error": "timeout"
                    }]
                },
                "config_snapshot": {}
            }),
            vec![json!({
                "query_log_id": 99,
                "question_index": 1,
                "question": "失败问题",
                "mode": "project_rag",
                "repetition_index": 1,
                "execution_order": 1,
                "status": "failed",
                "error": "timeout",
                "citation_audit": {}
            })],
        );

        assert_eq!(package["case_count"], 1);
        assert_eq!(package["cases"].as_array().unwrap().len(), 1);
        assert_eq!(package["cases"][0]["query_log_id"], 99);
    }
}

pub async fn schedule_queued_experiments(state: &AppState) -> Result<usize, ApiError> {
    let queued: Vec<(i32, i32)> = sqlx::query_as(
        "SELECT id, created_by FROM ai_experiment_runs WHERE status = 'queued' ORDER BY id",
    )
    .fetch_all(&state.pool)
    .await?;
    for (run_id, created_by) in &queued {
        let user = match sqlx::query_as::<_, UserRecord>(
            r#"
            SELECT id, username, password_hash, display_name, email,
                   lower(role::text) AS role, lower(status::text) AS status, auth_version
            FROM users
            WHERE id = $1
            "#,
        )
        .bind(created_by)
        .fetch_optional(&state.pool)
        .await?
        {
            Some(user) => user,
            None => {
                let _ = sqlx::query(
                    r#"
                    UPDATE ai_experiment_runs SET status = 'failed', completed_at = now(),
                        summary_json = (
                            summary_json::jsonb || jsonb_build_object(
                                'fatal_error', jsonb_build_object(
                                    'error', 'Creator user no longer exists',
                                    'failure_scope', 'run',
                                    'failure_code', 'creator_user_missing'
                                )
                            )
                        )::json
                    WHERE id = $1 AND status = 'queued'
                    "#,
                )
                .bind(run_id)
                .execute(&state.pool)
                .await;
                continue;
            }
        };
        spawn_experiment(state.clone(), user, *run_id);
    }
    Ok(queued.len())
}

fn spawn_experiment(state: AppState, user: UserRecord, run_id: i32) {
    let worker_pool = state.pool.clone();
    let panic_pool = state.pool.clone();
    let worker_id = state.worker_id().to_owned();
    tokio::spawn(async move {
        // 必须对「已构造的 Future」调用 catch_unwind 并真正 await：
        // std::panic::catch_unwind 包同步闭包只会构造出 Future 而不执行它，
        // 实验体会被整体丢弃，run 永远停在非终态（僵尸 run）。
        let result = AssertUnwindSafe(execute_experiment(state, user, run_id))
            .catch_unwind()
            .await;
        match result {
            Ok(Ok(())) => {}
            Ok(Err(error)) => {
                tracing::error!(run_id, %error.detail, "RAG experiment failed unexpectedly");
                let failure_code = experiment_run_failure_code(&error.detail);
                let _ = sqlx::query(
                    r#"
                    UPDATE ai_experiment_runs SET status = 'failed', completed_at = now(),
                        worker_id = NULL, heartbeat_at = NULL, lease_expires_at = NULL,
                        summary_json = (
                            summary_json::jsonb || jsonb_build_object(
                                'fatal_error', jsonb_build_object(
                                    'error', $2,
                                    'failure_scope', 'run',
                                    'failure_code', $4
                                )
                            )
                        )::json
                    WHERE id = $1 AND status = 'running' AND worker_id = $3
                      AND lease_expires_at > clock_timestamp()
                    "#,
                )
                .bind(run_id)
                .bind(error.detail)
                .bind(&worker_id)
                .bind(failure_code)
                .execute(&worker_pool)
                .await;
            }
            Err(panic_payload) => {
                tracing::error!(run_id, "RAG experiment worker panicked, marking as failed");
                let panic_message = panic_payload
                    .downcast_ref::<String>()
                    .map(String::as_str)
                    .or_else(|| panic_payload.downcast_ref::<&str>().copied())
                    .unwrap_or("worker panic");
                let _ = sqlx::query(
                    r#"
                    UPDATE ai_experiment_runs SET status = 'failed', completed_at = now(),
                        worker_id = NULL, heartbeat_at = NULL, lease_expires_at = NULL,
                        summary_json = (
                            summary_json::jsonb || jsonb_build_object(
                                'fatal_error', jsonb_build_object(
                                    'error', $2,
                                    'failure_scope', 'run',
                                    'failure_code', 'worker_panic'
                                )
                            )
                        )::json
                    WHERE id = $1 AND status = 'running'
                    "#,
                )
                .bind(run_id)
                .bind(panic_message)
                .execute(&panic_pool)
                .await;
            }
        }
    });
}

fn experiment_run_failure_code(detail: &str) -> &'static str {
    if detail.contains("input binding drift") {
        "input_binding_drift"
    } else {
        "worker_error"
    }
}

pub(super) async fn claim_experiment(state: &AppState, run_id: i32) -> Result<bool, ApiError> {
    Ok(sqlx::query(
        r#"
        UPDATE ai_experiment_runs
        SET status = 'running', worker_id = $2, heartbeat_at = now(),
            lease_expires_at = now() + make_interval(secs => $3)
        WHERE id = $1 AND status = 'queued'
        "#,
    )
    .bind(run_id)
    .bind(state.worker_id())
    .bind(EXPERIMENT_LEASE_SECONDS)
    .execute(&state.pool)
    .await?
    .rows_affected()
        == 1)
}

pub(super) async fn renew_experiment_lease(
    state: &AppState,
    run_id: i32,
) -> Result<bool, ApiError> {
    Ok(sqlx::query(
        r#"
        UPDATE ai_experiment_runs
        SET heartbeat_at = now(), lease_expires_at = now() + make_interval(secs => $3)
        WHERE id = $1 AND status = 'running' AND worker_id = $2
          AND lease_expires_at > clock_timestamp()
        "#,
    )
    .bind(run_id)
    .bind(state.worker_id())
    .bind(EXPERIMENT_LEASE_SECONDS)
    .execute(&state.pool)
    .await?
    .rows_affected()
        == 1)
}

async fn execute_experiment(
    state: AppState,
    user: UserRecord,
    run_id: i32,
) -> Result<(), ApiError> {
    if !claim_experiment(&state, run_id).await? {
        return Ok(());
    }
    let mut run = fetch_experiment(&state, run_id).await?;
    validate_current_experiment_input_bindings(&state, &run).await?;
    let plan = run
        .summary_json
        .get("execution_plan")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let attempted: std::collections::HashSet<i32> = sqlx::query_scalar(
        "SELECT experiment_execution_order FROM ai_query_logs WHERE experiment_run_id = $1 AND experiment_execution_order IS NOT NULL",
    )
    .bind(run_id)
    .fetch_all(&state.pool)
    .await?
    .into_iter()
    .collect();
    let mut errors = run
        .summary_json
        .get("errors")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut attempted = attempted;
    include_summary_error_orders(&mut attempted, &run.summary_json);
    for case in plan.iter().filter(|case| {
        case["execution_order"]
            .as_i64()
            .is_some_and(|order| !attempted.contains(&(order as i32)))
    }) {
        // 案例之间的处理（输入绑定校验、日志写入、计划迭代等）不经过查询心跳循环；
        // 在开始每个案例前显式续租，避免租约在案例间隙过期被清扫器误判为中断。
        if !renew_experiment_lease(&state, run_id).await? {
            return Ok(());
        }
        validate_current_experiment_input_bindings(&state, &run).await?;
        let mode = case["mode"].as_str().unwrap_or("project_rag").to_owned();
        let question = case["question"].as_str().unwrap_or_default().to_owned();
        let order = case["execution_order"].as_i64().unwrap_or_default() as i32;
        let question_index = case["question_index"].as_i64().unwrap_or_default() as i32;
        let repetition_index = case["repetition_index"].as_i64().unwrap_or(1) as i32;
        let query = query_project_rag_inner(
            state.clone(),
            user.clone(),
            run.project_id,
            RagQueryRequest {
                query: question.clone(),
                mode: mode.clone(),
                history: None,
            },
            Some(ExperimentLogContext {
                run_id,
                case_index: question_index,
                repetition_index,
                execution_order: order,
            }),
            None,
            None,
        );
        tokio::pin!(query);
        let query_result = loop {
            tokio::select! {
                biased;
                result = &mut query => break result,
                _ = tokio::time::sleep(Duration::from_secs(EXPERIMENT_HEARTBEAT_INTERVAL_SECONDS)) => {
                    if !renew_experiment_lease(&state, run_id).await? {
                        return Ok(());
                    }
                }
            }
        };
        if !renew_experiment_lease(&state, run_id).await? {
            return Ok(());
        }
        match query_result {
            Ok(Json(_response)) => {
                run.completed_cases += 1;
            }
            Err(error) => {
                run.failed_cases += 1;
                errors.push(json!({
                    "question_index": question_index,
                    "question": question,
                    "repetition_index": repetition_index,
                    "mode": mode,
                    "execution_order": order,
                    "error": error.detail,
                    "failure_scope": "case",
                    "failure_code": "query_error"
                }));
            }
        }
        run.summary_json["errors"] = json!(errors);
        run.summary_json["unexecuted_cases"] =
            json!((run.total_cases - run.completed_cases - run.failed_cases).max(0));
        let updated = sqlx::query(
            r#"
            UPDATE ai_experiment_runs SET completed_cases = $2, failed_cases = $3,
                summary_json = $4
            WHERE id = $1 AND status = 'running' AND worker_id = $5
              AND lease_expires_at > clock_timestamp()
            "#,
        )
        .bind(run_id)
        .bind(run.completed_cases)
        .bind(run.failed_cases)
        .bind(&run.summary_json)
        .bind(state.worker_id())
        .execute(&state.pool)
        .await?;
        if updated.rows_affected() != 1 {
            return Ok(());
        }
    }
    let status = if run.failed_cases == 0 {
        "completed"
    } else {
        "completed_with_errors"
    };
    let completed = sqlx::query(
        r#"
        UPDATE ai_experiment_runs
        SET status = $2, completed_at = now(), worker_id = NULL,
            heartbeat_at = NULL, lease_expires_at = NULL
        WHERE id = $1 AND status = 'running' AND worker_id = $3
          AND lease_expires_at > clock_timestamp()
        "#,
    )
    .bind(run_id)
    .bind(status)
    .bind(state.worker_id())
    .execute(&state.pool)
    .await?;
    if completed.rows_affected() != 1 {
        return Ok(());
    }
    write_audit(
        &state.pool,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(run.project_id),
            action: "run_rag_experiment",
            target_type: Some("ai_experiment_run"),
            target_id: Some(run_id),
            detail: json!({
                "total_cases": run.total_cases,
                "completed_cases": run.completed_cases,
                "failed_cases": run.failed_cases
            }),
            ip_address: None,
            user_agent: None,
        },
    )
    .await?;
    Ok(())
}

fn include_summary_error_orders(attempted: &mut std::collections::HashSet<i32>, summary: &Value) {
    let Some(errors) = summary.get("errors").and_then(Value::as_array) else {
        return;
    };
    attempted.extend(errors.iter().filter_map(|error| {
        error["execution_order"]
            .as_i64()
            .and_then(|order| i32::try_from(order).ok())
    }));
}

async fn fetch_experiment(state: &AppState, run_id: i32) -> Result<AIExperimentRunRead, ApiError> {
    let query = format!("SELECT {EXPERIMENT_COLUMNS} FROM ai_experiment_runs WHERE id = $1");
    sqlx::query_as::<_, AIExperimentRunRead>(&query)
        .bind(run_id)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Experiment run not found"))
}

const EXPERIMENT_PROJECT_LOCK_NAMESPACE: i32 = 1_163_152_197;
const ACTIVE_EXPERIMENT_INDEX: &str = "uq_ai_experiment_runs_one_active_per_project";

async fn lock_experiment_project(
    transaction: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    project_id: i32,
) -> Result<(), ApiError> {
    sqlx::query("SELECT pg_advisory_xact_lock($1, $2)")
        .bind(EXPERIMENT_PROJECT_LOCK_NAMESPACE)
        .bind(project_id)
        .execute(&mut **transaction)
        .await?;
    Ok(())
}

async fn ensure_no_active_experiment(
    transaction: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    project_id: i32,
) -> Result<(), ApiError> {
    let active: Option<i32> = sqlx::query_scalar(
        r#"
        SELECT id FROM ai_experiment_runs
        WHERE project_id = $1 AND status IN ('queued', 'running')
        ORDER BY id LIMIT 1
        "#,
    )
    .bind(project_id)
    .fetch_optional(&mut **transaction)
    .await?;
    if let Some(active) = active {
        Err(ApiError::new(
            StatusCode::CONFLICT,
            format!("Experiment #{active} is already queued or running"),
        ))
    } else {
        Ok(())
    }
}

pub(super) async fn transition_interrupted_to_queued(
    state: &AppState,
    run_id: i32,
    project_id: i32,
) -> Result<bool, ApiError> {
    let mut transaction = state.pool.begin().await?;
    lock_experiment_project(&mut transaction, project_id).await?;
    let transitioned = sqlx::query(
        r#"
        UPDATE ai_experiment_runs AS target
        SET status = 'queued', completed_at = NULL, worker_id = NULL,
            heartbeat_at = NULL, lease_expires_at = NULL
        WHERE target.id = $1 AND target.project_id = $2
          AND target.status = 'interrupted'
          AND NOT EXISTS (
              SELECT 1 FROM ai_experiment_runs AS active
              WHERE active.project_id = $2
                AND active.status IN ('queued', 'running')
          )
        "#,
    )
    .bind(run_id)
    .bind(project_id)
    .execute(&mut *transaction)
    .await
    .map_err(map_experiment_write_error)?
    .rows_affected()
        == 1;
    transaction.commit().await?;
    Ok(transitioned)
}

fn map_experiment_write_error(error: sqlx::Error) -> ApiError {
    if let sqlx::Error::Database(database) = &error {
        if database.code().as_deref() == Some("23505")
            && database.constraint() == Some(ACTIVE_EXPERIMENT_INDEX)
        {
            return ApiError::new(
                StatusCode::CONFLICT,
                "Another experiment is already queued or running for this project",
            );
        }
    }
    error.into()
}

pub(super) async fn experiment_csv_response(
    state: &AppState,
    run: &AIExperimentRunRead,
    filename: &str,
) -> Result<Response, ApiError> {
    let logs = sqlx::query_as::<_, QueryLogRow>(
        r#"
        SELECT id, project_id, user_id, question, answer, rag_mode,
               graph_hit_count, source_count, response_ms, conversation_id,
               graph_context_json, sources_json, provider, model_name,
               prompt_version, retrieval_config_json, usage_json,
               fallback_reason, error_message, experiment_run_id,
               experiment_case_index, experiment_repetition_index,
               experiment_execution_order, created_at
        FROM ai_query_logs WHERE experiment_run_id = $1
        ORDER BY experiment_execution_order, id
        "#,
    )
    .bind(run.id)
    .fetch_all(&state.pool)
    .await?;
    let mut csv = String::from(EXPERIMENT_CSV_HEADER);
    for log in &logs {
        let retrieval_fields =
            retrieval_snapshot_csv_fields(&run.config_snapshot_json, &log.retrieval_config_json);
        let mut row = vec![
            run.id.to_string(),
            log.experiment_case_index.unwrap_or_default().to_string(),
            csv_escape(&log.question),
            csv_escape(&log.rag_mode),
            log.experiment_repetition_index.unwrap_or(1).to_string(),
            log.experiment_execution_order
                .unwrap_or_default()
                .to_string(),
            if log.error_message.is_some() {
                "failed"
            } else {
                "completed"
            }
            .to_owned(),
            log.id.to_string(),
            csv_escape(log.answer.as_deref().unwrap_or_default()),
            log.source_count.to_string(),
            log.graph_hit_count.to_string(),
            log.response_ms.to_string(),
            csv_escape(&log.provider),
            csv_escape(log.model_name.as_deref().unwrap_or_default()),
            csv_escape(&log.prompt_version),
            csv_escape(log.fallback_reason.as_deref().unwrap_or_default()),
            csv_escape(&log.sources_json.to_string()),
            csv_escape(&log.graph_context_json.to_string()),
            csv_escape(&log.usage_json.to_string()),
            csv_escape(log.error_message.as_deref().unwrap_or_default()),
        ];
        row.extend(retrieval_fields.into_iter().map(|value| csv_escape(&value)));
        csv.push_str(&row.join(","));
        csv.push_str("\r\n");
    }
    let logged_orders: std::collections::HashSet<i32> = logs
        .iter()
        .filter_map(|log| log.experiment_execution_order)
        .collect();
    append_missing_experiment_errors(&mut csv, run.id, &run.summary_json, &logged_orders);
    let mut response = Body::from(csv).into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/csv; charset=utf-8"),
    );
    if let Ok(value) = HeaderValue::from_str(&format!("attachment; filename=\"{filename}\"")) {
        response
            .headers_mut()
            .insert(header::CONTENT_DISPOSITION, value);
    }
    Ok(response)
}

fn append_missing_experiment_errors(
    csv: &mut String,
    run_id: i32,
    summary: &Value,
    logged_orders: &std::collections::HashSet<i32>,
) {
    let Some(errors) = summary.get("errors").and_then(Value::as_array) else {
        return;
    };
    for error in errors {
        let Some(order) = error["execution_order"]
            .as_i64()
            .and_then(|value| i32::try_from(value).ok())
        else {
            continue;
        };
        if logged_orders.contains(&order) {
            continue;
        }
        let mut row = vec![
            run_id.to_string(),
            error["question_index"]
                .as_i64()
                .unwrap_or_default()
                .to_string(),
            csv_escape(error["question"].as_str().unwrap_or_default()),
            csv_escape(error["mode"].as_str().unwrap_or_default()),
            error["repetition_index"].as_i64().unwrap_or(1).to_string(),
            order.to_string(),
            "failed".to_owned(),
            String::new(),
            String::new(),
            "0".to_owned(),
            "0".to_owned(),
            "0".to_owned(),
            csv_escape("system"),
            String::new(),
            "experiment-unlogged-failure-v1".to_owned(),
            String::new(),
            csv_escape("[]"),
            csv_escape("[]"),
            csv_escape("{}"),
            csv_escape(error["error"].as_str().unwrap_or_default()),
        ];
        row.extend(std::iter::repeat_n(String::new(), 15));
        csv.push_str(&row.join(","));
        csv.push_str("\r\n");
    }
}

fn retrieval_snapshot_csv_fields(run_config: &Value, retrieval_config: &Value) -> Vec<String> {
    let scalar = |value: Option<&Value>| match value {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Number(value)) => value.to_string(),
        Some(Value::Bool(value)) => value.to_string(),
        _ => String::new(),
    };

    vec![
        retrieval_config.to_string(),
        scalar(retrieval_config.get("embedding_model")),
        scalar(run_config.get("corpus_snapshot_hash")),
        scalar(run_config.get("rag_index_version")),
        scalar(retrieval_config.get("index_version")),
        scalar(
            retrieval_config
                .get("graph_schema_version")
                .or_else(|| run_config.get("graph_schema_version")),
        ),
        scalar(retrieval_config.get("retrieval_strategy")),
        scalar(retrieval_config.get("retrieval_top_k")),
        scalar(retrieval_config.get("collection_retrieval_top_k")),
        scalar(retrieval_config.get("vector_candidate_k")),
        scalar(retrieval_config.get("graph_top_k")),
        scalar(retrieval_config.get("chunk_size")),
        scalar(retrieval_config.get("chunk_overlap")),
        scalar(retrieval_config.get("graph_min_score")),
        scalar(retrieval_config.get("retrieval_min_score")),
    ]
}

fn csv_escape(value: &str) -> String {
    let value = if value
        .chars()
        .next()
        .is_some_and(|first| matches!(first, '=' | '+' | '-' | '@') || first.is_control())
    {
        format!("'{value}")
    } else {
        value.to_owned()
    };
    if value.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value
    }
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use serde_json::json;

    use super::*;

    #[test]
    fn test_experiment_export_includes_unlogged_failures() {
        let mut csv = String::new();
        append_missing_experiment_errors(
            &mut csv,
            9,
            &json!({
                "errors": [
                    {
                        "question_index": 2,
                        "question": "=SUM(A1)",
                        "mode": "project_rag",
                        "repetition_index": 1,
                        "execution_order": 2,
                        "error": "timeout"
                    }
                ]
            }),
            &std::collections::HashSet::from([1]),
        );

        let row = csv
            .strip_suffix("\r\n")
            .unwrap()
            .split(',')
            .collect::<Vec<_>>();
        assert_eq!(row.len(), 35);
        assert_eq!(
            row[..20],
            [
                "9",
                "2",
                "'=SUM(A1)",
                "project_rag",
                "1",
                "2",
                "failed",
                "",
                "",
                "0",
                "0",
                "0",
                "system",
                "",
                "experiment-unlogged-failure-v1",
                "",
                "[]",
                "[]",
                "{}",
                "timeout",
            ]
        );
        assert!(row[20..].iter().all(|value| value.is_empty()));
    }

    #[test]
    fn test_experiment_resume_skips_summary_errors() {
        let mut attempted = std::collections::HashSet::from([1]);
        include_summary_error_orders(
            &mut attempted,
            &json!({
                "errors": [
                    {"execution_order": 2},
                    {"execution_order": "invalid"}
                ]
            }),
        );

        assert_eq!(attempted, std::collections::HashSet::from([1, 2]));
    }

    #[test]
    fn test_experiment_questions_are_trimmed_and_unique() {
        let questions =
            normalize_experiment_questions(vec!["  问题一  ".to_owned(), "问题二".to_owned()])
                .unwrap();
        assert_eq!(questions, vec!["问题一", "问题二"]);

        let error =
            normalize_experiment_questions(vec!["问题一".to_owned(), "  问题一  ".to_owned()])
                .unwrap_err();
        assert_eq!(error.status, StatusCode::UNPROCESSABLE_ENTITY);
        assert!(error.detail.contains("duplicates"));
    }

    #[test]
    fn test_input_hashes_are_stable_and_bound_to_inputs() {
        let questions = vec!["问题一".to_owned(), "Question two".to_owned()];
        let reordered_questions = vec!["Question two".to_owned(), "问题一".to_owned()];
        let question_hash = questions_sha256(&questions);
        assert_eq!(question_hash, questions_sha256(&questions));
        assert_ne!(question_hash, questions_sha256(&reordered_questions));
        assert_eq!(question_hash.len(), 64);
    }

    #[test]
    fn test_experiment_input_bindings_fail_closed_on_runtime_drift() {
        let questions = vec!["问题一".to_owned()];
        let corpus_hash = "c".repeat(64);
        let config = json!({
            "embedding_model": "embed-v1",
            "generation_model": "generate-v1",
            "questions_sha256": questions_sha256(&questions),
            "corpus_snapshot_hash": corpus_hash,
            "graph_snapshot_hash": null,
            "rag_index_version": "structured-v1",
            "graph_schema_version": "kg-v3-numbered-list-expansion"
        });
        let modes = json!(["project_rag"]);

        assert!(validate_experiment_input_bindings(
            &config,
            &json!(questions),
            &modes,
            ExperimentRuntimeBindings {
                corpus_snapshot_hash: Some(&corpus_hash),
                graph_snapshot_hash: Some(&"g".repeat(64)),
                index_version: "structured-v1",
                embedding_model: "embed-v1",
                generation_model: "generate-v1",
                graph_schema_version: "kg-v3-numbered-list-expansion",
            }
        )
        .is_ok());

        let corpus_error = validate_experiment_input_bindings(
            &config,
            &json!(questions),
            &modes,
            ExperimentRuntimeBindings {
                corpus_snapshot_hash: Some(&"d".repeat(64)),
                graph_snapshot_hash: Some(&"g".repeat(64)),
                index_version: "structured-v1",
                embedding_model: "embed-v1",
                generation_model: "generate-v1",
                graph_schema_version: "kg-v3-numbered-list-expansion",
            },
        )
        .unwrap_err();
        assert!(corpus_error.contains("corpus_snapshot_hash"));

        let question_error = validate_experiment_input_bindings(
            &config,
            &json!(["发生漂移的问题"]),
            &modes,
            ExperimentRuntimeBindings {
                corpus_snapshot_hash: Some(&corpus_hash),
                graph_snapshot_hash: Some(&"g".repeat(64)),
                index_version: "structured-v1",
                embedding_model: "embed-v1",
                generation_model: "generate-v1",
                graph_schema_version: "kg-v3-numbered-list-expansion",
            },
        )
        .unwrap_err();
        assert!(question_error.contains("questions_sha256"));

        let model_error = validate_experiment_input_bindings(
            &config,
            &json!(questions),
            &modes,
            ExperimentRuntimeBindings {
                corpus_snapshot_hash: Some(&corpus_hash),
                graph_snapshot_hash: Some(&"g".repeat(64)),
                index_version: "structured-v1",
                embedding_model: "embed-v2",
                generation_model: "generate-v1",
                graph_schema_version: "kg-v3-numbered-list-expansion",
            },
        )
        .unwrap_err();
        assert!(model_error.contains("embedding_model"));

        let graph_error = validate_experiment_input_bindings(
            &config,
            &json!(questions),
            &modes,
            ExperimentRuntimeBindings {
                corpus_snapshot_hash: Some(&corpus_hash),
                graph_snapshot_hash: Some(&"g".repeat(64)),
                index_version: "structured-v1",
                embedding_model: "embed-v1",
                generation_model: "generate-v1",
                graph_schema_version: "kg-v2-numbered-list-expansion",
            },
        )
        .unwrap_err();
        assert!(graph_error.contains("graph_schema_version"));

        let graph_config = json!({
            "embedding_model": "embed-v1",
            "generation_model": "generate-v1",
            "questions_sha256": questions_sha256(&questions),
            "corpus_snapshot_hash": corpus_hash,
            "graph_snapshot_hash": "g".repeat(64),
            "rag_index_version": "structured-v1",
            "graph_schema_version": "kg-v3-numbered-list-expansion"
        });
        let graph_modes = json!(["kg_enhanced_rag"]);
        let graph_hash_error = validate_experiment_input_bindings(
            &graph_config,
            &json!(questions),
            &graph_modes,
            ExperimentRuntimeBindings {
                corpus_snapshot_hash: Some(&corpus_hash),
                graph_snapshot_hash: Some(&"h".repeat(64)),
                index_version: "structured-v1",
                embedding_model: "embed-v1",
                generation_model: "generate-v1",
                graph_schema_version: "kg-v3-numbered-list-expansion",
            },
        )
        .unwrap_err();
        assert!(graph_hash_error.contains("graph_snapshot_hash"));
    }

    #[test]
    fn test_experiment_snapshot_mismatch_rejects_before_persistence_gate() {
        let modes = vec!["project_rag".to_owned(), "kg_enhanced_rag".to_owned()];
        let detail = compare_experiment_snapshots(
            &modes,
            Some("a".repeat(64).as_str()),
            Some("b".repeat(64).as_str()),
            Some("c".repeat(64).as_str()),
            Some("d".repeat(64).as_str()),
        )
        .unwrap();
        assert_eq!(detail["error"], "experiment_snapshot_drift");
        assert_eq!(detail["expected_corpus_snapshot_hash"], "a".repeat(64));
        assert_eq!(detail["actual_corpus_snapshot_hash"], "c".repeat(64));
        assert_eq!(detail["expected_graph_snapshot_hash"], "b".repeat(64));
        assert_eq!(detail["actual_graph_snapshot_hash"], "d".repeat(64));
    }

    #[test]
    fn test_expected_snapshot_bindings_follow_mode_requirements() {
        let corpus = "a".repeat(64);
        let graph = "b".repeat(64);
        assert!(validate_expected_snapshot_bindings(&["pure_llm".to_owned()], None, None,).is_ok());
        assert!(validate_expected_snapshot_bindings(
            &["structured_query".to_owned()],
            None,
            Some(&graph),
        )
        .is_ok());
        assert!(validate_expected_snapshot_bindings(
            &["project_rag".to_owned()],
            Some(&corpus),
            None,
        )
        .is_ok());
        assert_eq!(
            validate_expected_snapshot_bindings(
                &["project_rag".to_owned()],
                Some(&corpus),
                Some(&graph),
            )
            .unwrap_err()
            .status,
            StatusCode::UNPROCESSABLE_ENTITY
        );
        assert_eq!(
            validate_expected_snapshot_bindings(
                &["kg_enhanced_rag".to_owned()],
                Some("A"),
                Some(&graph),
            )
            .unwrap_err()
            .status,
            StatusCode::UNPROCESSABLE_ENTITY
        );
    }

    #[test]
    fn test_csv_escape_blocks_spreadsheet_formulas_and_control_prefixes() {
        for value in ["=1+1", "+cmd", "-2+3", "@SUM(A1:A2)", "\t=1+1", "\r@cmd"] {
            let escaped = csv_escape(value);
            let cell = escaped.trim_matches('"').replace("\"\"", "\"");
            assert!(cell.starts_with('\''), "unsafe CSV cell: {escaped:?}");
        }
        assert_eq!(csv_escape("ordinary"), "ordinary");
    }

    #[test]
    fn test_experiment_csv_binds_retrieval_snapshot_to_run_and_query_log() {
        let run_config = json!({
            "corpus_snapshot_hash": "corpus-sha",
            "rag_index_version": "index-v1",
            "graph_schema_version": "rust-kg-v1"
        });
        let retrieval_config = json!({
            "embedding_model": "embed-v1",
            "index_version": "index-v1",
            "retrieval_strategy": "rrf-v1",
            "retrieval_top_k": 6,
            "collection_retrieval_top_k": 12,
            "vector_candidate_k": 30,
            "graph_top_k": 10,
            "chunk_size": 800,
            "chunk_overlap": 120,
            "graph_min_score": 1.0,
            "retrieval_min_score": 0.2
        });

        let header = EXPERIMENT_CSV_HEADER
            .trim_start_matches('\u{feff}')
            .trim_end_matches("\r\n");
        let header_fields: Vec<&str> = header.split(',').collect();
        assert_eq!(header_fields.len(), 35);
        for field in [
            "retrieval_config_json",
            "embedding_model",
            "corpus_snapshot_hash",
            "rag_index_version",
            "index_version",
            "graph_schema_version",
            "retrieval_strategy",
            "retrieval_top_k",
            "collection_retrieval_top_k",
            "vector_candidate_k",
            "graph_top_k",
            "chunk_size",
            "chunk_overlap",
            "graph_min_score",
            "retrieval_min_score",
        ] {
            assert!(header_fields.contains(&field), "missing CSV field: {field}");
        }
        assert_eq!(
            retrieval_snapshot_csv_fields(&run_config, &retrieval_config),
            vec![
                "{\"chunk_overlap\":120,\"chunk_size\":800,\"collection_retrieval_top_k\":12,\"embedding_model\":\"embed-v1\",\"graph_min_score\":1.0,\"graph_top_k\":10,\"index_version\":\"index-v1\",\"retrieval_min_score\":0.2,\"retrieval_strategy\":\"rrf-v1\",\"retrieval_top_k\":6,\"vector_candidate_k\":30}".to_owned(),
                "embed-v1".to_owned(),
                "corpus-sha".to_owned(),
                "index-v1".to_owned(),
                "index-v1".to_owned(),
                "rust-kg-v1".to_owned(),
                "rrf-v1".to_owned(),
                "6".to_owned(),
                "12".to_owned(),
                "30".to_owned(),
                "10".to_owned(),
                "800".to_owned(),
                "120".to_owned(),
                "1.0".to_owned(),
                "0.2".to_owned(),
            ]
        );
    }
}
