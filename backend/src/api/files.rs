use std::path::{Path as FilePath, PathBuf};

use axum::{
    body::Body,
    extract::{Multipart, Path, Query, State},
    http::{header, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde_json::json;
use sha2::{Digest, Sha256};
use sqlx::FromRow;
use tokio::io::AsyncWriteExt;
use uuid::Uuid;

use crate::{
    api::auth::CurrentUser,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{FileRead, FileReviewRequest, FileUpdate, FileUploadQuery, UserRecord},
    permissions::{can_review_project, can_write_project, require_project_access},
    AppState,
};

const FILE_COLUMNS: &str = r#"
    id, project_id, note_id, uploaded_by,
    lower(file_category::text) AS file_category, original_filename,
    storage_path, mime_type, file_size, file_hash,
    lower(status::text) AS status, knowledge_sync_status,
    knowledge_synced_at, knowledge_sync_message, created_at
"#;

#[derive(Clone, Debug, FromRow)]
struct StoredFileRecord {
    id: i32,
    project_id: i32,
    note_id: Option<i32>,
    uploaded_by: i32,
    file_category: String,
    original_filename: String,
    storage_path: String,
    mime_type: Option<String>,
    file_size: i32,
    file_hash: String,
    status: String,
    knowledge_sync_status: String,
    knowledge_synced_at: Option<chrono::DateTime<chrono::Utc>>,
    knowledge_sync_message: Option<String>,
    created_at: chrono::DateTime<chrono::Utc>,
}

impl From<StoredFileRecord> for FileRead {
    fn from(record: StoredFileRecord) -> Self {
        Self {
            id: record.id,
            project_id: record.project_id,
            note_id: record.note_id,
            uploaded_by: record.uploaded_by,
            file_category: record.file_category,
            original_filename: record.original_filename,
            mime_type: record.mime_type,
            file_size: record.file_size,
            file_hash: record.file_hash,
            status: record.status,
            knowledge_sync_status: record.knowledge_sync_status,
            knowledge_synced_at: record.knowledge_synced_at,
            knowledge_sync_message: record.knowledge_sync_message,
            created_at: record.created_at,
        }
    }
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route(
            "/projects/{project_id}/files",
            get(list_project_files).post(upload_project_file),
        )
        .route(
            "/projects/{project_id}/documents",
            get(list_project_documents).post(upload_project_document),
        )
        .route("/notes/{note_id}/files", get(list_note_files))
        .route("/files/{file_id}", get(get_file).patch(update_file))
        .route("/files/{file_id}/archive", post(archive_file))
        .route("/files/{file_id}/review", post(review_file))
        .route("/documents/{file_id}/approve", post(approve_document))
        .route("/documents/{file_id}/reject", post(reject_document))
        .route("/files/{file_id}/download", get(download_file))
}

async fn upload_project_file(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Query(query): Query<FileUploadQuery>,
    multipart: Multipart,
) -> Result<Json<FileRead>, ApiError> {
    upload_file(
        &state,
        &user,
        project_id,
        &query.file_category,
        query.note_id,
        multipart,
    )
    .await
}

async fn upload_project_document(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    multipart: Multipart,
) -> Result<Json<FileRead>, ApiError> {
    upload_file(
        &state,
        &user,
        project_id,
        "knowledge_document",
        None,
        multipart,
    )
    .await
}

async fn upload_file(
    state: &AppState,
    user: &UserRecord,
    project_id: i32,
    file_category: &str,
    note_id: Option<i32>,
    mut multipart: Multipart,
) -> Result<Json<FileRead>, ApiError> {
    require_project_access(&state.pool, user, project_id).await?;
    require_write(state, user, project_id).await?;
    if !matches!(file_category, "knowledge_document" | "note_attachment") {
        return Err(ApiError::new(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Unsupported file category",
        ));
    }
    if let Some(note_id) = note_id {
        let valid: bool = sqlx::query_scalar(
            "SELECT EXISTS(SELECT 1 FROM experiment_notes WHERE id = $1 AND project_id = $2)",
        )
        .bind(note_id)
        .bind(project_id)
        .fetch_one(&state.pool)
        .await?;
        if !valid {
            return Err(ApiError::new(StatusCode::NOT_FOUND, "Note not found"));
        }
    }

    let stored = store_upload(
        &mut multipart,
        project_id,
        state.settings.upload_max_bytes,
        &state.settings.storage_root,
    )
    .await?;
    let knowledge_sync_status = if file_category == "knowledge_document" {
        "pending_review"
    } else {
        "not_applicable"
    };
    let knowledge_sync_message = (file_category == "knowledge_document")
        .then_some("等待资料审核，审核通过后进入知识库同步队列");
    let mut transaction = state.pool.begin().await?;
    let inserted = sqlx::query_scalar::<_, i32>(
        r#"
        INSERT INTO files (
            project_id, note_id, uploaded_by, file_category, original_filename,
            storage_path, mime_type, file_size, file_hash, status,
            knowledge_sync_status, knowledge_synced_at, knowledge_sync_message,
            created_at
        )
        VALUES (
            $1, $2, $3, upper($4)::filecategory, $5, $6, $7, $8, $9,
            'UPLOADED'::filestatus, $10, NULL, $11, now()
        )
        RETURNING id
        "#,
    )
    .bind(project_id)
    .bind(note_id)
    .bind(user.id)
    .bind(file_category)
    .bind(&stored.original_filename)
    .bind(stored.path.to_string_lossy().as_ref())
    .bind(&stored.mime_type)
    .bind(stored.size)
    .bind(&stored.hash)
    .bind(knowledge_sync_status)
    .bind(knowledge_sync_message)
    .fetch_one(&mut *transaction)
    .await;
    let file_id = match inserted {
        Ok(file_id) => file_id,
        Err(error) => {
            let _ = tokio::fs::remove_file(&stored.path).await;
            return Err(error.into());
        }
    };
    if let Err(error) = write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "upload_file",
            target_type: Some("file"),
            target_id: Some(file_id),
            detail: json!({}),
        },
    )
    .await
    {
        let _ = tokio::fs::remove_file(&stored.path).await;
        return Err(error.into());
    }
    if let Err(error) = transaction.commit().await {
        let _ = tokio::fs::remove_file(&stored.path).await;
        return Err(error.into());
    }
    Ok(Json(fetch_file(&state.pool, file_id).await?.into()))
}

