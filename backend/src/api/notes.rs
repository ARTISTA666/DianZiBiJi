use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde_json::json;
use sqlx::{PgPool, Postgres, Transaction};

use crate::{
    api::auth::CurrentUser,
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    knowledge_graph::extract_note,
    models::{
        page_bounds, ApprovalRequest, NoteApprovalRead, NoteCreate, NoteListQuery, NoteRead,
        NoteUpdate, NoteVersionRead, Paginated, UserRecord,
    },
    permissions::{can_review_project, can_write_project, require_project_access},
    AppState,
};

#[cfg(test)]
#[derive(Clone)]
struct ConcurrencyPause {
    operation: &'static str,
    entity_id: i32,
    reached: std::sync::Arc<tokio::sync::Notify>,
    resume: std::sync::Arc<tokio::sync::Notify>,
}

#[cfg(test)]
fn concurrency_pause_slot() -> &'static tokio::sync::Mutex<Option<ConcurrencyPause>> {
    static SLOT: std::sync::OnceLock<tokio::sync::Mutex<Option<ConcurrencyPause>>> =
        std::sync::OnceLock::new();
    SLOT.get_or_init(|| tokio::sync::Mutex::new(None))
}

#[cfg(test)]
async fn install_concurrency_pause(
    operation: &'static str,
    entity_id: i32,
) -> (
    std::sync::Arc<tokio::sync::Notify>,
    std::sync::Arc<tokio::sync::Notify>,
) {
    let reached = std::sync::Arc::new(tokio::sync::Notify::new());
    let resume = std::sync::Arc::new(tokio::sync::Notify::new());
    *concurrency_pause_slot().lock().await = Some(ConcurrencyPause {
        operation,
        entity_id,
        reached: reached.clone(),
        resume: resume.clone(),
    });
    (reached, resume)
}

#[cfg(test)]
async fn pause_for_concurrency_test(operation: &'static str, entity_id: i32) {
    let pause = concurrency_pause_slot()
        .lock()
        .await
        .as_ref()
        .filter(|pause| pause.operation == operation && pause.entity_id == entity_id)
        .cloned();
    if let Some(pause) = pause {
        pause.reached.notify_one();
        pause.resume.notified().await;
        *concurrency_pause_slot().lock().await = None;
    }
}

const NOTE_COLUMNS: &str = r#"
    id, project_id, template_id, title, experiment_type, experiment_date,
    owner_user_id, lower(status::text) AS status, current_version_id,
    created_at, updated_at
"#;

pub fn router() -> Router<AppState> {
    Router::new()
        .route(
            "/projects/{project_id}/notes",
            get(list_notes).post(create_note),
        )
        .route("/notes/{note_id}", get(get_note).patch(update_note))
        .route("/notes/{note_id}/submit", post(submit_note))
        .route("/notes/{note_id}/versions", get(list_note_versions))
        .route(
            "/notes/{note_id}/versions/{version_id}",
            get(get_note_version),
        )
        .route("/notes/{note_id}/archive", post(archive_note))
        .route("/notes/{note_id}/void", post(void_note))
        .route("/approvals/pending", get(list_pending_approvals))
        .route("/notes/{note_id}/approve", post(approve_note))
        .route("/notes/{note_id}/return", post(return_note))
        .route("/notes/{note_id}/approvals", get(list_note_approvals))
}

async fn list_notes(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Query(query): Query<NoteListQuery>,
) -> Result<Json<Paginated<NoteRead>>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    let (skip, limit) = page_bounds(query.skip, query.limit);
    let status = query.status.as_deref();
    let total: i64 = sqlx::query_scalar(
        r#"
        SELECT count(*) FROM experiment_notes
        WHERE project_id = $1
          AND ($2::text IS NULL OR lower(status::text) = lower($2))
        "#,
    )
    .bind(project_id)
    .bind(status)
    .fetch_one(&state.pool)
    .await?;
    let query_sql = format!(
        r#"
        SELECT {NOTE_COLUMNS} FROM experiment_notes
        WHERE project_id = $1
          AND ($2::text IS NULL OR lower(status::text) = lower($2))
        ORDER BY updated_at DESC
        OFFSET $3
        LIMIT $4
        "#
    );
    let items = sqlx::query_as::<_, NoteRead>(&query_sql)
        .bind(project_id)
        .bind(status)
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

