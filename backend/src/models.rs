use chrono::{DateTime, NaiveDate, Utc};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::OnceLock;

#[derive(Clone, Debug, sqlx::FromRow)]
pub struct UserRecord {
    pub id: i32,
    pub username: String,
    pub password_hash: String,
    pub display_name: String,
    pub email: Option<String>,
    pub role: String,
    pub status: String,
    pub auth_version: i32,
}

#[derive(Debug, Serialize)]
pub struct CurrentUserResponse {
    pub id: i32,
    pub username: String,
    pub display_name: String,
    pub role: String,
}

#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub username: String,
    pub password: String,
}

#[derive(Debug, Serialize)]
pub struct TokenResponse {
    pub access_token: String,
    pub token_type: &'static str,
}

#[derive(Debug, Deserialize)]
pub struct UserCreate {
    pub username: String,
    pub password: String,
    pub display_name: String,
    pub email: Option<String>,
    #[serde(default = "default_member_role")]
    pub role: String,
}

fn default_member_role() -> String {
    "member".to_owned()
}

#[derive(Debug, Default, Deserialize)]
pub struct UserUpdate {
    pub display_name: Option<String>,
    pub email: Option<String>,
    pub role: Option<String>,
    pub status: Option<String>,
    pub password: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UserPasswordChange {
    pub current_password: String,
    pub new_password: String,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct UserRead {
    pub id: i32,
    pub username: String,
    pub display_name: String,
    pub email: Option<String>,
    pub role: String,
    pub status: String,
}

pub fn validate_role(value: &str) -> Result<(), &'static str> {
    if matches!(
        value,
        "super_admin" | "pi" | "group_leader" | "project_owner" | "reviewer" | "member"
    ) {
        Ok(())
    } else {
        Err("Unsupported user role")
    }
}

pub fn validate_user_status(value: &str) -> Result<(), &'static str> {
    if matches!(value, "active" | "disabled") {
        Ok(())
    } else {
        Err("Unsupported user status")
    }
}

#[derive(Debug, Deserialize)]
pub struct ProjectCreate {
    pub name: String,
    pub description: Option<String>,
    #[serde(default)]
    pub is_sensitive: bool,
    #[serde(default = "default_true")]
    pub approval_enabled: bool,
    pub owner_user_id: Option<i32>,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Default, Deserialize)]
