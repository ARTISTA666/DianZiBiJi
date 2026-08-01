use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde_json::json;
use sqlx::{PgPool, Postgres, Transaction};

use crate::{
    api::auth::{require_admin, CurrentUser},
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{GroupCreate, GroupMemberCreate, GroupMemberRead, GroupRead, GroupUpdate},
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/groups", get(list_groups).post(create_group))
        .route("/groups/{group_id}", get(get_group).patch(update_group))
        .route(
            "/groups/{group_id}/members",
            get(list_group_members).post(add_group_member),
        )
        .route(
            "/groups/{group_id}/members/{user_id}",
            axum::routing::delete(remove_group_member),
        )
}

async fn list_groups(
    State(state): State<AppState>,
    CurrentUser(admin): CurrentUser,
) -> Result<Json<Vec<GroupRead>>, ApiError> {
    require_admin(&admin)?;
    Ok(Json(
        sqlx::query_as::<_, GroupRead>(
            "SELECT id, name, description, leader_user_id FROM groups ORDER BY id",
        )
        .fetch_all(&state.pool)
        .await?,
    ))
}

async fn create_group(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(admin): CurrentUser,
    Json(payload): Json<GroupCreate>,
) -> Result<Json<GroupRead>, ApiError> {
    require_admin(&admin)?;
    if payload.name.trim().is_empty() {
        return Err(validation_error("Group name cannot be empty"));
    }
    if let Some(user_id) = payload.leader_user_id {
        require_user(&state.pool, user_id).await?;
    }
    let duplicate: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM groups WHERE name = $1)")
        .bind(&payload.name)
        .fetch_one(&state.pool)
        .await?;
    if duplicate {
        return Err(ApiError::new(StatusCode::CONFLICT, "小组名称已存在"));
    }
    let mut transaction = state.pool.begin().await?;
    let group_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO groups (name, description, leader_user_id, created_at, updated_at)
        VALUES ($1, $2, $3, now(), now())
        RETURNING id
        "#,
    )
    .bind(&payload.name)
    .bind(&payload.description)
    .bind(payload.leader_user_id)
    .fetch_one(&mut *transaction)
    .await?;
    audit_group(
        &mut transaction,
        admin.id,
        "create_group",
        "group",
        group_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_group(&state.pool, group_id).await?))
}

async fn get_group(
    State(state): State<AppState>,
    CurrentUser(admin): CurrentUser,
    Path(group_id): Path<i32>,
) -> Result<Json<GroupRead>, ApiError> {
    require_admin(&admin)?;
    Ok(Json(fetch_group(&state.pool, group_id).await?))
}