async fn create_note(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Json(payload): Json<NoteCreate>,
) -> Result<Json<NoteRead>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    require_write(&state.pool, &user, project_id).await?;
    validate_note_create(&payload)?;

    let mut transaction = state.pool.begin().await?;
    let note_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO experiment_notes (
            project_id, template_id, title, experiment_type, experiment_date,
            owner_user_id, status, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, 'DRAFT'::notestatus, now(), now())
        RETURNING id
        "#,
    )
    .bind(project_id)
    .bind(payload.template_id)
    .bind(&payload.title)
    .bind(&payload.experiment_type)
    .bind(payload.experiment_date)
    .bind(user.id)
    .fetch_one(&mut *transaction)
    .await?;
    let version_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO note_versions (
            note_id, version_number, fixed_fields_json, content_json,
            created_by, change_summary, is_locked, created_at
        )
        VALUES ($1, 1, $2, $3, $4, 'Initial draft', false, now())
        RETURNING id
        "#,
    )
    .bind(note_id)
    .bind(sanitize_json(&payload.fixed_fields_json))
    .bind(sanitize_json(&payload.content_json))
    .bind(user.id)
    .fetch_one(&mut *transaction)
    .await?;
    sqlx::query("UPDATE experiment_notes SET current_version_id = $2 WHERE id = $1")
        .bind(note_id)
        .bind(version_id)
        .execute(&mut *transaction)
        .await?;
    audit_note(
        &mut transaction,
        &user,
        "create_note",
        project_id,
        note_id,
        json!({}),
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_note(&state.pool, note_id).await?))
}

async fn get_note(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
) -> Result<Json<NoteRead>, ApiError> {
    Ok(Json(
        require_note_access(&state.pool, &user, note_id).await?,
    ))
}

async fn update_note(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
    Json(payload): Json<NoteUpdate>,
) -> Result<Json<NoteRead>, ApiError> {
    let note = require_note_access(&state.pool, &user, note_id).await?;
    require_write(&state.pool, &user, note.project_id).await?;
    if !matches!(note.status.as_str(), "draft" | "returned") {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only draft or returned notes can be edited",
        ));
    }
    validate_note_update(&payload)?;

    let mut transaction = state.pool.begin().await?;
    let locked = fetch_note_for_update(&mut transaction, note_id).await?;
    if !matches!(locked.status.as_str(), "draft" | "returned") {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only draft or returned notes can be edited",
        ));
    }
    let current = if let Some(version_id) = locked.current_version_id {
        sqlx::query_as::<_, NoteVersionRead>(
            r#"
            SELECT id, note_id, version_number, fixed_fields_json, content_json,
                   created_by, change_summary, is_locked, created_at
            FROM note_versions WHERE id = $1
            "#,
        )
        .bind(version_id)
        .fetch_optional(&mut *transaction)
        .await?
    } else {
        None
    };
    let version_number: i32 = sqlx::query_scalar(
        "SELECT COALESCE(max(version_number), 0)::int + 1 FROM note_versions WHERE note_id = $1",
    )
    .bind(note_id)
    .fetch_one(&mut *transaction)
    .await?;
    let fixed_fields = payload
        .fixed_fields_json
        .or_else(|| current.as_ref().map(|item| item.fixed_fields_json.clone()))
        .unwrap_or_else(|| json!({}));
    let content = payload
        .content_json
        .or_else(|| current.as_ref().map(|item| item.content_json.clone()))
        .unwrap_or_else(|| json!({}));
    let change_summary = payload
        .change_summary
        .unwrap_or_else(|| "Updated draft".to_owned());
    let version_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO note_versions (
            note_id, version_number, fixed_fields_json, content_json,
            created_by, change_summary, is_locked, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, false, now())
        RETURNING id
        "#,
    )
    .bind(note_id)
    .bind(version_number)
    .bind(sanitize_json(&fixed_fields))
    .bind(sanitize_json(&content))
    .bind(user.id)
    .bind(change_summary)
    .fetch_one(&mut *transaction)
    .await?;
    sqlx::query(
        r#"
        UPDATE experiment_notes
        SET title = COALESCE($2, title),
            experiment_type = COALESCE($3, experiment_type),
            experiment_date = COALESCE($4, experiment_date),
            current_version_id = $5,
            updated_at = now()
        WHERE id = $1
        "#,
    )
    .bind(note_id)
    .bind(payload.title)
    .bind(payload.experiment_type)
    .bind(payload.experiment_date)
    .bind(version_id)
    .execute(&mut *transaction)
    .await?;
    audit_note(
        &mut transaction,
        &user,
        "update_note",
        note.project_id,
        note_id,
        json!({}),
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_note(&state.pool, note_id).await?))
}

