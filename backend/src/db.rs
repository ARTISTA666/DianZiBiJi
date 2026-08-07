use std::{collections::HashSet, time::Duration};

use chrono::Utc;
use serde_json::{json, Value};
use sqlx::{postgres::PgPoolOptions, PgConnection, PgPool, Postgres, Transaction};
use thiserror::Error;

use crate::{
    config::Settings,
    security::{hash_password, SecurityError},
};

pub const INITIAL_SCHEMA: &str = include_str!("../sql/0001_initial.sql");
const DATABASE_INITIALIZATION_LOCK_ID: i64 = 4_545_704_429_315_697;
const RAG_HNSW_INITIALIZATION_LOCK_ID: i64 = 4_545_704_429_315_698;
const RAG_HNSW_INDEX_NAME: &str = "ix_rag_chunks_embedding_hnsw";
const RUST_SCHEMA_VERSION: i32 = 3;
const LEGACY_EXPERIMENT_STALE_GRACE_SECONDS: i32 = 600;
pub const EXPERIMENT_HEARTBEAT_INTERVAL_SECONDS: u64 = 2;
pub const EXPERIMENT_LEASE_SECONDS: i32 = 6;
pub const STALE_EXPERIMENT_REAPER_INTERVAL_SECONDS: u64 = 1;

// This is the minimum schema shape required by the Rust runtime.  Checking a
// single legacy table is unsafe: an old Python database can contain `users`
// while still missing entire feature tables and post-baseline columns.
const RUNTIME_SCHEMA_SIGNATURE: &[(&str, &[&str])] = &[
    ("users", &["id", "auth_version"]),
    ("groups", &["id"]),
    ("group_members", &["id"]),
    ("group_projects", &["id"]),
    ("projects", &["id"]),
    ("project_members", &["id", "can_evaluate"]),
    ("project_reviewers", &["id"]),
    ("experiment_templates", &["id"]),
    ("experiment_notes", &["id"]),
    ("note_versions", &["id"]),
    ("note_approvals", &["id"]),
    (
        "files",
        &[
            "id",
            "knowledge_sync_status",
            "knowledge_synced_at",
            "knowledge_sync_message",
        ],
    ),
    ("audit_logs", &["id"]),
    ("search_documents", &["id"]),
    ("file_ocr_results", &["id", "review_status"]),
    ("kg_entities", &["id"]),
    ("kg_relations", &["id"]),
    ("kg_extraction_runs", &["id"]),
    (
        "project_rag_datasets",
        &["id", "provider", "embedding_model", "generation_model"],
    ),
    ("rag_file_syncs", &["id", "chunk_count", "content_hash"]),
    ("rag_document_chunks", &["id", "embedding"]),
    (
        "ai_query_logs",
        &[
            "id",
            "provider",
            "model_name",
            "prompt_version",
            "retrieval_config_json",
            "usage_json",
            "fallback_reason",
            "experiment_run_id",
            "experiment_case_index",
            "experiment_repetition_index",
            "experiment_execution_order",
        ],
    ),
    ("ai_query_evaluations", &["id", "review_protocol"]),
    (
        "ai_experiment_runs",
        &["id", "worker_id", "heartbeat_at", "lease_expires_at"],
    ),
    (
        "agent_generation_runs",
        &[
            "id",
            "provider",
            "model_name",
            "prompt_version",
            "usage_json",
        ],
    ),
];

pub struct SeedTemplate {
    pub name: &'static str,
    pub experiment_type: &'static str,
    pub fields: &'static [&'static str],
}

