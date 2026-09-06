use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

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
