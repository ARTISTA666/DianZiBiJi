use serde::{Deserialize, Serialize};

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
