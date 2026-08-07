mod agents;
mod audit;
mod auth;
mod files;
mod groups;
mod knowledge_graph;
mod maturity;
mod mcp;
mod notes;
mod ocr;
mod projects;
mod rag;
mod search;
mod templates;
mod users;

pub use rag::schedule_queued_experiments;

use std::{sync::OnceLock, time::Instant};

use axum::{
    extract::{DefaultBodyLimit, FromRequestParts, Query, Request, State},
    http::{header, request::Parts, HeaderMap, HeaderValue, Method, StatusCode},
    middleware::{self, Next},
    response::{Html, IntoResponse, Response},
    routing::get,
    Json, Router,
};
use regex::Regex;
use serde::Deserialize;
use serde_json::{json, Value};
use tower_http::cors::{AllowHeaders, AllowMethods, CorsLayer};
use uuid::Uuid;

use crate::{error::ApiError, state::RateLimitDecision, AppState};

/// Client connection metadata extracted from request headers and stored
/// in request extensions by the `observe_request` middleware.
#[derive(Clone, Debug)]
pub struct ClientInfo {
    pub ip_address: String,
    pub user_agent: Option<String>,
}

impl ClientInfo {
    pub fn ip_opt(&self) -> Option<&str> {
        if self.ip_address == "unknown" {
            None
        } else {
            Some(&self.ip_address)
        }
    }

    pub fn ua_opt(&self) -> Option<&str> {
        self.user_agent.as_deref()
    }
}

impl FromRequestParts<AppState> for ClientInfo {
    type Rejection = std::convert::Infallible;

    async fn from_request_parts(
        parts: &mut Parts,
        _state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        Ok(parts
            .extensions
            .get::<ClientInfo>()
            .cloned()
            .unwrap_or_else(|| ClientInfo {
                ip_address: "unknown".to_owned(),
                user_agent: None,
            }))
    }
}

/// Build the root router.
///
/// # API versioning strategy
///
/// All business routes are currently registered at their canonical paths
/// (e.g. `/api/projects`, `/auth/login`) **without** an `/api/v1` prefix.
/// This is intentional: the frontend client calls these paths directly,
/// and introducing a version segment would cause a breaking change (404s
/// across the entire UI).
///
/// When a future v2 API is planned the recommended migration path is:
///   1. Duplicate or nest the current router under `.nest("/api/v1", business_router)`.
///   2. Keep the un-versioned routes as a compatibility shim until the
///      frontend has been migrated.
///   3. Use the `api_version_header` middleware (below) to negotiate the
///      version via the `X-API-Version` request header, allowing gradual
///      per-route opt-in without path changes.
///   4. Remove the shim once all clients target `/api/v1`.
pub fn build_app(state: AppState) -> Router {
    let body_limit = DefaultBodyLimit::max(state.settings.upload_max_bytes + 1024 * 1024);
    let origins: Vec<HeaderValue> = state
        .settings
        .cors_origin_list()
        .into_iter()
        .filter_map(|origin| origin.parse().ok())
        .collect();
    let cors = CorsLayer::new()
        .allow_origin(origins)
        .allow_credentials(true)
        .allow_methods(AllowMethods::mirror_request())
        .allow_headers(AllowHeaders::mirror_request());

    // ── Business routes ──────────────────────────────────────────────
    // TODO(api-versioning): when introducing /api/v1, wrap these merges
    // in a sub-Router and .nest("/api/v1", business_router) it.
    let business_router = Router::new()
        .merge(auth::router())
        .merge(agents::router())
        .merge(files::router())
        .merge(users::router())
        .merge(projects::router())
        .merge(rag::router())
        .merge(groups::router())
        .merge(knowledge_graph::router())
        .merge(maturity::router())
        .merge(templates::router())
        .merge(audit::router())
        .merge(notes::router())
        .merge(ocr::router())
        .merge(search::router())
        .merge(mcp::router());

    Router::new()
        // ── Operational probes (must stay at root) ───────────────────
        .route("/health", get(health))
        .route("/metrics", get(metrics))
        .route("/ready", get(ready))
        .route("/openapi.json", get(openapi))
        .route("/docs", get(swagger_docs))
        .route("/redoc", get(redoc_docs))
        // Business routes live at their current paths (no /api/v1 prefix)
        // to stay compatible with the existing frontend.
        .merge(business_router)
        .fallback(not_found)
        .layer(body_limit)
        .layer(cors)
        .layer(middleware::from_fn_with_state(
            state.clone(),
            rate_limit_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            observe_request,
        ))
        .with_state(state)
}

