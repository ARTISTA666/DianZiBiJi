use axum::{extract::State, routing::get, Json, Router};

use crate::{api::auth::CurrentUser, error::ApiError, models::TemplateRead, AppState};

pub fn router() -> Router<AppState> {
    Router::new().route("/templates", get(list_templates))
}

async fn list_templates(
    State(state): State<AppState>,
    CurrentUser(_): CurrentUser,
) -> Result<Json<Vec<TemplateRead>>, ApiError> {
    Ok(Json(
        sqlx::query_as::<_, TemplateRead>(
            r#"
            SELECT id, name, experiment_type, schema_json,
                   default_content_json, is_active
            FROM experiment_templates
            WHERE is_active = true
            ORDER BY id
            "#,
        )
        .fetch_all(&state.pool)
        .await?,
    ))
}
