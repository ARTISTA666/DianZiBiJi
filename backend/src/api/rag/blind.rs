// 盲评区：盲评批次/条目管理、答案脱敏与盲评导出。

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::Response,
    Json,
};
use hmac::{Hmac, Mac};
use regex::Regex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use super::experiments::experiment_csv_response;
use super::{
    fetch_evaluations, require_manager, validate_evaluation, QueryLogRow, EXPERIMENT_COLUMNS,
};
use crate::{
    api::auth::CurrentUser,
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{
        AIExperimentRunRead, AIQueryEvaluationRead, AIQueryEvaluationRequest,
        BlindReviewBatchLockRequest, BlindReviewQuery, UserRecord,
    },
    permissions::{
        can_access_project, can_evaluate_project, can_manage_project, fetch_project,
        require_project_access, require_project_metadata_access,
    },
    AppState,
};

#[derive(Clone, Debug, sqlx::FromRow)]
struct FormalBlindReviewBatchRow {
    experiment_run_id: i32,
    #[allow(dead_code)]
    freeze_manifest_sha256: String,
    reviewer_a_user_id: i32,
    reviewer_b_user_id: i32,
    status: String,
}

pub(super) async fn list_blind_batches(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<Value>, ApiError> {
    require_project_metadata_access(&state.pool, &user, project_id).await?;
    let manager = can_manage_project(&state.pool, &user, project_id).await?;
    let independent = is_independent_evaluator(&state, &user, project_id).await?;
    if !manager && !independent {
        return Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "AI evaluation permission required",
        ));
    }
    let query = format!(
        "SELECT {EXPERIMENT_COLUMNS} FROM ai_experiment_runs WHERE project_id = $1 ORDER BY created_at DESC, id DESC"
    );
    let runs = sqlx::query_as::<_, AIExperimentRunRead>(&query)
        .bind(project_id)
        .fetch_all(&state.pool)
        .await?;
    let formal_batches =
        fetch_formal_batches_for_runs(&state, &runs.iter().map(|run| run.id).collect::<Vec<_>>())
            .await?;
    let mut batches = Vec::new();
    for run in runs {
        if !manager
            && formal_batches
                .get(&run.id)
                .is_some_and(|batch| !is_assigned_reviewer(batch, user.id))
        {
            continue;
        }
        let log_ids: Vec<i32> = sqlx::query_scalar(
            "SELECT id FROM ai_query_logs WHERE experiment_run_id = $1 AND error_message IS NULL",
        )
        .bind(run.id)
        .fetch_all(&state.pool)
        .await?;
        let completed = if manager {
            completed_masked_items(&state, &log_ids).await?.0
        } else if log_ids.is_empty() {
            0
        } else {
            sqlx::query_scalar::<_, i64>(
                "SELECT count(*) FROM ai_query_evaluations WHERE query_log_id = ANY($1) AND evaluator_user_id = $2 AND review_protocol = 'method_masked'",
            )
            .bind(&log_ids)
            .bind(user.id)
            .fetch_one(&state.pool)
            .await? as usize
        };
        batches.push(json!({
            "batch_id": blind_batch_id(&state, project_id, run.id),
            "total_items": run.total_cases.max(log_ids.len() as i32),
            "completed_items": completed
        }));
    }
    Ok(Json(json!(batches)))
}

