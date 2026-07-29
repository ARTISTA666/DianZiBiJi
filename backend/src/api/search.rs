use axum::{
    extract::{Query, State},
    http::StatusCode,
    routing::post,
    Json, Router,
};
use serde_json::Value;
use sqlx::FromRow;

use crate::{
    api::auth::CurrentUser,
    error::ApiError,
    models::{SearchIndexQuery, SearchRequest, SearchResult, SearchStatus},
    permissions::{accessible_project_ids, require_project_access},
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/search/index", post(reindex_search))
        .route("/api/search", post(search))
}

#[derive(Debug, FromRow)]
struct IndexableNote {
    id: i32,
    project_id: i32,
    title: String,
    experiment_type: String,
    fixed_fields_json: Option<Value>,
    content_json: Option<Value>,
}

#[derive(Debug, FromRow)]
struct SearchDocument {
    id: i32,
    note_id: i32,
    project_id: i32,
    title: String,
    search_text: String,
    source_ids: String,
}

async fn reindex_search(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Query(query): Query<SearchIndexQuery>,
) -> Result<Json<SearchStatus>, ApiError> {
    let project_ids = if let Some(project_id) = query.project_id {
        require_project_access(&state.pool, &user, project_id).await?;
        vec![project_id]
    } else if user.role == "super_admin" {
        sqlx::query_scalar("SELECT id FROM projects ORDER BY id")
            .fetch_all(&state.pool)
            .await?
    } else {
        accessible_project_ids(&state.pool, &user).await?
    };

    let mut transaction = state.pool.begin().await?;
    if query.project_id.is_none() && user.role == "super_admin" {
        sqlx::query("DELETE FROM search_documents")
            .execute(&mut *transaction)
            .await?;
    } else if !project_ids.is_empty() {
        sqlx::query("DELETE FROM search_documents WHERE project_id = ANY($1)")
            .bind(&project_ids)
            .execute(&mut *transaction)
            .await?;
    }

    let notes = if project_ids.is_empty() {
        Vec::new()
    } else {
        sqlx::query_as::<_, IndexableNote>(
            r#"
            SELECT n.id, n.project_id, n.title, n.experiment_type,
                   v.fixed_fields_json, v.content_json
            FROM experiment_notes n
            LEFT JOIN note_versions v ON v.id = n.current_version_id
            WHERE n.project_id = ANY($1) AND n.status = 'APPROVED'::notestatus
            ORDER BY n.id
            "#,
        )
        .bind(&project_ids)
        .fetch_all(&mut *transaction)
        .await?
    };
    for note in &notes {
        let search_text = build_search_text(note);
        sqlx::query(
            r#"
            INSERT INTO search_documents (
                note_id, project_id, title, search_text, source_ids, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (note_id) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                title = EXCLUDED.title,
                search_text = EXCLUDED.search_text,
                source_ids = EXCLUDED.source_ids,
                updated_at = now()
            "#,
        )
        .bind(note.id)
        .bind(note.project_id)
        .bind(&note.title)
        .bind(search_text)
        .bind(note.id.to_string())
        .execute(&mut *transaction)
        .await?;
    }
    transaction.commit().await?;
    let total_documents = sqlx::query_scalar("SELECT count(*) FROM search_documents")
        .fetch_one(&state.pool)
        .await?;
    Ok(Json(SearchStatus {
        total_documents,
        project_documents: notes.len(),
    }))
}

async fn search(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Json(payload): Json<SearchRequest>,
) -> Result<Json<Vec<SearchResult>>, ApiError> {
    let terms: Vec<String> = payload
        .query
        .split_whitespace()
        .map(str::trim)
        .filter(|term| !term.is_empty())
        .map(str::to_lowercase)
        .collect();
    if terms.is_empty() {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Query cannot be empty",
        ));
    }
    let project_ids = if let Some(project_id) = payload.project_id {
        require_project_access(&state.pool, &user, project_id).await?;
        vec![project_id]
    } else {
        accessible_project_ids(&state.pool, &user).await?
    };
    if project_ids.is_empty() {
        return Ok(Json(Vec::new()));
    }
    let documents = sqlx::query_as::<_, SearchDocument>(
        r#"
        SELECT d.id, d.note_id, d.project_id, d.title, d.search_text, d.source_ids
        FROM search_documents d
        JOIN experiment_notes n ON n.id = d.note_id
        WHERE d.project_id = ANY($1) AND n.status = 'APPROVED'::notestatus
        ORDER BY d.id
        "#,
    )
    .bind(&project_ids)
    .fetch_all(&state.pool)
    .await?;
    let results = documents
        .into_iter()
        .filter_map(|document| {
            let haystack = document.search_text.to_lowercase();
            terms
                .iter()
                .all(|term| haystack.contains(term))
                .then(|| SearchResult {
                    document_id: document.id,
                    note_id: document.note_id,
                    project_id: document.project_id,
                    title: document.title,
                    snippet: snippet(&document.search_text, &terms),
                    source_ids: document
                        .source_ids
                        .split(',')
                        .filter(|item| !item.is_empty())
                        .map(str::to_owned)
                        .collect(),
                })
        })
        .take(50)
        .collect();
    Ok(Json(results))
}

