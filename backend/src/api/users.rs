use axum::{
    extract::{Path, Query, State},
    http::{header::SET_COOKIE, StatusCode},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde_json::json;
use sqlx::{PgPool, Postgres, Transaction};

use crate::{
    api::auth::{auth_cookie, require_admin, CurrentUser},
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{
        validate_email, validate_password, validate_role, validate_user_status, validate_username,
        PageQuery, Paginated, TokenResponse, UserCreate, UserPasswordChange, UserRead, UserUpdate,
    },
    security::{create_access_token, hash_password, verify_password},
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/users", get(list_users).post(create_user))
        .route("/users/me/password", post(change_own_password))
        .route("/users/{user_id}", get(get_user).patch(update_user))
        .route("/users/{user_id}/disable", post(disable_user))
}

const USER_READ_COLUMNS: &str = r#"
    id, username, display_name, email,
    lower(role::text) AS role, lower(status::text) AS status
"#;
const ADMIN_INVARIANT_LOCK_ID: i64 = 0x454C_4E5F_4144_4D49;

async fn list_users(
    State(state): State<AppState>,
    CurrentUser(admin): CurrentUser,
    Query(page): Query<PageQuery>,
) -> Result<Json<Paginated<UserRead>>, ApiError> {
    require_admin(&admin)?;
    let (skip, limit) = page.bounds();
    let total: i64 = sqlx::query_scalar("SELECT count(*) FROM users")
        .fetch_one(&state.pool)
        .await?;
    let query = format!("SELECT {USER_READ_COLUMNS} FROM users ORDER BY id OFFSET $1 LIMIT $2");
    let items = sqlx::query_as::<_, UserRead>(&query)
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

async fn create_user(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(admin): CurrentUser,
    Json(payload): Json<UserCreate>,
) -> Result<Json<UserRead>, ApiError> {
    require_admin(&admin)?;
    validate_username(&payload.username).map_err(validation_error)?;
    validate_password(&payload.password).map_err(validation_error)?;
    validate_role(&payload.role).map_err(validation_error)?;
    if let Some(email) = &payload.email {
        validate_email(email).map_err(validation_error)?;
    }
    let duplicate: bool =
        sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM users WHERE username = $1)")
            .bind(&payload.username)
            .fetch_one(&state.pool)
            .await?;
    if duplicate {
        return Err(ApiError::new(StatusCode::CONFLICT, "用户名已存在"));
    }
    let password = payload.password;
    let password_hash = tokio::task::spawn_blocking(move || hash_password(&password))
        .await
        .map_err(ApiError::internal)?
        .map_err(ApiError::internal)?;
    let mut transaction = state.pool.begin().await?;
    let id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO users (
            username, password_hash, display_name, email, role, status, auth_version
        )
        VALUES ($1, $2, $3, $4, upper($5)::userrole, 'ACTIVE'::userstatus, 0)
        RETURNING id
        "#,
    )
    .bind(&payload.username)
    .bind(password_hash)
    .bind(&payload.display_name)
    .bind(&payload.email)
    .bind(&payload.role)
    .fetch_one(&mut *transaction)
    .await?;
    audit_user(
        &mut transaction,
        admin.id,
        "create_user",
        id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_user(&state.pool, id).await?))
}

async fn get_user(
    State(state): State<AppState>,
    CurrentUser(admin): CurrentUser,
    Path(user_id): Path<i32>,
) -> Result<Json<UserRead>, ApiError> {
    require_admin(&admin)?;
    Ok(Json(fetch_user(&state.pool, user_id).await?))
}