pub(super) async fn list_blind_items(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Query(query): Query<BlindReviewQuery>,
) -> Result<Json<Value>, ApiError> {
    require_project_metadata_access(&state.pool, &user, project_id).await?;
    require_independent_evaluator(&state, &user, project_id).await?;
    let run_id = if let Some(batch_id) = query.batch_id.as_deref() {
        Some(
            find_run_by_batch(&state, project_id, batch_id)
                .await?
                .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Review batch not found"))?
                .id,
        )
    } else {
        None
    };
    let logs = fetch_blind_logs(&state, project_id, run_id).await?;
    let formal_batches = fetch_formal_batches_for_runs(
        &state,
        &logs
            .iter()
            .filter_map(|log| log.experiment_run_id)
            .collect::<Vec<_>>(),
    )
    .await?;
    if let Some(run_id) = run_id {
        if formal_batches
            .get(&run_id)
            .is_some_and(|batch| !is_assigned_reviewer(batch, user.id))
        {
            return Err(ApiError::new(
                StatusCode::FORBIDDEN,
                "This formal blind-review batch is assigned to different reviewers",
            ));
        }
    }
    let log_ids: Vec<i32> = logs.iter().map(|log| log.id).collect();
    let evaluations = fetch_evaluations(&state, &log_ids).await?;
    let mut items = Vec::new();
    for log in logs {
        if log
            .experiment_run_id
            .and_then(|run_id| formal_batches.get(&run_id))
            .is_some_and(|batch| !is_assigned_reviewer(batch, user.id))
        {
            continue;
        }
        let evaluation = evaluations
            .iter()
            .find(|evaluation| {
                evaluation.query_log_id == log.id && evaluation.evaluator_user_id == user.id
            })
            .cloned();
        if query.pending_only && evaluation.is_some() {
            continue;
        }
        items.push(blind_item_json(&state, &log, evaluation));
    }
    items.sort_by(|left, right| left["blind_id"].as_str().cmp(&right["blind_id"].as_str()));
    Ok(Json(json!(items)))
}

pub(super) async fn evaluate_blind_item(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, blind_id)): Path<(i32, String)>,
    Json(payload): Json<AIQueryEvaluationRequest>,
) -> Result<Json<Value>, ApiError> {
    require_project_metadata_access(&state.pool, &user, project_id).await?;
    require_independent_evaluator(&state, &user, project_id).await?;
    validate_evaluation(&payload)?;
    let normalized = blind_id.to_uppercase();
    if !Regex::new(r"^B[A-F0-9]{12}$")
        .unwrap()
        .is_match(&normalized)
    {
        return Err(ApiError::new(
            StatusCode::NOT_FOUND,
            "Blind-review item not found",
        ));
    }
    let logs = fetch_blind_logs(&state, project_id, None).await?;
    let log = logs
        .into_iter()
        .find(|log| blind_item_id(&state, project_id, log.id) == normalized)
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Blind-review item not found"))?;
    if let Some(run_id) = log.experiment_run_id {
        if let Some(batch) = fetch_formal_batch_for_run(&state, run_id).await? {
            if !is_assigned_reviewer(&batch, user.id) {
                return Err(ApiError::new(
                    StatusCode::FORBIDDEN,
                    "This formal blind-review batch is assigned to different reviewers",
                ));
            }
        }
    }
    let mut transaction = state.pool.begin().await?;
    // Serialize first-rating with formal locking on the experiment run itself.
    // The authorization/read checks above are intentionally repeated by the
    // locked batch query below so a concurrent lock cannot be bypassed.
    if let Some(run_id) = log.experiment_run_id {
        sqlx::query("SELECT id FROM ai_experiment_runs WHERE id = $1 FOR UPDATE")
            .bind(run_id)
            .fetch_one(&mut *transaction)
            .await?;
        let formal_batch: Option<FormalBlindReviewBatchRow> = sqlx::query_as(
            r#"SELECT experiment_run_id, freeze_manifest_sha256,
                      reviewer_a_user_id, reviewer_b_user_id, status
               FROM ai_blind_review_batches
               WHERE experiment_run_id = $1"#,
        )
        .bind(run_id)
        .fetch_optional(&mut *transaction)
        .await?;
        if let Some(batch) = formal_batch {
            if !is_assigned_reviewer(&batch, user.id) {
                return Err(ApiError::new(
                    StatusCode::FORBIDDEN,
                    "This formal blind-review batch is assigned to different reviewers",
                ));
            }
        }
    }
    let evaluation = sqlx::query_as::<_, AIQueryEvaluationRead>(
        r#"
        INSERT INTO ai_query_evaluations (
            query_log_id, evaluator_user_id, score, is_accurate, is_traceable,
            comment, review_protocol, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, 'method_masked', now(), now())
        ON CONFLICT (query_log_id, evaluator_user_id) DO NOTHING
        RETURNING id, query_log_id, evaluator_user_id, score, is_accurate,
                  is_traceable, comment, review_protocol, created_at, updated_at
        "#,
    )
    .bind(log.id)
    .bind(user.id)
    .bind(payload.score)
    .bind(payload.is_accurate)
    .bind(payload.is_traceable)
    .bind(&payload.comment)
    .fetch_optional(&mut *transaction)
    .await?;
    let Some(evaluation) = evaluation else {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "This review has already been submitted",
        ));
    };
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "evaluate_ai_query_blind",
            target_type: Some("ai_query_log"),
            target_id: Some(log.id),
            detail: json!({
                "blind_id": normalized,
                "score": payload.score,
                "is_accurate": payload.is_accurate,
                "is_traceable": payload.is_traceable,
                "review_protocol": "method_masked"
            }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(json!({
        "score": evaluation.score,
        "is_accurate": evaluation.is_accurate,
        "is_traceable": evaluation.is_traceable,
        "comment": evaluation.comment,
        "updated_at": evaluation.updated_at
    })))
}