async fn submit_note(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
) -> Result<Json<NoteRead>, ApiError> {
    let note = fetch_note(&state.pool, note_id).await?;
    let project = require_project_access(&state.pool, &user, note.project_id).await?;
    if note.owner_user_id != user.id {
        return Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Only note owner can submit the draft",
        ));
    }
    if !matches!(note.status.as_str(), "draft" | "returned") {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Note cannot be submitted",
        ));
    }

    let mut transaction = state.pool.begin().await?;
    let locked = fetch_note_for_update(&mut transaction, note_id).await?;
    if !matches!(locked.status.as_str(), "draft" | "returned") {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Note cannot be submitted",
        ));
    }
    let status = if project.approval_enabled {
        "SUBMITTED"
    } else {
        if let Some(version_id) = locked.current_version_id {
            sqlx::query("UPDATE note_versions SET is_locked = true WHERE id = $1")
                .bind(version_id)
                .execute(&mut *transaction)
                .await?;
        }
        "APPROVED"
    };
    sqlx::query(
        "UPDATE experiment_notes SET status = $2::notestatus, updated_at = now() WHERE id = $1",
    )
    .bind(note_id)
    .bind(status)
    .execute(&mut *transaction)
    .await?;
    if !project.approval_enabled {
        let run = extract_note(&mut transaction, note_id, user.id, true).await?;
        audit_note(
            &mut transaction,
            &user,
            "auto_extract_note_kg",
            note.project_id,
            note_id,
            json!({
                "entities": run.extracted_entities,
                "relations": run.extracted_relations,
                "trigger": "submit_without_approval"
            }),
            client.ip_opt(),
            client.ua_opt(),
        )
        .await?;
    }
    audit_note(
        &mut transaction,
        &user,
        "submit_note",
        note.project_id,
        note_id,
        json!({"approval_enabled": project.approval_enabled}),
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_note(&state.pool, note_id).await?))
}

async fn list_note_versions(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
) -> Result<Json<Vec<NoteVersionRead>>, ApiError> {
    require_note_access(&state.pool, &user, note_id).await?;
    let versions = sqlx::query_as::<_, NoteVersionRead>(
        r#"
        SELECT id, note_id, version_number, fixed_fields_json, content_json,
               created_by, change_summary, is_locked, created_at
        FROM note_versions WHERE note_id = $1 ORDER BY version_number DESC
        "#,
    )
    .bind(note_id)
    .fetch_all(&state.pool)
    .await?;
    Ok(Json(versions))
}

async fn get_note_version(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path((note_id, version_id)): Path<(i32, i32)>,
) -> Result<Json<NoteVersionRead>, ApiError> {
    require_note_access(&state.pool, &user, note_id).await?;
    let version = sqlx::query_as::<_, NoteVersionRead>(
        r#"
        SELECT id, note_id, version_number, fixed_fields_json, content_json,
               created_by, change_summary, is_locked, created_at
        FROM note_versions WHERE id = $1 AND note_id = $2
        "#,
    )
    .bind(version_id)
    .bind(note_id)
    .fetch_optional(&state.pool)
    .await?
    .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Note version not found"))?;
    Ok(Json(version))
}

async fn archive_note(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
) -> Result<Json<NoteRead>, ApiError> {
    let note = require_note_access(&state.pool, &user, note_id).await?;
    require_write(&state.pool, &user, note.project_id).await?;
    if !matches!(note.status.as_str(), "approved" | "returned" | "draft") {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Note cannot be archived",
        ));
    }
    #[cfg(test)]
    pause_for_concurrency_test("archive_note", note_id).await;
    let mut transaction = state.pool.begin().await?;
    let locked = fetch_note_for_update(&mut transaction, note_id).await?;
    if !matches!(locked.status.as_str(), "approved" | "returned" | "draft") {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Note cannot be archived",
        ));
    }
    sqlx::query(
        "UPDATE experiment_notes SET status = 'ARCHIVED'::notestatus, updated_at = now() WHERE id = $1",
    )
    .bind(note_id)
    .execute(&mut *transaction)
    .await?;
    clear_note_artifacts(&mut transaction, note_id).await?;
    audit_note(
        &mut transaction,
        &user,
        "archive_note",
        locked.project_id,
        note_id,
        json!({}),
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_note(&state.pool, note_id).await?))
}

async fn void_note(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
    Json(payload): Json<ApprovalRequest>,
) -> Result<Json<NoteRead>, ApiError> {
    let note = require_note_access(&state.pool, &user, note_id).await?;
    require_review(&state.pool, &user, note.project_id).await?;
    if note.status == "voided" {
        return Err(ApiError::new(StatusCode::CONFLICT, "Note already voided"));
    }
    if !matches!(note.status.as_str(), "submitted" | "approved") {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only submitted or approved notes can be voided",
        ));
    }
    #[cfg(test)]
    pause_for_concurrency_test("void_note", note_id).await;
    let mut transaction = state.pool.begin().await?;
    let locked = fetch_note_for_update(&mut transaction, note_id).await?;
    if locked.status == "voided" {
        return Err(ApiError::new(StatusCode::CONFLICT, "Note already voided"));
    }
    if !matches!(locked.status.as_str(), "submitted" | "approved") {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only submitted or approved notes can be voided",
        ));
    }
    let version_id = locked
        .current_version_id
        .ok_or_else(|| ApiError::internal("Note has no current version"))?;
    sqlx::query(
        "UPDATE experiment_notes SET status = 'VOIDED'::notestatus, updated_at = now() WHERE id = $1",
    )
    .bind(note_id)
    .execute(&mut *transaction)
    .await?;
    clear_note_artifacts(&mut transaction, note_id).await?;
    insert_approval(
        &mut transaction,
        note_id,
        version_id,
        user.id,
        "voided",
        payload.comment,
    )
    .await?;
    audit_note(
        &mut transaction,
        &user,
        "void_note",
        locked.project_id,
        note_id,
        json!({}),
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_note(&state.pool, note_id).await?))
}

