use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// 蓝图来源优先级：数值越小优先级越高。
/// 组会纪要（导师意见）> 项目计划书 > 学生手动调整。
pub const BLUEPRINT_PRIORITY_MEETING_NOTE: i32 = 10;
pub const BLUEPRINT_PRIORITY_PLAN_DOCUMENT: i32 = 50;
pub const BLUEPRINT_PRIORITY_MANUAL: i32 = 100;

pub const BLUEPRINT_SOURCE_MEETING_NOTE: &str = "meeting_note";
pub const BLUEPRINT_SOURCE_PLAN_DOCUMENT: &str = "plan_document";

/// 蓝图节点可用的实体类型（排除 note/project/user/file 等系统结构类型）。
pub const BLUEPRINT_ENTITY_TYPES: &[&str] = &[
    "reagent",
    "instrument",
    "sample",
    "result",
    "experiment_type",
    "treatment",
    "perturbation",
    "culture",
    "cell_type",
    "cell_line",
    "group",
    "biosample",
    "geo_accession",
    "software",
    "condition",
];

/// 蓝图边可用的关系类型（排除 has_note/created_by/has_attachment 等系统结构关系）。
pub const BLUEPRINT_RELATION_TYPES: &[&str] = &[
    "uses_reagent",
    "uses_instrument",
    "uses_sample",
    "produces_result",
    "has_experiment_type",
    "has_condition",
];

#[derive(Debug, Deserialize)]
pub struct BlueprintParseRequest {
    pub title: String,
    pub source_kind: String,
    pub priority: Option<i32>,
    pub text: Option<String>,
    pub file_id: Option<i32>,
    pub note_id: Option<i32>,
}

#[derive(Clone, Debug, Serialize)]
pub struct BlueprintParseResponse {
    pub document_id: i32,
    pub parse_mode: String,
    pub nodes_added: i64,
    pub nodes_updated: i64,
    pub edges_added: i64,
    pub edges_dropped: i64,
    pub message: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct BlueprintEvidence {
    pub entity_ids: Vec<i32>,
    pub entity_count: i64,
    pub last_evidence_at: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, Serialize)]
pub struct BlueprintNodeRead {
    pub id: i32,
    pub entity_type: String,
    pub label: String,
    pub description: String,
    pub status: String,
    pub source_kind: String,
    pub source_label: String,
    pub priority: i32,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub evidence: BlueprintEvidence,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct BlueprintEdgeRead {
    pub id: i32,
    pub source_node_id: i32,
    pub target_node_id: i32,
    pub relation_type: String,
    pub status: String,
    pub priority: i32,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct BlueprintDocumentRead {
    pub id: i32,
    pub title: String,
    pub source_kind: String,
    pub parse_mode: String,
    pub node_count: i64,
    pub edge_count: i64,
    pub message: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Clone, Debug, Serialize)]
pub struct BlueprintCoverage {
    pub total_nodes: i64,
    pub covered_nodes: i64,
    pub completion: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct KnowledgeBlueprintRead {
    pub project_id: i32,
    pub coverage: BlueprintCoverage,
    pub nodes: Vec<BlueprintNodeRead>,
    pub edges: Vec<BlueprintEdgeRead>,
    pub documents: Vec<BlueprintDocumentRead>,
}

#[derive(Debug, Deserialize)]
pub struct BlueprintNodePatchRequest {
    pub status: Option<String>,
    pub description: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct BlueprintEdgePatchRequest {
    pub status: Option<String>,
}