pub(super) async fn lock_blind_batch(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, batch_id)): Path<(i32, String)>,
    Json(payload): Json<BlindReviewBatchLockRequest>,
) -> Result<(StatusCode, Json<Value>), ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    require_manager(&state, &user, project_id).await?;
    let run = find_run_by_batch(&state, project_id, &batch_id)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Review batch not found"))?;
    if run.status != "completed" || run.failed_cases != 0 || run.completed_cases < run.total_cases {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only cleanly completed experiment batches can be locked for formal blind review",
        ));
    }
    let mut reviewer_user_ids = payload.reviewer_user_ids;
    reviewer_user_ids.sort_unstable();
    reviewer_user_ids.dedup();
    if reviewer_user_ids.len() != 2 {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Formal blind review requires exactly two distinct reviewer_user_ids",
        ));
    }
    let freeze_manifest_sha256 = payload.freeze_manifest_sha256.trim().to_ascii_lowercase();
    if !Regex::new(r"^[a-f0-9]{64}$")
        .unwrap()
        .is_match(&freeze_manifest_sha256)
    {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "freeze_manifest_sha256 must be a lowercase SHA-256 digest",
        ));
    }
    let log_ids: Vec<i32> = sqlx::query_scalar(
        "SELECT id FROM ai_query_logs WHERE experiment_run_id = $1 AND error_message IS NULL",
    )
    .bind(run.id)
    .fetch_all(&state.pool)
    .await?;
    if log_ids.is_empty() {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Cannot lock an empty blind-review batch",
        ));
    }
    let mut transaction = state.pool.begin().await?;
    sqlx::query("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        .execute(&mut *transaction)
        .await?;
    lock_formal_batch_project(&mut transaction, project_id).await?;
    let locked_run: AIExperimentRunRead = sqlx::query_as(&format!(
        "SELECT {EXPERIMENT_COLUMNS} FROM ai_experiment_runs WHERE id = $1 AND project_id = $2 FOR UPDATE"
    ))
    .bind(run.id)
    .bind(project_id)
    .fetch_optional(&mut *transaction)
    .await?
    .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Review batch not found"))?;
    if locked_run.status != "completed"
        || locked_run.failed_cases != 0
        || locked_run.completed_cases < locked_run.total_cases
    {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only cleanly completed experiment batches can be locked for formal blind review",
        ));
    }
    let existing: Option<i32> = sqlx::query_scalar(
        "SELECT id FROM ai_blind_review_batches WHERE experiment_run_id = $1 FOR UPDATE",
    )
    .bind(run.id)
    .fetch_optional(&mut *transaction)
    .await?;
    if existing.is_some() {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "This blind-review batch has already been locked",
        ));
    }
    let masked_count: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM ai_query_evaluations WHERE query_log_id = ANY($1) AND review_protocol = 'method_masked'",
    )
    .bind(&log_ids)
    .fetch_one(&mut *transaction)
    .await?;
    if masked_count > 0 {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Cannot lock a blind-review batch after method-masked ratings have started",
        ));
    }
    for reviewer_user_id in &reviewer_user_ids {
        if !formal_batch_reviewer_eligible(&mut transaction, project_id, *reviewer_user_id).await? {
            return Err(ApiError::new(
                StatusCode::CONFLICT,
                format!("User {reviewer_user_id} is not an eligible independent reviewer for this project"),
            ));
        }
    }
    sqlx::query(
        r#"
        INSERT INTO ai_blind_review_batches (
            project_id, experiment_run_id, freeze_manifest_sha256,
            reviewer_a_user_id, reviewer_b_user_id, status, created_by, created_at
        )
        VALUES ($1, $2, $3, $4, $5, 'LOCKED', $6, now())
        "#,
    )
    .bind(project_id)
    .bind(run.id)
    .bind(&freeze_manifest_sha256)
    .bind(reviewer_user_ids[0])
    .bind(reviewer_user_ids[1])
    .bind(user.id)
    .execute(&mut *transaction)
    .await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "lock_blind_review_batch",
            target_type: Some("ai_experiment_run"),
            target_id: Some(run.id),
            detail: json!({
                "batch_id": batch_id.to_uppercase(),
                "status": "LOCKED",
                "reviewer_user_ids": reviewer_user_ids,
                "freeze_manifest_sha256": freeze_manifest_sha256
            }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok((
        StatusCode::CREATED,
        Json(json!({
            "batch_id": batch_id.to_uppercase(),
            "status": "LOCKED",
            "reviewer_user_ids": reviewer_user_ids,
            "freeze_manifest_sha256": freeze_manifest_sha256,
            "total_items": log_ids.len()
        })),
    ))
}