async fn health() -> Json<Value> {
    Json(json!({"status": "ok"}))
}

async fn openapi() -> Json<Value> {
    Json(
        serde_json::from_str(include_str!("../../openapi.json"))
            .expect("embedded OpenAPI contract must be valid JSON"),
    )
}

async fn swagger_docs() -> Html<&'static str> {
    Html(API_DOCS_HTML)
}

async fn redoc_docs() -> Html<&'static str> {
    Html(API_DOCS_HTML)
}

const API_DOCS_HTML: &str = r#"<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ELN API reference</title>
  <style>body{max-width:48rem;margin:4rem auto;padding:0 1.5rem;font:16px/1.6 system-ui,sans-serif;color:#172033}a{color:#155eef}</style>
</head>
<body>
  <h1>ELN API reference</h1>
  <p>The versioned OpenAPI 3.1 contract is served from this deployment without third-party assets.</p>
  <p><a href="openapi.json">Open the OpenAPI JSON contract</a></p>
</body>
</html>"#;

async fn metrics(State(state): State<AppState>, headers: HeaderMap) -> Response {
    let snapshot = state.metrics_snapshot();
    let accept = headers
        .get(header::ACCEPT)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("");
    if !accept.contains("application/json")
        && (accept.contains("text/plain") || accept.contains("openmetrics"))
    {
        return (
            [(header::CONTENT_TYPE, "text/plain; version=0.0.4")],
            metrics_prometheus(&snapshot),
        )
            .into_response();
    }
    Json(snapshot).into_response()
}

/// Render the JSON snapshot as Prometheus text exposition format,
/// mirroring the Python backend's metric names.
fn metrics_prometheus(snapshot: &Value) -> String {
    let number = |key: &str| snapshot.get(key).cloned().unwrap_or_else(|| json!(0));
    let mut lines = vec![
        "# HELP eln_uptime_seconds Seconds since the process started.".to_owned(),
        "# TYPE eln_uptime_seconds gauge".to_owned(),
        format!("eln_uptime_seconds {}", number("uptime_seconds")),
        "# HELP eln_requests_in_flight Requests currently being processed.".to_owned(),
        "# TYPE eln_requests_in_flight gauge".to_owned(),
        format!("eln_requests_in_flight {}", number("in_flight")),
        "# HELP eln_requests_total Total HTTP requests processed.".to_owned(),
        "# TYPE eln_requests_total counter".to_owned(),
        format!("eln_requests_total {}", number("total_requests")),
        "# HELP eln_requests_by_status_total HTTP requests grouped by status family.".to_owned(),
        "# TYPE eln_requests_by_status_total counter".to_owned(),
    ];
    if let Some(counts) = snapshot.get("status_counts").and_then(Value::as_object) {
        for (family, count) in counts {
            lines.push(format!(
                "eln_requests_by_status_total{{family=\"{family}\"}} {count}"
            ));
        }
    }
    lines.extend([
        "# HELP eln_request_duration_ms Request latency summary in milliseconds.".to_owned(),
        "# TYPE eln_request_duration_ms summary".to_owned(),
        format!(
            "eln_request_duration_ms{{stat=\"avg\"}} {}",
            number("avg_duration_ms")
        ),
        format!(
            "eln_request_duration_ms{{stat=\"p95\"}} {}",
            number("p95_duration_ms")
        ),
        format!(
            "eln_request_duration_ms{{stat=\"max\"}} {}",
            number("max_duration_ms")
        ),
    ]);
    lines.join("\n") + "\n"
}

#[derive(Deserialize, Default)]
struct ReadyQuery {
    deep: Option<String>,
}

async fn ready(
    State(state): State<AppState>,
    Query(query): Query<ReadyQuery>,
) -> Result<Json<Value>, ApiError> {
    // Basic checks – database connectivity and storage availability.
    sqlx::query("SELECT 1")
        .execute(&state.pool)
        .await
        .map_err(|_| ApiError::new(StatusCode::SERVICE_UNAVAILABLE, "Database unavailable"))?;
    let storage = tokio::fs::metadata("/storage")
        .await
        .map_err(|_| ApiError::new(StatusCode::SERVICE_UNAVAILABLE, "Storage unavailable"))?;
    if !storage.is_dir() || storage.permissions().readonly() {
        return Err(ApiError::new(
            StatusCode::SERVICE_UNAVAILABLE,
            "Storage unavailable",
        ));
    }

    let is_deep = query
        .deep
        .as_deref()
        .map(|v| v == "true" || v == "1")
        .unwrap_or(false);

    if !is_deep {
        return Ok(Json(json!({
            "status": "ready",
            "checks": {
                "database": "ok",
                "storage": "ok",
            },
            "revision": state.settings.app_revision,
        })));
    }

    // ── Deep checks ──────────────────────────────────────────────
    // Storage writability: attempt to create (and remove) a temp file.
    let storage_status = match tokio::fs::write("/storage/.healthcheck_probe", b"").await {
        Ok(_) => {
            let _ = tokio::fs::remove_file("/storage/.healthcheck_probe").await;
            "ok"
        }
        Err(_) => "readonly",
    };

    // LLM API: check configuration and attempt a lightweight connectivity probe.
    let llm_status = if state.settings.deepseek_api_key.trim().is_empty() {
        "unconfigured"
    } else {
        let base_url = state.settings.deepseek_api_base_url.trim_end_matches('/');
        let probe_url = format!("{base_url}/v1/models");
        match state
            .client
            .get(&probe_url)
            .bearer_auth(&state.settings.deepseek_api_key)
            .timeout(std::time::Duration::from_secs(5))
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() || resp.status().is_redirection() => "ok",
            Ok(resp)
                if resp.status() == StatusCode::UNAUTHORIZED
                    || resp.status() == StatusCode::FORBIDDEN =>
            {
                // API responded – key may be invalid but endpoint is reachable.
                "ok"
            }
            Ok(_) => "unreachable",
            Err(_) => "unreachable",
        }
    };

    let degraded = storage_status != "ok" || llm_status == "unreachable";

    Ok(Json(json!({
        "status": if degraded { "degraded" } else { "ready" },
        "checks": {
            "database": "ok",
            "storage": storage_status,
            "llm_api": llm_status,
        },
        "revision": state.settings.app_revision,
    })))
}

