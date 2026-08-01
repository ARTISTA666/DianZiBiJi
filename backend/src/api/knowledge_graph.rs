use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde_json::json;

use crate::{
    api::auth::CurrentUser,
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    knowledge_graph::{extract_note, note_graph, project_graph},
    models::{KnowledgeExtractionRequest, KnowledgeExtractionRunRead, KnowledgeGraphRead},
    permissions::{can_write_project, require_project_access},
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/notes/{note_id}/kg/extract", post(extract_note_knowledge))
        .route(
            "/projects/{project_id}/kg/rebuild",
            post(rebuild_project_knowledge),
        )
        .route(
            "/projects/{project_id}/kg/graph",
            get(get_project_knowledge_graph),
        )
        .route("/notes/{note_id}/kg/graph", get(get_note_knowledge_graph))
}

async fn extract_note_knowledge(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
    payload: Option<Json<KnowledgeExtractionRequest>>,
) -> Result<Json<KnowledgeExtractionRunRead>, ApiError> {
    let (project_id, status) = fetch_note_context(&state, note_id).await?;
    require_project_access(&state.pool, &user, project_id).await?;
    require_write(&state, &user, project_id).await?;
    if status != "approved" {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only approved notes can be extracted",
        ));
    }
    let rebuild = payload.map(|Json(payload)| payload.rebuild).unwrap_or(true);
    let mut transaction = state.pool.begin().await?;
    let run = extract_note(&mut transaction, note_id, user.id, rebuild).await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "extract_note_kg",
            target_type: Some("note"),
            target_id: Some(note_id),
            detail: json!({}),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(run))
}

async fn rebuild_project_knowledge(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<Vec<KnowledgeExtractionRunRead>>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    require_write(&state, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let note_ids: Vec<i32> = sqlx::query_scalar(
        r#"
        SELECT id FROM experiment_notes
        WHERE project_id = $1 AND status = 'APPROVED'::notestatus ORDER BY id
        "#,
    )
    .bind(project_id)
    .fetch_all(&mut *transaction)
    .await?;
    let mut runs = Vec::with_capacity(note_ids.len());
    for note_id in note_ids {
        runs.push(extract_note(&mut transaction, note_id, user.id, true).await?);
    }
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "rebuild_project_kg",
            target_type: Some("project"),
            target_id: Some(project_id),
            detail: json!({}),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(runs))
}

async fn get_project_knowledge_graph(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<KnowledgeGraphRead>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let (entities, relations) = project_graph(&mut transaction, project_id).await?;
    transaction.commit().await?;
    Ok(Json(KnowledgeGraphRead {
        project_id,
        entities,
        relations,
    }))
}

async fn get_note_knowledge_graph(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
) -> Result<Json<KnowledgeGraphRead>, ApiError> {
    let (project_id, _) = fetch_note_context(&state, note_id).await?;
    require_project_access(&state.pool, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let (entities, relations) = note_graph(&mut transaction, project_id, note_id).await?;
    transaction.commit().await?;
    Ok(Json(KnowledgeGraphRead {
        project_id,
        entities,
        relations,
    }))
}

async fn fetch_note_context(state: &AppState, note_id: i32) -> Result<(i32, String), ApiError> {
    sqlx::query_as("SELECT project_id, lower(status::text) FROM experiment_notes WHERE id = $1")
        .bind(note_id)
        .fetch_optional(&state.pool)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Note not found"))
}

async fn require_write(
    state: &AppState,
    user: &crate::models::UserRecord,
    project_id: i32,
) -> Result<(), ApiError> {
    if can_write_project(&state.pool, user, project_id).await? {
        Ok(())
    } else {
        Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Write permission required",
        ))
    }
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
        let bytes = to_bytes(response.into_body(), 256 * 1024).await.unwrap();
        let body = if bytes.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&bytes).unwrap()
        };
        (status, body)
    }

    #[tokio::test]
    async fn test_extract_and_rebuild_knowledge_graph_idempotently() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("kg_admin_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            ("SECRET_KEY".to_owned(), "rust-kg-secret".to_owned()),
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
                "name": format!("KG Project {suffix}"),
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
                "title": "Cell viability assay",
                "experiment_type": "Cell assay",
                "fixed_fields_json": {
                    "reagents": ["PBS", "Trypsin"],
                    "instrument": "Centrifuge",
                    "cell_line": "H226",
                    "condition": "control",
                    "processing_software": ["TopHat2 v2.0.13", "HTSeq v0.6.1"],
                    "source_accession": "GSM3035185"
                },
                "content_json": {
                    "text": "样本: Cell sample A\n结果: Cells remained viable"
                }
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

        let (extract_status, run) = call(
            &app,
            "POST",
            &format!("/notes/{note_id}/kg/extract"),
            Some(admin),
            Some(json!({"rebuild": true})),
        )
        .await;
        assert_eq!(extract_status, StatusCode::OK);
        assert_eq!(run["status"], "completed");
        assert!(run["extracted_entities"].as_i64().unwrap() >= 10);
        let (_, graph) = call(
            &app,
            "GET",
            &format!("/notes/{note_id}/kg/graph"),
            Some(admin),
            None,
        )
        .await;
        let labels: Vec<&str> = graph["entities"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|entity| entity["label"].as_str())
            .collect();
        for expected in [
            "Cell viability assay",
            "PBS",
            "Trypsin",
            "Centrifuge",
            "H226",
            "control",
            "TopHat2 v2.0.13",
            "GSM3035185",
            "Cell sample A",
            "Cells remained viable",
        ] {
            assert!(
                labels.contains(&expected),
                "missing graph label: {expected}"
            );
        }
        let first_entities = graph["entities"].as_array().unwrap().len();
        let first_relations = graph["relations"].as_array().unwrap().len();
        let (rebuild_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/rebuild"),
            Some(admin),
            None,
        )
        .await;
        assert_eq!(rebuild_status, StatusCode::OK);
        let (_, rebuilt) = call(
            &app,
            "GET",
            &format!("/notes/{note_id}/kg/graph"),
            Some(admin),
            None,
        )
        .await;
        assert_eq!(
            rebuilt["entities"].as_array().unwrap().len(),
            first_entities
        );
        assert_eq!(
            rebuilt["relations"].as_array().unwrap().len(),
            first_relations
        );
    }
}