pub(super) async fn export_blind_batch(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, batch_id)): Path<(i32, String)>,
) -> Result<Response, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    require_manager(&state, &user, project_id).await?;
    let gate_hash = final_maturity_gate_hash().await.ok_or_else(|| {
        ApiError::new(
            StatusCode::CONFLICT,
            "Final maturity gate has not passed; confirmatory human-review export is blocked",
        )
    })?;
    let run = find_run_by_batch(&state, project_id, &batch_id)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Review batch not found"))?;
    if run.status != "completed" || run.failed_cases != 0 || run.completed_cases < run.total_cases {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            format!(
                "Blind-review batch experiment is not cleanly completed: status={}, completed={}/{}, failed={}",
                run.status, run.completed_cases, run.total_cases, run.failed_cases
            ),
        ));
    }
    let logs = fetch_blind_logs(&state, project_id, Some(run.id)).await?;
    let mut seen = std::collections::HashSet::new();
    for log in &logs {
        if !seen.insert((log.experiment_case_index, log.rag_mode.clone())) {
            return Err(ApiError::new(
                StatusCode::CONFLICT,
                "Blind-review batch contains repeated question/mode items",
            ));
        }
    }
    let log_ids: Vec<i32> = logs.iter().map(|log| log.id).collect();
    let (completed, reviewer_sets) = completed_masked_items(&state, &log_ids).await?;
    if log_ids.is_empty() || completed < log_ids.len() {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            format!(
                "Blind-review batch is not complete: {completed}/{} items have two method-masked ratings",
                log_ids.len()
            ),
        ));
    }
    if reviewer_sets
        .windows(2)
        .any(|pair| pair.first() != pair.get(1))
    {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Blind-review batch uses inconsistent reviewer sets",
        ));
    }
    if let Some(batch) = fetch_formal_batch_for_run(&state, run.id).await? {
        let expected = assigned_reviewer_ids(&batch);
        let actual = reviewer_sets.first().cloned().unwrap_or_default();
        if batch.status != "LOCKED" {
            return Err(ApiError::new(
                StatusCode::CONFLICT,
                "Only LOCKED formal blind-review batches can be exported",
            ));
        }
        if actual != expected {
            return Err(ApiError::new(
                StatusCode::CONFLICT,
                "Blind-review batch ratings do not match the locked reviewer assignment",
            ));
        }
    }
    write_audit(
        &state.pool,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "export_blind_review_batch",
            target_type: Some("ai_experiment_run"),
            target_id: Some(run.id),
            detail: json!({
                "batch_id": batch_id.to_uppercase(),
                "filename": "confirmatory-human-review-export.csv",
                "final_maturity_gate_sha256": gate_hash,
                "total_items": log_ids.len(),
                "reviewer_user_ids": reviewer_sets.first().cloned().unwrap_or_default(),
                "review_protocol": "method_masked"
            }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    experiment_csv_response(&state, &run, "confirmatory-human-review-export.csv").await
}

async fn fetch_blind_logs(
    state: &AppState,
    project_id: i32,
    run_id: Option<i32>,
) -> Result<Vec<QueryLogRow>, ApiError> {
    let query = if run_id.is_some() {
        r#"
        SELECT id, project_id, user_id, question, answer, rag_mode,
               graph_hit_count, source_count, response_ms, conversation_id,
               graph_context_json, sources_json, provider, model_name,
               prompt_version, retrieval_config_json, usage_json,
               fallback_reason, error_message, experiment_run_id,
               experiment_case_index, experiment_repetition_index,
               experiment_execution_order, created_at
        FROM ai_query_logs
        WHERE project_id = $1 AND error_message IS NULL AND experiment_run_id = $2
        ORDER BY id
        "#
    } else {
        r#"
        SELECT id, project_id, user_id, question, answer, rag_mode,
               graph_hit_count, source_count, response_ms, conversation_id,
               graph_context_json, sources_json, provider, model_name,
               prompt_version, retrieval_config_json, usage_json,
               fallback_reason, error_message, experiment_run_id,
               experiment_case_index, experiment_repetition_index,
               experiment_execution_order, created_at
        FROM ai_query_logs
        WHERE project_id = $1 AND error_message IS NULL
          AND experiment_run_id IS NOT NULL
        ORDER BY id
        "#
    };
    let mut query = sqlx::query_as::<_, QueryLogRow>(query).bind(project_id);
    if let Some(run_id) = run_id {
        query = query.bind(run_id);
    }
    Ok(query.fetch_all(&state.pool).await?)
}

fn blind_item_json(
    state: &AppState,
    log: &QueryLogRow,
    evaluation: Option<AIQueryEvaluationRead>,
) -> Value {
    let sources = log.sources_json.as_array().cloned().unwrap_or_default();
    let filenames = sources
        .iter()
        .filter_map(|source| source["filename"].as_str())
        .filter(|filename| !filename.trim().is_empty())
        .collect::<Vec<_>>();
    let mut evidence = Vec::new();
    for source in &sources {
        let snippet = source["snippet"].as_str().unwrap_or_default().trim();
        let content = if snippet.is_empty() {
            "项目证据".to_owned()
        } else {
            neutralize_blind_text(snippet, &filenames)
        };
        evidence.push(json!({
            "evidence_id": format!("E{}", evidence.len() + 1),
            "content": content
        }));
    }
    for relation in log
        .graph_context_json
        .as_array()
        .cloned()
        .unwrap_or_default()
    {
        let content = [
            relation["source_label"].as_str().unwrap_or_default(),
            relation["relation_label"]
                .as_str()
                .or_else(|| relation["relation_type"].as_str())
                .unwrap_or("相关"),
            relation["target_label"].as_str().unwrap_or_default(),
        ]
        .into_iter()
        .filter(|part| !part.trim().is_empty())
        .collect::<Vec<_>>()
        .join(" ");
        evidence.push(json!({
            "evidence_id": format!("E{}", evidence.len() + 1),
            "content": neutralize_blind_text(&content, &filenames)
        }));
    }
    let evaluation = evaluation.map(|evaluation| {
        json!({
            "score": evaluation.score,
            "is_accurate": evaluation.is_accurate,
            "is_traceable": evaluation.is_traceable,
            "comment": evaluation.comment,
            "updated_at": evaluation.updated_at
        })
    });
    json!({
        "blind_id": blind_item_id(state, log.project_id, log.id),
        "question": neutralize_blind_text(&log.question, &filenames),
        "answer": log.answer.as_deref().map(|answer| {
            neutralize_blind_text(&neutralize_answer(answer, sources.len()), &filenames)
        }),
        "evidence": evidence,
        "evaluation": evaluation
    })
}

fn neutralize_answer(answer: &str, source_count: usize) -> String {
    let marker = Regex::new(r"(?i)\[([SG])(\d+)\]").unwrap();
    let neutral = marker
        .replace_all(answer, |captures: &regex::Captures<'_>| {
            let index = captures[2].parse::<usize>().unwrap_or_default();
            let evidence = if captures[1].eq_ignore_ascii_case("S") {
                index
            } else {
                source_count + index
            };
            format!("[E{evidence}]")
        })
        .into_owned();
    neutralize_method_labels(&neutral)
}

