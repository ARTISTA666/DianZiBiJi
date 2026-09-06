use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::pagination::Paginated;

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

/// 项目列表响应与通用分页结构完全同构，直接复用，避免重复定义漂移。
pub type ProjectListResponse = Paginated<ProjectRead>;

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
    #[serde(default = "default_member_role")]
    pub project_role: String,
    #[serde(default = "default_true")]
    pub can_read: bool,
    #[serde(default)]
    pub can_write: bool,
    #[serde(default)]
    pub can_review: bool,
    #[serde(default)]
    pub can_evaluate: bool,
    #[serde(default)]
    pub can_manage: bool,
}

fn default_member_role() -> String {
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
    pub display_name: String,
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
    if ["owner", "reviewer", "member", "viewer"].contains(&value) {
        Ok(())
    } else {
        Err("Unsupported project role")
    }
}

pub fn validate_project_status(value: &str) -> Result<(), &'static str> {
    if ["active", "archived"].contains(&value) {
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
    #[serde(default = "default_member_role")]
    pub group_role: String,
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
