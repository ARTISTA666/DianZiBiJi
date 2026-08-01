use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use serde_json::json;
use sqlx::{FromRow, Postgres, Transaction};

use crate::{
    api::auth::CurrentUser,
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{OcrCorrectionRequest, OcrJobRequest, OcrJobResult, UserRecord},
    ocr::{extract_text, OcrError, OcrSource},
    permissions::{can_review_project, require_project_access},
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

#[derive(Debug, FromRow)]
struct OcrResultRow {
    id: i32,
    file_id: i32,
    raw_text: String,
    corrected_text: String,
    extraction_method: String,
    character_count: i32,
    truncated: bool,
    review_status: String,
    created_by: i32,
    reviewed_by: Option<i32>,
    created_at: DateTime<Utc>,
    reviewed_at: Option<DateTime<Utc>>,
}

impl From<OcrResultRow> for OcrJobResult {
    fn from(row: OcrResultRow) -> Self {
        Self {
            ocr_result_id: row.id,
            file_id: row.file_id,
            extracted_text: row.corrected_text,
            raw_text: row.raw_text,
            source_ids: vec![row.file_id.to_string()],
            character_count: row.character_count,
            truncated: row.truncated,
            extraction_method: row.extraction_method,
            review_status: row.review_status,
            created_by: row.created_by,
            reviewed_by: row.reviewed_by,
            created_at: row.created_at,
            reviewed_at: row.reviewed_at,
        }
    }
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/ocr/extract", post(extract_ocr))
        .route("/api/ocr/files/{file_id}/latest", get(get_latest_result))
        .route("/api/ocr/results/{result_id}/confirm", post(confirm_result))
}

async fn extract_ocr(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Json(payload): Json<OcrJobRequest>,
) -> Result<Json<OcrJobResult>, ApiError> {
    let source = fetch_source(&state, payload.file_id).await?;
    require_project_access(&state.pool, &user, source.project_id).await?;
    let extracted = extract_text(
        &state.settings,
        &OcrSource {
            file_id: payload.file_id,
            original_filename: source.original_filename,
            storage_path: source.storage_path,
        },
    )
    .await
    .map_err(map_ocr_error)?;
    let mut transaction = state.pool.begin().await?;
    let current_file_hash = lock_source_file(&mut transaction, payload.file_id).await?;
    if current_file_hash != source.file_hash {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "The source file changed during extraction",
        ));
    }
    let result_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO file_ocr_results (
            file_id, project_id, created_by, file_hash, raw_text, corrected_text,
            extraction_method, character_count, truncated, review_status,
            reviewed_by, created_at, reviewed_at
        )
        VALUES ($1, $2, $3, $4, $5, $5, $6, $7, $8, 'pending_review', NULL, now(), NULL)
        RETURNING id
        "#,
    )
    .bind(payload.file_id)
    .bind(source.project_id)
    .bind(user.id)
    .bind(source.file_hash)
    .bind(&extracted.text)
    .bind(&extracted.extraction_method)
    .bind(extracted.character_count)
    .bind(extracted.truncated)
    .fetch_one(&mut *transaction)
    .await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(source.project_id),
            action: "extract_file_text",
            target_type: Some("file"),
            target_id: Some(payload.file_id),
            detail: json!({
                "extraction_method": extracted.extraction_method,
                "character_count": extracted.character_count,
                "truncated": extracted.truncated,
                "ocr_result_id": result_id,
                "review_status": "pending_review"
            }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_result(&state, result_id).await?.into()))
}

async fn get_latest_result(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(file_id): Path<i32>,
) -> Result<Json<OcrJobResult>, ApiError> {
    let source = fetch_source(&state, file_id).await?;
    require_project_access(&state.pool, &user, source.project_id).await?;
    let result = query_result(
        &state,
        "WHERE file_id = $1 ORDER BY id DESC LIMIT 1",
        file_id,
    )
    .await?
    .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "No text extraction result found"))?;
    Ok(Json(result.into()))
}