struct StoredUpload {
    original_filename: String,
    path: PathBuf,
    mime_type: Option<String>,
    size: i32,
    hash: String,
}

async fn store_upload(
    multipart: &mut Multipart,
    project_id: i32,
    max_bytes: usize,
    storage_root: &str,
) -> Result<StoredUpload, ApiError> {
    while let Some(mut field) = multipart
        .next_field()
        .await
        .map_err(|error| ApiError::new(StatusCode::BAD_REQUEST, error.to_string()))?
    {
        if field.name() != Some("upload") {
            continue;
        }
        let original_filename = field.file_name().unwrap_or("file").to_owned();
        let mime_type = field.content_type().map(str::to_owned);
        let suffix = FilePath::new(&original_filename)
            .extension()
            .and_then(|extension| extension.to_str())
            .filter(|extension| {
                extension.len() <= 20
                    && extension
                        .chars()
                        .all(|character| character.is_alphanumeric())
            })
            .map(|extension| format!(".{extension}"))
            .unwrap_or_default();
        let directory = PathBuf::from(storage_root)
            .join("projects")
            .join(project_id.to_string());
        tokio::fs::create_dir_all(&directory)
            .await
            .map_err(ApiError::internal)?;
        let path = directory.join(format!("{}{}", Uuid::new_v4().simple(), suffix));
        let mut output = tokio::fs::File::create(&path)
            .await
            .map_err(ApiError::internal)?;
        let mut digest = Sha256::new();
        let mut size = 0usize;
        loop {
            let chunk = match field.chunk().await {
                Ok(chunk) => chunk,
                Err(error) => {
                    drop(output);
                    let _ = tokio::fs::remove_file(&path).await;
                    return Err(ApiError::new(StatusCode::BAD_REQUEST, error.to_string()));
                }
            };
            let Some(chunk) = chunk else {
                break;
            };
            size = size.saturating_add(chunk.len());
            if size > max_bytes {
                drop(output);
                let _ = tokio::fs::remove_file(&path).await;
                return Err(ApiError::new(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    format!("File exceeds upload limit of {max_bytes} bytes"),
                ));
            }
            digest.update(&chunk);
            if let Err(error) = output.write_all(&chunk).await {
                drop(output);
                let _ = tokio::fs::remove_file(&path).await;
                return Err(ApiError::internal(error));
            }
        }
        output.flush().await.map_err(ApiError::internal)?;
        let size = i32::try_from(size).map_err(ApiError::internal)?;
        return Ok(StoredUpload {
            original_filename,
            path,
            mime_type,
            size,
            hash: format!("{:x}", digest.finalize()),
        });
    }
    Err(ApiError::new(
        StatusCode::UNPROCESSABLE_ENTITY,
        "Upload file is required",
    ))
}