#[derive(Debug, Error)]
pub enum DatabaseError {
    #[error("Database operation failed: {0}")]
    Sql(#[from] sqlx::Error),
    #[error("Password initialization failed: {0}")]
    Security(#[from] SecurityError),
    #[error("Demo file initialization failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("Demo knowledge graph initialization failed: {0}")]
    Domain(String),
}

pub async fn connect_database(settings: &Settings) -> Result<PgPool, DatabaseError> {
    Ok(PgPoolOptions::new()
        .max_connections(20)
        .min_connections(1)
        .acquire_timeout(Duration::from_secs(30))
        .connect(&settings.database_url())
        .await?)
}

pub async fn initialize_database(pool: &PgPool, settings: &Settings) -> Result<(), DatabaseError> {
    let mut transaction = pool.begin().await?;
    sqlx::query("SELECT pg_advisory_xact_lock($1)")
        .bind(DATABASE_INITIALIZATION_LOCK_ID)
        .execute(&mut *transaction)
        .await?;
    let schema_exists: bool = sqlx::query_scalar("SELECT to_regclass('public.users') IS NOT NULL")
        .fetch_one(&mut *transaction)
        .await?;
    if !schema_exists {
        sqlx::raw_sql(INITIAL_SCHEMA)
            .execute(&mut *transaction)
            .await?;
        // pg_dump clears search_path for the session. Restore it before this
        // pooled connection is returned, otherwise later unqualified queries
        // can fail nondeterministically.
        sqlx::query("SET search_path TO public")
            .execute(&mut *transaction)
            .await?;
    }
    sqlx::raw_sql(
        r#"
        ALTER TABLE public.ai_experiment_runs
            ADD COLUMN IF NOT EXISTS worker_id varchar(80),
            ADD COLUMN IF NOT EXISTS heartbeat_at timestamp with time zone,
            ADD COLUMN IF NOT EXISTS lease_expires_at timestamp with time zone;
        CREATE INDEX IF NOT EXISTS ix_ai_experiment_runs_lease
            ON public.ai_experiment_runs (status, lease_expires_at);
        -- Mirrors Alembic migration 0011: time-ordered audit log listings.
        CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at
            ON public.audit_logs (created_at DESC)
        "#,
    )
    .execute(&mut *transaction)
    .await?;
    // Mirrors legacy Alembic migration 0010: file_size must be bigint so
    // uploads above 2 GiB and the i64 model decode both stay valid.
    sqlx::query(
        r#"
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'files'
                  AND column_name = 'file_size' AND data_type = 'integer'
            ) THEN
                ALTER TABLE public.files ALTER COLUMN file_size TYPE bigint;
            END IF;
        END
        $$
        "#,
    )
    .execute(&mut *transaction)
    .await?;
    let duplicate_active_project: Option<i32> = sqlx::query_scalar(
        r#"
        SELECT project_id FROM public.ai_experiment_runs
        WHERE status IN ('queued', 'running')
        GROUP BY project_id HAVING count(*) > 1
        ORDER BY project_id LIMIT 1
        "#,
    )
    .fetch_optional(&mut *transaction)
    .await?;
    if let Some(project_id) = duplicate_active_project {
        return Err(DatabaseError::Domain(format!(
            "Cannot enforce one active experiment per project: project {project_id} has multiple queued/running runs"
        )));
    }
    sqlx::query(
        r#"
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_experiment_runs_one_active_per_project
        ON public.ai_experiment_runs (project_id)
        WHERE status IN ('queued', 'running')
        "#,
    )
    .execute(&mut *transaction)
    .await?;
    validate_runtime_schema(&mut transaction).await?;
    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS public.rust_schema_versions (
            version integer PRIMARY KEY,
            applied_at timestamp with time zone NOT NULL DEFAULT now()
        )
        "#,
    )
    .execute(&mut *transaction)
    .await?;
    sqlx::query(
        "INSERT INTO public.rust_schema_versions (version) VALUES (2) ON CONFLICT DO NOTHING",
    )
    .execute(&mut *transaction)
    .await?;
    ensure_seed_data(&mut transaction, settings).await?;
    transaction.commit().await?;
    ensure_rag_hnsw_index(pool).await?;
    Ok(())
}

async fn ensure_rag_hnsw_index(pool: &PgPool) -> Result<(), DatabaseError> {
    let mut connection = pool.acquire().await?;
    sqlx::query("SELECT pg_advisory_lock($1)")
        .bind(RAG_HNSW_INITIALIZATION_LOCK_ID)
        .execute(&mut *connection)
        .await?;

    let migration_result = ensure_rag_hnsw_index_locked(&mut connection).await;
    let unlock_result: Result<bool, sqlx::Error> =
        sqlx::query_scalar("SELECT pg_advisory_unlock($1)")
            .bind(RAG_HNSW_INITIALIZATION_LOCK_ID)
            .fetch_one(&mut *connection)
            .await;

    migration_result?;
    if !unlock_result? {
        return Err(DatabaseError::Domain(
            "Failed to release the RAG HNSW schema advisory lock".to_owned(),
        ));
    }
    Ok(())
}

async fn ensure_rag_hnsw_index_locked(connection: &mut PgConnection) -> Result<(), DatabaseError> {
    if let Some((definition, valid, ready)) = rag_hnsw_index_state(connection).await? {
        if valid && ready {
            if !is_expected_rag_hnsw_index(&definition) {
                return Err(DatabaseError::Domain(format!(
                    "Existing index {RAG_HNSW_INDEX_NAME} has an incompatible definition: {definition}"
                )));
            }
            stamp_rust_schema_v3(connection).await?;
            return Ok(());
        }
        sqlx::query("DROP INDEX CONCURRENTLY IF EXISTS public.ix_rag_chunks_embedding_hnsw")
            .execute(&mut *connection)
            .await?;
    }

    sqlx::query(
        r#"
        CREATE INDEX CONCURRENTLY ix_rag_chunks_embedding_hnsw
        ON public.rag_document_chunks
        USING hnsw (embedding public.vector_cosine_ops)
        "#,
    )
    .execute(&mut *connection)
    .await?;

    let Some((definition, valid, ready)) = rag_hnsw_index_state(connection).await? else {
        return Err(DatabaseError::Domain(format!(
            "PostgreSQL did not create {RAG_HNSW_INDEX_NAME}"
        )));
    };
    if !valid || !ready || !is_expected_rag_hnsw_index(&definition) {
        return Err(DatabaseError::Domain(format!(
            "PostgreSQL created an invalid RAG HNSW index: {definition} (valid={valid}, ready={ready})"
        )));
    }
    stamp_rust_schema_v3(connection).await?;
    Ok(())
}

async fn rag_hnsw_index_state(
    connection: &mut PgConnection,
) -> Result<Option<(String, bool, bool)>, sqlx::Error> {
    sqlx::query_as(
        r#"
        SELECT pg_get_indexdef(indexrelid), indisvalid, indisready
        FROM pg_index
        WHERE indexrelid = to_regclass('public.ix_rag_chunks_embedding_hnsw')
        "#,
    )
    .fetch_optional(connection)
    .await
}

fn is_expected_rag_hnsw_index(definition: &str) -> bool {
    definition
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_ascii_lowercase()
        .replace("public.vector_cosine_ops", "vector_cosine_ops")
        .contains(" on public.rag_document_chunks using hnsw (embedding vector_cosine_ops)")
}

async fn stamp_rust_schema_v3(connection: &mut PgConnection) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO public.rust_schema_versions (version) VALUES ($1) ON CONFLICT DO NOTHING",
    )
    .bind(RUST_SCHEMA_VERSION)
    .execute(connection)
    .await?;
    Ok(())
}