fn neutralize_method_labels(value: &str) -> String {
    let mut neutral = value.to_owned();
    for (pattern, replacement) in [
        (r"(?i)BM25\s*检索", "系统"),
        (r"(?i)纯\s*(?:LLM|大模型)", "系统"),
        (r"(?i)项目(?:级)?\s*RAG", "系统"),
        ("结构化查询", "系统"),
        (r"(?i)\bBM25(?:[_ -]?RAG)?\b", "系统"),
        (r"(?i)\bpure[_ -]?llm\b", "系统"),
        (r"(?i)\bproject[_ -]?rag\b", "系统"),
        (r"(?i)\bstructured[_ -]?query\b", "系统"),
        (r"(?i)\bkg[_ -]?(?:enhanced[_ -]?)?rag\b", "系统"),
        (r"(?i)\bRAG\b", "系统"),
        ("知识图谱增强", "系统"),
        ("知识图谱", "证据"),
        ("图谱关系", "证据"),
        ("图谱", "证据"),
        ("向量检索", "检索"),
    ] {
        neutral = Regex::new(pattern)
            .unwrap()
            .replace_all(&neutral, replacement)
            .into_owned();
    }
    neutral
}

fn neutralize_blind_text(value: &str, filenames: &[&str]) -> String {
    let citation = Regex::new(r"(?i)\[[SG]\d+\]").unwrap();
    let mut neutral = citation.replace_all(value, "[证据]").into_owned();
    neutral = neutralize_method_labels(&neutral);
    let mut filenames = filenames.to_vec();
    filenames.sort_by_key(|filename| std::cmp::Reverse(filename.chars().count()));
    filenames.dedup();
    for filename in filenames {
        let pattern = format!("(?i){}", regex::escape(filename));
        neutral = Regex::new(&pattern)
            .unwrap()
            .replace_all(&neutral, "项目资料")
            .into_owned();
    }
    neutral
}