async fn confirm_result(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(result_id): Path<i32>,
    Json(payload): Json<OcrCorrectionRequest>,
) -> Result<Json<OcrJobResult>, ApiError> {
    if payload.corrected_text.is_empty() || payload.corrected_text.chars().count() > 2_000_000 {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Invalid corrected text length",
        ));
    }
    let context = sqlx::query_as::<_, OcrContext>(
        r#"
        SELECT r.file_id, r.project_id, r.file_hash AS result_file_hash,
               r.review_status, r.raw_text
        FROM file_ocr_results r
        WHERE r.id = $1
        "#,
    )
    .bind(result_id)
    .fetch_optional(&state.pool)
    .await?
    .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Text extraction result not found"))?;
    require_project_access(&state.pool, &user, context.project_id).await?;
    require_review(&state, &user, context.project_id).await?;
    let corrected_text = payload.corrected_text.trim().to_owned();
    if corrected_text.chars().count() > state.settings.document_text_max_chars {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Corrected text is too long",
        ));
    }
    let corrected_count =
        i32::try_from(corrected_text.chars().count()).map_err(ApiError::internal)?;
    let mut transaction = state.pool.begin().await?;
    let current_file_hash = lock_source_file(&mut transaction, context.file_id).await?;
    let locked_context = lock_ocr_result(&mut transaction, result_id, context.file_id).await?;
    let latest_id: i32 = sqlx::query_scalar(
        "SELECT id FROM file_ocr_results WHERE file_id = $1 ORDER BY id DESC LIMIT 1",
    )
    .bind(locked_context.file_id)
    .fetch_one(&mut *transaction)
    .await?;
    if latest_id != result_id {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "A newer extraction result exists",
        ));
    }
    if locked_context.review_status == "confirmed" {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Text extraction result is already confirmed",
        ));
    }
    if locked_context.result_file_hash != current_file_hash {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "The source file has changed",
        ));
    }
    #[cfg(test)]
    pause_for_concurrency_test("confirm_result", result_id).await;
    let result = sqlx::query(
        r#"
        UPDATE file_ocr_results
        SET corrected_text = $2, character_count = $3, review_status = 'confirmed',
            reviewed_by = $4, reviewed_at = now()
        WHERE id = $1 AND review_status <> 'confirmed'
        "#,
    )
    .bind(result_id)
    .bind(&corrected_text)
    .bind(corrected_count)
    .bind(user.id)
    .execute(&mut *transaction)
    .await?;
    if result.rows_affected() != 1 {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Text extraction result is already confirmed",
        ));
    }
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(locked_context.project_id),
            action: "confirm_file_ocr",
            target_type: Some("file_ocr_result"),
            target_id: Some(result_id),
            detail: json!({
                "file_id": locked_context.file_id,
                "raw_character_count": locked_context.raw_text.chars().count(),
                "corrected_character_count": corrected_count
            }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_result(&state, result_id).await?.into()))
}

#[derive(Debug, FromRow)]
struct SourceContext {
    project_id: i32,
    original_filename: String,
    storage_path: String,
    file_hash: String,
}

#[derive(Debug, FromRow)]
struct OcrContext {
    file_id: i32,
    project_id: i32,
    result_file_hash: String,
    review_status: String,
    raw_text: String,
}

async fn lock_source_file(
    transaction: &mut Transaction<'_, Postgres>,
    file_id: i32,
) -> Result<String, ApiError> {
    sqlx::query_scalar("SELECT file_hash FROM files WHERE id = $1 FOR UPDATE")
        .bind(file_id)
        .fetch_optional(&mut **transaction)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "File not found"))
}

async fn lock_ocr_result(
    transaction: &mut Transaction<'_, Postgres>,
    result_id: i32,
    file_id: i32,
) -> Result<OcrContext, ApiError> {
    sqlx::query_as::<_, OcrContext>(
        r#"
        SELECT file_id, project_id, file_hash AS result_file_hash, review_status, raw_text
        FROM file_ocr_results
        WHERE id = $1 AND file_id = $2
        FOR UPDATE
        "#,
    )
    .bind(result_id)
    .bind(file_id)
    .fetch_optional(&mut **transaction)
    .await?
    .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Text extraction result not found"))
}

async fn fetch_source(state: &AppState, file_id: i32) -> Result<SourceContext, ApiError> {
    sqlx::query_as(
        "SELECT project_id, original_filename, storage_path, file_hash FROM files WHERE id = $1",
    )
    .bind(file_id)
    .fetch_optional(&state.pool)
    .await?
    .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "File not found"))
}

async fn fetch_result(state: &AppState, result_id: i32) -> Result<OcrResultRow, ApiError> {
    query_result(state, "WHERE id = $1", result_id)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Text extraction result not found"))
}