pub struct ProjectUpdate {
    pub name: Option<String>,
    pub description: Option<String>,
    pub is_sensitive: Option<bool>,
    pub status: Option<String>,
    pub approval_enabled: Option<bool>,
    pub owner_user_id: Option<i32>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct ProjectRead {
    pub id: i32,
    pub name: String,
    pub description: Option<String>,
    pub is_sensitive: bool,
    pub status: String,
    pub approval_enabled: bool,
    pub owner_user_id: Option<i32>,
}

#[derive(Debug, Serialize)]
pub struct ProjectListResponse {
    pub items: Vec<ProjectRead>,
    pub total: i64,
    pub skip: i64,
    pub limit: i64,
}

#[derive(Debug, Serialize)]
pub struct Paginated<T> {
    pub items: Vec<T>,
    pub total: i64,
    pub skip: i64,
    pub limit: i64,
}

#[derive(Debug, Default, Deserialize)]
pub struct PageQuery {
    pub skip: Option<i64>,
    pub limit: Option<i64>,
}

impl PageQuery {
    pub fn bounds(&self) -> (i64, i64) {
        page_bounds(self.skip, self.limit)
    }
}

pub fn page_bounds(skip: Option<i64>, limit: Option<i64>) -> (i64, i64) {
    (skip.unwrap_or(0).max(0), limit.unwrap_or(50).clamp(1, 200))
}

#[derive(Debug, Default, Deserialize)]
pub struct NoteListQuery {
    pub skip: Option<i64>,
    pub limit: Option<i64>,
    pub status: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ProjectListQuery {
    #[serde(default)]
    pub skip: i64,
    #[serde(default = "default_project_limit")]
    pub limit: i64,
}

fn default_project_limit() -> i64 {
    20
}

#[derive(Debug, Deserialize)]
pub struct ProjectMemberCreate {
    pub user_id: i32,
    #[serde(default = "default_project_member_role")]
    pub project_role: String,
    #[serde(default = "default_true")]
    pub can_read: bool,
    #[serde(default = "default_true")]
    pub can_write: bool,
    #[serde(default)]
    pub can_review: bool,
    #[serde(default)]
    pub can_evaluate: bool,
    #[serde(default)]
    pub can_manage: bool,
}

fn default_project_member_role() -> String {
    "member".to_owned()
}

#[derive(Debug, Default, Deserialize)]
pub struct ProjectMemberUpdate {
    pub project_role: Option<String>,
    pub can_read: Option<bool>,
    pub can_write: Option<bool>,
    pub can_review: Option<bool>,
    pub can_evaluate: Option<bool>,
    pub can_manage: Option<bool>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct ProjectMemberRead {
    pub id: i32,
    pub project_id: i32,
    pub user_id: i32,
    pub project_role: String,
    pub can_read: bool,
    pub can_write: bool,
    pub can_review: bool,
    pub can_evaluate: bool,
    pub can_manage: bool,
    pub is_independent_reviewer: bool,
}

#[derive(Debug, Deserialize)]
pub struct ProjectReviewerCreate {
    pub user_id: i32,
    #[serde(default = "default_review_scope")]
    pub review_scope: String,
}

fn default_review_scope() -> String {
    "all".to_owned()
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct ProjectReviewerRead {
    pub id: i32,
    pub project_id: i32,
    pub user_id: i32,
    pub review_scope: String,
}

pub fn validate_project_role(value: &str) -> Result<(), &'static str> {
    if matches!(value, "owner" | "reviewer" | "member" | "viewer") {
        Ok(())
    } else {
        Err("Unsupported project role")
    }
}

pub fn validate_project_status(value: &str) -> Result<(), &'static str> {
    if matches!(value, "active" | "archived") {
        Ok(())
    } else {
        Err("Unsupported project status")
    }
}

#[derive(Debug, Deserialize)]
pub struct GroupCreate {
    pub name: String,
    pub description: Option<String>,
    pub leader_user_id: Option<i32>,
}

#[derive(Debug, Default, Deserialize)]
pub struct GroupUpdate {
    pub name: Option<String>,
    pub description: Option<String>,
    pub leader_user_id: Option<i32>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct GroupRead {
    pub id: i32,
    pub name: String,
    pub description: Option<String>,
    pub leader_user_id: Option<i32>,
}

#[derive(Debug, Deserialize)]
pub struct GroupMemberCreate {
    pub user_id: i32,
    #[serde(default = "default_group_role")]
    pub group_role: String,
}

fn default_group_role() -> String {
    "member".to_owned()
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct GroupMemberRead {
    pub id: i32,
    pub group_id: i32,
    pub user_id: i32,
    pub group_role: String,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct TemplateRead {
    pub id: i32,
    pub name: String,
    pub experiment_type: String,
    pub schema_json: Value,
    pub default_content_json: Value,
    pub is_active: bool,
}

#[derive(Debug, Default, Deserialize)]
pub struct AuditQuery {
    pub actor_user_id: Option<i32>,
    pub project_id: Option<i32>,
    pub action: Option<String>,
    pub date_from: Option<DateTime<Utc>>,
    pub date_to: Option<DateTime<Utc>>,
    pub skip: Option<i64>,
    pub limit: Option<i64>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct AuditLogRead {
    pub id: i32,
    pub actor_user_id: Option<i32>,
    pub project_id: Option<i32>,
    pub action: String,
    pub target_type: Option<String>,
    pub target_id: Option<i32>,
    pub detail_json: Value,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
pub struct NoteCreate {
    pub title: String,
    pub experiment_type: String,
    pub experiment_date: Option<NaiveDate>,
    pub template_id: Option<i32>,
    #[serde(default = "empty_json_object")]
    pub fixed_fields_json: Value,
    #[serde(default = "empty_json_object")]
    pub content_json: Value,
    /// 自由文本正文。content_json 尚无 "text" 键时会归一写入 content_json["text"]。
    #[serde(default)]
    pub content_text: Option<String>,
}

fn empty_json_object() -> Value {
    serde_json::json!({})
}

#[derive(Debug, Default, Deserialize)]
pub struct NoteUpdate {
    pub title: Option<String>,
    pub experiment_type: Option<String>,
    pub experiment_date: Option<NaiveDate>,
    pub fixed_fields_json: Option<Value>,
    pub content_json: Option<Value>,
    /// 自由文本正文。content_json 尚无 "text" 键时会归一写入 content_json["text"]。
    #[serde(default)]
    pub content_text: Option<String>,
    pub change_summary: Option<String>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct NoteRead {
    pub id: i32,
    pub project_id: i32,
    pub template_id: Option<i32>,
    pub title: String,
    pub experiment_type: String,
    pub experiment_date: Option<NaiveDate>,
    pub owner_user_id: i32,
    pub status: String,
    pub current_version_id: Option<i32>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct NoteVersionRead {
    pub id: i32,
    pub note_id: i32,
    pub version_number: i32,
    pub fixed_fields_json: Value,
    pub content_json: Value,
    pub created_by: i32,
    pub change_summary: Option<String>,
    pub is_locked: bool,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Default, Deserialize)]
pub struct ApprovalRequest {
    pub comment: Option<String>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct NoteApprovalRead {
    pub id: i32,
    pub note_id: i32,
    pub version_id: i32,
    pub reviewer_user_id: i32,
    pub action: String,
    pub comment: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Default, Deserialize)]
pub struct SearchIndexQuery {
    pub project_id: Option<i32>,
}

#[derive(Debug, Deserialize)]
pub struct SearchRequest {
    pub query: String,
    pub project_id: Option<i32>,
}

#[derive(Debug, Serialize)]
pub struct SearchResult {
    pub document_id: i32,
    pub note_id: i32,
    pub project_id: i32,
    pub title: String,
    pub snippet: String,
    pub source_ids: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct SearchStatus {
    pub total_documents: i64,
    pub project_documents: usize,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct KnowledgeEntityRead {
    pub id: i32,
    pub project_id: i32,
    pub entity_type: String,
    pub label: String,
    pub normalized_label: String,
    pub natural_key: String,
    pub source_type: Option<String>,
    pub source_id: Option<i32>,
    pub properties: Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct KnowledgeRelationRead {
    pub id: i32,
    pub project_id: i32,
    pub source_entity_id: i32,
    pub target_entity_id: i32,
    pub relation_type: String,
    pub source_type: Option<String>,
    pub source_id: Option<i32>,
    pub confidence: f64,
    pub properties: Value,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
pub struct KnowledgeGraphRead {
    pub project_id: i32,
    pub entities: Vec<KnowledgeEntityRead>,
    pub relations: Vec<KnowledgeRelationRead>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct KnowledgeExtractionRunRead {
    pub id: i32,
    pub project_id: i32,
    pub note_id: i32,
    pub triggered_by: i32,
    pub status: String,
    pub extracted_entities: i32,
    pub extracted_relations: i32,
    pub message: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
pub struct KnowledgeExtractionRequest {
    #[serde(default = "default_true")]
    pub rebuild: bool,
}

#[derive(Debug, Deserialize)]
pub struct FileUploadQuery {
    #[serde(default = "default_file_category")]
    pub file_category: String,
    pub note_id: Option<i32>,
}

fn default_file_category() -> String {
    "knowledge_document".to_owned()
}

#[derive(Debug, Default, Deserialize)]
pub struct FileUpdate {
    pub original_filename: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct FileReviewRequest {
    pub action: String,
    pub comment: Option<String>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct FileRead {
    pub id: i32,
    pub project_id: i32,
    pub note_id: Option<i32>,
    pub uploaded_by: i32,
    pub file_category: String,
    pub original_filename: String,
    pub mime_type: Option<String>,
    pub file_size: i64,
    pub file_hash: String,
    pub status: String,
    pub knowledge_sync_status: String,
    pub knowledge_synced_at: Option<DateTime<Utc>>,
    pub knowledge_sync_message: Option<String>,
    pub created_at: DateTime<Utc>,
}

impl Default for KnowledgeExtractionRequest {
    fn default() -> Self {
        Self { rebuild: true }
    }
}

#[derive(Debug, Deserialize)]
pub struct OcrJobRequest {
    pub file_id: i32,
}

#[derive(Debug, Deserialize)]
pub struct OcrCorrectionRequest {
    pub corrected_text: String,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct OcrJobResult {
    #[sqlx(rename = "id")]
    pub ocr_result_id: i32,
    pub file_id: i32,
    #[sqlx(rename = "corrected_text")]
    pub extracted_text: String,
    pub raw_text: String,
    #[sqlx(skip)]
    pub source_ids: Vec<String>,
    pub character_count: i32,
    pub truncated: bool,
    pub extraction_method: String,
    pub review_status: String,
    pub created_by: i32,
    pub reviewed_by: Option<i32>,
    pub created_at: DateTime<Utc>,
    pub reviewed_at: Option<DateTime<Utc>>,
}

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
pub struct RagStatusRead {
    pub initialized: bool,
    pub dataset: Option<RagDatasetRead>,
    pub pending_sync_count: i64,
    pub failed_sync_count: i64,
    pub synced_count: i64,
}

#[derive(Debug, Deserialize)]
pub struct RagQueryRequest {
    pub query: String,
    #[serde(default = "default_rag_mode")]
    pub mode: String,
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
}

#[derive(Clone, Debug, Serialize)]
pub struct RagGraphContextRead {
    pub relation_id: i32,
    pub relation_type: String,
    pub relation_label: String,
    pub source_entity_id: i32,
    pub source_label: String,
    pub source_entity_type: String,
    pub source_entity_type_label: String,
    pub target_entity_id: i32,
    pub target_label: String,
    pub target_entity_type: String,
    pub target_entity_type_label: String,
    pub confidence: f64,
    pub retrieval_score: f64,
    pub relation_roles: Vec<String>,
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
}

#[derive(Debug, Deserialize)]
pub struct AIQueryEvaluationRequest {
    pub score: i32,
    pub is_accurate: bool,
    pub is_traceable: bool,
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

#[derive(Debug, Deserialize)]
pub struct AgentGenerateRequest {
    pub project_id: i32,
    #[serde(default = "default_agent_task_type")]
    pub task_type: String,
    pub date_from: Option<NaiveDate>,
    pub date_to: Option<NaiveDate>,
}

fn default_agent_task_type() -> String {
    "experiment_summary".to_owned()
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct AgentGenerationRunRead {
    pub id: i32,
    pub project_id: i32,
    pub user_id: i32,
    pub task_type: String,
    pub input_params_json: Value,
    pub title: String,
    pub body: String,
    pub source_note_ids_json: Value,
    pub source_file_ids_json: Value,
    pub source_graph_relation_ids_json: Value,
    pub provider: String,
    pub model_name: Option<String>,
    pub prompt_version: String,
    pub usage_json: Value,
    pub status: String,
    pub response_ms: i32,
    pub message: Option<String>,
    pub created_at: DateTime<Utc>,
}

pub fn validate_username(value: &str) -> Result<(), &'static str> {
    static USERNAME: OnceLock<Regex> = OnceLock::new();
    let length = value.chars().count();
    if !(3..=64).contains(&length) {
        return Err("Username must contain between 3 and 64 characters");
    }
    if !USERNAME
        .get_or_init(|| Regex::new(r"^[A-Za-z0-9_.-]+$").unwrap())
        .is_match(value)
    {
        return Err("Username contains unsupported characters");
    }
    Ok(())
}

pub fn validate_password(value: &str) -> Result<(), &'static str> {
    if !(8..=128).contains(&value.chars().count()) {
        return Err("Password must contain between 8 and 128 characters");
    }
    if !value.chars().any(|c| c.is_uppercase()) {
        return Err("密码必须至少包含一个大写字母");
    }
    if !value.chars().any(|c| c.is_lowercase()) {
        return Err("密码必须至少包含一个小写字母");
    }
    if !value.chars().any(|c| c.is_ascii_digit()) {
        return Err("密码必须至少包含一个数字");
    }
    Ok(())
}

pub fn validate_email(value: &str) -> Result<(), &'static str> {
    static EMAIL: OnceLock<Regex> = OnceLock::new();
    if value.len() <= 255
        && EMAIL
            .get_or_init(|| Regex::new(r"^[^\s@]+@[^\s@]+\.[^\s@]+$").unwrap())
            .is_match(value)
    {
        Ok(())
    } else {
        Err("Invalid email address")
    }
}

#[cfg(test)]
mod tests {
    use super::{validate_email, validate_password, validate_username};

    #[test]
    fn test_user_input_validation_matches_existing_contract() {
        assert!(validate_username("alice.smith-1").is_ok());
        assert!(validate_username("ab").is_err());
        assert!(validate_username("alice smith").is_err());
        assert!(validate_password("Password1").is_ok());
        assert!(validate_password("12345678").is_err());
        assert!(validate_password("short").is_err());
        assert!(validate_password("alllowercase1").is_err());
        assert!(validate_password("ALLUPPERCASE1").is_err());
        assert!(validate_password("NoDigitsHere").is_err());
        assert!(validate_email("alice@example.com").is_ok());
        assert!(validate_email("not-an-email").is_err());
    }
}