pub(super) async fn is_independent_evaluator(
    state: &AppState,
    user: &UserRecord,
    project_id: i32,
) -> Result<bool, ApiError> {
    let project = fetch_project(&state.pool, project_id).await?;
    Ok(can_evaluate_project(&state.pool, user, project_id).await?
        && !can_access_project(&state.pool, user, &project).await?
        && !can_manage_project(&state.pool, user, project_id).await?)
}

async fn require_independent_evaluator(
    state: &AppState,
    user: &UserRecord,
    project_id: i32,
) -> Result<(), ApiError> {
    if is_independent_evaluator(state, user, project_id).await? {
        Ok(())
    } else {
        Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Blind review is restricted to evaluators without project read access",
        ))
    }
}

fn blind_item_id(state: &AppState, project_id: i32, log_id: i32) -> String {
    blind_hmac(
        &state.settings.secret_key,
        &format!("rag-blind-review:{project_id}:{log_id}"),
        'B',
    )
}

fn blind_batch_id(state: &AppState, project_id: i32, run_id: i32) -> String {
    blind_hmac(
        &state.settings.secret_key,
        &format!("rag-blind-review-batch:{project_id}:{run_id}"),
        'R',
    )
}

fn blind_hmac(secret: &str, message: &str, prefix: char) -> String {
    let mut mac = Hmac::<Sha256>::new_from_slice(secret.as_bytes()).expect("HMAC accepts any key");
    mac.update(message.as_bytes());
    let hex = format!("{:X}", mac.finalize().into_bytes());
    format!("{prefix}{}", &hex[..12])
}