fn runtime_schema_gaps(columns: &[(String, String)]) -> Vec<String> {
    let available = columns
        .iter()
        .map(|(table, column)| (table.as_str(), column.as_str()))
        .collect::<HashSet<_>>();
    let mut gaps = Vec::new();
    for (table, required_columns) in RUNTIME_SCHEMA_SIGNATURE {
        for column in *required_columns {
            if !available.contains(&(*table, *column)) {
                gaps.push(format!("{table}.{column}"));
            }
        }
    }
    gaps
}

async fn validate_runtime_schema(
    transaction: &mut Transaction<'_, Postgres>,
) -> Result<(), DatabaseError> {
    let columns: Vec<(String, String)> = sqlx::query_as(
        r#"
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        "#,
    )
    .fetch_all(&mut **transaction)
    .await?;
    let mut gaps = runtime_schema_gaps(&columns);
    let active_index_exists: bool = sqlx::query_scalar(
        "SELECT to_regclass('public.uq_ai_experiment_runs_one_active_per_project') IS NOT NULL",
    )
    .fetch_one(&mut **transaction)
    .await?;
    if !active_index_exists {
        gaps.push("index.uq_ai_experiment_runs_one_active_per_project".to_owned());
    }
    if gaps.is_empty() {
        return Ok(());
    }

    let shown = gaps.iter().take(16).cloned().collect::<Vec<_>>().join(", ");
    let remainder = gaps.len().saturating_sub(16);
    let suffix = if remainder == 0 {
        String::new()
    } else {
        format!(" (and {remainder} more)")
    };
    Err(DatabaseError::Domain(format!(
        "Existing database schema is incompatible with this Rust backend; missing {shown}{suffix}. Apply legacy migrations through 0004_experiment_single_active with the previous migration image, or restore a compatible backup. Refusing to stamp Rust schema version 2."
    )))
}

pub async fn recover_interrupted_experiment_runs(pool: &PgPool) -> Result<usize, DatabaseError> {
    let mut transaction = pool.begin().await?;
    let runs: Vec<(i32, i32, i32, i32, Value)> = sqlx::query_as(
        r#"
        SELECT id, total_cases, completed_cases, failed_cases, summary_json
        FROM ai_experiment_runs
        WHERE status = 'running'
          AND COALESCE(
                lease_expires_at,
                heartbeat_at + make_interval(secs => $1),
                created_at + make_interval(secs => $1)
              ) <= now()
        FOR UPDATE
        "#,
    )
    .bind(LEGACY_EXPERIMENT_STALE_GRACE_SECONDS)
    .fetch_all(&mut *transaction)
    .await?;
    let recovered_at = Utc::now().to_rfc3339();

    for (run_id, total_cases, previous_completed, previous_failed, summary) in &runs {
        let logs: Vec<(Option<i32>, Option<String>)> = sqlx::query_as(
            r#"
            SELECT experiment_execution_order, error_message
            FROM ai_query_logs
            WHERE experiment_run_id = $1
            "#,
        )
        .bind(run_id)
        .fetch_all(&mut *transaction)
        .await?;
        let successful: HashSet<i32> = logs
            .iter()
            .filter_map(|(order, error)| error.is_none().then_some(*order).flatten())
            .collect();
        let failed: HashSet<i32> = logs
            .iter()
            .filter_map(|(order, error)| error.is_some().then_some(*order).flatten())
            .filter(|order| !successful.contains(order))
            .collect();
        let completed_cases = (*previous_completed).max(successful.len() as i32);
        let failed_cases = (*previous_failed).max(failed.len() as i32);
        let summary = recovered_experiment_summary(
            summary.clone(),
            *total_cases,
            completed_cases,
            failed_cases,
            &recovered_at,
        );
        sqlx::query(
            r#"
            UPDATE ai_experiment_runs
            SET status = 'interrupted', completed_cases = $2, failed_cases = $3,
                summary_json = $4, completed_at = now(), worker_id = NULL,
                heartbeat_at = NULL, lease_expires_at = NULL
            WHERE id = $1 AND status = 'running'
            "#,
        )
        .bind(run_id)
        .bind(completed_cases)
        .bind(failed_cases)
        .bind(summary)
        .execute(&mut *transaction)
        .await?;
    }
    transaction.commit().await?;
    Ok(runs.len())
}

fn recovered_experiment_summary(
    mut summary: Value,
    total_cases: i32,
    completed_cases: i32,
    failed_cases: i32,
    recovered_at: &str,
) -> Value {
    if !summary.is_object() {
        summary = json!({});
    }
    summary["interruption"] =
        json!("Experiment worker lease expired before the experiment completed");
    summary["recovered_at"] = json!(recovered_at);
    summary["unexecuted_cases"] = json!((total_cases - completed_cases - failed_cases).max(0));
    summary
}

