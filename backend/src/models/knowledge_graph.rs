use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

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

fn default_true() -> bool {
    true
}

impl Default for KnowledgeExtractionRequest {
    fn default() -> Self {
        Self { rebuild: true }
    }
}