async fn find_run_by_batch(
    state: &AppState,
    project_id: i32,
    batch_id: &str,
) -> Result<Option<AIExperimentRunRead>, ApiError> {
    let normalized = batch_id.to_uppercase();
    if !Regex::new(r"^R[A-F0-9]{12}$")
        .unwrap()
        .is_match(&normalized)
    {
        return Ok(None);
    }
    let query =
        format!("SELECT {EXPERIMENT_COLUMNS} FROM ai_experiment_runs WHERE project_id = $1");
    let runs = sqlx::query_as::<_, AIExperimentRunRead>(&query)
        .bind(project_id)
        .fetch_all(&state.pool)
        .await?;
    Ok(runs
        .into_iter()
        .find(|run| blind_batch_id(state, project_id, run.id) == normalized))
}

async fn completed_masked_items(
    state: &AppState,
    log_ids: &[i32],
) -> Result<(usize, Vec<Vec<i32>>), ApiError> {
    if log_ids.is_empty() {
        return Ok((0, Vec::new()));
    }
    let rows: Vec<(i32, i32)> = sqlx::query_as(
        r#"
        SELECT query_log_id, evaluator_user_id FROM ai_query_evaluations
        WHERE query_log_id = ANY($1) AND review_protocol = 'method_masked'
        ORDER BY query_log_id, evaluator_user_id
        "#,
    )
    .bind(log_ids)
    .fetch_all(&state.pool)
    .await?;
    let mut by_log: std::collections::HashMap<i32, std::collections::HashSet<i32>> =
        std::collections::HashMap::new();
    for (log_id, evaluator_id) in rows {
        by_log.entry(log_id).or_default().insert(evaluator_id);
    }
    let mut sets = Vec::new();
    let mut completed = 0;
    for log_id in log_ids {
        let set = by_log.get(log_id).cloned().unwrap_or_default();
        if set.len() >= 2 {
            completed += 1;
            let mut values: Vec<i32> = set.into_iter().collect();
            values.sort();
            sets.push(values);
        }
    }
    Ok((completed, sets))
}

async fn fetch_formal_batch_for_run(
    state: &AppState,
    run_id: i32,
) -> Result<Option<FormalBlindReviewBatchRow>, ApiError> {
    Ok(sqlx::query_as::<_, FormalBlindReviewBatchRow>(
        r#"
        SELECT experiment_run_id, freeze_manifest_sha256,
               reviewer_a_user_id, reviewer_b_user_id, status
        FROM ai_blind_review_batches
        WHERE experiment_run_id = $1
        "#,
    )
    .bind(run_id)
    .fetch_optional(&state.pool)
    .await?)
}

async fn fetch_formal_batches_for_runs(
    state: &AppState,
    run_ids: &[i32],
) -> Result<std::collections::HashMap<i32, FormalBlindReviewBatchRow>, ApiError> {
    if run_ids.is_empty() {
        return Ok(std::collections::HashMap::new());
    }
    let rows = sqlx::query_as::<_, FormalBlindReviewBatchRow>(
        r#"
        SELECT experiment_run_id, freeze_manifest_sha256,
               reviewer_a_user_id, reviewer_b_user_id, status
        FROM ai_blind_review_batches
        WHERE experiment_run_id = ANY($1)
        "#,
    )
    .bind(run_ids)
    .fetch_all(&state.pool)
    .await?;
    Ok(rows
        .into_iter()
        .map(|row| (row.experiment_run_id, row))
        .collect())
}

fn assigned_reviewer_ids(batch: &FormalBlindReviewBatchRow) -> Vec<i32> {
    let mut reviewers = vec![batch.reviewer_a_user_id, batch.reviewer_b_user_id];
    reviewers.sort_unstable();
    reviewers
}

fn is_assigned_reviewer(batch: &FormalBlindReviewBatchRow, user_id: i32) -> bool {
    assigned_reviewer_ids(batch).contains(&user_id)
}

