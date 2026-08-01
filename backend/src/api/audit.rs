use axum::{
    extract::{Query, State},
    routing::get,
    Json, Router,
};

use crate::{
    api::auth::{require_admin, CurrentUser},
    error::ApiError,
    models::{page_bounds, AuditLogRead, AuditQuery, Paginated},
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new().route("/audit-logs", get(list_audit_logs))
}

async fn list_audit_logs(
    State(state): State<AppState>,
    CurrentUser(admin): CurrentUser,
    Query(query): Query<AuditQuery>,
) -> Result<Json<Paginated<AuditLogRead>>, ApiError> {
    require_admin(&admin)?;
    let (skip, limit) = page_bounds(query.skip, query.limit);
    let total: i64 = sqlx::query_scalar(
        r#"
        SELECT count(*)
        FROM audit_logs
        WHERE ($1::integer IS NULL OR actor_user_id = $1)
          AND ($2::integer IS NULL OR project_id = $2)
          AND ($3::text IS NULL OR action = $3)
          AND ($4::timestamptz IS NULL OR created_at >= $4)
          AND ($5::timestamptz IS NULL OR created_at <= $5)
        "#,
    )
    .bind(query.actor_user_id)
    .bind(query.project_id)
    .bind(query.action.as_deref())
    .bind(query.date_from)
    .bind(query.date_to)
    .fetch_one(&state.pool)
    .await?;
    let items = sqlx::query_as::<_, AuditLogRead>(
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
        OFFSET $6
        LIMIT $7
        "#,
    )
    .bind(query.actor_user_id)
    .bind(query.project_id)
    .bind(query.action.as_deref())
    .bind(query.date_from)
    .bind(query.date_to)
    .bind(skip)
    .bind(limit)
    .fetch_all(&state.pool)
    .await?;
    Ok(Json(Paginated {
        items,
        total,
        skip,
        limit,
    }))
}