async fn list_pending_approvals(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
) -> Result<Json<Vec<NoteRead>>, ApiError> {
    let query = format!(
        r#"
        SELECT {NOTE_COLUMNS}
        FROM experiment_notes
        WHERE status = 'SUBMITTED'::notestatus
          AND NOT EXISTS(
              SELECT 1 FROM project_reviewers pr
              WHERE pr.project_id = experiment_notes.project_id
                AND pr.user_id = $1
          )
          AND (
              $2 OR EXISTS(
                  SELECT 1 FROM project_members pm
                  WHERE pm.project_id = experiment_notes.project_id
                    AND pm.user_id = $1
                    AND (pm.can_review = true OR pm.can_manage = true)
              )
          )
        ORDER BY updated_at DESC
        "#
    );
    let notes = sqlx::query_as::<_, NoteRead>(&query)
        .bind(user.id)
        .bind(user.role == "super_admin")
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(notes))
}

async fn approve_note(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
    Json(payload): Json<ApprovalRequest>,
) -> Result<Json<NoteRead>, ApiError> {
    review_note(
        &state,
        &user,
        note_id,
        payload,
        true,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await
}

async fn return_note(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
    Json(payload): Json<ApprovalRequest>,
) -> Result<Json<NoteRead>, ApiError> {
    review_note(
        &state,
        &user,
        note_id,
        payload,
        false,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await
}

async fn review_note(
    state: &AppState,
    user: &UserRecord,
    note_id: i32,
    payload: ApprovalRequest,
    approve: bool,
    ip_address: Option<&str>,
    user_agent: Option<&str>,
) -> Result<Json<NoteRead>, ApiError> {
    let note = require_note_access(&state.pool, user, note_id).await?;
    require_review(&state.pool, user, note.project_id).await?;
    if note.status != "submitted" {
        let detail = if approve {
            "Only submitted notes can be approved"
        } else {
            "Only submitted notes can be returned"
        };
        return Err(ApiError::new(StatusCode::CONFLICT, detail));
    }
    let version_id = note
        .current_version_id
        .ok_or_else(|| ApiError::internal("Note has no current version"))?;
    let (status, action, audit_action) = if approve {
        ("APPROVED", "approved", "approve_note")
    } else {
        ("RETURNED", "returned", "return_note")
    };
    let mut transaction = state.pool.begin().await?;
    let result = sqlx::query(
        r#"
        UPDATE experiment_notes
        SET status = $2::notestatus, updated_at = now()
        WHERE id = $1 AND status = 'SUBMITTED'::notestatus
        "#,
    )
    .bind(note_id)
    .bind(status)
    .execute(&mut *transaction)
    .await?;
    if result.rows_affected() != 1 {
        let detail = if approve {
            "Only submitted notes can be approved"
        } else {
            "Only submitted notes can be returned"
        };
        return Err(ApiError::new(StatusCode::CONFLICT, detail));
    }
    if approve {
        sqlx::query("UPDATE note_versions SET is_locked = true WHERE id = $1")
            .bind(version_id)
            .execute(&mut *transaction)
            .await?;
    }
    insert_approval(
        &mut transaction,
        note_id,
        version_id,
        user.id,
        action,
        payload.comment,
    )
    .await?;
    if approve {
        let run = extract_note(&mut transaction, note_id, user.id, true).await?;
        audit_note(
            &mut transaction,
            user,
            "auto_extract_note_kg",
            note.project_id,
            note_id,
            json!({
                "entities": run.extracted_entities,
                "relations": run.extracted_relations,
                "trigger": "approve_note"
            }),
            ip_address,
            user_agent,
        )
        .await?;
    }
    audit_note(
        &mut transaction,
        user,
        audit_action,
        note.project_id,
        note_id,
        json!({}),
        ip_address,
        user_agent,
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_note(&state.pool, note_id).await?))
}

async fn list_note_approvals(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
) -> Result<Json<Vec<NoteApprovalRead>>, ApiError> {
    require_note_access(&state.pool, &user, note_id).await?;
    let approvals = sqlx::query_as::<_, NoteApprovalRead>(
        r#"
        SELECT id, note_id, version_id, reviewer_user_id, action, comment, created_at
        FROM note_approvals WHERE note_id = $1 ORDER BY created_at DESC
        "#,
    )
    .bind(note_id)
    .fetch_all(&state.pool)
    .await?;
    Ok(Json(approvals))
}

async fn fetch_note(pool: &PgPool, note_id: i32) -> Result<NoteRead, ApiError> {
    let query = format!("SELECT {NOTE_COLUMNS} FROM experiment_notes WHERE id = $1");
    sqlx::query_as::<_, NoteRead>(&query)
        .bind(note_id)
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Note not found"))
}

async fn fetch_note_for_update(
    transaction: &mut Transaction<'_, Postgres>,
    note_id: i32,
) -> Result<NoteRead, ApiError> {
    let query = format!("SELECT {NOTE_COLUMNS} FROM experiment_notes WHERE id = $1 FOR UPDATE");
    sqlx::query_as::<_, NoteRead>(&query)
        .bind(note_id)
        .fetch_optional(&mut **transaction)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Note not found"))
}

async fn require_note_access(
    pool: &PgPool,
    user: &UserRecord,
    note_id: i32,
) -> Result<NoteRead, ApiError> {
    let note = fetch_note(pool, note_id).await?;
    require_project_access(pool, user, note.project_id).await?;
    Ok(note)
}

async fn require_write(pool: &PgPool, user: &UserRecord, project_id: i32) -> Result<(), ApiError> {
    if can_write_project(pool, user, project_id).await? {
        Ok(())
    } else {
        Err(ApiError::new(StatusCode::FORBIDDEN, "需要写入权限"))
    }
}

async fn require_review(pool: &PgPool, user: &UserRecord, project_id: i32) -> Result<(), ApiError> {
    if can_review_project(pool, user, project_id).await? {
        Ok(())
    } else {
        Err(ApiError::new(StatusCode::FORBIDDEN, "需要审核权限"))
    }
}

fn sanitize_json(value: &serde_json::Value) -> serde_json::Value {
    match value {
        serde_json::Value::String(s) => {
            let sanitized = s
                .replace('&', "&amp;")
                .replace('<', "&lt;")
                .replace('>', "&gt;")
                .replace('"', "&quot;")
                .replace('\'', "&#x27;");
            serde_json::Value::String(sanitized)
        }
        serde_json::Value::Object(map) => {
            let sanitized: serde_json::Map<String, serde_json::Value> = map
                .iter()
                .map(|(key, val)| (key.clone(), sanitize_json(val)))
                .collect();
            serde_json::Value::Object(sanitized)
        }
        serde_json::Value::Array(arr) => {
            serde_json::Value::Array(arr.iter().map(sanitize_json).collect())
        }
        other => other.clone(),
    }
}

fn validate_note_create(payload: &NoteCreate) -> Result<(), ApiError> {
    if payload.title.trim().is_empty() || payload.experiment_type.trim().is_empty() {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Title and experiment type are required",
        ));
    }
    if !payload.fixed_fields_json.is_object() || !payload.content_json.is_object() {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Note fields must be JSON objects",
        ));
    }
    Ok(())
}