async fn lock_formal_batch_project(
    transaction: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    project_id: i32,
) -> Result<(), ApiError> {
    sqlx::query("SELECT pg_advisory_xact_lock($1, $2)")
        .bind(8742_i64)
        .bind(project_id)
        .fetch_one(&mut **transaction)
        .await?;
    Ok(())
}

async fn formal_batch_reviewer_eligible(
    transaction: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    project_id: i32,
    user_id: i32,
) -> Result<bool, ApiError> {
    let exists: Option<i32> = sqlx::query_scalar(
        "SELECT id FROM users WHERE id = $1 FOR NO KEY UPDATE /* blind_batch_reviewer_lock */",
    )
    .bind(user_id)
    .fetch_optional(&mut **transaction)
    .await?;
    if exists.is_none() {
        return Err(ApiError::new(StatusCode::NOT_FOUND, "User not found"));
    }
    Ok(sqlx::query_scalar(
        r#"
        SELECT EXISTS(
            SELECT 1
            FROM project_members pm
            JOIN project_reviewers pr
              ON pr.project_id = pm.project_id
             AND pr.user_id = pm.user_id
            WHERE pm.project_id = $1
              AND pm.user_id = $2
              AND pm.project_role = 'REVIEWER'::projectrole
              AND pm.can_read = false
              AND pm.can_write = false
              AND pm.can_review = false
              AND pm.can_evaluate = true
              AND pm.can_manage = false
        )
        "#,
    )
    .bind(project_id)
    .bind(user_id)
    .fetch_one(&mut **transaction)
    .await?)
}

async fn final_maturity_gate_hash() -> Option<String> {
    let candidates = [
        "/app/docs/experiments/final-maturity-gate-latest.json",
        "../docs/experiments/final-maturity-gate-latest.json",
        "docs/experiments/final-maturity-gate-latest.json",
    ];
    for candidate in candidates {
        let Ok(bytes) = tokio::fs::read(candidate).await else {
            continue;
        };
        let Ok(payload) = serde_json::from_slice::<Value>(&bytes) else {
            continue;
        };
        let required = [
            "internal release-candidate gate passed",
            "production configuration was checked in production mode",
            "external confirmatory human-review freeze passed",
            "long soak evidence passed",
            "real TLS deployment evidence passed",
            "offsite encrypted backup evidence passed",
            "final maturity evidence manifest verified",
        ];
        let checks = payload["checks"].as_array().cloned().unwrap_or_default();
        let names: std::collections::HashSet<&str> = checks
            .iter()
            .filter(|check| check["passed"] == true)
            .filter_map(|check| check["name"].as_str())
            .collect();
        if payload["passed"] == true
            && payload["scope"] == "final maturity gate for confirmatory human review"
            && payload["failures"].as_array().is_some_and(Vec::is_empty)
            && payload["generated_at"].is_string()
            && required.iter().all(|name| names.contains(name))
        {
            return Some(format!("{:x}", Sha256::digest(&bytes)));
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::{neutralize_answer, neutralize_blind_text};

    #[test]
    fn test_blind_output_masks_all_method_labels() {
        let answer = "BM25_RAG / pure_llm / project_rag / structured_query / KG-enhanced RAG / BM25 检索 / 纯 LLM / 纯大模型 / 项目级 RAG / 结构化查询 [S1]";

        let masked = neutralize_answer(answer, 1);
        let normalized = masked.to_ascii_lowercase();

        for method in [
            "bm25",
            "pure_llm",
            "project_rag",
            "structured_query",
            "kg-enhanced",
            "bm25 检索",
            "纯 llm",
            "纯大模型",
            "项目级 rag",
            "结构化查询",
        ] {
            assert!(!normalized.contains(method), "method leaked: {method}");
        }
        assert!(masked.contains("[E1]"));
    }

    #[test]
    fn test_blind_output_masks_internal_source_markers() {
        let masked = neutralize_blind_text("原文引用 [S1] 和 [G2]", &[]);

        assert_eq!(masked, "原文引用 [证据] 和 [证据]");
    }
}
