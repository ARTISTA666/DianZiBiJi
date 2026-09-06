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
const RUST_SCHEMA_VERSION: i32 = 5;
// Compatibility marker only: it is not an index/chunk version or provenance.
const LEGACY_SCHEMA_RECOVERY_GUIDANCE: &str =
    "Apply the complete legacy Alembic history through 0013_rust_retrieval_identity with the previous migration image, or restore a compatible backup.";
const LEGACY_EXPERIMENT_STALE_GRACE_SECONDS: i32 = 600;
pub const EXPERIMENT_HEARTBEAT_INTERVAL_SECONDS: u64 = 5;
pub const EXPERIMENT_LEASE_SECONDS: i32 = 30;
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
        "kg_blueprint_nodes",
        &["id", "normalized_label", "priority"],
    ),
    ("kg_blueprint_edges", &["id", "relation_type", "priority"]),
    ("kg_blueprint_documents", &["id", "parse_mode"]),
    (
        "project_rag_datasets",
        &["id", "provider", "embedding_model", "generation_model"],
    ),
    (
        "rag_file_syncs",
        &["id", "chunk_count", "content_hash", "index_version"],
    ),
    (
        "rag_document_chunks",
        &["id", "embedding", "chunk_version", "index_version"],
    ),
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
    (
        "mcp_personal_access_tokens",
        &["id", "token_hash", "scopes_json", "revoked_at"],
    ),
    (
        "mcp_http_sessions",
        &["id", "user_id", "protocol_version", "expires_at"],
    ),
    (
        "agent_sessions",
        &["id", "project_id", "status", "usage_json", "active_turn"],
    ),
    (
        "agent_turns",
        &[
            "id",
            "session_id",
            "prompt_version",
            "profile",
            "status",
            "plan_hash",
            "lease_expires_at",
        ],
    ),
    (
        "agent_events",
        &["id", "session_id", "turn_id", "event_type"],
    ),
    (
        "agent_messages",
        &["id", "session_id", "role", "content_redacted"],
    ),
    ("agent_steps", &["id", "session_id", "tool_name", "status"]),
    (
        "agent_pending_actions",
        &["id", "tool_name", "arguments_hash", "expires_at", "status"],
    ),
    (
        "tool_execution_keys",
        &["user_id", "tool_name", "idempotency_key", "result_json"],
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
    // Align the pgvector embedding column with the configured embedding dimension.
    // The vector(n) type has a fixed dimension; the runtime inserts vectors of
    // settings.embedding_dimension. A mismatch (e.g. a legacy 512-dim schema with
    // a 1024-dim bge-m3 config) makes every chunk insert fail with a dimension
    // error, so the column and its HNSW index are rebuilt to match and all
    // previously synced chunks are marked stale: an embedding change invalidates
    // the whole index and requires an explicit rebuild anyway.
    let embedding_column_dim: Option<i32> = sqlx::query_scalar(
        r#"
        SELECT atttypmod
        FROM pg_attribute
        WHERE attrelid = 'public.rag_document_chunks'::regclass
          AND attname = 'embedding'
          AND NOT attisdropped
        "#,
    )
    .fetch_optional(&mut *transaction)
    .await?;
    let configured_dim = i32::try_from(settings.embedding_dimension)
        .map_err(|_| DatabaseError::Domain("EMBEDDING_DIMENSION does not fit i32".to_owned()))?;
    if embedding_column_dim != Some(configured_dim) {
        if embedding_column_dim.is_some() {
            sqlx::raw_sql(
                r#"
                -- 旧维度 chunk 全部失效：清空后重建列（非空表不能直接 ADD COLUMN ... NOT NULL）。
                DELETE FROM public.rag_document_chunks;
                DROP INDEX IF EXISTS ix_rag_chunks_embedding_hnsw;
                ALTER TABLE public.rag_document_chunks DROP COLUMN embedding;
                "#,
            )
            .execute(&mut *transaction)
            .await?;
        }
        // PostgreSQL 类型修饰符不接受绑定参数，必须内联常量；维度来自配置的整数。
        let add_embedding_column = format!(
            "ALTER TABLE public.rag_document_chunks ADD COLUMN embedding public.vector({configured_dim}) NOT NULL"
        );
        sqlx::raw_sql(&add_embedding_column)
            .execute(&mut *transaction)
            .await?;
        sqlx::query(
            "CREATE INDEX ix_rag_chunks_embedding_hnsw ON public.rag_document_chunks USING hnsw (embedding public.vector_cosine_ops)",
        )
        .execute(&mut *transaction)
        .await?;
        // 维度变更使既有 chunk 全部失效：标记 stale，等待显式重建。
        sqlx::query(
            r#"
            UPDATE public.rag_file_syncs SET sync_status = 'stale', updated_at = now()
            WHERE sync_status = 'synced'
            "#,
        )
        .execute(&mut *transaction)
        .await?;
        sqlx::query(
            r#"
            UPDATE public.files SET knowledge_sync_status = 'pending_sync',
                knowledge_sync_message = 'Embedding dimension changed; explicit rebuild required'
            WHERE knowledge_sync_status = 'synced'
            "#,
        )
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
            ON public.audit_logs (created_at DESC);

        CREATE TABLE IF NOT EXISTS public.mcp_personal_access_tokens (
            id uuid PRIMARY KEY,
            user_id integer NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            name varchar(120) NOT NULL,
            token_prefix varchar(24) NOT NULL,
            token_hash varchar(64) NOT NULL UNIQUE,
            scopes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            expires_at timestamp with time zone NOT NULL,
            revoked_at timestamp with time zone,
            last_used_at timestamp with time zone,
            created_at timestamp with time zone NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_mcp_pat_user ON public.mcp_personal_access_tokens (user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS public.mcp_http_sessions (
            id uuid PRIMARY KEY,
            user_id integer NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            protocol_version varchar(20) NOT NULL,
            expires_at timestamp with time zone NOT NULL,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            last_seen_at timestamp with time zone NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_mcp_http_sessions_user
            ON public.mcp_http_sessions (user_id, expires_at);

        CREATE TABLE IF NOT EXISTS public.agent_sessions (
            id uuid PRIMARY KEY,
            user_id integer NOT NULL REFERENCES public.users(id),
            project_id integer REFERENCES public.projects(id),
            status varchar(32) NOT NULL,
            provider varchar(80) NOT NULL,
            model_name varchar(160) NOT NULL,
            prompt_version varchar(120) NOT NULL,
            source_map_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            usage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            final_state_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_agent_sessions_user ON public.agent_sessions (user_id, updated_at DESC);
        ALTER TABLE public.agent_sessions
            ADD COLUMN IF NOT EXISTS active_turn uuid;

        CREATE TABLE IF NOT EXISTS public.agent_turns (
            id uuid PRIMARY KEY,
            session_id uuid NOT NULL REFERENCES public.agent_sessions(id) ON DELETE CASCADE,
            user_id integer NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            profile varchar(16) NOT NULL DEFAULT 'fast',
            prompt_version varchar(120) NOT NULL DEFAULT 'agent-orchestrator-v1',
            status varchar(40) NOT NULL,
            input_redacted text NOT NULL,
            plan_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            plan_hash varchar(64),
            budget_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            usage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            worker_id varchar(80),
            heartbeat_at timestamp with time zone,
            lease_expires_at timestamp with time zone,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            completed_at timestamp with time zone,
            UNIQUE (session_id, id)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_turns_session ON public.agent_turns (session_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS ix_agent_turns_lease ON public.agent_turns (status, lease_expires_at);
        ALTER TABLE public.agent_turns
            ADD COLUMN IF NOT EXISTS prompt_version varchar(120) NOT NULL DEFAULT 'agent-orchestrator-v1';
        CREATE TABLE IF NOT EXISTS public.agent_events (
            id bigserial PRIMARY KEY,
            session_id uuid NOT NULL REFERENCES public.agent_sessions(id) ON DELETE CASCADE,
            turn_id uuid REFERENCES public.agent_turns(id) ON DELETE CASCADE,
            event_type varchar(48) NOT NULL,
            payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamp with time zone NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_agent_events_session ON public.agent_events (session_id, id);

        CREATE TABLE IF NOT EXISTS public.agent_messages (
            id bigserial PRIMARY KEY,
            session_id uuid NOT NULL REFERENCES public.agent_sessions(id) ON DELETE CASCADE,
            role varchar(24) NOT NULL,
            content_redacted text NOT NULL,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamp with time zone NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_agent_messages_session ON public.agent_messages (session_id, id);

        CREATE TABLE IF NOT EXISTS public.agent_steps (
            id bigserial PRIMARY KEY,
            session_id uuid NOT NULL REFERENCES public.agent_sessions(id) ON DELETE CASCADE,
            turn_id uuid NOT NULL,
            sequence_no integer NOT NULL,
            tool_name varchar(120) NOT NULL,
            risk varchar(24) NOT NULL,
            arguments_summary text NOT NULL,
            arguments_hash varchar(64) NOT NULL,
            result_redacted_json jsonb,
            idempotency_key varchar(120),
            status varchar(32) NOT NULL,
            started_at timestamp with time zone NOT NULL DEFAULT now(),
            completed_at timestamp with time zone,
            UNIQUE (session_id, turn_id, sequence_no)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_step_idempotency
            ON public.agent_steps (session_id, tool_name, idempotency_key)
            WHERE idempotency_key IS NOT NULL;

        CREATE TABLE IF NOT EXISTS public.agent_pending_actions (
            id uuid PRIMARY KEY,
            session_id uuid REFERENCES public.agent_sessions(id) ON DELETE CASCADE,
            user_id integer NOT NULL REFERENCES public.users(id),
            project_id integer REFERENCES public.projects(id),
            tool_name varchar(120) NOT NULL,
            arguments_json jsonb NOT NULL,
            arguments_summary text NOT NULL,
            arguments_hash varchar(64) NOT NULL,
            idempotency_key varchar(120) NOT NULL,
            status varchar(32) NOT NULL DEFAULT 'pending',
            expires_at timestamp with time zone NOT NULL,
            decided_at timestamp with time zone,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            UNIQUE (user_id, tool_name, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS ix_agent_pending_active
            ON public.agent_pending_actions (user_id, status, expires_at);

        CREATE TABLE IF NOT EXISTS public.tool_execution_keys (
            user_id integer NOT NULL REFERENCES public.users(id),
            tool_name varchar(120) NOT NULL,
            idempotency_key varchar(120) NOT NULL,
            arguments_hash varchar(64) NOT NULL,
            result_json jsonb NOT NULL,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, tool_name, idempotency_key)
        );

        ALTER TABLE public.rag_file_syncs
            ADD COLUMN IF NOT EXISTS index_version varchar(80) NOT NULL DEFAULT 'legacy-unknown';
        ALTER TABLE public.rag_document_chunks
            ADD COLUMN IF NOT EXISTS chunk_version varchar(80) NOT NULL DEFAULT 'legacy-unknown',
            ADD COLUMN IF NOT EXISTS index_version varchar(80) NOT NULL DEFAULT 'legacy-unknown';
        ALTER TABLE public.rag_file_syncs
            ALTER COLUMN index_version SET DEFAULT 'legacy-unknown';
        ALTER TABLE public.rag_document_chunks
            ALTER COLUMN chunk_version SET DEFAULT 'legacy-unknown',
            ALTER COLUMN index_version SET DEFAULT 'legacy-unknown';
        -- legacy-unknown is a compatibility marker only, never model/corpus provenance.
        UPDATE public.rag_file_syncs
        SET index_version='legacy-unknown'
        WHERE index_version='legacy-v1';
        UPDATE public.rag_document_chunks
        SET chunk_version='legacy-unknown'
        WHERE chunk_version='legacy-v1';
        UPDATE public.rag_document_chunks
        SET index_version='legacy-unknown'
        WHERE index_version='legacy-v1';
        CREATE INDEX IF NOT EXISTS ix_rag_chunks_project_version
            ON public.rag_document_chunks (project_id, index_version, id)
        "#,
    )
    .execute(&mut *transaction)
    .await?;
    sqlx::query(
        r#"
        UPDATE public.rag_file_syncs
        SET sync_status='stale', sync_message='Index version changed; explicit rebuild required', updated_at=now()
        WHERE sync_status='synced' AND index_version <> $1
        "#,
    )
    .bind(&settings.rag_index_version)
    .execute(&mut *transaction)
    .await?;
    sqlx::query(
        r#"
        UPDATE public.files AS f
        SET knowledge_sync_status='pending_sync',
            knowledge_sync_message='Index version changed; explicit rebuild required'
        WHERE f.status='APPROVED'::filestatus
          AND f.file_category='KNOWLEDGE_DOCUMENT'::filecategory
          AND EXISTS (
              SELECT 1 FROM public.rag_file_syncs AS r
              WHERE r.file_id=f.id AND r.sync_status='stale' AND r.index_version <> $1
          )
        "#,
    )
    .bind(&settings.rag_index_version)
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
    // Mirrors legacy Alembic migration 0015: knowledge blueprint tables
    // (创新点一：动态知识蓝图——计划态节点/边、来源优先级与解析留痕).
    sqlx::raw_sql(
        r#"
        CREATE TABLE IF NOT EXISTS public.kg_blueprint_nodes (
            id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            project_id integer NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
            entity_type varchar(40) NOT NULL,
            label varchar(200) NOT NULL,
            normalized_label varchar(240) NOT NULL,
            description text NOT NULL DEFAULT '',
            status varchar(16) NOT NULL DEFAULT 'planned',
            source_kind varchar(24) NOT NULL DEFAULT 'plan_document',
            source_label varchar(200) NOT NULL DEFAULT '',
            priority integer NOT NULL DEFAULT 50,
            created_by integer NOT NULL REFERENCES public.users(id),
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_kg_blueprint_nodes_project
            ON public.kg_blueprint_nodes (project_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_blueprint_node_label
            ON public.kg_blueprint_nodes (project_id, entity_type, normalized_label)
            WHERE status <> 'retired';

        CREATE TABLE IF NOT EXISTS public.kg_blueprint_edges (
            id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            project_id integer NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
            source_node_id integer NOT NULL REFERENCES public.kg_blueprint_nodes(id) ON DELETE CASCADE,
            target_node_id integer NOT NULL REFERENCES public.kg_blueprint_nodes(id) ON DELETE CASCADE,
            relation_type varchar(40) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'planned',
            source_kind varchar(24) NOT NULL DEFAULT 'plan_document',
            priority integer NOT NULL DEFAULT 50,
            created_at timestamp with time zone NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_kg_blueprint_edges_project
            ON public.kg_blueprint_edges (project_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_blueprint_edge
            ON public.kg_blueprint_edges (project_id, source_node_id, target_node_id, relation_type)
            WHERE status <> 'retired';

        CREATE TABLE IF NOT EXISTS public.kg_blueprint_documents (
            id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            project_id integer NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
            title varchar(200) NOT NULL,
            source_kind varchar(24) NOT NULL,
            parse_mode varchar(16) NOT NULL,
            node_count integer NOT NULL DEFAULT 0,
            edge_count integer NOT NULL DEFAULT 0,
            message text NOT NULL DEFAULT '',
            created_by integer NOT NULL REFERENCES public.users(id),
            created_at timestamp with time zone NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_kg_blueprint_documents_project
            ON public.kg_blueprint_documents (project_id);
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
        "INSERT INTO public.rust_schema_versions (version) VALUES ($1) ON CONFLICT DO NOTHING",
    )
    .bind(RUST_SCHEMA_VERSION)
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

fn runtime_index_gaps(indexes: &[String]) -> Vec<String> {
    let available = indexes.iter().map(String::as_str).collect::<HashSet<_>>();
    let required = [
        (
            "index.kg_entities_project_natural_key",
            [
                "uq_kg_entity_project_natural_key",
                "ux_kg_entities_project_natural_key",
            ],
        ),
        (
            "index.kg_entities_project_normalized_label",
            [
                "ix_kg_entities_normalized_label",
                "ix_kg_entities_project_normalized_label",
            ],
        ),
    ];
    required
        .into_iter()
        .filter_map(|(label, aliases)| {
            (!aliases.iter().any(|alias| available.contains(alias))).then_some(label.to_owned())
        })
        .collect()
}

fn runtime_schema_error(gaps: &[String]) -> String {
    let shown = gaps.iter().take(16).cloned().collect::<Vec<_>>().join(", ");
    let remainder = gaps.len().saturating_sub(16);
    let suffix = if remainder == 0 {
        String::new()
    } else {
        format!(" (and {remainder} more)")
    };
    format!(
        "Existing database schema is incompatible with this Rust backend; missing {shown}{suffix}. {LEGACY_SCHEMA_RECOVERY_GUIDANCE} Refusing to stamp Rust schema version {RUST_SCHEMA_VERSION}."
    )
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
    let indexes: Vec<String> =
        sqlx::query_scalar("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            .fetch_all(&mut **transaction)
            .await?;
    gaps.extend(runtime_index_gaps(&indexes));
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
    Err(DatabaseError::Domain(runtime_schema_error(&gaps)))
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
        recovered_experiment_summary, runtime_index_gaps, runtime_schema_error,
        runtime_schema_gaps, seed_templates, EXPERIMENT_HEARTBEAT_INTERVAL_SECONDS,
        EXPERIMENT_LEASE_SECONDS, INITIAL_SCHEMA, LEGACY_SCHEMA_RECOVERY_GUIDANCE,
        RUST_SCHEMA_VERSION, STALE_EXPERIMENT_REAPER_INTERVAL_SECONDS,
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
            "mcp_personal_access_tokens",
            "mcp_http_sessions",
            "agent_sessions",
            "agent_turns",
            "agent_events",
            "agent_messages",
            "agent_steps",
            "agent_pending_actions",
            "tool_execution_keys",
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
        for identity_column in ["chunk_version", "index_version"] {
            assert!(
                INITIAL_SCHEMA.contains(&format!("{identity_column} character varying(80)")),
                "missing Rust retrieval identity column {identity_column}"
            );
        }
        assert!(INITIAL_SCHEMA.contains("ix_rag_chunks_project_version"));
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
    fn test_runtime_schema_error_guides_legacy_databases_to_current_history() {
        assert!(LEGACY_SCHEMA_RECOVERY_GUIDANCE.contains("0013"));
        assert!(LEGACY_SCHEMA_RECOVERY_GUIDANCE.contains("compatible backup"));
        let message = runtime_schema_error(&["index.example".to_owned()]);
        assert!(message.contains(&format!("version {RUST_SCHEMA_VERSION}")));
    }

    #[test]
    fn test_runtime_index_signature_requires_kg_natural_key_and_label_indexes() {
        let gaps = runtime_index_gaps(&["uq_ai_experiment_runs_one_active_per_project".to_owned()]);

        assert!(gaps.contains(&"index.kg_entities_project_natural_key".to_owned()));
        assert!(gaps.contains(&"index.kg_entities_project_normalized_label".to_owned()));
        assert!(!gaps.contains(&"index.uq_ai_experiment_runs_one_active_per_project".to_owned()));
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
        // 编译期不变量：心跳必须在租约内至少完成两次续租，避免单次心跳延迟触发清扫器误判。
        const _: () =
            assert!(EXPERIMENT_HEARTBEAT_INTERVAL_SECONDS * 2 < EXPERIMENT_LEASE_SECONDS as u64);
        // 租约不能过长：worker 崩溃后，清扫器应在可接受的窗口内恢复运行。
        const _: () = assert!(EXPERIMENT_LEASE_SECONDS <= 120);
        const _: () = assert!(STALE_EXPERIMENT_REAPER_INTERVAL_SECONDS <= 10);
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
        let identity_columns: Vec<(String, String, String, Option<String>)> = sqlx::query_as(
            r#"
            SELECT table_name, column_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND (
                  (table_name = 'rag_file_syncs' AND column_name = 'index_version')
                  OR (table_name = 'rag_document_chunks' AND column_name IN ('chunk_version', 'index_version'))
              )
            ORDER BY table_name, column_name
            "#,
        )
        .fetch_all(&database_pool)
        .await
        .unwrap();
        let schema_version: i32 =
            sqlx::query_scalar("SELECT max(version) FROM public.rust_schema_versions")
                .fetch_one(&database_pool)
                .await
                .unwrap();
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
        assert_eq!(schema_version, RUST_SCHEMA_VERSION);
        assert_eq!(identity_columns.len(), 3);
        assert!(identity_columns
            .iter()
            .all(|(_, _, nullable, default)| nullable == "NO"
                && default
                    .as_deref()
                    .is_some_and(|value| value.contains("legacy-unknown"))));
        let version_index_definition: String = sqlx::query_scalar(
            "SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indexrelid = 'ix_rag_chunks_project_version'::regclass",
        )
        .fetch_one(&database_pool)
        .await
        .unwrap();
        assert!(version_index_definition.ends_with("(project_id, index_version, id)"));
        database_pool.close().await;
        sqlx::query(&format!(r#"DROP DATABASE "{database_name}""#))
            .execute(&admin_pool)
            .await
            .unwrap();
        admin_pool.close().await;
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
            ALTER TABLE public.rag_file_syncs
                ALTER COLUMN index_version SET DEFAULT 'legacy-v1';
            ALTER TABLE public.rag_document_chunks
                ALTER COLUMN chunk_version SET DEFAULT 'legacy-v1',
                ALTER COLUMN index_version SET DEFAULT 'legacy-v1';
            "#,
        )
        .execute(&database_pool)
        .await
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
            DROP INDEX IF EXISTS public.ix_rag_chunks_project_version;
            ALTER TABLE public.rag_file_syncs
                DROP COLUMN index_version;
            ALTER TABLE public.rag_document_chunks
                DROP COLUMN chunk_version,
                DROP COLUMN index_version;
            DROP INDEX IF EXISTS public.ix_rag_chunks_embedding_hnsw;
            DELETE FROM public.rust_schema_versions WHERE version = 4
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
            index_state.expect("Rust schema upgrade must create the HNSW index");
        assert!(index_definition
            .replace("public.vector_cosine_ops", "vector_cosine_ops")
            .contains("USING hnsw (embedding vector_cosine_ops)"));
        assert!(index_valid);
        assert!(index_ready);
        assert_eq!(version, RUST_SCHEMA_VERSION);
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
    async fn embedding_column_dimension_aligns_with_runtime_config_on_existing_database() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let database_name = format!("eln_dim_{suffix}");
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
        let make_settings = |dim: usize| {
            let mut map = HashMap::from([
                (
                    "DATABASE_URL".to_owned(),
                    database_pool.connect_options().to_url_lossy().to_string(),
                ),
                (
                    "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                    format!("rust_dim_{suffix}"),
                ),
                (
                    "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                    "RustDim123!".to_owned(),
                ),
                ("EMBEDDING_DIMENSION".to_owned(), dim.to_string()),
            ]);
            // 1024 维只对 openai_compatible + BAAI/bge-m3 配置合法；512 维用默认 hash 后端。
            if dim == 1024 {
                map.insert(
                    "EMBEDDING_BACKEND".to_owned(),
                    "openai_compatible".to_owned(),
                );
                map.insert("EMBEDDING_MODEL".to_owned(), "BAAI/bge-m3".to_owned());
                map.insert(
                    "EMBEDDING_API_URL".to_owned(),
                    "http://localhost:11434/v1/embeddings".to_owned(),
                );
            }
            Settings::from_map(&map).unwrap()
        };
        // fresh init with the configured dimension (1024)
        initialize_database(&database_pool, &make_settings(1024))
            .await
            .unwrap();
        // simulate the legacy 512-dim schema
        sqlx::raw_sql(
            r#"
            ALTER TABLE public.rag_document_chunks
                ALTER COLUMN embedding TYPE public.vector(512)
            "#,
        )
        .execute(&database_pool)
        .await
        .unwrap();
        // re-running initialize must realign the column to the configured dimension
        initialize_database(&database_pool, &make_settings(1024))
            .await
            .unwrap();
        let dim: i32 = sqlx::query_scalar(
            r#"
            SELECT atttypmod FROM pg_attribute
            WHERE attrelid = 'public.rag_document_chunks'::regclass
              AND attname = 'embedding' AND NOT attisdropped
            "#,
        )
        .fetch_one(&database_pool)
        .await
        .unwrap();
        assert_eq!(dim, 1024);
        let index_exists: bool = sqlx::query_scalar(
            r#"
            SELECT EXISTS(
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'rag_document_chunks'
                  AND indexname = 'ix_rag_chunks_embedding_hnsw'
            )
            "#,
        )
        .fetch_one(&database_pool)
        .await
        .unwrap();
        assert!(index_exists);
        // 512-dim settings must also be honored (dev hash backend)
        initialize_database(&database_pool, &make_settings(512))
            .await
            .unwrap();
        let dim512: i32 = sqlx::query_scalar(
            r#"
            SELECT atttypmod FROM pg_attribute
            WHERE attrelid = 'public.rag_document_chunks'::regclass
              AND attname = 'embedding' AND NOT attisdropped
            "#,
        )
        .fetch_one(&database_pool)
        .await
        .unwrap();
        assert_eq!(dim512, 512);
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
