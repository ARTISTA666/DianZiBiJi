use axum::{
    extract::{FromRequestParts, State},
    http::{header::SET_COOKIE, request::Parts, StatusCode},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde_json::json;

use crate::{
    api::ClientInfo,
    config::Settings,
    error::ApiError,
    models::{CurrentUserResponse, LoginRequest, TokenResponse, UserRecord},
    security::{create_access_token, decode_access_token, verify_password},
    AppState,
};

pub const AUTH_COOKIE_NAME: &str = "eln_access_token";
const INVALID_CREDENTIALS_MESSAGE: &str = "账号或密码错误";
const LOGIN_RATE_LIMIT_MESSAGE: &str = "登录尝试次数过多，请稍后再试";
// A valid cost-12 bcrypt hash keeps unknown and disabled-user failures on the
// same password-verification path as active users without exposing a real hash.
const DUMMY_PASSWORD_HASH: &str = "$2b$12$tGevqvIrxJXMwGuFVrrSuu.jAgV9Txm1CdklGWuvfnqJgc7D6KFq2";

fn cookie_token(parts: &Parts) -> Option<String> {
    let cookies = parts
        .headers
        .get("cookie")
        .and_then(|value| value.to_str().ok())?;
    cookies.split(';').find_map(|pair| {
        let (name, value) = pair.trim().split_once('=')?;
        (name == AUTH_COOKIE_NAME).then(|| value.to_owned())
    })
}

pub(crate) fn auth_cookie(settings: &Settings, token: &str, max_age_seconds: i64) -> String {
    let mut cookie = format!(
        "{AUTH_COOKIE_NAME}={token}; Max-Age={max_age_seconds}; Path=/; HttpOnly; SameSite=Lax"
    );
    if settings.app_env == "production" {
        cookie.push_str("; Secure");
    }
    cookie
}

#[derive(Clone, Debug)]
pub struct CurrentUser(pub UserRecord);

impl FromRequestParts<AppState> for CurrentUser {
    type Rejection = ApiError;

    async fn from_request_parts(
        parts: &mut Parts,
        state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        // Bearer header first (API scripts/tests), HttpOnly cookie for browsers.
        let token = match parts
            .headers
            .get("authorization")
            .and_then(|value| value.to_str().ok())
        {
            Some(authorization) => authorization
                .strip_prefix("Bearer ")
                .ok_or_else(|| ApiError::new(StatusCode::UNAUTHORIZED, "Invalid token"))?
                .to_owned(),
            None => cookie_token(parts)
                .ok_or_else(|| ApiError::new(StatusCode::UNAUTHORIZED, "Not authenticated"))?,
        };
        let claims = decode_access_token(&token, &state.settings.secret_key)
            .map_err(|_| ApiError::new(StatusCode::UNAUTHORIZED, "Invalid token"))?;
        let user_id = claims
            .subject
            .parse::<i32>()
            .map_err(|_| ApiError::new(StatusCode::UNAUTHORIZED, "Invalid user"))?;
        let user = sqlx::query_as::<_, UserRecord>(
            r#"
            SELECT id, username, password_hash, display_name, email,
                   lower(role::text) AS role, lower(status::text) AS status, auth_version
            FROM users
            WHERE id = $1
            "#,
        )
        .bind(user_id)
        .fetch_optional(&state.pool)
        .await
        .map_err(ApiError::from)?
        .filter(|user| user.status == "active" && user.auth_version == claims.auth_version)
        .ok_or_else(|| ApiError::new(StatusCode::UNAUTHORIZED, "Invalid user"))?;
        Ok(Self(user))
    }
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/auth/login", post(login))
        .route("/auth/me", get(me))
        .route("/auth/logout", post(logout))
}

async fn login(
    State(state): State<AppState>,
    client: ClientInfo,
    Json(payload): Json<LoginRequest>,
) -> Result<impl IntoResponse, ApiError> {
    let _login_attempt = state
        .try_acquire_login_attempt()
        .ok_or_else(|| ApiError::new(StatusCode::TOO_MANY_REQUESTS, LOGIN_RATE_LIMIT_MESSAGE))?;
    let user = sqlx::query_as::<_, UserRecord>(
        r#"
        SELECT id, username, password_hash, display_name, email,
               lower(role::text) AS role, lower(status::text) AS status, auth_version
        FROM users
        WHERE username = $1
        "#,
    )
    .bind(&payload.username)
    .fetch_optional(&state.pool)
    .await?;
    let user = user.filter(|user| user.status == "active");
    let password = payload.password;
    let password_hash = user
        .as_ref()
        .map(|user| user.password_hash.clone())
        .unwrap_or_else(|| DUMMY_PASSWORD_HASH.to_owned());
    let valid = tokio::task::spawn_blocking(move || verify_password(&password, &password_hash))
        .await
        .map_err(ApiError::internal)?;
    let Some(user) = user.filter(|_| valid) else {
        let decision = state.record_login_failure(&payload.username);
        tokio::time::sleep(decision.delay).await;
        let status = if decision.limited {
            StatusCode::TOO_MANY_REQUESTS
        } else {
            StatusCode::UNAUTHORIZED
        };
        let message = if status == StatusCode::TOO_MANY_REQUESTS {
            LOGIN_RATE_LIMIT_MESSAGE
        } else {
            INVALID_CREDENTIALS_MESSAGE
        };
        return Err(ApiError::new(status, message));
    };
    state.clear_login_failures(&payload.username);
    sqlx::query(
        r#"
        INSERT INTO audit_logs (
            actor_user_id, project_id, action, target_type, target_id,
            detail_json, ip_address, user_agent
        )
        VALUES ($1, NULL, 'login', 'user', $1, '{}'::json, $2, $3)
        "#,
    )
    .bind(user.id)
    .bind(client.ip_opt())
    .bind(client.ua_opt())
    .execute(&state.pool)
    .await?;
    let access_token = create_access_token(
        &user.id.to_string(),
        user.auth_version,
        &state.settings.secret_key,
        state.settings.access_token_expire_minutes,
    )
    .map_err(ApiError::internal)?;
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

async fn me(CurrentUser(user): CurrentUser) -> Json<CurrentUserResponse> {
    Json(CurrentUserResponse {
        id: user.id,
        username: user.username,
        display_name: user.display_name,
        role: user.role,
    })
}

async fn logout(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
) -> Result<impl IntoResponse, ApiError> {
    let mut transaction = state.pool.begin().await?;
    sqlx::query("UPDATE users SET auth_version = auth_version + 1 WHERE id = $1")
        .bind(user.id)
        .execute(&mut *transaction)
        .await?;
    sqlx::query(
        r#"
        INSERT INTO audit_logs (
            actor_user_id, project_id, action, target_type, target_id,
            detail_json, ip_address, user_agent
        )
        VALUES ($1, NULL, 'logout', 'user', $1, '{}'::json, $2, $3)
        "#,
    )
    .bind(user.id)
    .bind(client.ip_opt())
    .bind(client.ua_opt())
    .execute(&mut *transaction)
    .await?;
    transaction.commit().await?;
    let cookie = auth_cookie(&state.settings, "", 0);
    Ok(([(SET_COOKIE, cookie)], Json(json!({"ok": true}))))
}

pub fn require_admin(user: &UserRecord) -> Result<(), ApiError> {
    if user.role == "super_admin" {
        Ok(())
    } else {
        Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Admin permission required",
        ))
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use axum::{
        body::{to_bytes, Body},
        http::{Request, StatusCode},
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

    #[test]
    fn test_dummy_password_hash_uses_a_real_bcrypt_work_factor() {
        assert!(super::DUMMY_PASSWORD_HASH.starts_with("$2b$12$"));
        assert!(crate::security::verify_password(
            "dummy-login-password",
            super::DUMMY_PASSWORD_HASH
        ));
    }

    #[tokio::test]
    async fn test_login_me_logout_revokes_presented_token() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let admin_username = format!("auth_admin_{}", &Uuid::new_v4().simple().to_string()[..8]);
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

        let login = app
            .clone()
            .oneshot(
                Request::post("/auth/login")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({"username": admin_username, "password": "RustAdmin123!"})
                            .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(login.status(), StatusCode::OK);
        let set_cookie = login
            .headers()
            .get("set-cookie")
            .and_then(|value| value.to_str().ok())
            .unwrap()
            .to_owned();
        assert!(set_cookie.starts_with(super::AUTH_COOKIE_NAME));
        assert!(set_cookie.contains("HttpOnly"));
        let cookie_pair = set_cookie.split(';').next().unwrap().to_owned();
        let payload: Value =
            serde_json::from_slice(&to_bytes(login.into_body(), 4096).await.unwrap()).unwrap();
        let token = payload["access_token"].as_str().unwrap();
        let authorization = format!("Bearer {token}");

        let me_via_cookie = app
            .clone()
            .oneshot(
                Request::get("/auth/me")
                    .header("cookie", &cookie_pair)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(me_via_cookie.status(), StatusCode::OK);

        let me = app
            .clone()
            .oneshot(
                Request::get("/auth/me")
                    .header("authorization", &authorization)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(me.status(), StatusCode::OK);

        let logout = app
            .clone()
            .oneshot(
                Request::post("/auth/logout")
                    .header("authorization", &authorization)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(logout.status(), StatusCode::OK);

        let revoked = app
            .oneshot(
                Request::get("/auth/me")
                    .header("authorization", &authorization)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(revoked.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_login_rate_limit_counts_unknown_and_wrong_password_and_success_resets() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let admin_username = format!("auth_limit_{}", &Uuid::new_v4().simple().to_string()[..8]);
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
            ("LOGIN_RATE_LIMIT_MAX_ATTEMPTS".to_owned(), "2".to_owned()),
            (
                "LOGIN_RATE_LIMIT_WINDOW_SECONDS".to_owned(),
                "60".to_owned(),
            ),
            ("LOGIN_RATE_LIMIT_MAX_ENTRIES".to_owned(), "32".to_owned()),
            ("LOGIN_FAILURE_DELAY_BASE_MS".to_owned(), "1".to_owned()),
            ("LOGIN_FAILURE_DELAY_MAX_MS".to_owned(), "2".to_owned()),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let app = build_app(AppState::new(pool.clone(), settings).unwrap());

        let request_login = |username: String, password: &'static str| {
            Request::post("/auth/login")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({"username": username, "password": password}).to_string(),
                ))
                .unwrap()
        };
        let unknown_username = format!("missing_{}", Uuid::new_v4().simple());

        let unknown_first = app
            .clone()
            .oneshot(request_login(unknown_username.clone(), "WrongPass123!"))
            .await
            .unwrap();
        let unknown_second = app
            .clone()
            .oneshot(request_login(unknown_username, "WrongPass123!"))
            .await
            .unwrap();
        let wrong_first = app
            .clone()
            .oneshot(request_login(admin_username.clone(), "WrongPass123!"))
            .await
            .unwrap();
        let wrong_second = app
            .clone()
            .oneshot(request_login(admin_username.clone(), "WrongPass123!"))
            .await
            .unwrap();

        assert_eq!(unknown_first.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(unknown_second.status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(wrong_first.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(wrong_second.status(), StatusCode::TOO_MANY_REQUESTS);
        let unknown_body = to_bytes(unknown_second.into_body(), 4096).await.unwrap();
        let wrong_body = to_bytes(wrong_second.into_body(), 4096).await.unwrap();
        assert_eq!(unknown_body, wrong_body);

        let reset_username = format!("auth_reset_{}", &Uuid::new_v4().simple().to_string()[..8]);
        let password_hash = crate::security::hash_password("ResetPass123!").unwrap();
        sqlx::query(
            r#"
            INSERT INTO users (
                username, password_hash, display_name, email, role, status, auth_version
            )
            VALUES ($1, $2, 'Rate limit reset user', NULL, 'MEMBER', 'ACTIVE', 0)
            "#,
        )
        .bind(&reset_username)
        .bind(password_hash)
        .execute(&pool)
        .await
        .unwrap();

        let reset_wrong = app
            .clone()
            .oneshot(request_login(reset_username.clone(), "WrongPass123!"))
            .await
            .unwrap();
        let reset_success = app
            .clone()
            .oneshot(request_login(reset_username.clone(), "ResetPass123!"))
            .await
            .unwrap();
        let after_reset = app
            .oneshot(request_login(reset_username, "WrongPass123!"))
            .await
            .unwrap();

        assert_eq!(reset_wrong.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(reset_success.status(), StatusCode::OK);
        assert_eq!(after_reset.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_correct_password_is_not_locked_out_by_five_attacker_failures() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let admin_username = format!("auth_no_lock_{}", &Uuid::new_v4().simple().to_string()[..8]);
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
            ("LOGIN_RATE_LIMIT_MAX_ATTEMPTS".to_owned(), "5".to_owned()),
            (
                "LOGIN_RATE_LIMIT_WINDOW_SECONDS".to_owned(),
                "60".to_owned(),
            ),
            ("LOGIN_FAILURE_DELAY_BASE_MS".to_owned(), "1".to_owned()),
            ("LOGIN_FAILURE_DELAY_MAX_MS".to_owned(), "2".to_owned()),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let app = build_app(AppState::new(pool, settings).unwrap());

        for attempt in 1..=5 {
            let response = app
                .clone()
                .oneshot(
                    Request::post("/auth/login")
                        .header("content-type", "application/json")
                        .body(Body::from(
                            json!({"username": &admin_username, "password": "WrongPass123!"})
                                .to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            let expected = if attempt == 5 {
                StatusCode::TOO_MANY_REQUESTS
            } else {
                StatusCode::UNAUTHORIZED
            };
            assert_eq!(response.status(), expected);
        }

        let correct = app
            .oneshot(
                Request::post("/auth/login")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({"username": &admin_username, "password": "RustAdmin123!"})
                            .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(correct.status(), StatusCode::OK);
    }
}
