use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};

use crate::{
    api::auth::{require_admin, CurrentUser},
    api::rag::require_unblinded_access,
    error::ApiError,
    models::{page_bounds, AuditLogRead, AuditQuery, Paginated},
    permissions::{can_manage_project, require_project_access},
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/audit-logs", get(list_audit_logs))
        .route(
            "/projects/{project_id}/audit-logs",
            get(list_project_audit_logs),
        )
}

async fn list_audit_logs(
    State(state): State<AppState>,
    CurrentUser(admin): CurrentUser,
    Query(query): Query<AuditQuery>,
) -> Result<Json<Paginated<AuditLogRead>>, ApiError> {
    require_admin(&admin)?;
    fetch_audit_logs(&state, &query).await
}

/// 项目级审计日志：仅项目管理者可见，固定按路径中的 project_id 过滤，
/// 查询参数中的 project_id 会被忽略。
async fn list_project_audit_logs(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Query(mut query): Query<AuditQuery>,
) -> Result<Json<Paginated<AuditLogRead>>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    if !can_manage_project(&state.pool, &user, project_id).await? {
        return Err(ApiError::new(StatusCode::FORBIDDEN, "需要项目管理权限"));
    }
    // 盲评隔离：独立评审员必须走 blind-review API，不能读取项目审计记录。
    require_unblinded_access(&state, &user, project_id).await?;
    query.project_id = Some(project_id);
    fetch_audit_logs(&state, &query).await
}