async fn not_found() -> ApiError {
    ApiError::new(StatusCode::NOT_FOUND, "Not Found")
}

/// Paths that bypass the global rate limiter because they are either
/// operational probes or have their own dedicated throttling.
const RATE_LIMIT_EXEMPT_PATHS: &[&str] = &[
    "/health",
    "/metrics",
    "/ready",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/auth/login",
];

/// Extract the client IP address from the request, preferring proxy headers.
fn client_ip(request: &Request) -> String {
    request
        .headers()
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.split(',').next())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .or_else(|| {
            request
                .headers()
                .get("x-real-ip")
                .and_then(|v| v.to_str().ok())
                .filter(|s| !s.is_empty())
        })
        .unwrap_or("unknown")
        .to_owned()
}

async fn rate_limit_middleware(
    State(state): State<AppState>,
    request: Request,
    next: Next,
) -> Response {
    let path = request.uri().path();
    if RATE_LIMIT_EXEMPT_PATHS.contains(&path) {
        return next.run(request).await;
    }
    let ip = client_ip(&request);
    let is_read = matches!(
        *request.method(),
        Method::GET | Method::HEAD | Method::OPTIONS
    );
    let RateLimitDecision { allowed } = state.check_global_rate_limit(&ip, is_read);
    if !allowed {
        tracing::warn!(ip, path, "global rate limit exceeded");
        return (
            StatusCode::TOO_MANY_REQUESTS,
            Json(json!({"detail": "请求过于频繁，请稍后再试"})),
        )
            .into_response();
    }
    next.run(request).await
}