async fn update_user(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(admin): CurrentUser,
    Path(user_id): Path<i32>,
    Json(payload): Json<UserUpdate>,
) -> Result<Json<UserRead>, ApiError> {
    require_admin(&admin)?;
    fetch_user(&state.pool, user_id).await?;
    if let Some(email) = &payload.email {
        validate_email(email).map_err(validation_error)?;
    }
    if let Some(role) = &payload.role {
        validate_role(role).map_err(validation_error)?;
    }
    if let Some(status) = &payload.status {
        validate_user_status(status).map_err(validation_error)?;
    }
    if let Some(password) = &payload.password {
        validate_password(password).map_err(validation_error)?;
    }
    if user_id == admin.id {
        if payload
            .status
            .as_deref()
            .is_some_and(|status| status != "active")
        {
            return Err(ApiError::new(
                StatusCode::CONFLICT,
                "Cannot disable current admin",
            ));
        }
        if payload
            .role
            .as_deref()
            .is_some_and(|role| role != "super_admin")
        {
            return Err(ApiError::new(
                StatusCode::CONFLICT,
                "Cannot change current admin role",
            ));
        }
    }
    let password_hash = if let Some(password) = payload.password {
        Some(
            tokio::task::spawn_blocking(move || hash_password(&password))
                .await
                .map_err(ApiError::internal)?
                .map_err(ApiError::internal)?,
        )
    } else {
        None
    };
    let mut transaction = state.pool.begin().await?;
    if payload
        .role
        .as_deref()
        .is_some_and(|role| role != "super_admin")
        || payload
            .status
            .as_deref()
            .is_some_and(|status| status != "active")
    {
        protect_last_active_admin(&mut transaction, user_id).await?;
    }
    if let Some(role) = payload.role.as_deref() {
        protect_reviewer_role_transition(&mut transaction, user_id, role).await?;
    }
    if let Some(display_name) = payload.display_name {
        sqlx::query("UPDATE users SET display_name = $2, updated_at = now() WHERE id = $1")
            .bind(user_id)
            .bind(display_name)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(email) = payload.email {
        sqlx::query("UPDATE users SET email = $2, updated_at = now() WHERE id = $1")
            .bind(user_id)
            .bind(email)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(role) = payload.role {
        sqlx::query(
            r#"
            UPDATE users
            SET role = upper($2)::userrole,
                auth_version = auth_version + CASE
                    WHEN role = upper($2)::userrole THEN 0
                    ELSE 1
                END,
                updated_at = now()
            WHERE id = $1
            "#,
        )
        .bind(user_id)
        .bind(role)
        .execute(&mut *transaction)
        .await?;
    }
    if let Some(status) = payload.status {
        sqlx::query(
            r#"
            UPDATE users
            SET status = upper($2)::userstatus,
                auth_version = auth_version + CASE
                    WHEN status = upper($2)::userstatus THEN 0
                    ELSE 1
                END,
                updated_at = now()
            WHERE id = $1
            "#,
        )
        .bind(user_id)
        .bind(status)
        .execute(&mut *transaction)
        .await?;
    }
    if let Some(password_hash) = password_hash {
        sqlx::query(
            "UPDATE users SET password_hash = $2, auth_version = auth_version + 1, updated_at = now() WHERE id = $1",
        )
        .bind(user_id)
        .bind(password_hash)
        .execute(&mut *transaction)
        .await?;
    }
    audit_user(
        &mut transaction,
        admin.id,
        "update_user",
        user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_user(&state.pool, user_id).await?))
}

async fn protect_reviewer_role_transition(
    transaction: &mut Transaction<'_, Postgres>,
    user_id: i32,
    next_role: &str,
) -> Result<(), ApiError> {
    let exists: Option<i32> = sqlx::query_scalar(
        "SELECT id FROM users WHERE id = $1 FOR NO KEY UPDATE /* reviewer_role_user_lock */",
    )
    .bind(user_id)
    .fetch_optional(&mut **transaction)
    .await?;
    if exists.is_none() {
        return Err(ApiError::new(StatusCode::NOT_FOUND, "User not found"));
    }

    let conflicts: bool = match next_role {
        "super_admin" => {
            sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM project_reviewers WHERE user_id = $1)")
                .bind(user_id)
                .fetch_one(&mut **transaction)
                .await?
        }
        "pi" => {
            sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM project_reviewers pr
                    JOIN projects p ON p.id = pr.project_id
                    WHERE pr.user_id = $1 AND p.is_sensitive = false
                )
                "#,
            )
            .bind(user_id)
            .fetch_one(&mut **transaction)
            .await?
        }
        _ => false,
    };
    if conflicts {
        Err(ApiError::new(
            StatusCode::CONFLICT,
            "User role would give an independent reviewer automatic project access",
        ))
    } else {
        Ok(())
    }
}