async fn ensure_seed_data(
    transaction: &mut Transaction<'_, Postgres>,
    settings: &Settings,
) -> Result<(), DatabaseError> {
    let admin_id: Option<i32> = sqlx::query_scalar("SELECT id FROM users WHERE username = $1")
        .bind(&settings.bootstrap_admin_username)
        .fetch_optional(&mut **transaction)
        .await?;
    let admin_id = if let Some(admin_id) = admin_id {
        admin_id
    } else {
        let password_hash = hash_password(&settings.bootstrap_admin_password)?;
        let inserted: Option<i32> = sqlx::query_scalar(
            r#"
            INSERT INTO users (
                username, password_hash, display_name, email, role, status, auth_version
            )
            VALUES ($1, $2, '系统管理员', 'admin@example.local',
                    'SUPER_ADMIN'::userrole, 'ACTIVE'::userstatus, 0)
            ON CONFLICT (username) DO NOTHING
            RETURNING id
            "#,
        )
        .bind(&settings.bootstrap_admin_username)
        .bind(password_hash)
        .fetch_optional(&mut **transaction)
        .await?;
        if let Some(admin_id) = inserted {
            admin_id
        } else {
            sqlx::query_scalar("SELECT id FROM users WHERE username = $1")
                .bind(&settings.bootstrap_admin_username)
                .fetch_one(&mut **transaction)
                .await?
        }
    };

    for template in seed_templates() {
        let schema = json!({
            "fields": template
                .fields
                .iter()
                .map(|field| json!({"key": field, "label": field, "type": "textarea"}))
                .collect::<Vec<Value>>()
        });
        let content = json!({
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": template.name}]
                },
                {
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": "请记录实验过程、关键观察、结果分析和下一步计划。"
                    }]
                }
            ]
        });
        sqlx::query(
            r#"
            INSERT INTO experiment_templates (
                name, experiment_type, schema_json, default_content_json,
                is_active, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, true, now(), now())
            ON CONFLICT (name) DO NOTHING
            "#,
        )
        .bind(template.name)
        .bind(template.experiment_type)
        .bind(schema)
        .bind(content)
        .execute(&mut **transaction)
        .await?;
    }
    if settings.seed_demo_data {
        ensure_demo_data(transaction, admin_id, &settings.storage_root).await?;
    }
    Ok(())
}