async fn query_result(
    state: &AppState,
    suffix: &str,
    id: i32,
) -> Result<Option<OcrResultRow>, ApiError> {
    let query = format!(
        r#"
        SELECT id, file_id, raw_text, corrected_text, extraction_method,
               character_count, truncated, review_status, created_by,
               reviewed_by, created_at, reviewed_at
        FROM file_ocr_results {suffix}
        "#
    );
    Ok(sqlx::query_as::<_, OcrResultRow>(&query)
        .bind(id)
        .fetch_optional(&state.pool)
        .await?)
}

async fn require_review(
    state: &AppState,
    user: &UserRecord,
    project_id: i32,
) -> Result<(), ApiError> {
    if can_review_project(&state.pool, user, project_id).await? {
        Ok(())
    } else {
        Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "File review permission required",
        ))
    }
}

fn map_ocr_error(error: OcrError) -> ApiError {
    match error {
        OcrError::NotFound(detail) => ApiError::new(StatusCode::NOT_FOUND, detail),
        OcrError::Unsupported(detail) => ApiError::new(StatusCode::UNPROCESSABLE_ENTITY, detail),
        OcrError::Internal(detail) => ApiError::internal(detail),
    }
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
    use tokio::time::{sleep, timeout};
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
        content_type: Option<&str>,
        body: Vec<u8>,
    ) -> (StatusCode, Vec<u8>) {
        let mut request = Request::builder().method(method).uri(path);
        if let Some(token) = token {
            request = request.header("authorization", format!("Bearer {token}"));
        }
        if let Some(content_type) = content_type {
            request = request.header("content-type", content_type);
        }
        let response = app
            .clone()
            .oneshot(request.body(Body::from(body)).unwrap())
            .await
            .unwrap();
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
        (status, bytes.to_vec())
    }

    async fn json_call(
        app: &Router,
        method: &str,
        path: &str,
        token: Option<&str>,
        body: Option<Value>,
    ) -> (StatusCode, Value) {
        let (status, bytes) = call(
            app,
            method,
            path,
            token,
            body.as_ref().map(|_| "application/json"),
            body.map_or_else(Vec::new, |value| value.to_string().into_bytes()),
        )
        .await;
        let body = if bytes.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&bytes).unwrap()
        };
        (status, body)
    }

    #[tokio::test]
    async fn test_text_extraction_latest_and_confirmation() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("ocr_admin_{suffix}");
        let storage = tempfile::tempdir().unwrap();
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            ("SECRET_KEY".to_owned(), "rust-ocr-secret".to_owned()),
            (
                "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                admin_username.clone(),
            ),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustAdmin123!".to_owned(),
            ),
            (
                "STORAGE_ROOT".to_owned(),
                storage.path().to_string_lossy().into_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let app = build_app(AppState::new(pool, settings).unwrap());
        let (_, login) = json_call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": admin_username, "password": "RustAdmin123!"})),
        )
        .await;
        let admin = login["access_token"].as_str().unwrap();
        let (_, project) = json_call(
            &app,
            "POST",
            "/projects",
            Some(admin),
            Some(json!({"name": format!("OCR Project {suffix}")})),
        )
        .await;
        let project_id = project["id"].as_i64().unwrap();
        let boundary = "eln-ocr-boundary";
        let multipart = format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"upload\"; filename=\"notes.txt\"\r\nContent-Type: text/plain\r\n\r\nexperiment temperature 58 C\r\n--{boundary}--\r\n"
        );
        let (_, uploaded) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/files?file_category=note_attachment"),
            Some(admin),
            Some(&format!("multipart/form-data; boundary={boundary}")),
            multipart.into_bytes(),
        )
        .await;
        let uploaded: Value = serde_json::from_slice(&uploaded).unwrap();
        let file_id = uploaded["id"].as_i64().unwrap();

        let (extract_status, extracted) = json_call(
            &app,
            "POST",
            "/api/ocr/extract",
            Some(admin),
            Some(json!({"file_id": file_id})),
        )
        .await;
        assert_eq!(extract_status, StatusCode::OK);
        assert_eq!(extracted["extraction_method"], "plain_text");
        assert_eq!(extracted["extracted_text"], "experiment temperature 58 C");
        assert_eq!(extracted["review_status"], "pending_review");
        let result_id = extracted["ocr_result_id"].as_i64().unwrap();

        let (confirm_status, confirmed) = json_call(
            &app,
            "POST",
            &format!("/api/ocr/results/{result_id}/confirm"),
            Some(admin),
            Some(json!({"corrected_text": "experiment temperature 58 °C"})),
        )
        .await;
        assert_eq!(confirm_status, StatusCode::OK);
        assert_eq!(confirmed["review_status"], "confirmed");
        assert_eq!(confirmed["raw_text"], "experiment temperature 58 C");
        assert_eq!(confirmed["extracted_text"], "experiment temperature 58 °C");
        let (_, latest) = json_call(
            &app,
            "GET",
            &format!("/api/ocr/files/{file_id}/latest"),
            Some(admin),
            None,
        )
        .await;
        assert_eq!(latest["ocr_result_id"], result_id);
        let (duplicate, _) = json_call(
            &app,
            "POST",
            &format!("/api/ocr/results/{result_id}/confirm"),
            Some(admin),
            Some(json!({"corrected_text": "again"})),
        )
        .await;
        assert_eq!(duplicate, StatusCode::CONFLICT);
    }

    #[tokio::test]
    async fn test_confirm_serializes_with_a_new_extraction_for_the_same_file() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("ocr_concurrency_admin_{suffix}");
        let storage = tempfile::tempdir().unwrap();
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "SECRET_KEY".to_owned(),
                "rust-ocr-concurrency-secret".to_owned(),
            ),
            (
                "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                admin_username.clone(),
            ),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustAdmin123!".to_owned(),
            ),
            (
                "STORAGE_ROOT".to_owned(),
                storage.path().to_string_lossy().into_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let app = build_app(AppState::new(pool.clone(), settings).unwrap());
        let (_, login) = json_call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": admin_username, "password": "RustAdmin123!"})),
        )
        .await;
        let admin = login["access_token"].as_str().unwrap().to_owned();
        let (_, project) = json_call(
            &app,
            "POST",
            "/projects",
            Some(&admin),
            Some(json!({"name": format!("OCR concurrency project {suffix}")})),
        )
        .await;
        let project_id = project["id"].as_i64().unwrap();
        let boundary = "eln-ocr-concurrency-boundary";
        let multipart = format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"upload\"; filename=\"race.txt\"\r\nContent-Type: text/plain\r\n\r\nconcurrent extraction\r\n--{boundary}--\r\n"
        );
        let (_, uploaded) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/files?file_category=note_attachment"),
            Some(&admin),
            Some(&format!("multipart/form-data; boundary={boundary}")),
            multipart.into_bytes(),
        )
        .await;
        let uploaded: Value = serde_json::from_slice(&uploaded).unwrap();
        let file_id = uploaded["id"].as_i64().unwrap();
        let (first_status, first) = json_call(
            &app,
            "POST",
            "/api/ocr/extract",
            Some(&admin),
            Some(json!({"file_id": file_id})),
        )
        .await;
        assert_eq!(first_status, StatusCode::OK);
        let result_id = first["ocr_result_id"].as_i64().unwrap();
        let (reached, resume) =
            super::install_concurrency_pause("confirm_result", result_id as i32).await;

        let confirm_app = app.clone();
        let confirm_admin = admin.clone();
        let confirm_task = tokio::spawn(async move {
            json_call(
                &confirm_app,
                "POST",
                &format!("/api/ocr/results/{result_id}/confirm"),
                Some(&confirm_admin),
                Some(json!({"corrected_text": "confirmed before next extraction"})),
            )
            .await
        });
        if timeout(Duration::from_secs(5), reached.notified())
            .await
            .is_err()
        {
            resume.notify_one();
            panic!("confirmation did not reach the concurrency pause");
        }

        let extract_app = app.clone();
        let extract_admin = admin.clone();
        let extract_task = tokio::spawn(async move {
            json_call(
                &extract_app,
                "POST",
                "/api/ocr/extract",
                Some(&extract_admin),
                Some(json!({"file_id": file_id})),
            )
            .await
        });
        let inserted_while_confirm_paused = timeout(Duration::from_secs(1), async {
            loop {
                let count: i64 =
                    sqlx::query_scalar("SELECT count(*) FROM file_ocr_results WHERE file_id = $1")
                        .bind(file_id)
                        .fetch_one(&pool)
                        .await
                        .unwrap();
                if count > 1 {
                    break;
                }
                sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .is_ok();
        resume.notify_one();

        let (confirm_status, _) = confirm_task.await.unwrap();
        let (extract_status, _) = extract_task.await.unwrap();
        assert_eq!(confirm_status, StatusCode::OK);
        assert_eq!(extract_status, StatusCode::OK);
        assert!(
            !inserted_while_confirm_paused,
            "a new extraction committed while confirmation held the per-file critical section"
        );
    }
}