async fn change_own_password(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Json(payload): Json<UserPasswordChange>,
) -> Result<impl IntoResponse, ApiError> {
    validate_password(&payload.new_password).map_err(validation_error)?;
    let current = payload.current_password;
    let current_hash = user.password_hash.clone();
    let valid = tokio::task::spawn_blocking(move || verify_password(&current, &current_hash))
        .await
        .map_err(ApiError::internal)?;
    if !valid {
        return Err(ApiError::new(
            StatusCode::BAD_REQUEST,
            "Current password is incorrect",
        ));
    }
    let new_password = payload.new_password;
    let password_hash = tokio::task::spawn_blocking(move || hash_password(&new_password))
        .await
        .map_err(ApiError::internal)?
        .map_err(ApiError::internal)?;
    let mut transaction = state.pool.begin().await?;
    let auth_version: i32 = sqlx::query_scalar(
        r#"
        UPDATE users
        SET password_hash = $2, auth_version = auth_version + 1, updated_at = now()
        WHERE id = $1
        RETURNING auth_version
        "#,
    )
    .bind(user.id)
    .bind(password_hash)
    .fetch_one(&mut *transaction)
    .await?;
    audit_user(
        &mut transaction,
        user.id,
        "change_password",
        user.id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    let access_token = create_access_token(
        &user.id.to_string(),
        auth_version,
        &state.settings.secret_key,
        state.settings.access_token_expire_minutes,
    )
    .map_err(ApiError::internal)?;
    // Refresh the auth cookie so browser sessions survive the auth_version bump.
    let cookie = auth_cookie(
        &state.settings,
        &access_token,
        state.settings.access_token_expire_minutes * 60,
    );
    Ok((
        [(SET_COOKIE, cookie)],
        Json(TokenResponse {
            access_token,
            token_type: "bearer",
        }),
    ))
}

async fn disable_user(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(admin): CurrentUser,
    Path(user_id): Path<i32>,
) -> Result<Json<UserRead>, ApiError> {
    require_admin(&admin)?;
    fetch_user(&state.pool, user_id).await?;
    if user_id == admin.id {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Cannot disable current admin",
        ));
    }
    let mut transaction = state.pool.begin().await?;
    protect_last_active_admin(&mut transaction, user_id).await?;
    sqlx::query(
        r#"
        UPDATE users
        SET status = 'DISABLED'::userstatus,
            auth_version = auth_version + 1,
            updated_at = now()
        WHERE id = $1
        "#,
    )
    .bind(user_id)
    .execute(&mut *transaction)
    .await?;
    audit_user(
        &mut transaction,
        admin.id,
        "update_user",
        user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_user(&state.pool, user_id).await?))
}

async fn protect_last_active_admin(
    transaction: &mut Transaction<'_, Postgres>,
    user_id: i32,
) -> Result<(), ApiError> {
    sqlx::query("SELECT pg_advisory_xact_lock($1)")
        .bind(ADMIN_INVARIANT_LOCK_ID)
        .execute(&mut **transaction)
        .await?;
    let target_is_active_admin: bool = sqlx::query_scalar(
        r#"
        SELECT role = 'SUPER_ADMIN'::userrole AND status = 'ACTIVE'::userstatus
        FROM users
        WHERE id = $1
        FOR UPDATE
        "#,
    )
    .bind(user_id)
    .fetch_one(&mut **transaction)
    .await?;
    if !target_is_active_admin {
        return Ok(());
    }
    let remaining: i64 = sqlx::query_scalar(
        r#"
        SELECT count(*)
        FROM users
        WHERE id <> $1
          AND role = 'SUPER_ADMIN'::userrole
          AND status = 'ACTIVE'::userstatus
        "#,
    )
    .bind(user_id)
    .fetch_one(&mut **transaction)
    .await?;
    if remaining == 0 {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Cannot remove the last active super administrator",
        ));
    }
    Ok(())
}

async fn fetch_user(pool: &PgPool, user_id: i32) -> Result<UserRead, ApiError> {
    let query = format!("SELECT {USER_READ_COLUMNS} FROM users WHERE id = $1");
    sqlx::query_as::<_, UserRead>(&query)
        .bind(user_id)
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "User not found"))
}

