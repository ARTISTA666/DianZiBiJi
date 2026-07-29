use axum::{
    extract::{Query, State},
    routing::get,
    Json, Router,
};

use crate::{
    api::auth::{require_admin, CurrentUser},
    error::ApiError,
    models::{AuditLogRead, AuditQuery},
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new().route("/audit-logs", get(list_audit_logs))
}

async fn list_audit_logs(
    State(state): State<AppState>,
    CurrentUser(admin): CurrentUser,
    Query(query): Query<AuditQuery>,
) -> Result<Json<Vec<AuditLogRead>>, ApiError> {
    require_admin(&admin)?;
    Ok(Json(
        sqlx::query_as::<_, AuditLogRead>(
            r#"
            SELECT id, actor_user_id, project_id, action, target_type,
                   target_id, detail_json, created_at
            FROM audit_logs
            WHERE ($1::integer IS NULL OR actor_user_id = $1)
              AND ($2::integer IS NULL OR project_id = $2)
              AND ($3::text IS NULL OR action = $3)
              AND ($4::timestamptz IS NULL OR created_at >= $4)
              AND ($5::timestamptz IS NULL OR created_at <= $5)
            ORDER BY created_at DESC
            LIMIT 200
            "#,
        )
        .bind(query.actor_user_id)
        .bind(query.project_id)
        .bind(query.action)
        .bind(query.date_from)
        .bind(query.date_to)
        .fetch_all(&state.pool)
        .await?,
    ))
}