async fn list_project_files(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<Vec<FileRead>>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    Ok(Json(
        list_files(&state, "project_id = $1", project_id)
            .await?
            .into_iter()
            .map(Into::into)
            .collect(),
    ))
}

async fn list_project_documents(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<Vec<FileRead>>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    let query = format!(
        "SELECT {FILE_COLUMNS} FROM files WHERE project_id = $1 AND file_category = 'KNOWLEDGE_DOCUMENT'::filecategory ORDER BY created_at DESC"
    );
    let records = sqlx::query_as::<_, StoredFileRecord>(&query)
        .bind(project_id)
        .fetch_all(&state.pool)
        .await?;
    Ok(Json(records.into_iter().map(Into::into).collect()))
}

async fn list_note_files(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(note_id): Path<i32>,
) -> Result<Json<Vec<FileRead>>, ApiError> {
    let project_id: i32 =
        sqlx::query_scalar("SELECT project_id FROM experiment_notes WHERE id = $1")
            .bind(note_id)
            .fetch_optional(&state.pool)
            .await?
            .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Note not found"))?;
    require_project_access(&state.pool, &user, project_id).await?;
    Ok(Json(
        list_files(&state, "note_id = $1", note_id)
            .await?
            .into_iter()
            .map(Into::into)
            .collect(),
    ))
}

async fn list_files(
    state: &AppState,
    predicate: &str,
    id: i32,
) -> Result<Vec<StoredFileRecord>, ApiError> {
    let query =
        format!("SELECT {FILE_COLUMNS} FROM files WHERE {predicate} ORDER BY created_at DESC");
    Ok(sqlx::query_as::<_, StoredFileRecord>(&query)
        .bind(id)
        .fetch_all(&state.pool)
        .await?)
}

async fn get_file(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(file_id): Path<i32>,
) -> Result<Json<FileRead>, ApiError> {
    Ok(Json(require_file(&state, &user, file_id).await?.into()))
}

async fn update_file(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(file_id): Path<i32>,
    Json(payload): Json<FileUpdate>,
) -> Result<Json<FileRead>, ApiError> {
    let record = require_file(&state, &user, file_id).await?;
    require_write(&state, &user, record.project_id).await?;
    if let Some(filename) = payload.original_filename {
        let filename = filename.trim();
        if filename.is_empty() {
            return Err(ApiError::new(
                StatusCode::UNPROCESSABLE_ENTITY,
                "Filename cannot be empty",
            ));
        }
        let filename: String = filename.chars().take(255).collect();
        sqlx::query("UPDATE files SET original_filename = $2 WHERE id = $1")
            .bind(file_id)
            .bind(filename)
            .execute(&state.pool)
            .await?;
    }
    audit_file(&state, &user, "update_file", &record, json!({})).await?;
    Ok(Json(fetch_file(&state.pool, file_id).await?.into()))
}

async fn archive_file(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(file_id): Path<i32>,
) -> Result<Json<FileRead>, ApiError> {
    let record = require_file(&state, &user, file_id).await?;
    require_write(&state, &user, record.project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let locked_category: String =
        sqlx::query_scalar("SELECT lower(file_category::text) FROM files WHERE id = $1 FOR UPDATE")
            .bind(file_id)
            .fetch_one(&mut *transaction)
            .await?;
    if locked_category == "knowledge_document" {
        sqlx::query("DELETE FROM rag_document_chunks WHERE file_id = $1")
            .bind(file_id)
            .execute(&mut *transaction)
            .await?;
        sqlx::query("DELETE FROM rag_file_syncs WHERE file_id = $1")
            .bind(file_id)
            .execute(&mut *transaction)
            .await?;
    }
    sqlx::query(
        r#"
        UPDATE files
        SET status = 'ARCHIVED'::filestatus,
            knowledge_sync_status = CASE WHEN file_category = 'KNOWLEDGE_DOCUMENT'::filecategory
                THEN 'not_applicable' ELSE knowledge_sync_status END,
            knowledge_sync_message = CASE WHEN file_category = 'KNOWLEDGE_DOCUMENT'::filecategory
                THEN '资料已归档，不再进入知识库同步队列' ELSE knowledge_sync_message END,
            knowledge_synced_at = CASE WHEN file_category = 'KNOWLEDGE_DOCUMENT'::filecategory
                THEN NULL ELSE knowledge_synced_at END
        WHERE id = $1
        "#,
    )
    .bind(file_id)
    .execute(&mut *transaction)
    .await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(record.project_id),
            action: "archive_file",
            target_type: Some("file"),
            target_id: Some(file_id),
            detail: json!({}),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_file(&state.pool, file_id).await?.into()))
}