async fn ensure_demo_data(
    transaction: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    admin_id: i32,
    storage_root: &str,
) -> Result<(), DatabaseError> {
    let project_id: Option<i32> =
        sqlx::query_scalar("SELECT id FROM projects WHERE name = '论文演示项目：KG-RAG 实验流程'")
            .fetch_optional(&mut **transaction)
            .await?;
    let project_id = if let Some(project_id) = project_id {
        project_id
    } else {
        sqlx::query_scalar(
            r#"
            INSERT INTO projects (
                name, description, is_sensitive, status, approval_enabled, owner_user_id
            )
            VALUES (
                '论文演示项目：KG-RAG 实验流程',
                '用于论文截图和实验章节的演示项目，覆盖实验笔记、资料库、知识图谱、RAG 问答、评价和智能体生成闭环。',
                false, 'ACTIVE'::projectstatus, false, $1
            )
            RETURNING id
            "#,
        )
        .bind(admin_id)
        .fetch_one(&mut **transaction)
        .await?
    };

    let notes = [
        (
            "PCR 条件优化实验",
            "PCR",
            "2026-06-03",
            json!({
                "reagents": "Taq DNA Polymerase、dNTP、MgCl2、模板 DNA",
                "instrument": "PCR Thermal Cycler",
                "sample": "样本 A、样本 B",
                "result": "退火温度 58℃ 时扩增条带最清晰，非特异性条带减少。"
            }),
            "试剂: Taq DNA Polymerase、dNTP、MgCl2\n仪器: PCR Thermal Cycler\n样本: 样本 A、样本 B\n结果: 58℃ 条件下条带清晰。",
        ),
        (
            "细胞活力检测实验",
            "细胞培养",
            "2026-06-04",
            json!({
                "reagents": "CCK-8、PBS、DMEM 培养基",
                "instrument": "酶标仪、CO2 培养箱",
                "sample": "处理组细胞、对照组细胞",
                "result": "处理组细胞活力较对照组下降约 18%，重复孔结果稳定。"
            }),
            "试剂: CCK-8、PBS、DMEM 培养基\n仪器: 酶标仪、CO2 培养箱\n样本: 处理组细胞、对照组细胞\n结果: 细胞活力下降约 18%。",
        ),
        (
            "Western Blot 蛋白表达验证",
            "Western Blot",
            "2026-06-05",
            json!({
                "reagents": "RIPA 裂解液、BCA 试剂盒、一抗、二抗",
                "instrument": "电泳仪、转膜仪、凝胶成像系统",
                "sample": "蛋白样本 P1、蛋白样本 P2",
                "result": "目标蛋白在处理组表达降低，内参条带稳定。"
            }),
            "试剂: RIPA 裂解液、BCA 试剂盒、一抗、二抗\n仪器: 电泳仪、转膜仪、凝胶成像系统\n样本: 蛋白样本 P1、蛋白样本 P2\n结果: 处理组目标蛋白表达降低。",
        ),
        (
            "qPCR 定量验证实验",
            "PCR",
            "2026-05-28",
            json!({
                "reagents": "SYBR Green Master Mix、cDNA 模板、引物对、无酶水",
                "instrument": "荧光定量 PCR 仪、微量分光光度计",
                "sample": "cDNA 样本 1、cDNA 样本 2、阴性对照",
                "result": "目标基因在样本 1 中表达量约为样本 2 的 2.3 倍，融解曲线单一峰。"
            }),
            "试剂: SYBR Green Master Mix、cDNA 模板、引物对、无酶水\n仪器: 荧光定量 PCR 仪、微量分光光度计\n样本: cDNA 样本 1、2、阴性对照\n结果: 目标基因差异表达约 2.3 倍。",
        ),
    ];
    let mut new_note_ids = Vec::new();
    for (title, experiment_type, experiment_date, fixed_fields, content_text) in notes {
        let existing: Option<i32> = sqlx::query_scalar(
            "SELECT id FROM experiment_notes WHERE project_id = $1 AND title = $2",
        )
        .bind(project_id)
        .bind(title)
        .fetch_optional(&mut **transaction)
        .await?;
        if existing.is_some() {
            continue;
        }
        let note_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO experiment_notes (
                project_id, template_id, title, experiment_type, experiment_date,
                owner_user_id, status, current_version_id, created_at, updated_at
            )
            VALUES ($1, NULL, $2, $3, $4::date, $5, 'APPROVED'::notestatus,
                    NULL, now(), now())
            RETURNING id
            "#,
        )
        .bind(project_id)
        .bind(title)
        .bind(experiment_type)
        .bind(experiment_date)
        .bind(admin_id)
        .fetch_one(&mut **transaction)
        .await?;
        let version_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO note_versions (
                note_id, version_number, fixed_fields_json, content_json,
                created_by, change_summary, is_locked
            )
            VALUES ($1, 1, $2, $3, $4, '论文演示数据', true)
            RETURNING id
            "#,
        )
        .bind(note_id)
        .bind(fixed_fields)
        .bind(json!({"text": content_text}))
        .bind(admin_id)
        .fetch_one(&mut **transaction)
        .await?;
        sqlx::query("UPDATE experiment_notes SET current_version_id = $2 WHERE id = $1")
            .bind(note_id)
            .bind(version_id)
            .execute(&mut **transaction)
            .await?;
        sqlx::query(
            r#"
            INSERT INTO note_approvals (
                note_id, version_id, reviewer_user_id, action, comment
            )
            VALUES ($1, $2, $3, 'approved', '论文演示数据审核通过')
            "#,
        )
        .bind(note_id)
        .bind(version_id)
        .bind(admin_id)
        .execute(&mut **transaction)
        .await?;
        new_note_ids.push(note_id);
    }

    let demo_dir = std::path::Path::new(storage_root).join("demo");
    tokio::fs::create_dir_all(&demo_dir).await?;
    for (filename, content) in [
        (
            "PCR_protocol_demo.txt",
            "PCR 体系配置、循环条件和退火温度优化说明。",
        ),
        (
            "cell_assay_reference_demo.txt",
            "CCK-8 检测步骤、读数要求和细胞活力统计说明。",
        ),
    ] {
        let path = demo_dir.join(filename);
        if !tokio::fs::try_exists(&path).await? {
            tokio::fs::write(&path, content.as_bytes()).await?;
        }
        let existing: Option<i32> = sqlx::query_scalar(
            "SELECT id FROM files WHERE project_id = $1 AND original_filename = $2",
        )
        .bind(project_id)
        .bind(filename)
        .fetch_optional(&mut **transaction)
        .await?;
        if existing.is_some() {
            continue;
        }
        let file_size = i64::try_from(tokio::fs::metadata(&path).await?.len())
            .map_err(|error| DatabaseError::Domain(error.to_string()))?;
        let storage_path = path.to_string_lossy().into_owned();
        sqlx::query(
            r#"
            INSERT INTO files (
                project_id, note_id, uploaded_by, file_category, original_filename,
                storage_path, mime_type, file_size, file_hash, status,
                knowledge_sync_status, knowledge_synced_at, knowledge_sync_message
            )
            VALUES ($1, NULL, $2, 'KNOWLEDGE_DOCUMENT'::filecategory, $3, $4,
                    'text/plain', $5, $6, 'APPROVED'::filestatus,
                    'pending_sync', NULL, '等待本地向量入库')
            "#,
        )
        .bind(project_id)
        .bind(admin_id)
        .bind(filename)
        .bind(storage_path)
        .bind(file_size)
        .bind(format!("demo-{filename}"))
        .execute(&mut **transaction)
        .await?;
    }

    for note_id in new_note_ids {
        crate::knowledge_graph::extract_note(transaction, note_id, admin_id, true)
            .await
            .map_err(|error| DatabaseError::Domain(error.to_string()))?;
    }
    Ok(())
}

pub fn seed_templates() -> Vec<SeedTemplate> {
    vec![
        SeedTemplate {
            name: "PCR",
            experiment_type: "PCR",
            fields: &[
                "实验目的",
                "样本信息",
                "引物信息",
                "反应体系",
                "循环条件",
                "电泳结果",
                "结论",
            ],
        },
        SeedTemplate {
            name: "Western Blot",
            experiment_type: "Western Blot",
            fields: &[
                "实验目的",
                "样本处理",
                "蛋白定量",
                "电泳转膜",
                "抗体信息",
                "显影结果",
                "结论",
            ],
        },
        SeedTemplate {
            name: "细胞培养",
            experiment_type: "细胞培养",
            fields: &[
                "细胞系",
                "培养基",
                "传代比例",
                "培养条件",
                "细胞状态",
                "污染检查",
                "下一步",
            ],
        },
        SeedTemplate {
            name: "质粒构建/转染",
            experiment_type: "质粒构建/转染",
            fields: &[
                "载体信息",
                "插入片段",
                "连接/转化",
                "菌检结果",
                "转染条件",
                "表达验证",
                "结论",
            ],
        },
        SeedTemplate {
            name: "动物实验/样本处理",
            experiment_type: "动物实验/样本处理",
            fields: &[
                "动物信息",
                "分组设计",
                "处理方案",
                "采样时间",
                "样本编号",
                "观察记录",
                "伦理备注",
            ],
        },
    ]
}

#[cfg(test)]
mod tests {
    use std::{collections::HashMap, str::FromStr};