async fn observe_request(
    State(state): State<AppState>,
    mut request: Request,
    next: Next,
) -> Response {
    static REQUEST_ID: OnceLock<Regex> = OnceLock::new();
    let request_id = request
        .headers()
        .get("x-request-id")
        .and_then(|value| value.to_str().ok())
        .filter(|value| {
            REQUEST_ID
                .get_or_init(|| Regex::new(r"^[A-Za-z0-9._-]{1,64}$").unwrap())
                .is_match(value)
        })
        .map(str::to_owned)
        .unwrap_or_else(|| Uuid::new_v4().simple().to_string());
    request
        .headers_mut()
        .insert("x-request-id", HeaderValue::from_str(&request_id).unwrap());
    // Extract client IP and User-Agent and store in request extensions.
    let ip = client_ip(&request);
    let user_agent = request
        .headers()
        .get(header::USER_AGENT)
        .and_then(|value| value.to_str().ok())
        .map(|s| s.to_owned());
    request.extensions_mut().insert(ClientInfo {
        ip_address: ip,
        user_agent,
    });
    let method: Method = request.method().clone();
    let path = request.uri().path().to_owned();
    let started = Instant::now();
    state.request_started();
    let mut response = next.run(request).await;
    let duration_ms = started.elapsed().as_millis() as u64;
    state.request_finished(response.status().as_u16(), duration_ms);
    response
        .headers_mut()
        .insert("x-request-id", HeaderValue::from_str(&request_id).unwrap());
    response
        .headers_mut()
        .insert("x-backend-runtime", HeaderValue::from_static("axum"));
    tracing::info!(
        request_id,
        method = %method,
        path,
        status = response.status().as_u16(),
        duration_ms,
        "request"
    );
    response
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use axum::{
        body::{to_bytes, Body},
        http::{Method, Request, StatusCode},
    };
    use serde_json::Value;
    use sqlx::postgres::PgPoolOptions;
    use tower::ServiceExt;

    use super::build_app;
    use crate::{config::Settings, AppState};

    fn test_state() -> AppState {
        let settings = Settings::from_map(&HashMap::new()).unwrap();
        let pool = PgPoolOptions::new()
            .connect_lazy("postgresql://unused:unused@127.0.0.1/unused")
            .unwrap();
        AppState::new(pool, settings).unwrap()
    }

    #[tokio::test]
    async fn test_health_contract_and_runtime_headers() {
        let response = build_app(test_state())
            .oneshot(
                Request::get("/health")
                    .header("x-request-id", "contract-123")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()["x-request-id"], "contract-123");
        assert_eq!(response.headers()["x-backend-runtime"], "axum");
        let body: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), 1024).await.unwrap()).unwrap();
        assert_eq!(body, serde_json::json!({"status": "ok"}));
    }

    #[tokio::test]
    async fn test_auth_me_without_token_returns_fastapi_compatible_401() {
        let response = build_app(test_state())
            .oneshot(Request::get("/auth/me").body(Body::empty()).unwrap())
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let body: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), 1024).await.unwrap()).unwrap();
        assert_eq!(body, serde_json::json!({"detail": "Not authenticated"}));
    }

    #[tokio::test]
    async fn test_openapi_contract_lists_all_migrated_operations() {
        let response = build_app(test_state())
            .oneshot(Request::get("/openapi.json").body(Body::empty()).unwrap())
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), 256 * 1024).await.unwrap())
                .unwrap();
        let operations = body["paths"]
            .as_object()
            .unwrap()
            .values()
            .filter_map(Value::as_object)
            .map(|path| path.len())
            .sum::<usize>();
        assert_eq!(operations, 85);
        assert!(body["paths"]["/api/agents/generate"]["post"].is_object());
        assert!(body["paths"]["/maturity/status"]["get"].is_object());
    }

    #[tokio::test]
    async fn api_docs_are_same_origin_and_proxy_prefix_safe() {
        for path in ["/docs", "/redoc"] {
            let response = build_app(test_state())
                .oneshot(Request::get(path).body(Body::empty()).unwrap())
                .await
                .unwrap();

            assert_eq!(response.status(), StatusCode::OK);
            let body = String::from_utf8(
                to_bytes(response.into_body(), 64 * 1024)
                    .await
                    .unwrap()
                    .to_vec(),
            )
            .unwrap();
            assert!(body.contains("href=\"openapi.json\""));
            assert!(!body.contains("https://"));
            assert!(!body.contains("<script"));
        }
    }

    #[tokio::test]
    async fn every_openapi_operation_is_registered_on_the_rust_router() {
        let contract: Value = serde_json::from_str(include_str!("../../openapi.json")).unwrap();
        let app = build_app(test_state());
        for (path, operations) in contract["paths"].as_object().unwrap() {
            let concrete_path = path
                .split('/')
                .map(|segment| {
                    if segment.starts_with('{') && segment.ends_with('}') {
                        "1"
                    } else {
                        segment
                    }
                })
                .collect::<Vec<_>>()
                .join("/");
            for method in operations.as_object().unwrap().keys() {
                let method = Method::from_bytes(method.to_ascii_uppercase().as_bytes()).unwrap();
                let response = app
                    .clone()
                    .oneshot(
                        Request::builder()
                            .method(method.clone())
                            .uri(&concrete_path)
                            .header("content-type", "application/json")
                            .body(Body::from("{}"))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                let status = response.status();
                let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
                assert!(
                    status != StatusCode::NOT_FOUND
                        || body.as_ref() != br#"{"detail":"Not Found"}"#,
                    "missing Rust route: {method} {path}"
                );
            }
        }
    }

    #[tokio::test]
    async fn every_openapi_operation_rejects_anonymous_requests() {
        // Endpoints that are public by design; everything else must return 401
        // when neither a Bearer token nor the auth cookie is presented.
        let public_routes = [
            ("get", "/health"),
            ("get", "/metrics"),
            ("get", "/ready"),
            ("post", "/auth/login"),
        ];
        let contract: Value = serde_json::from_str(include_str!("../../openapi.json")).unwrap();
        // Raise the global rate limits well above the operation count so the
        // anonymous sweep asserts 401 instead of tripping 429 from one IP.
        let app = build_app(rate_limited_test_state(10_000, 10_000));
        for (path, operations) in contract["paths"].as_object().unwrap() {
            let concrete_path = path
                .split('/')
                .map(|segment| {
                    if segment.starts_with('{') && segment.ends_with('}') {
                        "1"
                    } else {
                        segment
                    }
                })
                .collect::<Vec<_>>()
                .join("/");
            for method in operations.as_object().unwrap().keys() {
                if public_routes.contains(&(method.as_str(), path.as_str())) {
                    continue;
                }
                let method = Method::from_bytes(method.to_ascii_uppercase().as_bytes()).unwrap();
                let response = app
                    .clone()
                    .oneshot(
                        Request::builder()
                            .method(method.clone())
                            .uri(&concrete_path)
                            .header("content-type", "application/json")
                            .body(Body::from("{}"))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                assert_eq!(
                    response.status(),
                    StatusCode::UNAUTHORIZED,
                    "endpoint reachable without credentials: {method} {path}"
                );
            }
        }
    }

    fn rate_limited_test_state(read_limit: u64, write_limit: u64) -> AppState {
        let settings = Settings::from_map(&HashMap::from([
            (
                "GLOBAL_RATE_LIMIT_READ_PER_MINUTE".to_owned(),
                read_limit.to_string(),
            ),
            (
                "GLOBAL_RATE_LIMIT_WRITE_PER_MINUTE".to_owned(),
                write_limit.to_string(),
            ),
        ]))
        .unwrap();
        let pool = PgPoolOptions::new()
            .connect_lazy("postgresql://unused:unused@127.0.0.1/unused")
            .unwrap();
        AppState::new(pool, settings).unwrap()
    }

    #[tokio::test]
    async fn test_rate_limit_exempts_health_endpoint() {
        // Even with the minimum read limit (1/min) the health endpoint must
        // still respond 200 because it is on the exemption list.
        let app = build_app(rate_limited_test_state(1, 1));
        // Exhaust the single allowed read request first.
        let _ = app
            .clone()
            .oneshot(Request::get("/api/projects").body(Body::empty()).unwrap())
            .await
            .unwrap();
        // Health must remain reachable even after the read quota is gone.
        let response = app
            .oneshot(Request::get("/health").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_rate_limit_returns_429_when_write_quota_exhausted() {
        let app = build_app(rate_limited_test_state(1000, 1));
        // First write should succeed (quota = 1).
        let first = app
            .clone()
            .oneshot(
                Request::post("/api/projects")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_ne!(first.status(), StatusCode::TOO_MANY_REQUESTS);

        // Second write from the same IP must be rejected with 429.
        let second = app
            .oneshot(
                Request::post("/api/projects")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(second.status(), StatusCode::TOO_MANY_REQUESTS);
        let body: Value =
            serde_json::from_slice(&to_bytes(second.into_body(), 1024).await.unwrap()).unwrap();
        assert_eq!(body["detail"], "请求过于频繁，请稍后再试");
    }

    #[tokio::test]
    async fn test_rate_limit_respects_x_forwarded_for() {
        let app = build_app(rate_limited_test_state(1000, 1));
        // First request from IP-A succeeds.
        let r1 = app
            .clone()
            .oneshot(
                Request::post("/api/projects")
                    .header("x-forwarded-for", "10.0.0.1")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_ne!(r1.status(), StatusCode::TOO_MANY_REQUESTS);

        // Second request from IP-A is blocked.
        let r2 = app
            .clone()
            .oneshot(
                Request::post("/api/projects")
                    .header("x-forwarded-for", "10.0.0.1")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(r2.status(), StatusCode::TOO_MANY_REQUESTS);

        // Request from IP-B still succeeds (separate quota).
        let r3 = app
            .oneshot(
                Request::post("/api/projects")
                    .header("x-forwarded-for", "10.0.0.2")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_ne!(r3.status(), StatusCode::TOO_MANY_REQUESTS);
    }
}
