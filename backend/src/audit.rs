use serde_json::Value;
use sqlx::{Executor, Postgres};

pub struct AuditEvent<'a> {
    pub actor_user_id: Option<i32>,
    pub project_id: Option<i32>,
    pub action: &'a str,
    pub target_type: Option<&'a str>,
    pub target_id: Option<i32>,
    pub detail: Value,
    pub ip_address: Option<String>,
    pub user_agent: Option<String>,
}

pub async fn write_audit<'e, E>(executor: E, event: AuditEvent<'_>) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    sqlx::query(
        r#"
        INSERT INTO audit_logs (
            actor_user_id, project_id, action, target_type, target_id,
            detail_json, ip_address, user_agent
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        "#,
    )
    .bind(event.actor_user_id)
    .bind(event.project_id)
    .bind(event.action)
    .bind(event.target_type)
    .bind(event.target_id)
    .bind(event.detail)
    .bind(event.ip_address)
    .bind(event.user_agent)
    .execute(executor)
    .await?;
    Ok(())
}