fn validate_note_update(payload: &NoteUpdate) -> Result<(), ApiError> {
    if payload
        .title
        .as_ref()
        .is_some_and(|value| value.trim().is_empty())
        || payload
            .experiment_type
            .as_ref()
            .is_some_and(|value| value.trim().is_empty())
    {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Title and experiment type cannot be empty",
        ));
    }
    if payload
        .fixed_fields_json
        .as_ref()
        .is_some_and(|value| !value.is_object())
        || payload
            .content_json
            .as_ref()
            .is_some_and(|value| !value.is_object())
    {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Note fields must be JSON objects",
        ));
    }
    Ok(())
}

async fn insert_approval(
    transaction: &mut Transaction<'_, Postgres>,
    note_id: i32,
    version_id: i32,
    reviewer_user_id: i32,
    action: &str,
    comment: Option<String>,
) -> Result<(), ApiError> {
    sqlx::query(
        r#"
        INSERT INTO note_approvals (
            note_id, version_id, reviewer_user_id, action, comment, created_at
        )
        VALUES ($1, $2, $3, $4, $5, now())
        "#,
    )
    .bind(note_id)
    .bind(version_id)
    .bind(reviewer_user_id)
    .bind(action)
    .bind(comment)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

#[allow(clippy::too_many_arguments)]
async fn audit_note(
    transaction: &mut Transaction<'_, Postgres>,
    user: &UserRecord,
    action: &str,
    project_id: i32,
    note_id: i32,
    detail: serde_json::Value,
    ip_address: Option<&str>,
    user_agent: Option<&str>,
) -> Result<(), ApiError> {
    write_audit(
        &mut **transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action,
            target_type: Some("note"),
            target_id: Some(note_id),
            detail,
            ip_address: ip_address.map(str::to_owned),
            user_agent: user_agent.map(str::to_owned),
        },
    )
    .await?;
    Ok(())
}

