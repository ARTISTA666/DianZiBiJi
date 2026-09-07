use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// 预警指标标识（v1 四类，全部可由系统内既有数据推导）。
pub const ALERT_METRIC_REVIEW_STALL_HOURS: &str = "review_stall_hours";
pub const ALERT_METRIC_RETURN_RATE: &str = "return_rate";
pub const ALERT_METRIC_BLUEPRINT_STAGNANT_DAYS: &str = "blueprint_stagnant_days";
pub const ALERT_METRIC_PROGRESS_DEVIATION: &str = "progress_deviation";

/// 指标白名单：阈值配置只允许这四个 key，防止拼错 key 静默失效。
pub const ALERT_METRICS: &[&str] = &[
    ALERT_METRIC_REVIEW_STALL_HOURS,
    ALERT_METRIC_RETURN_RATE,
    ALERT_METRIC_BLUEPRINT_STAGNANT_DAYS,
    ALERT_METRIC_PROGRESS_DEVIATION,
];

/// 指标的人类可读说明（前端/文档共用口径）。
pub fn alert_metric_description(metric: &str) -> &'static str {
    match metric {
        ALERT_METRIC_REVIEW_STALL_HOURS => "最老一条待审笔记的等待时长（小时）",
        ALERT_METRIC_RETURN_RATE => "近 10 条审批中退回占比（0-1）",
        ALERT_METRIC_BLUEPRINT_STAGNANT_DAYS => "知识蓝图最近实证距今天数",
        ALERT_METRIC_PROGRESS_DEVIATION => "蓝图待实证知识点占比（0-1）",
        _ => "未知指标",
    }
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct AlertThresholdRead {
    pub id: i32,
    pub project_id: i32,
    pub metric: String,
    pub warn_threshold: f64,
    pub critical_threshold: f64,
    pub enabled: bool,
    pub updated_by: i32,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
pub struct AlertThresholdUpsertRequest {
    pub metric: String,
    pub warn_threshold: f64,
    pub critical_threshold: f64,
    pub enabled: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct AlertMetricSnapshot {
    pub metric: String,
    pub value: f64,
    pub level: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct AlertEvaluationSummary {
    pub evaluated_at: DateTime<Utc>,
    pub metrics: Vec<AlertMetricSnapshot>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct ProjectAlertRead {
    pub id: i32,
    pub project_id: i32,
    pub metric: String,
    pub metric_value: f64,
    pub level: String,
    pub status: String,
    pub detail: String,
    pub acknowledged_by: Option<i32>,
    pub acknowledged_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
pub struct AlertAcknowledgeRequest {
    pub note: Option<String>,
}
