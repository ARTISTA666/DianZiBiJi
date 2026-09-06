use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

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