    use chrono::{DateTime, Utc};
    use serde_json::json;
    use sqlx::{
        postgres::{PgConnectOptions, PgPoolOptions},
        ConnectOptions, PgPool,
    };
    use uuid::Uuid;

    use super::{
        connect_database, initialize_database, recover_interrupted_experiment_runs,
        recovered_experiment_summary, runtime_schema_gaps, seed_templates,
        EXPERIMENT_HEARTBEAT_INTERVAL_SECONDS, EXPERIMENT_LEASE_SECONDS, INITIAL_SCHEMA,
        STALE_EXPERIMENT_REAPER_INTERVAL_SECONDS,
    };
    use crate::config::Settings;

    async fn rag_hnsw_index_state(pool: &PgPool) -> Option<(String, bool, bool)> {
        sqlx::query_as(
            r#"
            SELECT pg_get_indexdef(indexrelid), indisvalid, indisready
            FROM pg_index
            WHERE indexrelid = to_regclass('public.ix_rag_chunks_embedding_hnsw')
            "#,
        )
        .fetch_optional(pool)
        .await
        .unwrap()
    }

    #[test]
    fn test_initial_schema_contains_every_runtime_table() {
        let required = [
            "users",
            "groups",
            "group_members",
            "projects",
            "project_members",
            "project_reviewers",
            "experiment_templates",
            "experiment_notes",
            "note_versions",
            "note_approvals",
            "files",
            "audit_logs",
            "search_documents",
            "file_ocr_results",
            "kg_entities",
            "kg_relations",
            "kg_extraction_runs",
            "project_rag_datasets",
            "rag_file_syncs",
            "rag_document_chunks",
            "ai_query_logs",
            "ai_query_evaluations",
            "ai_experiment_runs",
            "agent_generation_runs",
        ];

        for table in required {
            assert!(
                INITIAL_SCHEMA.contains(&format!("CREATE TABLE public.{table}")),
                "missing table {table}"
            );
        }
        for lease_column in ["worker_id", "heartbeat_at", "lease_expires_at"] {
            assert!(
                INITIAL_SCHEMA.contains(&format!("{lease_column} ")),
                "missing experiment lease column {lease_column}"
            );
        }
        assert!(INITIAL_SCHEMA.contains("uq_ai_experiment_runs_one_active_per_project"));
        assert!(
            INITIAL_SCHEMA.contains(
                "CREATE INDEX ix_rag_chunks_embedding_hnsw ON public.rag_document_chunks USING hnsw (embedding public.vector_cosine_ops)"
            ),
            "fresh Rust-owned schema must create the pgvector cosine HNSW index"
        );
    }

    #[test]
    fn test_runtime_schema_signature_rejects_legacy_python_schema() {
        let legacy_columns = vec![
            ("users".to_owned(), "id".to_owned()),
            ("files".to_owned(), "id".to_owned()),
            ("project_members".to_owned(), "id".to_owned()),
            ("ai_query_logs".to_owned(), "id".to_owned()),
        ];

        let gaps = runtime_schema_gaps(&legacy_columns);

        assert!(gaps.contains(&"users.auth_version".to_owned()));
        assert!(gaps.contains(&"files.knowledge_sync_status".to_owned()));
        assert!(gaps.contains(&"project_members.can_evaluate".to_owned()));
        assert!(gaps.contains(&"file_ocr_results.id".to_owned()));
        assert!(gaps.contains(&"ai_query_logs.experiment_execution_order".to_owned()));
    }

    #[test]
    fn test_seed_templates_preserves_five_existing_templates() {
        let templates = seed_templates();

        assert_eq!(templates.len(), 5);
        assert_eq!(templates[0].name, "PCR");
        assert!(templates.iter().any(|item| item.name == "Western Blot"));
        assert!(templates
            .iter()
            .any(|item| item.name == "动物实验/样本处理"));
    }

    #[test]
    fn recovery_summary_preserves_plan_and_records_progress() {
        let summary = recovered_experiment_summary(
            json!({"execution_plan": [{"execution_order": 1}], "errors": []}),
            10,
            4,
            2,
            "2026-07-23T12:00:00+00:00",
        );

        assert_eq!(summary["execution_plan"][0]["execution_order"], 1);
        assert_eq!(summary["unexecuted_cases"], 4);
        assert_eq!(summary["recovered_at"], "2026-07-23T12:00:00+00:00");
        assert!(summary["interruption"]
            .as_str()
            .unwrap()
            .contains("worker lease expired"));
    }

    #[test]
    fn experiment_lease_timing_fits_restart_recovery_window() {
        assert!(EXPERIMENT_HEARTBEAT_INTERVAL_SECONDS * 2 < EXPERIMENT_LEASE_SECONDS as u64);
        assert!(EXPERIMENT_LEASE_SECONDS as u64 + STALE_EXPERIMENT_REAPER_INTERVAL_SECONDS < 10);
    }

