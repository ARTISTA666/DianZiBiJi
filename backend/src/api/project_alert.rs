use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde_json::{json, Value};

use crate::{
    api::auth::CurrentUser,
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{
        AlertAcknowledgeRequest, AlertEvaluationSummary, AlertThresholdRead,
        AlertThresholdUpsertRequest, ProjectAlertRead,
    },
    permissions::{can_manage_project, require_project_access},
    project_alert::{
        acknowledge_alert, close_resolved_alerts, evaluate_project_alerts, evaluation_audit_detail,
        project_alert_thresholds, upsert_alert_threshold,
    },
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route(
            "/projects/{project_id}/alerts/evaluate",
            post(evaluate_alerts),
        )
        .route("/projects/{project_id}/alerts", get(list_alerts))
        .route(
            "/projects/{project_id}/alerts/{alert_id}/acknowledge",
            post(acknowledge_project_alert),
        )
        .route(
            "/projects/{project_id}/alerts/thresholds",
            get(get_alert_thresholds).post(upsert_alert_thresholds),
        )
}

/// 评估当前指标并落库告警（默认阈值兜底，可在 thresholds 端点调整）。
async fn evaluate_alerts(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<AlertEvaluationSummary>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let summary = evaluate_project_alerts(&mut transaction, project_id).await?;
    let resolved = close_resolved_alerts(&mut transaction, project_id, &summary).await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "alerts_evaluate",
            target_type: Some("project"),
            target_id: Some(project_id),
            detail: {
                let mut detail = evaluation_audit_detail(&summary);
                if let Some(object) = detail.as_object_mut() {
                    object.insert("resolved".to_owned(), json!(resolved));
                }
                detail
            },
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(summary))
}

/// 报警收件箱：open 在前，之后按 updated_at 倒序。
async fn list_alerts(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<Value>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let thresholds = project_alert_thresholds(&mut transaction, project_id).await?;
    let alerts: Vec<ProjectAlertRead> = sqlx::query_as(
        r#"
        SELECT id, project_id, metric, metric_value, level, status, detail,
               acknowledged_by, acknowledged_at, created_at
        FROM public.project_alerts
        WHERE project_id = $1
        ORDER BY (status = 'open') DESC, updated_at DESC, id DESC
        LIMIT 100
        "#,
    )
    .bind(project_id)
    .fetch_all(&mut *transaction)
    .await?;
    transaction.commit().await?;
    Ok(Json(json!({
        "alerts": alerts,
        "thresholds": thresholds,
    })))
}