async fn audit_user(
    transaction: &mut Transaction<'_, Postgres>,
    actor_id: i32,
    action: &str,
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
            target_type: Some("user"),
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
    use sqlx::PgPool;
    use tower::ServiceExt;
    use uuid::Uuid;

    use crate::{
        build_app,
        config::Settings,
        db::{connect_database, initialize_database},
        security::hash_password,
        AppState,
    };

    async fn test_app() -> Option<(Router, PgPool)> {
        let database_url = std::env::var("TEST_DATABASE_URL").ok()?;
        let admin_username = format!(
            "user_guard_admin_{}",
            &Uuid::new_v4().simple().to_string()[..8]
        );
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "SECRET_KEY".to_owned(),
                "rust-integration-secret".to_owned(),
            ),
            ("BOOTSTRAP_ADMIN_USERNAME".to_owned(), admin_username),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustAdmin123!".to_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let app = build_app(AppState::new(pool.clone(), settings).unwrap());
        Some((app, pool))
    }

    async fn insert_test_user(pool: &PgPool, role: &str) -> (i32, String, String) {
        let username = format!("rust_user_{}", &Uuid::new_v4().simple().to_string()[..8]);
        let password = "TestPassword123!".to_owned();
        let password_hash = hash_password(&password).unwrap();
        let user_id = sqlx::query_scalar(
            r#"
            INSERT INTO users (
                username, password_hash, display_name, email, role, status, auth_version
            )
            VALUES ($1, $2, 'Rust Test User', NULL,
                    upper($3)::userrole, 'ACTIVE'::userstatus, 0)
            RETURNING id
            "#,
        )
        .bind(&username)
        .bind(password_hash)
        .bind(role)
        .fetch_one(pool)
        .await
        .unwrap();
        (user_id, username, password)
    }

    async fn patch_user(app: &Router, token: &str, user_id: i32, payload: Value) -> StatusCode {
        app.clone()
            .oneshot(
                Request::patch(format!("/users/{user_id}"))
                    .header("authorization", format!("Bearer {token}"))
                    .header("content-type", "application/json")
                    .body(Body::from(payload.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap()
            .status()
    }

    async fn login(app: &Router, username: &str, password: &str) -> String {
        let response = app
            .clone()
            .oneshot(
                Request::post("/auth/login")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({"username": username, "password": password}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let payload: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), 4096).await.unwrap()).unwrap();
        payload["access_token"].as_str().unwrap().to_owned()
    }

    async fn list_users_status(app: &Router, token: &str) -> StatusCode {
        app.clone()
            .oneshot(
                Request::get("/users")
                    .header("authorization", format!("Bearer {token}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap()
            .status()
    }

    async fn insert_test_project(pool: &PgPool, owner_id: i32, is_sensitive: bool) -> i32 {
        sqlx::query_scalar(
            r#"
            INSERT INTO projects (
                name, description, is_sensitive, status, approval_enabled,
                owner_user_id, created_at, updated_at
            )
            VALUES ($1, 'User role reviewer invariant', $2,
                    'ACTIVE'::projectstatus, true, $3, now(), now())
            RETURNING id
            "#,
        )
        .bind(format!("User Role Guard {}", Uuid::new_v4()))
        .bind(is_sensitive)
        .bind(owner_id)
        .fetch_one(pool)
        .await
        .unwrap()
    }

    async fn insert_reviewer_assignment(pool: &PgPool, project_id: i32, user_id: i32) {
        sqlx::query(
            r#"
            INSERT INTO project_reviewers (project_id, user_id, review_scope, created_at)
            VALUES ($1, $2, 'all', now())
            "#,
        )
        .bind(project_id)
        .bind(user_id)
        .execute(pool)
        .await
        .unwrap();
        sqlx::query(
            r#"
            INSERT INTO project_members (
                project_id, user_id, project_role, can_read, can_write,
                can_review, can_evaluate, can_manage, created_at
            )
            VALUES ($1, $2, 'REVIEWER'::projectrole,
                    false, false, false, true, false, now())
            "#,
        )
        .bind(project_id)
        .bind(user_id)
        .execute(pool)
        .await
        .unwrap();
    }

    #[tokio::test]
    async fn test_update_user_role_rejects_reviewer_conflicts() {
        let Some((app, pool)) = test_app().await else {
            return;
        };
        let (admin_id, admin_username, admin_password) =
            insert_test_user(&pool, "super_admin").await;
        let (super_target, _, _) = insert_test_user(&pool, "reviewer").await;
        let (public_pi_target, _, _) = insert_test_user(&pool, "reviewer").await;
        let (sensitive_pi_target, _, _) = insert_test_user(&pool, "reviewer").await;
        let admin_token = login(&app, &admin_username, &admin_password).await;
        let sensitive_project = insert_test_project(&pool, admin_id, true).await;
        let public_project = insert_test_project(&pool, admin_id, false).await;
        insert_reviewer_assignment(&pool, sensitive_project, super_target).await;
        insert_reviewer_assignment(&pool, public_project, public_pi_target).await;
        insert_reviewer_assignment(&pool, sensitive_project, sensitive_pi_target).await;

        assert_eq!(
            patch_user(
                &app,
                &admin_token,
                super_target,
                json!({"role": "super_admin"}),
            )
            .await,
            StatusCode::CONFLICT
        );
        assert_eq!(
            patch_user(&app, &admin_token, public_pi_target, json!({"role": "pi"}),).await,
            StatusCode::CONFLICT
        );
        assert_eq!(
            patch_user(
                &app,
                &admin_token,
                sensitive_pi_target,
                json!({"role": "pi"}),
            )
            .await,
            StatusCode::OK
        );

        let roles: Vec<String> = sqlx::query_scalar(
            "SELECT lower(role::text) FROM users WHERE id = ANY($1) ORDER BY id",
        )
        .bind(vec![super_target, public_pi_target, sensitive_pi_target])
        .fetch_all(&pool)
        .await
        .unwrap();
        assert_eq!(roles, vec!["reviewer", "reviewer", "pi"]);
    }

    #[tokio::test]
    async fn test_update_user_role_rechecks_reviewer_after_user_lock_wait() {
        let Some((app, pool)) = test_app().await else {
            return;
        };
        let (admin_id, admin_username, admin_password) =
            insert_test_user(&pool, "super_admin").await;
        let (target_id, _, _) = insert_test_user(&pool, "reviewer").await;
        let admin_token = login(&app, &admin_username, &admin_password).await;
        let project_id = insert_test_project(&pool, admin_id, true).await;

        let mut blocker = pool.begin().await.unwrap();
        sqlx::query("SELECT id FROM users WHERE id = $1 FOR UPDATE")
            .bind(target_id)
            .fetch_one(&mut *blocker)
            .await
            .unwrap();
        let patch_app = app.clone();
        let mut role_update = tokio::spawn(async move {
            patch_user(
                &patch_app,
                &admin_token,
                target_id,
                json!({"role": "super_admin"}),
            )
            .await
        });

        let mut waiting_for_user_lock = false;
        for _ in 0..100 {
            waiting_for_user_lock = sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND wait_event_type = 'Lock'
                      AND query LIKE '%reviewer_role_user_lock%'
                )
                "#,
            )
            .fetch_one(&pool)
            .await
            .unwrap();
            if waiting_for_user_lock {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
        assert!(
            waiting_for_user_lock,
            "role update did not wait on the explicit reviewer invariant lock"
        );

        sqlx::query(
            r#"
            INSERT INTO project_reviewers (project_id, user_id, review_scope, created_at)
            VALUES ($1, $2, 'all', now())
            "#,
        )
        .bind(project_id)
        .bind(target_id)
        .execute(&mut *blocker)
        .await
        .unwrap();
        blocker.commit().await.unwrap();

        let status = tokio::time::timeout(std::time::Duration::from_secs(2), &mut role_update)
            .await
            .expect("role update should resume after user lock release")
            .unwrap();
        assert_eq!(status, StatusCode::CONFLICT);
        let persisted_role: String =
            sqlx::query_scalar("SELECT lower(role::text) FROM users WHERE id = $1")
                .bind(target_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(persisted_role, "reviewer");
    }

    #[tokio::test]
    async fn test_list_users_requires_super_admin() {
        let Some((app, pool)) = test_app().await else {
            return;
        };
        let (_, admin_username, admin_password) = insert_test_user(&pool, "super_admin").await;
        let (_, member_username, member_password) = insert_test_user(&pool, "member").await;
        let admin_token = login(&app, &admin_username, &admin_password).await;
        let member_token = login(&app, &member_username, &member_password).await;

        assert_eq!(
            list_users_status(&app, &member_token).await,
            StatusCode::FORBIDDEN
        );
        assert_eq!(list_users_status(&app, &admin_token).await, StatusCode::OK);
    }

    #[tokio::test]
    async fn test_update_user_rejects_current_admin_self_disable() {
        let Some((app, pool)) = test_app().await else {
            return;
        };
        let (admin_id, username, password) = insert_test_user(&pool, "super_admin").await;
        let admin_token = login(&app, &username, &password).await;

        let status = patch_user(&app, &admin_token, admin_id, json!({"status": "disabled"})).await;

        assert_eq!(status, StatusCode::CONFLICT);
        let persisted_status: String =
            sqlx::query_scalar("SELECT lower(status::text) FROM users WHERE id = $1")
                .bind(admin_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(persisted_status, "active");
    }

    #[tokio::test]
    async fn test_update_user_rejects_current_admin_self_demotion() {
        let Some((app, pool)) = test_app().await else {
            return;
        };
        let (admin_id, username, password) = insert_test_user(&pool, "super_admin").await;
        let admin_token = login(&app, &username, &password).await;

        let status = patch_user(&app, &admin_token, admin_id, json!({"role": "member"})).await;

        assert_eq!(status, StatusCode::CONFLICT);
        let persisted_role: String =
            sqlx::query_scalar("SELECT lower(role::text) FROM users WHERE id = $1")
                .bind(admin_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(persisted_role, "super_admin");
    }

    #[tokio::test]
    async fn test_update_user_status_change_permanently_revokes_existing_token() {
        let Some((app, pool)) = test_app().await else {
            return;
        };
        let (admin_id, admin_username, admin_password) =
            insert_test_user(&pool, "super_admin").await;
        let (member_id, member_username, member_password) = insert_test_user(&pool, "member").await;
        let admin_token = login(&app, &admin_username, &admin_password).await;
        let member_token = login(&app, &member_username, &member_password).await;
        let initial_version: i32 =
            sqlx::query_scalar("SELECT auth_version FROM users WHERE id = $1")
                .bind(member_id)
                .fetch_one(&pool)
                .await
                .unwrap();

        assert_eq!(
            patch_user(&app, &admin_token, member_id, json!({"status": "disabled"}),).await,
            StatusCode::OK
        );
        let disabled_version: i32 =
            sqlx::query_scalar("SELECT auth_version FROM users WHERE id = $1")
                .bind(member_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(disabled_version, initial_version + 1);

        assert_eq!(
            patch_user(&app, &admin_token, member_id, json!({"status": "active"}),).await,
            StatusCode::OK
        );
        let reenabled_version: i32 =
            sqlx::query_scalar("SELECT auth_version FROM users WHERE id = $1")
                .bind(member_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(reenabled_version, disabled_version + 1);

        assert_eq!(
            patch_user(&app, &admin_token, member_id, json!({"status": "active"}),).await,
            StatusCode::OK
        );
        let unchanged_version: i32 =
            sqlx::query_scalar("SELECT auth_version FROM users WHERE id = $1")
                .bind(member_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(unchanged_version, reenabled_version);

        let old_token = app
            .clone()
            .oneshot(
                Request::get("/auth/me")
                    .header("authorization", format!("Bearer {member_token}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(old_token.status(), StatusCode::UNAUTHORIZED);

        let admin_still_active = app
            .oneshot(
                Request::get("/auth/me")
                    .header("authorization", format!("Bearer {admin_token}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(admin_still_active.status(), StatusCode::OK);
        assert_ne!(admin_id, member_id);
    }

    #[tokio::test]
    async fn test_update_user_role_change_permanently_revokes_existing_token() {
        let Some((app, pool)) = test_app().await else {
            return;
        };
        let (_, admin_username, admin_password) = insert_test_user(&pool, "super_admin").await;
        let (member_id, member_username, member_password) = insert_test_user(&pool, "member").await;
        let admin_token = login(&app, &admin_username, &admin_password).await;
        let member_token = login(&app, &member_username, &member_password).await;
        let initial_version: i32 =
            sqlx::query_scalar("SELECT auth_version FROM users WHERE id = $1")
                .bind(member_id)
                .fetch_one(&pool)
                .await
                .unwrap();

        assert_eq!(
            patch_user(&app, &admin_token, member_id, json!({"role": "reviewer"})).await,
            StatusCode::OK
        );
        let changed_version: i32 =
            sqlx::query_scalar("SELECT auth_version FROM users WHERE id = $1")
                .bind(member_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(changed_version, initial_version + 1);

        let old_token = app
            .oneshot(
                Request::get("/auth/me")
                    .header("authorization", format!("Bearer {member_token}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(old_token.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_last_active_super_admin_guard_rejects_removal() {
        let Some((_, pool)) = test_app().await else {
            return;
        };
        let (target_id, _, _) = insert_test_user(&pool, "super_admin").await;
        let mut transaction = pool.begin().await.unwrap();
        sqlx::query(
            r#"
            UPDATE users
            SET status = 'DISABLED'::userstatus
            WHERE role = 'SUPER_ADMIN'::userrole AND id <> $1
            "#,
        )
        .bind(target_id)
        .execute(&mut *transaction)
        .await
        .unwrap();

        let error = super::protect_last_active_admin(&mut transaction, target_id)
            .await
            .unwrap_err();

        assert_eq!(error.status, StatusCode::CONFLICT);
        assert!(error.detail.contains("last active"));
        transaction.rollback().await.unwrap();
    }

    #[tokio::test]
    async fn test_user_crud_permissions_and_password_rotation() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let admin_username = format!(
            "user_crud_admin_{}",
            &Uuid::new_v4().simple().to_string()[..8]
        );
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
        let username = format!("rust_user_{}", &Uuid::new_v4().simple().to_string()[..8]);

        let created = app
            .clone()
            .oneshot(
                Request::post("/users")
                    .header("authorization", format!("Bearer {admin_token}"))
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "username": username,
                            "password": "MemberPass123!",
                            "display_name": "Rust Member",
                            "email": "rust.member@example.com",
                            "role": "member"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(created.status(), StatusCode::OK);
        let member: Value =
            serde_json::from_slice(&to_bytes(created.into_body(), 4096).await.unwrap()).unwrap();
        let user_id = member["id"].as_i64().unwrap();
        assert_eq!(member["status"], "active");

        let member_token = login(&app, &username, "MemberPass123!").await;
        let forbidden = app
            .clone()
            .oneshot(
                Request::post("/users")
                    .header("authorization", format!("Bearer {member_token}"))
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "username": "forbidden_user",
                            "password": "Password123!",
                            "display_name": "Forbidden"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(forbidden.status(), StatusCode::FORBIDDEN);

        let updated = app
            .clone()
            .oneshot(
                Request::patch(format!("/users/{user_id}"))
                    .header("authorization", format!("Bearer {admin_token}"))
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({"display_name": "Updated Rust Member"}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(updated.status(), StatusCode::OK);

        let changed = app
            .clone()
            .oneshot(
                Request::post("/users/me/password")
                    .header("authorization", format!("Bearer {member_token}"))
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "current_password": "MemberPass123!",
                            "new_password": "NewMemberPass123!"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(changed.status(), StatusCode::OK);
        let changed_payload: Value =
            serde_json::from_slice(&to_bytes(changed.into_body(), 4096).await.unwrap()).unwrap();
        let replacement = changed_payload["access_token"].as_str().unwrap();

        let revoked = app
            .clone()
            .oneshot(
                Request::get("/auth/me")
                    .header("authorization", format!("Bearer {member_token}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(revoked.status(), StatusCode::UNAUTHORIZED);
        let active = app
            .oneshot(
                Request::get("/auth/me")
                    .header("authorization", format!("Bearer {replacement}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(active.status(), StatusCode::OK);
    }
}