    #[tokio::test]
    async fn concurrent_initializers_serialize_an_empty_database() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let database_name = format!("eln_init_{suffix}");
        let username = format!("rust_concurrent_{suffix}");
        let admin_options = PgConnectOptions::from_str(&database_url)
            .unwrap()
            .database("postgres");
        let admin_pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_with(admin_options)
            .await
            .unwrap();
        sqlx::query(&format!(r#"CREATE DATABASE "{database_name}""#))
            .execute(&admin_pool)
            .await
            .unwrap();
        let database_options = PgConnectOptions::from_str(&database_url)
            .unwrap()
            .database(&database_name);
        let database_pool = PgPoolOptions::new()
            .max_connections(8)
            .connect_with(database_options)
            .await
            .unwrap();
        let settings = Settings::from_map(&HashMap::from([
            (
                "DATABASE_URL".to_owned(),
                database_pool.connect_options().to_url_lossy().to_string(),
            ),
            ("BOOTSTRAP_ADMIN_USERNAME".to_owned(), username.clone()),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustConcurrent123!".to_owned(),
            ),
        ]))
        .unwrap();

        let results = tokio::join!(
            initialize_database(&database_pool, &settings),
            initialize_database(&database_pool, &settings),
            initialize_database(&database_pool, &settings),
            initialize_database(&database_pool, &settings),
        );

        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM users WHERE username = $1")
            .bind(username)
            .fetch_one(&database_pool)
            .await
            .unwrap();
        let index_state = rag_hnsw_index_state(&database_pool).await;
        let schema_version: i32 =
            sqlx::query_scalar("SELECT max(version) FROM public.rust_schema_versions")
                .fetch_one(&database_pool)
                .await
                .unwrap();
        database_pool.close().await;
        sqlx::query(&format!(r#"DROP DATABASE "{database_name}""#))
            .execute(&admin_pool)
            .await
            .unwrap();
        admin_pool.close().await;

        assert!(results.0.is_ok(), "first initializer: {:?}", results.0);
        assert!(results.1.is_ok(), "second initializer: {:?}", results.1);
        assert!(results.2.is_ok(), "third initializer: {:?}", results.2);
        assert!(results.3.is_ok(), "fourth initializer: {:?}", results.3);
        assert_eq!(count, 1);
        let (index_definition, index_valid, index_ready) =
            index_state.expect("fresh initialization must create the HNSW index");
        assert!(index_definition
            .replace("public.vector_cosine_ops", "vector_cosine_ops")
            .contains("USING hnsw (embedding vector_cosine_ops)"));
        assert!(index_valid);
        assert!(index_ready);
        assert_eq!(schema_version, 3);
    }

    #[tokio::test]
    async fn existing_database_is_upgraded_with_experiment_lease_columns() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let database_name = format!("eln_upgrade_{suffix}");
        let admin_options = PgConnectOptions::from_str(&database_url)
            .unwrap()
            .database("postgres");
        let admin_pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_with(admin_options)
            .await
            .unwrap();
        sqlx::query(&format!(r#"CREATE DATABASE "{database_name}""#))
            .execute(&admin_pool)
            .await
            .unwrap();
        let database_options = PgConnectOptions::from_str(&database_url)
            .unwrap()
            .database(&database_name);
        let database_pool = PgPoolOptions::new()
            .max_connections(2)
            .connect_with(database_options)
            .await
            .unwrap();
        let settings = Settings::from_map(&HashMap::from([
            (
                "DATABASE_URL".to_owned(),
                database_pool.connect_options().to_url_lossy().to_string(),
            ),
            (
                "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                format!("rust_upgrade_{suffix}"),
            ),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustUpgrade123!".to_owned(),
            ),
        ]))
        .unwrap();
        initialize_database(&database_pool, &settings)
            .await
            .unwrap();
        sqlx::raw_sql(
            r#"
            DROP INDEX public.ix_ai_experiment_runs_lease;
            ALTER TABLE public.ai_experiment_runs
                DROP COLUMN worker_id,
                DROP COLUMN heartbeat_at,
                DROP COLUMN lease_expires_at;
            DROP INDEX IF EXISTS public.ix_rag_chunks_embedding_hnsw;
            DELETE FROM public.rust_schema_versions WHERE version = 3
            "#,
        )
        .execute(&database_pool)
        .await
        .unwrap();

        let upgraded = initialize_database(&database_pool, &settings).await;
        let lease_columns: i64 = sqlx::query_scalar(
            r#"
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'ai_experiment_runs'
              AND column_name IN ('worker_id', 'heartbeat_at', 'lease_expires_at')
            "#,
        )
        .fetch_one(&database_pool)
        .await
        .unwrap();
        let version: i32 =
            sqlx::query_scalar("SELECT max(version) FROM public.rust_schema_versions")
                .fetch_one(&database_pool)
                .await
                .unwrap();
        let index_state = rag_hnsw_index_state(&database_pool).await;
        database_pool.close().await;
        sqlx::query(&format!(r#"DROP DATABASE "{database_name}""#))
            .execute(&admin_pool)
            .await
            .unwrap();
        admin_pool.close().await;

        assert!(upgraded.is_ok(), "existing database upgrade: {upgraded:?}");
        assert_eq!(lease_columns, 3);
        let (index_definition, index_valid, index_ready) =
            index_state.expect("v2 schema upgrade must create the HNSW index");
        assert!(index_definition
            .replace("public.vector_cosine_ops", "vector_cosine_ops")
            .contains("USING hnsw (embedding vector_cosine_ops)"));
        assert!(index_valid);
        assert!(index_ready);
        assert_eq!(version, 3);
    }

    #[tokio::test]
    async fn running_experiment_is_marked_interrupted_on_startup() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let username = format!("rust_recovery_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            ("BOOTSTRAP_ADMIN_USERNAME".to_owned(), username.clone()),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustRecovery123!".to_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let user_id: i32 = sqlx::query_scalar("SELECT id FROM users WHERE username = $1")
            .bind(&username)
            .fetch_one(&pool)
            .await
            .unwrap();
        let project_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO projects (
                name, description, is_sensitive, status, approval_enabled, owner_user_id
            )
            VALUES ($1, NULL, false, 'ACTIVE'::projectstatus, false, $2)
            RETURNING id
            "#,
        )
        .bind(format!("Recovery project {suffix}"))
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .unwrap();
        let run_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO ai_experiment_runs (
                project_id, created_by, name, status, questions_json, modes_json,
                config_snapshot_json, summary_json, total_cases, completed_cases,
                failed_cases, created_at, completed_at
            )
            VALUES ($1, $2, 'recovery verification', 'running', '[]'::json,
                    '[]'::json, '{}'::json, '{"execution_plan": [1]}'::json,
                    5, 1, 0, now() - interval '11 minutes', NULL)
            RETURNING id
            "#,
        )
        .bind(project_id)
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .unwrap();

        assert!(recover_interrupted_experiment_runs(&pool).await.unwrap() >= 1);
        let recovered: (String, i32, i32, serde_json::Value, Option<DateTime<Utc>>) =
            sqlx::query_as(
                r#"
                SELECT status, completed_cases, failed_cases, summary_json, completed_at
                FROM ai_experiment_runs WHERE id = $1
                "#,
            )
            .bind(run_id)
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(recovered.0, "interrupted");
        assert_eq!(recovered.1, 1);
        assert_eq!(recovered.2, 0);
        assert_eq!(recovered.3["unexecuted_cases"], 4);
        assert!(recovered.4.is_some());
    }

    #[tokio::test]
    async fn active_experiment_lease_survives_other_instance_startup() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let username = format!("rust_lease_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            ("BOOTSTRAP_ADMIN_USERNAME".to_owned(), username.clone()),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustLease123!".to_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let user_id: i32 = sqlx::query_scalar("SELECT id FROM users WHERE username = $1")
            .bind(&username)
            .fetch_one(&pool)
            .await
            .unwrap();
        let project_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO projects (
                name, description, is_sensitive, status, approval_enabled, owner_user_id
            )
            VALUES ($1, NULL, false, 'ACTIVE'::projectstatus, false, $2)
            RETURNING id
            "#,
        )
        .bind(format!("Lease project {suffix}"))
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .unwrap();
        let expired_project_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO projects (
                name, description, is_sensitive, status, approval_enabled, owner_user_id
            )
            VALUES ($1, NULL, false, 'ACTIVE'::projectstatus, false, $2)
            RETURNING id
            "#,
        )
        .bind(format!("Expired lease project {suffix}"))
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .unwrap();
        let active_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO ai_experiment_runs (
                project_id, created_by, name, status, questions_json, modes_json,
                config_snapshot_json, summary_json, total_cases, completed_cases,
                failed_cases, created_at, completed_at, worker_id, heartbeat_at,
                lease_expires_at
            )
            VALUES ($1, $2, 'active lease', 'running', '[]'::json, '[]'::json,
                    '{}'::json, '{}'::json, 1, 0, 0, now(), NULL, 'worker-a',
                    now(), now() + interval '5 minutes')
            RETURNING id
            "#,
        )
        .bind(project_id)
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .unwrap();
        let expired_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO ai_experiment_runs (
                project_id, created_by, name, status, questions_json, modes_json,
                config_snapshot_json, summary_json, total_cases, completed_cases,
                failed_cases, created_at, completed_at, worker_id, heartbeat_at,
                lease_expires_at
            )
            VALUES ($1, $2, 'expired lease', 'running', '[]'::json, '[]'::json,
                    '{}'::json, '{}'::json, 1, 0, 0, now(), NULL, 'worker-old',
                    now() - interval '2 minutes', now() - interval '1 minute')
            RETURNING id
            "#,
        )
        .bind(expired_project_id)
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .unwrap();

        let recovered = recover_interrupted_experiment_runs(&pool).await.unwrap();
        let statuses: Vec<(i32, String)> = sqlx::query_as(
            "SELECT id, status FROM ai_experiment_runs WHERE id IN ($1, $2) ORDER BY id",
        )
        .bind(active_id)
        .bind(expired_id)
        .fetch_all(&pool)
        .await
        .unwrap();

        assert!(recovered >= 1);
        assert_eq!(statuses[0], (active_id, "running".to_owned()));
        assert_eq!(statuses[1], (expired_id, "interrupted".to_owned()));
        sqlx::query(
            r#"
            UPDATE ai_experiment_runs
            SET status = 'completed', completed_at = now(), worker_id = NULL,
                heartbeat_at = NULL, lease_expires_at = NULL
            WHERE id = $1
            "#,
        )
        .bind(active_id)
        .execute(&pool)
        .await
        .unwrap();
    }

    #[tokio::test]
    async fn demo_seed_creates_the_existing_project_notes_and_files() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let storage = tempfile::tempdir().unwrap();
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                format!("rust_demo_{suffix}"),
            ),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustDemoSeed123!".to_owned(),
            ),
            ("SEED_DEMO_DATA".to_owned(), "true".to_owned()),
            (
                "STORAGE_ROOT".to_owned(),
                storage.path().to_string_lossy().into_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();

        initialize_database(&pool, &settings).await.unwrap();

        let project_id: i32 = sqlx::query_scalar(
            "SELECT id FROM projects WHERE name = '论文演示项目：KG-RAG 实验流程'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        let note_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM experiment_notes WHERE project_id = $1 AND status = 'APPROVED'::notestatus",
        )
        .bind(project_id)
        .fetch_one(&pool)
        .await
        .unwrap();
        let file_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM files WHERE project_id = $1 AND status = 'APPROVED'::filestatus",
        )
        .bind(project_id)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(note_count, 4);
        assert_eq!(file_count, 2);
    }
}