async fn review_file(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(file_id): Path<i32>,
    Json(payload): Json<FileReviewRequest>,
) -> Result<Json<FileRead>, ApiError> {
    review_file_action(&state, &user, file_id, payload).await
}

async fn approve_document(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(file_id): Path<i32>,
) -> Result<Json<FileRead>, ApiError> {
    review_file_action(
        &state,
        &user,
        file_id,
        FileReviewRequest {
            action: "approve".to_owned(),
            comment: None,
        },
    )
    .await
}

async fn reject_document(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(file_id): Path<i32>,
) -> Result<Json<FileRead>, ApiError> {
    review_file_action(
        &state,
        &user,
        file_id,
        FileReviewRequest {
            action: "reject".to_owned(),
            comment: None,
        },
    )
    .await
}

async fn review_file_action(
    state: &AppState,
    user: &UserRecord,
    file_id: i32,
    payload: FileReviewRequest,
) -> Result<Json<FileRead>, ApiError> {
    let record = require_file(state, user, file_id).await?;
    if record.file_category != "knowledge_document" {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only knowledge documents can be reviewed",
        ));
    }
    if record.status != "uploaded" {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only uploaded documents can be reviewed",
        ));
    }
    if !can_review_project(&state.pool, user, record.project_id).await? {
        return Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Review permission required",
        ));
    }
    let (status, sync_status, message) = match payload.action.as_str() {
        "approve" => (
            "APPROVED",
            "pending_sync",
            "资料已审核通过，等待后续 RAG/Dify 同步任务处理".to_owned(),
        ),
        "reject" => (
            "REJECTED",
            "not_applicable",
            payload
                .comment
                .clone()
                .unwrap_or_else(|| "资料审核未通过，不进入知识库".to_owned()),
        ),
        _ => {
            return Err(ApiError::new(
                StatusCode::UNPROCESSABLE_ENTITY,
                "Unsupported review action",
            ))
        }
    };
    let mut transaction = state.pool.begin().await?;
    let result = sqlx::query(
        r#"
        UPDATE files SET status = $2::filestatus,
            knowledge_sync_status = $3, knowledge_sync_message = $4
        WHERE id = $1 AND status = 'UPLOADED'::filestatus
        "#,
    )
    .bind(file_id)
    .bind(status)
    .bind(sync_status)
    .bind(message)
    .execute(&mut *transaction)
    .await?;
    if result.rows_affected() != 1 {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Only uploaded documents can be reviewed",
        ));
    }
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(record.project_id),
            action: "review_document",
            target_type: Some("file"),
            target_id: Some(file_id),
            detail: json!({"review_action": payload.action, "comment": payload.comment}),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_file(&state.pool, file_id).await?.into()))
}

async fn download_file(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(file_id): Path<i32>,
) -> Result<Response, ApiError> {
    let record = require_file(&state, &user, file_id).await?;
    let bytes = tokio::fs::read(&record.storage_path)
        .await
        .map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                ApiError::new(StatusCode::NOT_FOUND, "Stored file missing")
            } else {
                ApiError::internal(error)
            }
        })?;
    audit_file(&state, &user, "download_file", &record, json!({})).await?;
    let mut response = Body::from(bytes).into_response();
    let content_type = record
        .mime_type
        .as_deref()
        .and_then(|value| HeaderValue::from_str(value).ok())
        .unwrap_or_else(|| HeaderValue::from_static("application/octet-stream"));
    response
        .headers_mut()
        .insert(header::CONTENT_TYPE, content_type);
    let safe_filename = record.original_filename.replace(['\r', '\n', '"'], "_");
    let disposition = format!("attachment; filename=\"{safe_filename}\"");
    if let Ok(value) = HeaderValue::from_str(&disposition) {
        response
            .headers_mut()
            .insert(header::CONTENT_DISPOSITION, value);
    } else {
        // 非 ASCII 文件名使用 RFC 5987 编码
        let encoded: String = record
            .original_filename
            .bytes()
            .flat_map(|b| match b {
                b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                    vec![b]
                }
                _ => format!("%{b:02X}").into_bytes(),
            })
            .map(|b| b as char)
            .collect();
        let disposition =
            format!("attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{encoded}");
        if let Ok(value) = HeaderValue::from_str(&disposition) {
            response
                .headers_mut()
                .insert(header::CONTENT_DISPOSITION, value);
        }
    }
    Ok(response)
}