async fn fetch_audit_logs(
    state: &AppState,
    query: &AuditQuery,
) -> Result<Json<Paginated<AuditLogRead>>, ApiError> {
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

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use axum::{
        body::{to_bytes, Body},
        http::Request,
        http::StatusCode,
        Router,
    };
    use serde_json::{json, Value};
    use tower::ServiceExt;
    use uuid::Uuid;

    use crate::{build_app, config::Settings, db::connect_database, db::initialize_database};

    async fn json_call(
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
        let body_bytes = body
            .as_ref()
            .map(|value| value.to_string().into_bytes())
            .unwrap_or_default();
        if body.is_some() {
            request = request.header("content-type", "application/json");
        }
        let response = app
            .clone()
            .oneshot(request.body(Body::from(body_bytes)).unwrap())
            .await
            .unwrap();
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
        let parsed = if bytes.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&bytes).unwrap()
        };
        (status, parsed)
    }

    #[tokio::test]
    async fn test_project_audit_logs_require_manager_and_hide_blind_reviewers() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("proj_audit_admin_{suffix}");
        let storage = tempfile::tempdir().unwrap();
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "SECRET_KEY".to_owned(),
                "rust-project-audit-secret".to_owned(),
            ),
            (
                "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                admin_username.clone(),
            ),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustProjAudit123!".to_owned(),
            ),
            (
                "STORAGE_ROOT".to_owned(),
                storage.path().to_string_lossy().into_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let app = build_app(crate::AppState::new(pool.clone(), settings).unwrap());

        let (_, login) = json_call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({
                "username": admin_username,
                "password": "RustProjAudit123!"
            })),
        )
        .await;
        let admin = login["access_token"].as_str().unwrap();
        let admin_id: i32 = sqlx::query_scalar("SELECT id FROM users WHERE username = $1")
            .bind(&admin_username)
            .fetch_one(&pool)
            .await
            .unwrap();

        let (_, project_a) = json_call(
            &app,
            "POST",
            "/projects",
            Some(admin),
            Some(json!({"name": format!("Audit Project A {suffix}")})),
        )
        .await;
        let project_a_id = project_a["id"].as_i64().unwrap() as i32;
        let (_, project_b) = json_call(
            &app,
            "POST",
            "/projects",
            Some(admin),
            Some(json!({"name": format!("Audit Project B {suffix}")})),
        )
        .await;
        let project_b_id = project_b["id"].as_i64().unwrap() as i32;

        // 直接插入带标记动作的审计日志，避免依赖其他端点的落盘行为。
        for (project_id, action) in [
            (project_a_id, "proj_audit_marker_a1"),
            (project_a_id, "proj_audit_marker_a2"),
            (project_b_id, "proj_audit_marker_b1"),
        ] {
            sqlx::query(
                r#"
                INSERT INTO audit_logs (
                    actor_user_id, project_id, action, target_type, target_id,
                    detail_json, ip_address, user_agent
                )
                VALUES ($1, $2, $3, 'project', $2, '{}'::json, NULL, NULL)
                "#,
            )
            .bind(admin_id)
            .bind(project_id)
            .bind(action)
            .execute(&pool)
            .await
            .unwrap();
        }

        // 管理者：200，且只见本项目日志；查询参数中的 project_id 被忽略。
        let (status, body) = json_call(
            &app,
            "GET",
            &format!("/projects/{project_a_id}/audit-logs?limit=200&project_id={project_b_id}"),
            Some(admin),
            None,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        let items = body["items"].as_array().unwrap();
        assert!(!items.is_empty());
        let actions: Vec<&str> = items
            .iter()
            .filter_map(|item| item["action"].as_str())
            .collect();
        assert!(actions.contains(&"proj_audit_marker_a1"));
        assert!(actions.contains(&"proj_audit_marker_a2"));
        assert!(!actions.contains(&"proj_audit_marker_b1"));
        assert!(items
            .iter()
            .all(|item| item["project_id"].as_i64() == Some(project_a_id as i64)));
        assert_eq!(body["total"].as_i64().unwrap(), actions.len() as i64);

        // 过滤器仍然生效：action 精确匹配。
        let (filtered_status, filtered) = json_call(
            &app,
            "GET",
            &format!("/projects/{project_a_id}/audit-logs?action=proj_audit_marker_a1"),
            Some(admin),
            None,
        )
        .await;
        assert_eq!(filtered_status, StatusCode::OK);
        assert_eq!(filtered["total"], 1);
        assert_eq!(filtered["items"][0]["action"], "proj_audit_marker_a1");

        // 只读成员：403。
        let viewer_username = format!("proj_audit_viewer_{suffix}");
        json_call(
            &app,
            "POST",
            "/users",
            Some(admin),
            Some(json!({
                "username": viewer_username,
                "password": "ViewerAudit123!",
                "display_name": "Viewer"
            })),
        )
        .await;
        let viewer_id: i32 = sqlx::query_scalar("SELECT id FROM users WHERE username = $1")
            .bind(&viewer_username)
            .fetch_one(&pool)
            .await
            .unwrap();
        json_call(
            &app,
            "POST",
            &format!("/projects/{project_a_id}/members"),
            Some(admin),
            Some(json!({
                "user_id": viewer_id,
                "project_role": "viewer",
                "can_read": true,
                "can_write": false,
                "can_review": false,
                "can_evaluate": false,
                "can_manage": false
            })),
        )
        .await;
        let (_, viewer_login) = json_call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({
                "username": viewer_username,
                "password": "ViewerAudit123!"
            })),
        )
        .await;
        let viewer_token = viewer_login["access_token"].as_str().unwrap();
        let (viewer_status, viewer_body) = json_call(
            &app,
            "GET",
            &format!("/projects/{project_a_id}/audit-logs"),
            Some(viewer_token),
            None,
        )
        .await;
        assert_eq!(viewer_status, StatusCode::FORBIDDEN);
        assert_eq!(viewer_body["detail"], "需要项目管理权限");

        // 独立盲评人：403（盲评隔离）。
        let reviewer_username = format!("proj_audit_blind_{suffix}");
        json_call(
            &app,
            "POST",
            "/users",
            Some(admin),
            Some(json!({
                "username": reviewer_username,
                "password": "BlindAudit123!",
                "display_name": "Blind Reviewer"
            })),
        )
        .await;
        let reviewer_id: i32 = sqlx::query_scalar("SELECT id FROM users WHERE username = $1")
            .bind(&reviewer_username)
            .fetch_one(&pool)
            .await
            .unwrap();
        let (add_reviewer_status, _) = json_call(
            &app,
            "POST",
            &format!("/projects/{project_a_id}/reviewers"),
            Some(admin),
            Some(json!({"user_id": reviewer_id})),
        )
        .await;
        assert_eq!(add_reviewer_status, StatusCode::OK);
        let (_, reviewer_login) = json_call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({
                "username": reviewer_username,
                "password": "BlindAudit123!"
            })),
        )
        .await;
        let reviewer_token = reviewer_login["access_token"].as_str().unwrap();
        let (reviewer_status, _) = json_call(
            &app,
            "GET",
            &format!("/projects/{project_a_id}/audit-logs"),
            Some(reviewer_token),
            None,
        )
        .await;
        assert_eq!(reviewer_status, StatusCode::FORBIDDEN);

        // 未登录：401。
        let (anonymous_status, _) = json_call(
            &app,
            "GET",
            &format!("/projects/{project_a_id}/audit-logs"),
            None,
            None,
        )
        .await;
        assert_eq!(anonymous_status, StatusCode::UNAUTHORIZED);
    }
}