fn build_search_text(note: &IndexableNote) -> String {
    let mut parts = vec![note.title.clone(), note.experiment_type.clone()];
    if let Some(Value::Object(fields)) = &note.fixed_fields_json {
        for value in fields.values() {
            match value {
                Value::String(text) => parts.push(text.clone()),
                Value::Array(_) | Value::Object(_) => {
                    if let Ok(text) = serde_json::to_string(value) {
                        parts.push(text);
                    }
                }
                _ => {}
            }
        }
    }
    if let Some(content) = &note.content_json {
        if let Ok(text) = serde_json::to_string(content) {
            parts.push(text);
        }
    }
    parts.join("\n")
}

fn snippet(text: &str, terms: &[String]) -> String {
    let lowercase = text.to_lowercase();
    let match_start = terms
        .iter()
        .filter_map(|term| lowercase.find(term))
        .next()
        .unwrap_or(0);
    let mut start = match_start.saturating_sub(40);
    while start > 0 && !text.is_char_boundary(start) {
        start -= 1;
    }
    let mut end = (start + 160).min(text.len());
    while end > start && !text.is_char_boundary(end) {
        end -= 1;
    }
    text[start..end].to_owned()
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use axum::{
        body::{to_bytes, Body},
        http::{Request, StatusCode},
        Router,
    };
    use serde_json::{json, Value};
    use tower::ServiceExt;
    use uuid::Uuid;

    use crate::{
        build_app,
        config::Settings,
        db::{connect_database, initialize_database},
        AppState,
    };

    async fn call(
        app: &Router,
        method: &str,
        path: &str,
        token: Option<&str>,
        body: Option<Value>,
    ) -> (StatusCode, Value) {
        let mut request = Request::builder().method(method).uri(path);
        if let Some(token) = token {
            request = request.header("authorization", format!("Bearer {token}"));
        }
        if body.is_some() {
            request = request.header("content-type", "application/json");
        }
        let response = app
            .clone()
            .oneshot(
                request
                    .body(body.map_or_else(Body::empty, |value| Body::from(value.to_string())))
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 128 * 1024).await.unwrap();
        let body = if bytes.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&bytes).unwrap()
        };
        (status, body)
    }

    #[tokio::test]
    async fn test_search_reindex_and_project_boundary() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("search_admin_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            ("SECRET_KEY".to_owned(), "rust-search-secret".to_owned()),
            (
                "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                admin_username.clone(),
            ),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustAdmin123!".to_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let app = build_app(AppState::new(pool, settings).unwrap());
        let (_, login) = call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": admin_username, "password": "RustAdmin123!"})),
        )
        .await;
        let admin = login["access_token"].as_str().unwrap();
        let (_, project) = call(
            &app,
            "POST",
            "/projects",
            Some(admin),
            Some(json!({
                "name": format!("Search Project {suffix}"),
                "approval_enabled": false
            })),
        )
        .await;
        let project_id = project["id"].as_i64().unwrap();
        let (_, note) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/notes"),
            Some(admin),
            Some(json!({
                "title": "PCR result",
                "experiment_type": "PCR",
                "fixed_fields_json": {"reagent": "Taq polymerase"},
                "content_json": {"result": "clear target band"}
            })),
        )
        .await;
        let note_id = note["id"].as_i64().unwrap();
        call(
            &app,
            "POST",
            &format!("/notes/{note_id}/submit"),
            Some(admin),
            None,
        )
        .await;

        let (index_status, indexed) = call(
            &app,
            "POST",
            &format!("/api/search/index?project_id={project_id}"),
            Some(admin),
            None,
        )
        .await;
        assert_eq!(index_status, StatusCode::OK);
        assert_eq!(indexed["project_documents"], 1);
        let (search_status, results) = call(
            &app,
            "POST",
            "/api/search",
            Some(admin),
            Some(json!({"query": "taq band", "project_id": project_id})),
        )
        .await;
        assert_eq!(search_status, StatusCode::OK);
        assert_eq!(results[0]["note_id"], note_id);
        assert!(results[0]["snippet"].as_str().unwrap().contains("Taq"));

        let (_, outsider) = call(
            &app,
            "POST",
            "/users",
            Some(admin),
            Some(json!({
                "username": format!("search_outsider_{suffix}"),
                "password": "Outsider123!",
                "display_name": "Outsider"
            })),
        )
        .await;
        assert!(outsider["id"].is_number());
        let (_, outsider_login) = call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({
                "username": format!("search_outsider_{suffix}"),
                "password": "Outsider123!"
            })),
        )
        .await;
        let outsider_token = outsider_login["access_token"].as_str().unwrap();
        let (forbidden, _) = call(
            &app,
            "POST",
            "/api/search",
            Some(outsider_token),
            Some(json!({"query": "Taq", "project_id": project_id})),
        )
        .await;
        assert_eq!(forbidden, StatusCode::FORBIDDEN);
        let (_, global_results) = call(
            &app,
            "POST",
            "/api/search",
            Some(outsider_token),
            Some(json!({"query": "Taq"})),
        )
        .await;
        assert!(global_results.as_array().unwrap().is_empty());
    }
}
