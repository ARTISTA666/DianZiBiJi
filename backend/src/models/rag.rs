use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct RagDatasetRead {
    pub id: i32,
    pub project_id: i32,
    pub dify_dataset_id: String,
    pub dify_dataset_name: String,
    pub provider: String,
    pub embedding_model: String,
    pub generation_model: String,
    pub status: String,
    pub created_by: i32,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
pub struct RagCorpusSnapshotRead {
    pub dataset_id: Option<i32>,
    pub corpus_snapshot_hash: Option<String>,
    pub corpus_chunk_count: i64,
    pub rag_index_version: String,
    pub embedding_model: Option<String>,
    pub graph_snapshot_hash: Option<String>,
    pub graph_entity_count: i64,
    pub graph_relation_count: i64,
}

#[derive(Debug, Serialize)]
pub struct RagStatusRead {
    pub initialized: bool,
    pub dataset: Option<RagDatasetRead>,
    pub pending_sync_count: i64,
    pub failed_sync_count: i64,
    pub synced_count: i64,
    pub corpus_snapshot: RagCorpusSnapshotRead,
}

#[derive(Debug, Deserialize)]
pub struct RagQueryRequest {
    pub query: String,
    #[serde(default = "default_rag_mode")]
    pub mode: String,
    /// 可选的多轮对话历史（由客户端传入最近若干轮），用于拼入提示词。
    #[serde(default)]
    pub history: Option<Vec<RagHistoryEntry>>,
}

#[derive(Debug, Deserialize)]
pub struct RagRetrievalRequest {
    pub query: String,
    pub mode: String,
    pub expected_corpus_snapshot_hash: String,
    pub expected_graph_snapshot_hash: String,
}

/// 一轮历史对话：用户问题与系统回答。
#[derive(Clone, Debug, Deserialize)]
pub struct RagHistoryEntry {
    pub question: String,
    pub answer: String,
}

fn default_rag_mode() -> String {
    "auto".to_owned()
}

#[derive(Clone, Debug, Serialize)]
pub struct RagSourceRead {
    pub chunk_id: Option<i32>,
    pub file_id: Option<i32>,
    pub filename: Option<String>,
    pub dify_document_id: Option<String>,
    pub snippet: Option<String>,
    pub vector_score: Option<f64>,
    pub lexical_score: Option<f64>,
    pub retrieval_score: Option<f64>,
    pub content: Option<String>,
    pub content_sha256: Option<String>,
    pub file_hash: Option<String>,
    pub chunk_index: Option<i32>,
}

#[derive(Clone, Debug, Serialize)]
pub struct RagGraphContextRead {
    pub relation_id: i32,
    pub relation_type: String,
    pub relation_label: String,
    pub source_entity_id: i32,
    pub source_label: String,
    pub source_normalized_label: String,
    pub source_natural_key: String,
    pub source_entity_type: String,
    pub source_entity_type_label: String,
    pub target_entity_id: i32,
    pub target_label: String,
    pub target_normalized_label: String,
    pub target_natural_key: String,
    pub target_entity_type: String,
    pub target_entity_type_label: String,
    pub confidence: f64,
    pub retrieval_score: f64,
    pub relation_roles: Vec<String>,
    pub relation_properties: Value,
}

#[derive(Clone, Debug, Serialize)]
pub struct RagCitationAuditRead {
    pub passed: bool,
    pub citation_count: usize,
    pub invalid_citations: Vec<String>,
    pub has_evidence: bool,
    pub message: String,
    pub repair_attempted: bool,
}

#[derive(Debug, Serialize)]
pub struct RagQueryResponse {
    pub answer: String,
    pub conversation_id: Option<String>,
    pub sources: Vec<RagSourceRead>,
    pub graph_context: Vec<RagGraphContextRead>,
    pub rag_mode: String,
    pub query_log_id: Option<i32>,
    pub response_ms: Option<i32>,
    pub provider: String,
    pub model_name: Option<String>,
    pub fallback_reason: Option<String>,
    pub citation_audit: Option<RagCitationAuditRead>,
    pub evidence_status: String,
    pub retrieval_strategy: String,
    pub retrieval_trace_id: String,
}

#[derive(Debug, Serialize)]
pub struct RagRetrievalResponse {
    pub retrieval_only: bool,
    pub generation_invoked: bool,
    pub llm_query_rewrite_invoked: bool,
    pub citation_repair_invoked: bool,
    pub mode: String,
    pub sources: Vec<RagSourceRead>,
    pub graph_context: Vec<RagGraphContextRead>,
    pub effective_retrieval_config: Value,
    pub actual_corpus_snapshot_hash: String,
    pub actual_graph_snapshot_hash: String,
    pub used_corpus_snapshot_hash: String,
    pub used_graph_snapshot_hash: String,
    pub corpus_snapshot_hash: String,
    pub graph_snapshot_hash: String,
    pub corpus_chunk_count: i64,
    pub graph_entity_count: i64,
    pub graph_relation_count: i64,
}

#[derive(Debug, Deserialize)]
pub struct AIQueryEvaluationRequest {
    pub score: i32,
    pub is_accurate: bool,
    pub is_traceable: bool,
    pub comment: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct AIQueryFeedbackRequest {
    pub value: String,
    pub comment: Option<String>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct AIQueryEvaluationRead {
    pub id: i32,
    pub query_log_id: i32,
    pub evaluator_user_id: i32,
    pub score: i32,
    pub is_accurate: bool,
    pub is_traceable: bool,
    pub comment: Option<String>,
    pub review_protocol: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Default, Deserialize)]
pub struct BlindReviewQuery {
    pub batch_id: Option<String>,
    #[serde(default = "default_true")]
    pub pending_only: bool,
}

#[derive(Debug, Deserialize)]
pub struct BlindReviewBatchLockRequest {
    pub reviewer_user_ids: Vec<i32>,
    pub freeze_manifest_sha256: String,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Deserialize)]
pub struct AIExperimentRunRequest {
    pub name: String,
    pub questions: Vec<String>,
    #[serde(default = "default_experiment_modes")]
    pub modes: Vec<String>,
    #[serde(default = "default_one")]
    pub repetitions: i32,
    #[serde(default = "default_true")]
    pub randomize_order: bool,
    pub random_seed: Option<i32>,
    #[serde(default)]
    pub expected_corpus_snapshot_hash: Option<String>,
    #[serde(default)]
    pub expected_graph_snapshot_hash: Option<String>,
}

fn default_experiment_modes() -> Vec<String> {
    vec!["project_rag".to_owned(), "kg_enhanced_rag".to_owned()]
}

fn default_one() -> i32 {
    1
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct AIExperimentRunRead {
    pub id: i32,
    pub project_id: i32,
    pub created_by: i32,
    pub name: String,
    pub status: String,
    pub questions_json: Value,
    pub modes_json: Value,
    pub config_snapshot_json: Value,
    pub summary_json: Value,
    pub total_cases: i32,
    pub completed_cases: i32,
    pub failed_cases: i32,
    pub created_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
}