async fn update_group(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(admin): CurrentUser,
    Path(group_id): Path<i32>,
    Json(payload): Json<GroupUpdate>,
) -> Result<Json<GroupRead>, ApiError> {
    require_admin(&admin)?;
    fetch_group(&state.pool, group_id).await?;
    if let Some(user_id) = payload.leader_user_id {
        require_user(&state.pool, user_id).await?;
    }
    let mut transaction = state.pool.begin().await?;
    if let Some(name) = payload.name {
        sqlx::query("UPDATE groups SET name = $2, updated_at = now() WHERE id = $1")
            .bind(group_id)
            .bind(name)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(description) = payload.description {
        sqlx::query("UPDATE groups SET description = $2, updated_at = now() WHERE id = $1")
            .bind(group_id)
            .bind(description)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(leader_user_id) = payload.leader_user_id {
        sqlx::query("UPDATE groups SET leader_user_id = $2, updated_at = now() WHERE id = $1")
            .bind(group_id)
            .bind(leader_user_id)
            .execute(&mut *transaction)
            .await?;
    }
    audit_group(
        &mut transaction,
        admin.id,
        "update_group",
        "group",
        group_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_group(&state.pool, group_id).await?))
}

async fn list_group_members(
    State(state): State<AppState>,
    CurrentUser(admin): CurrentUser,
    Path(group_id): Path<i32>,
) -> Result<Json<Vec<GroupMemberRead>>, ApiError> {
    require_admin(&admin)?;
    fetch_group(&state.pool, group_id).await?;
    Ok(Json(
        sqlx::query_as::<_, GroupMemberRead>(
            r#"
            SELECT id, group_id, user_id, group_role
            FROM group_members WHERE group_id = $1 ORDER BY id
            "#,
        )
        .bind(group_id)
        .fetch_all(&state.pool)
        .await?,
    ))
}

async fn add_group_member(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(admin): CurrentUser,
    Path(group_id): Path<i32>,
    Json(payload): Json<GroupMemberCreate>,
) -> Result<Json<GroupMemberRead>, ApiError> {
    require_admin(&admin)?;
    fetch_group(&state.pool, group_id).await?;
    require_user(&state.pool, payload.user_id).await?;
    let mut transaction = state.pool.begin().await?;
    let existing: Option<i32> =
        sqlx::query_scalar("SELECT id FROM group_members WHERE group_id = $1 AND user_id = $2")
            .bind(group_id)
            .bind(payload.user_id)
            .fetch_optional(&mut *transaction)
            .await?;
    let membership_id = if let Some(id) = existing {
        sqlx::query("UPDATE group_members SET group_role = $2 WHERE id = $1")
            .bind(id)
            .bind(&payload.group_role)
            .execute(&mut *transaction)
            .await?;
        id
    } else {
        sqlx::query_scalar(
            r#"
            INSERT INTO group_members (group_id, user_id, group_role, created_at)
            VALUES ($1, $2, $3, now()) RETURNING id
            "#,
        )
        .bind(group_id)
        .bind(payload.user_id)
        .bind(&payload.group_role)
        .fetch_one(&mut *transaction)
        .await?
    };
    audit_group(
        &mut transaction,
        admin.id,
        "update_group_member",
        "user",
        payload.user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(
        sqlx::query_as::<_, GroupMemberRead>(
            "SELECT id, group_id, user_id, group_role FROM group_members WHERE id = $1",
        )
        .bind(membership_id)
        .fetch_one(&state.pool)
        .await?,
    ))
}

async fn remove_group_member(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(admin): CurrentUser,
    Path((group_id, user_id)): Path<(i32, i32)>,
) -> Result<Json<serde_json::Value>, ApiError> {
    require_admin(&admin)?;
    let mut transaction = state.pool.begin().await?;
    let removed = sqlx::query("DELETE FROM group_members WHERE group_id = $1 AND user_id = $2")
        .bind(group_id)
        .bind(user_id)
        .execute(&mut *transaction)
        .await?
        .rows_affected();
    if removed == 0 {
        return Err(ApiError::new(
            StatusCode::NOT_FOUND,
            "Group member not found",
        ));
    }
    audit_group(
        &mut transaction,
        admin.id,
        "update_group_member",
        "user",
        user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(json!({"ok": true})))
}

async fn fetch_group(pool: &PgPool, group_id: i32) -> Result<GroupRead, ApiError> {
    sqlx::query_as::<_, GroupRead>(
        "SELECT id, name, description, leader_user_id FROM groups WHERE id = $1",
    )
    .bind(group_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Group not found"))
}

async fn require_user(pool: &PgPool, user_id: i32) -> Result<(), ApiError> {
    if sqlx::query_scalar::<_, bool>("SELECT EXISTS(SELECT 1 FROM users WHERE id = $1)")
        .bind(user_id)
        .fetch_one(pool)
        .await?
    {
        Ok(())
    } else {
        Err(ApiError::new(StatusCode::NOT_FOUND, "User not found"))
    }
}

async fn audit_group(
    transaction: &mut Transaction<'_, Postgres>,
    actor_id: i32,
    action: &str,
    target_type: &str,
    target_id: i32,
    ip_address: Option<&str>,
    user_agent: Option<&str>,
) -> Result<(), ApiError> {
    write_audit(
        &mut **transaction,
        AuditEvent {
            actor_user_id: Some(actor_id),
            project_id: None,
            action,
            target_type: Some(target_type),
            target_id: Some(target_id),
            detail: json!({}),
            ip_address: ip_address.map(str::to_owned),
            user_agent: user_agent.map(str::to_owned),
        },
    )
    .await?;
    Ok(())
}

fn validation_error(detail: &'static str) -> ApiError {
    ApiError::new(StatusCode::UNPROCESSABLE_ENTITY, detail)
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
        let bytes = to_bytes(response.into_body(), 64 * 1024).await.unwrap();
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
    async fn test_groups_templates_and_audit_permissions() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("group_admin_{suffix}");
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
        let username = format!("group_member_{suffix}");
        let (_, member) = call(
            &app,
            "POST",
            "/users",
            Some(&admin_token),
            Some(json!({
                "username": username,
                "password": "GroupPass123!",
                "display_name": "Group Member"
            })),
        )
        .await;
        let member_id = member["id"].as_i64().unwrap();
        let member_token = login(&app, &username, "GroupPass123!").await;

        let (created, group) = call(
            &app,
            "POST",
            "/groups",
            Some(&admin_token),
            Some(json!({
                "name": format!("Rust Group {suffix}"),
                "description": "Integration group",
                "leader_user_id": member_id
            })),
        )
        .await;
        assert_eq!(created, StatusCode::OK);
        let group_id = group["id"].as_i64().unwrap();

        let (added, membership) = call(
            &app,
            "POST",
            &format!("/groups/{group_id}/members"),
            Some(&admin_token),
            Some(json!({"user_id": member_id, "group_role": "leader"})),
        )
        .await;
        assert_eq!(added, StatusCode::OK);
        assert_eq!(membership["group_role"], "leader");

        let (forbidden, _) = call(&app, "GET", "/groups", Some(&member_token), None).await;
        assert_eq!(forbidden, StatusCode::FORBIDDEN);

        let (templates_status, templates) =
            call(&app, "GET", "/templates", Some(&member_token), None).await;
        assert_eq!(templates_status, StatusCode::OK);
        assert!(templates.as_array().unwrap().len() >= 5);

        let (audit_status, logs) = call(
            &app,
            "GET",
            "/audit-logs?action=create_group",
            Some(&admin_token),
            None,
        )
        .await;
        assert_eq!(audit_status, StatusCode::OK);
        assert!(logs["items"]
            .as_array()
            .unwrap()
            .iter()
            .all(|log| log["action"] == "create_group"));
    }
}