async fn clear_note_artifacts(
    transaction: &mut Transaction<'_, Postgres>,
    note_id: i32,
) -> Result<(), ApiError> {
    sqlx::query("DELETE FROM search_documents WHERE note_id = $1")
        .bind(note_id)
        .execute(&mut **transaction)
        .await?;
    let entity_ids: Vec<i32> = sqlx::query_scalar(
        r#"
        SELECT source_entity_id FROM kg_relations
        WHERE source_type IN ('note', 'note_extraction') AND source_id = $1
        UNION
        SELECT target_entity_id FROM kg_relations
        WHERE source_type IN ('note', 'note_extraction') AND source_id = $1
        UNION
        SELECT id FROM kg_entities WHERE source_type = 'note' AND source_id = $1
        "#,
    )
    .bind(note_id)
    .fetch_all(&mut **transaction)
    .await?;
    sqlx::query(
        "DELETE FROM kg_relations WHERE source_type IN ('note', 'note_extraction') AND source_id = $1",
    )
    .bind(note_id)
    .execute(&mut **transaction)
    .await?;
    if !entity_ids.is_empty() {
        sqlx::query(
            r#"
            DELETE FROM kg_entities e
            WHERE e.id = ANY($1)
              AND NOT EXISTS (
                  SELECT 1 FROM kg_relations r
                  WHERE r.source_entity_id = e.id OR r.target_entity_id = e.id
              )
              AND (e.source_type IS NULL OR (e.source_type = 'note' AND e.source_id = $2))
            "#,
        )
        .bind(&entity_ids)
        .bind(note_id)
        .execute(&mut **transaction)
        .await?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::{collections::HashMap, time::Duration};

    use axum::{
        body::{to_bytes, Body},
        http::{Request, StatusCode},
        Router,
    };
    use serde_json::{json, Value};
    use tokio::time::timeout;
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

    async fn login(app: &Router, username: &str, password: &str) -> String {
        let (status, body) = call(
            app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": username, "password": password})),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        body["access_token"].as_str().unwrap().to_owned()
    }

    #[tokio::test]
    async fn test_note_version_and_approval_state_machine() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("note_admin_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "SECRET_KEY".to_owned(),
                "rust-integration-secret".to_owned(),
            ),
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
        let admin = login(&app, &admin_username, "RustAdmin123!").await;
        let writer_name = format!("note_writer_{suffix}");
        let reviewer_name = format!("note_reviewer_{suffix}");
        let (_, writer) = call(
            &app,
            "POST",
            "/users",
            Some(&admin),
            Some(json!({
                "username": writer_name,
                "password": "WriterPass123!",
                "display_name": "Writer"
            })),
        )
        .await;
        let (_, reviewer) = call(
            &app,
            "POST",
            "/users",
            Some(&admin),
            Some(json!({
                "username": reviewer_name,
                "password": "ReviewerPass123!",
                "display_name": "Reviewer"
            })),
        )
        .await;
        let writer_id = writer["id"].as_i64().unwrap();
        let reviewer_id = reviewer["id"].as_i64().unwrap();
        let (_, project) = call(
            &app,
            "POST",
            "/projects",
            Some(&admin),
            Some(json!({
                "name": format!("Note Project {suffix}"),
                "approval_enabled": true
            })),
        )
        .await;
        let project_id = project["id"].as_i64().unwrap();
        call(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&admin),
            Some(json!({
                "user_id": writer_id,
                "project_role": "member",
                "can_read": true,
                "can_write": true
            })),
        )
        .await;
        call(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&admin),
            Some(json!({
                "user_id": reviewer_id,
                "project_role": "reviewer",
                "can_read": true,
                "can_write": false,
                "can_review": true
            })),
        )
        .await;
        let writer_token = login(&app, &writer_name, "WriterPass123!").await;
        let reviewer_token = login(&app, &reviewer_name, "ReviewerPass123!").await;

        let (created_status, created) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/notes"),
            Some(&writer_token),
            Some(json!({
                "title": "PCR draft",
                "experiment_type": "PCR",
                "fixed_fields_json": {"reagents": "Taq"},
                "content_json": {"text": "Initial result"}
            })),
        )
        .await;
        assert_eq!(created_status, StatusCode::OK);
        assert_eq!(created["status"], "draft");
        let note_id = created["id"].as_i64().unwrap();

        let (updated_status, updated) = call(
            &app,
            "PATCH",
            &format!("/notes/{note_id}"),
            Some(&writer_token),
            Some(json!({
                "title": "PCR updated",
                "content_json": {"text": "Updated result"},
                "change_summary": "second version"
            })),
        )
        .await;
        assert_eq!(updated_status, StatusCode::OK);
        assert_eq!(updated["title"], "PCR updated");
        let (versions_status, versions) = call(
            &app,
            "GET",
            &format!("/notes/{note_id}/versions"),
            Some(&writer_token),
            None,
        )
        .await;
        assert_eq!(versions_status, StatusCode::OK);
        assert_eq!(versions.as_array().unwrap().len(), 2);
        assert_eq!(versions[0]["version_number"], 2);

        let (submitted, body) = call(
            &app,
            "POST",
            &format!("/notes/{note_id}/submit"),
            Some(&writer_token),
            None,
        )
        .await;
        assert_eq!(submitted, StatusCode::OK);
        assert_eq!(body["status"], "submitted");

        let (pending_status, pending) = call(
            &app,
            "GET",
            "/approvals/pending",
            Some(&reviewer_token),
            None,
        )
        .await;
        assert_eq!(pending_status, StatusCode::OK);
        assert!(pending
            .as_array()
            .unwrap()
            .iter()
            .any(|item| item["id"] == note_id));

        let (approved, body) = call(
            &app,
            "POST",
            &format!("/notes/{note_id}/approve"),
            Some(&reviewer_token),
            Some(json!({"comment": "Looks good"})),
        )
        .await;
        assert_eq!(approved, StatusCode::OK);
        assert_eq!(body["status"], "approved");

        let (graph_status, graph) = call(
            &app,
            "GET",
            &format!("/notes/{note_id}/kg/graph"),
            Some(&writer_token),
            None,
        )
        .await;
        assert_eq!(graph_status, StatusCode::OK);
        assert!(graph["entities"].as_array().unwrap().len() >= 5);
        assert!(graph["relations"]
            .as_array()
            .unwrap()
            .iter()
            .any(|relation| relation["relation_type"] == "uses_reagent"));

        let (approvals_status, approvals) = call(
            &app,
            "GET",
            &format!("/notes/{note_id}/approvals"),
            Some(&writer_token),
            None,
        )
        .await;
        assert_eq!(approvals_status, StatusCode::OK);
        assert_eq!(approvals[0]["action"], "approved");

        let (immutable, body) = call(
            &app,
            "PATCH",
            &format!("/notes/{note_id}"),
            Some(&writer_token),
            Some(json!({"title": "Forbidden edit"})),
        )
        .await;
        assert_eq!(immutable, StatusCode::CONFLICT);
        assert_eq!(body["detail"], "Only draft or returned notes can be edited");
    }

    #[tokio::test]
    async fn test_pending_approvals_excludes_independent_reviewer_note_metadata() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("pending_guard_admin_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "SECRET_KEY".to_owned(),
                "rust-integration-secret".to_owned(),
            ),
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
        let admin_token = login(&app, &admin_username, "RustAdmin123!").await;

        let writer_name = format!("pending_guard_writer_{suffix}");
        let reviewer_name = format!("pending_guard_reviewer_{suffix}");
        let (writer_status, writer) = call(
            &app,
            "POST",
            "/users",
            Some(&admin_token),
            Some(json!({
                "username": writer_name,
                "password": "WriterPass123!",
                "display_name": "Pending Guard Writer",
                "role": "member"
            })),
        )
        .await;
        assert_eq!(writer_status, StatusCode::OK);
        let (reviewer_status, reviewer) = call(
            &app,
            "POST",
            "/users",
            Some(&admin_token),
            Some(json!({
                "username": reviewer_name,
                "password": "ReviewerPass123!",
                "display_name": "Pending Guard Reviewer",
                "role": "reviewer"
            })),
        )
        .await;
        assert_eq!(reviewer_status, StatusCode::OK);
        let writer_id = writer["id"].as_i64().unwrap();
        let reviewer_id = reviewer["id"].as_i64().unwrap();

        let (project_status, project) = call(
            &app,
            "POST",
            "/projects",
            Some(&admin_token),
            Some(json!({
                "name": format!("Pending Guard Project {suffix}"),
                "description": "must stay hidden from independent reviewer",
                "is_sensitive": true,
                "approval_enabled": true,
                "owner_user_id": writer_id
            })),
        )
        .await;
        assert_eq!(project_status, StatusCode::OK);
        let project_id = project["id"].as_i64().unwrap();
        let (reviewer_added, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&admin_token),
            Some(json!({"user_id": reviewer_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(reviewer_added, StatusCode::OK);

        let writer_token = login(&app, &writer_name, "WriterPass123!").await;
        let reviewer_token = login(&app, &reviewer_name, "ReviewerPass123!").await;
        let (note_status, note) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/notes"),
            Some(&writer_token),
            Some(json!({
                "title": "Secret experiment title",
                "experiment_type": "Secret method",
                "fixed_fields_json": {},
                "content_json": {"text": "Secret result"}
            })),
        )
        .await;
        assert_eq!(note_status, StatusCode::OK);
        let note_id = note["id"].as_i64().unwrap();
        let (submitted, _) = call(
            &app,
            "POST",
            &format!("/notes/{note_id}/submit"),
            Some(&writer_token),
            None,
        )
        .await;
        assert_eq!(submitted, StatusCode::OK);

        let (pending_status, pending) = call(
            &app,
            "GET",
            "/approvals/pending",
            Some(&reviewer_token),
            None,
        )
        .await;
        assert_eq!(pending_status, StatusCode::OK);
        assert!(
            pending
                .as_array()
                .unwrap()
                .iter()
                .all(|item| item["id"] != note_id),
            "independent reviewer received ordinary NoteRead metadata"
        );
    }

    #[tokio::test]
    async fn test_archive_and_void_recheck_concurrent_note_transitions() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("note_concurrency_admin_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "SECRET_KEY".to_owned(),
                "rust-note-concurrency-secret".to_owned(),
            ),
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
        let app = build_app(AppState::new(pool.clone(), settings).unwrap());
        let admin = login(&app, &admin_username, "RustAdmin123!").await;
        let (project_status, project) = call(
            &app,
            "POST",
            "/projects",
            Some(&admin),
            Some(json!({
                "name": format!("Note concurrency project {suffix}"),
                "approval_enabled": true
            })),
        )
        .await;
        assert_eq!(project_status, StatusCode::OK);
        let project_id = project["id"].as_i64().unwrap();

        let (draft_status, draft) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/notes"),
            Some(&admin),
            Some(json!({
                "title": "Archive race",
                "experiment_type": "Concurrency",
                "fixed_fields_json": {},
                "content_json": {"text": "archive versus submit"}
            })),
        )
        .await;
        assert_eq!(draft_status, StatusCode::OK);
        let archive_note_id = draft["id"].as_i64().unwrap();
        let (archive_reached, archive_resume) =
            super::install_concurrency_pause("archive_note", archive_note_id as i32).await;
        let archive_app = app.clone();
        let archive_admin = admin.clone();
        let archive_task = tokio::spawn(async move {
            call(
                &archive_app,
                "POST",
                &format!("/notes/{archive_note_id}/archive"),
                Some(&archive_admin),
                None,
            )
            .await
        });
        if timeout(Duration::from_secs(5), archive_reached.notified())
            .await
            .is_err()
        {
            archive_resume.notify_one();
            panic!("archive did not reach the concurrency pause");
        }
        let (submit_status, _) = call(
            &app,
            "POST",
            &format!("/notes/{archive_note_id}/submit"),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(submit_status, StatusCode::OK);
        archive_resume.notify_one();
        let (archive_status, _) = archive_task.await.unwrap();
        let archived_race_status: String =
            sqlx::query_scalar("SELECT lower(status::text) FROM experiment_notes WHERE id = $1")
                .bind(archive_note_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(archive_status, StatusCode::CONFLICT);
        assert_eq!(archived_race_status, "submitted");

        let (void_draft_status, void_draft) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/notes"),
            Some(&admin),
            Some(json!({
                "title": "Void race",
                "experiment_type": "Concurrency",
                "fixed_fields_json": {},
                "content_json": {"text": "void versus return"}
            })),
        )
        .await;
        assert_eq!(void_draft_status, StatusCode::OK);
        let void_note_id = void_draft["id"].as_i64().unwrap();
        let (void_submit_status, _) = call(
            &app,
            "POST",
            &format!("/notes/{void_note_id}/submit"),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(void_submit_status, StatusCode::OK);
        let (void_reached, void_resume) =
            super::install_concurrency_pause("void_note", void_note_id as i32).await;
        let void_app = app.clone();
        let void_admin = admin.clone();
        let void_task = tokio::spawn(async move {
            call(
                &void_app,
                "POST",
                &format!("/notes/{void_note_id}/void"),
                Some(&void_admin),
                Some(json!({"comment": "void request"})),
            )
            .await
        });
        if timeout(Duration::from_secs(5), void_reached.notified())
            .await
            .is_err()
        {
            void_resume.notify_one();
            panic!("void did not reach the concurrency pause");
        }
        let (return_status, _) = call(
            &app,
            "POST",
            &format!("/notes/{void_note_id}/return"),
            Some(&admin),
            Some(json!({"comment": "concurrent return"})),
        )
        .await;
        assert_eq!(return_status, StatusCode::OK);
        void_resume.notify_one();
        let (void_status, _) = void_task.await.unwrap();
        let voided_race_status: String =
            sqlx::query_scalar("SELECT lower(status::text) FROM experiment_notes WHERE id = $1")
                .bind(void_note_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(void_status, StatusCode::CONFLICT);
        assert_eq!(voided_race_status, "returned");
    }
}