/// 确认告警（导师人工动作）：open → acknowledged。
async fn acknowledge_project_alert(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, alert_id)): Path<(i32, i32)>,
    payload: Option<Json<AlertAcknowledgeRequest>>,
) -> Result<StatusCode, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    if !can_manage_project(&state.pool, &user, project_id).await? {
        return Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Manage permission required",
        ));
    }
    let note = payload.and_then(|Json(payload)| payload.note);
    let mut transaction = state.pool.begin().await?;
    acknowledge_alert(
        &mut transaction,
        project_id,
        alert_id,
        user.id,
        note.as_deref(),
    )
    .await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "alert_acknowledge",
            target_type: Some("project_alert"),
            target_id: Some(alert_id),
            detail: json!({ "note": note }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

/// 阈值读取（读权限即可见，便于成员理解当前口径）。
async fn get_alert_thresholds(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<Vec<AlertThresholdRead>>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let thresholds = project_alert_thresholds(&mut transaction, project_id).await?;
    transaction.commit().await?;
    Ok(Json(thresholds))
}

/// 阈值调整（仅导师/负责人）：每次调整留审计。
async fn upsert_alert_thresholds(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Json(payload): Json<AlertThresholdUpsertRequest>,
) -> Result<Json<AlertThresholdRead>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    if !can_manage_project(&state.pool, &user, project_id).await? {
        return Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Manage permission required",
        ));
    }
    let mut transaction = state.pool.begin().await?;
    let threshold = upsert_alert_threshold(&mut transaction, project_id, user.id, &payload).await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "alert_threshold_upsert",
            target_type: Some("project_alert_threshold"),
            target_id: Some(threshold.id),
            detail: json!({
                "metric": threshold.metric,
                "warn_threshold": threshold.warn_threshold,
                "critical_threshold": threshold.critical_threshold,
                "enabled": threshold.enabled,
            }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(threshold))
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

    async fn setup(
        database_url: &str,
        prefix: &str,
    ) -> (Router, String, String, i64, sqlx::PgPool) {
        let _ = tracing_subscriber::fmt()
            .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
            .with_test_writer()
            .try_init();
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("{prefix}_admin_{suffix}");
        let member_username = format!("{prefix}_member_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url.to_owned()),
            ("SECRET_KEY".to_owned(), "rust-alert-secret".to_owned()),
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
        let (_, login) = call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": admin_username, "password": "RustAdmin123!"})),
        )
        .await;
        let admin = login["access_token"].as_str().unwrap().to_owned();
        call(
            &app,
            "POST",
            "/users",
            Some(&admin),
            Some(json!({
                "username": member_username,
                "password": "Member123!",
                "display_name": "普通成员"
            })),
        )
        .await;
        let (_, member_login) = call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": member_username, "password": "Member123!"})),
        )
        .await;
        let member = member_login["access_token"].as_str().unwrap().to_owned();
        let (_, project) = call(
            &app,
            "POST",
            "/projects",
            Some(&admin),
            Some(json!({
                "name": format!("Alert Project {suffix}"),
                "approval_enabled": true
            })),
        )
        .await;
        let project_id = project["id"].as_i64().unwrap();
        (app, admin, member, project_id, pool)
    }

    /// 审批停滞指标：提交一条笔记（不审批）→ 评估 → open 告警；
    /// 确认后 acknowledged；重复评估幂等不新建。
    #[tokio::test]
    async fn test_review_stall_alert_lifecycle() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (app, admin, _member, project_id, pool) = setup(&database_url, "alert_a").await;

        // 阈值调到极小，保证刚提交的笔记立即触发 critical
        let (threshold_status, threshold) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/thresholds"),
            Some(&admin),
            Some(json!({
                "metric": "review_stall_hours",
                "warn_threshold": 0.0001,
                "critical_threshold": 0.0002,
                "enabled": true
            })),
        )
        .await;
        assert_eq!(threshold_status, StatusCode::OK);
        assert_eq!(threshold["metric"], "review_stall_hours");

        // 提交一条笔记（审批流开启，留在 SUBMITTED）
        let (_, note) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/notes"),
            Some(&admin),
            Some(json!({
                "title": "Stall alert note",
                "experiment_type": "Assay",
                "fixed_fields_json": {},
                "content_json": {"text": "结果: 状态良好"}
            })),
        )
        .await;
        let note_id = note["id"].as_i64().unwrap();
        let (submit_status, _) = call(
            &app,
            "POST",
            &format!("/notes/{note_id}/submit"),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(submit_status, StatusCode::OK);

        // 把 updated_at 回拨 2 小时，模拟"提交后无人审批"的停滞
        sqlx::query(
            "UPDATE experiment_notes SET updated_at = now() - interval '2 hours' WHERE id = $1",
        )
        .bind(note_id as i32)
        .execute(&pool)
        .await
        .unwrap();

        // 评估 → review_stall critical 告警落库
        let (eval_status, summary) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/evaluate"),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(eval_status, StatusCode::OK);
        let stall = summary["metrics"]
            .as_array()
            .unwrap()
            .iter()
            .find(|m| m["metric"] == "review_stall_hours")
            .unwrap();
        assert_eq!(stall["level"], "critical");

        let (_, inbox) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/alerts"),
            Some(&admin),
            None,
        )
        .await;
        let alerts = inbox["alerts"].as_array().unwrap();
        assert_eq!(alerts.len(), 1);
        assert_eq!(alerts[0]["status"], "open");
        assert_eq!(alerts[0]["level"], "critical");
        let alert_id = alerts[0]["id"].as_i64().unwrap();

        // 再评估一次：open 幂等去重，不新建
        let (_, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/evaluate"),
            Some(&admin),
            None,
        )
        .await;
        let (_, inbox) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/alerts"),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(inbox["alerts"].as_array().unwrap().len(), 1);

        // 审批通过 → 指标回落 → 评估自动 resolved
        let (approve_status, _) = call(
            &app,
            "POST",
            &format!("/notes/{note_id}/approve"),
            Some(&admin),
            Some(json!({})),
        )
        .await;
        assert_eq!(approve_status, StatusCode::OK);
        let (_, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/evaluate"),
            Some(&admin),
            None,
        )
        .await;
        let (_, inbox) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/alerts"),
            Some(&admin),
            None,
        )
        .await;
        let alerts = inbox["alerts"].as_array().unwrap();
        assert_eq!(alerts.len(), 1);
        assert_eq!(alerts[0]["status"], "resolved");

        // 已 resolved 的历史不再被 acknowledge 改动
        let (ack_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/{alert_id}/acknowledge"),
            Some(&admin),
            Some(json!({"note": "late ack"})),
        )
        .await;
        assert_eq!(ack_status, StatusCode::NOT_FOUND);
    }

    /// 确认闭环：critical 告警 → 导师确认（带备注）→ acknowledged + 审计留痕。
    #[tokio::test]
    async fn test_alert_acknowledge_and_threshold_permission() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (app, admin, member, project_id, pool) = setup(&database_url, "alert_b").await;

        // 拉高退回率阈值到 0 不可触发；用 review_stall 触发
        call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/thresholds"),
            Some(&admin),
            Some(json!({
                "metric": "review_stall_hours",
                "warn_threshold": 0.0001,
                "critical_threshold": 0.0002,
                "enabled": true
            })),
        )
        .await;
        let (_, note) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/notes"),
            Some(&admin),
            Some(json!({
                "title": "Ack alert note",
                "experiment_type": "Assay",
                "fixed_fields_json": {},
                "content_json": {"text": "结果: 状态良好"}
            })),
        )
        .await;
        let note_id_b = note["id"].as_i64().unwrap();
        call(
            &app,
            "POST",
            &format!("/notes/{note_id_b}/submit"),
            Some(&admin),
            None,
        )
        .await;
        sqlx::query(
            "UPDATE experiment_notes SET updated_at = now() - interval '2 hours' WHERE id = $1",
        )
        .bind(note_id_b as i32)
        .execute(&pool)
        .await
        .unwrap();
        call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/evaluate"),
            Some(&admin),
            None,
        )
        .await;
        let (_, inbox) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/alerts"),
            Some(&admin),
            None,
        )
        .await;
        let alert_id = inbox["alerts"][0]["id"].as_i64().unwrap();

        // 普通成员无 manage 权限：确认与调阈均 403
        let (member_ack_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/{alert_id}/acknowledge"),
            Some(&member),
            Some(json!({})),
        )
        .await;
        assert_eq!(member_ack_status, StatusCode::FORBIDDEN);
        let (member_threshold_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/thresholds"),
            Some(&member),
            Some(json!({
                "metric": "review_stall_hours",
                "warn_threshold": 1.0,
                "critical_threshold": 2.0,
                "enabled": true
            })),
        )
        .await;
        assert_eq!(member_threshold_status, StatusCode::FORBIDDEN);

        // 导师确认 → acknowledged，备注写入 detail
        let (ack_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/{alert_id}/acknowledge"),
            Some(&admin),
            Some(json!({"note": "已线下提醒学生提交"})),
        )
        .await;
        assert_eq!(ack_status, StatusCode::NO_CONTENT);
        let (_, inbox) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/alerts"),
            Some(&admin),
            None,
        )
        .await;
        let alert = inbox["alerts"]
            .as_array()
            .unwrap()
            .iter()
            .find(|a| a["id"].as_i64().unwrap() == alert_id)
            .unwrap();
        assert_eq!(alert["status"], "acknowledged");
        assert!(alert["detail"]
            .as_str()
            .unwrap()
            .contains("已线下提醒学生提交"));
        assert!(alert["acknowledged_at"].is_string());

        // 非法指标 / warn > critical 被拒
        let (bad_metric_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/thresholds"),
            Some(&admin),
            Some(json!({
                "metric": "vibes",
                "warn_threshold": 1.0,
                "critical_threshold": 2.0,
                "enabled": true
            })),
        )
        .await;
        assert_eq!(bad_metric_status, StatusCode::BAD_REQUEST);
        let (inverted_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/thresholds"),
            Some(&admin),
            Some(json!({
                "metric": "return_rate",
                "warn_threshold": 0.9,
                "critical_threshold": 0.3,
                "enabled": true
            })),
        )
        .await;
        assert_eq!(inverted_status, StatusCode::BAD_REQUEST);
    }
}