async fn require_file(
    state: &AppState,
    user: &UserRecord,
    file_id: i32,
) -> Result<StoredFileRecord, ApiError> {
    let record = fetch_file(&state.pool, file_id).await?;
    require_project_access(&state.pool, user, record.project_id).await?;
    Ok(record)
}

async fn fetch_file(pool: &sqlx::PgPool, file_id: i32) -> Result<StoredFileRecord, ApiError> {
    let query = format!("SELECT {FILE_COLUMNS} FROM files WHERE id = $1");
    sqlx::query_as::<_, StoredFileRecord>(&query)
        .bind(file_id)
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "File not found"))
}

async fn require_write(
    state: &AppState,
    user: &UserRecord,
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

async fn audit_file(
    state: &AppState,
    user: &UserRecord,
    action: &str,
    record: &StoredFileRecord,
    detail: serde_json::Value,
) -> Result<(), ApiError> {
    write_audit(
        &state.pool,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(record.project_id),
            action,
            target_type: Some("file"),
            target_id: Some(record.id),
            detail,
        },
    )
    .await?;
    Ok(())
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

    async fn request(
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
        let (status, bytes) = request(
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
    async fn test_file_upload_review_download_and_archive() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("file_admin_{suffix}");
        let storage = tempfile::tempdir().unwrap();
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            ("SECRET_KEY".to_owned(), "rust-file-secret".to_owned()),
            (
                "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                admin_username.clone(),
            ),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustAdmin123!".to_owned(),
            ),
            ("UPLOAD_MAX_BYTES".to_owned(), "1024".to_owned()),
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
            Some(json!({"name": format!("File Project {suffix}")})),
        )
        .await;
        let project_id = project["id"].as_i64().unwrap();

        let boundary = "eln-rust-boundary";
        let multipart = format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"upload\"; filename=\"evidence.txt\"\r\nContent-Type: text/plain\r\n\r\nhello rust file\r\n--{boundary}--\r\n"
        );
        let (upload_status, bytes) = request(
            &app,
            "POST",
            &format!("/projects/{project_id}/files?file_category=knowledge_document"),
            Some(admin),
            Some(&format!("multipart/form-data; boundary={boundary}")),
            multipart.into_bytes(),
        )
        .await;
        assert_eq!(upload_status, StatusCode::OK);
        let uploaded: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(uploaded["original_filename"], "evidence.txt");
        assert_eq!(uploaded["file_size"], 15);
        assert_eq!(uploaded["status"], "uploaded");
        assert_eq!(uploaded["knowledge_sync_status"], "pending_review");
        let file_id = uploaded["id"].as_i64().unwrap();

        let (review_status, reviewed) = json_call(
            &app,
            "POST",
            &format!("/files/{file_id}/review"),
            Some(admin),
            Some(json!({"action": "approve", "comment": "ok"})),
        )
        .await;
        assert_eq!(review_status, StatusCode::OK);
        assert_eq!(reviewed["status"], "approved");
        assert_eq!(reviewed["knowledge_sync_status"], "pending_sync");

        let (download_status, downloaded) = request(
            &app,
            "GET",
            &format!("/files/{file_id}/download"),
            Some(admin),
            None,
            Vec::new(),
        )
        .await;
        assert_eq!(download_status, StatusCode::OK);
        assert_eq!(downloaded, b"hello rust file");

        let (archive_status, archived) = json_call(
            &app,
            "POST",
            &format!("/files/{file_id}/archive"),
            Some(admin),
            None,
        )
        .await;
        assert_eq!(archive_status, StatusCode::OK);
        assert_eq!(archived["status"], "archived");
        assert_eq!(archived["knowledge_sync_status"], "not_applicable");
    }
}
