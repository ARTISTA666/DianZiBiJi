use axum::http::StatusCode;
use chrono::Utc;
use serde_json::json;
use sqlx::{Postgres, Transaction};

use crate::{
    error::ApiError,
    models::{
        AlertEvaluationSummary, AlertMetricSnapshot, AlertThresholdRead,
        AlertThresholdUpsertRequest, ALERT_METRICS, ALERT_METRIC_BLUEPRINT_STAGNANT_DAYS,
        ALERT_METRIC_PROGRESS_DEVIATION, ALERT_METRIC_RETURN_RATE, ALERT_METRIC_REVIEW_STALL_HOURS,
    },
};

pub const ALERT_LEVELS: &[&str] = &["warn", "critical"];
/// 近 N 条审批用于计算退回率（与导师讨论的"提交质量"口径）。
pub const RETURN_RATE_WINDOW: i64 = 10;

fn is_alert_metric(metric: &str) -> bool {
    ALERT_METRICS.contains(&metric)
}

/// 项目预警阈值行（缺省阈值在无行时生效）。
pub async fn project_alert_thresholds(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
) -> Result<Vec<AlertThresholdRead>, ApiError> {
    let rows = sqlx::query_as(
        r#"
        SELECT id, project_id, metric, warn_threshold, critical_threshold, enabled, updated_by, updated_at
        FROM public.project_alert_thresholds
        WHERE project_id = $1
        ORDER BY metric
        "#,
    )
    .bind(project_id)
    .fetch_all(&mut **transaction)
    .await?;
    Ok(rows)
}

/// 指标计算与告警判定（Level = none/warn/critical）。
pub async fn evaluate_project_alerts(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
) -> Result<AlertEvaluationSummary, ApiError> {
    let thresholds = project_alert_thresholds(transaction, project_id).await?;
    let mut metrics: Vec<AlertMetricSnapshot> = Vec::new();

    // ── 指标 1：最老待审笔记等待时长（小时）──
    let review_stall: Option<f64> = sqlx::query_scalar(
        r#"
        SELECT (EXTRACT(EPOCH FROM (now() - n.updated_at)) / 3600.0)::float8
        FROM public.experiment_notes n
        WHERE n.project_id = $1 AND n.status = 'SUBMITTED'::notestatus
        ORDER BY n.updated_at ASC LIMIT 1
        "#,
    )
    .bind(project_id)
    .fetch_optional(&mut **transaction)
    .await?;
    metrics.push(snapshot_metric(
        &thresholds,
        ALERT_METRIC_REVIEW_STALL_HOURS,
        review_stall.unwrap_or(0.0),
    ));

    // ── 指标 2：近 RETURN_RATE_WINDOW 条审批的退回占比 ──
    let recent: Vec<String> = sqlx::query_scalar(
        r#"
        SELECT lower(action)
        FROM public.note_approvals a
        JOIN public.experiment_notes n ON n.id = a.note_id
        WHERE n.project_id = $1
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT $2
        "#,
    )
    .bind(project_id)
    .bind(RETURN_RATE_WINDOW as i32)
    .fetch_all(&mut **transaction)
    .await?;
    let return_rate = if recent.is_empty() {
        0.0
    } else {
        recent
            .iter()
            .filter(|action| action.as_str() == "return")
            .count() as f64
            / recent.len() as f64
    };
    metrics.push(snapshot_metric(
        &thresholds,
        ALERT_METRIC_RETURN_RATE,
        return_rate,
    ));

    // ── 指标 3：蓝图最近实证距今天数（无蓝图视为 0，不告警）──
    let blueprint_stagnant: Option<f64> = sqlx::query_scalar(
        r#"
        SELECT (EXTRACT(EPOCH FROM (now() - max(e.updated_at))) / 86400.0)::float8
        FROM public.kg_blueprint_nodes b
        JOIN public.kg_entities e
            ON e.project_id = b.project_id AND e.entity_type = b.entity_type
           AND e.normalized_label = b.normalized_label
        WHERE b.project_id = $1 AND b.status <> 'retired'
        "#,
    )
    .bind(project_id)
    .fetch_optional(&mut **transaction)
    .await?
    .flatten();
    metrics.push(snapshot_metric(
        &thresholds,
        ALERT_METRIC_BLUEPRINT_STAGNANT_DAYS,
        blueprint_stagnant.unwrap_or(0.0),
    ));

    // ── 指标 4：进展偏差率 = 蓝图待实证知识点占比（无蓝图视为 0）──
    let deviation: Option<f64> = sqlx::query_scalar(
        r#"
        SELECT
            CASE WHEN count(*) = 0 THEN NULL::float8
                 ELSE (count(*) FILTER (WHERE e.id IS NULL))::float8 / count(*)::float8
            END
        FROM public.kg_blueprint_nodes b
        LEFT JOIN public.kg_entities e
            ON e.project_id = b.project_id AND e.entity_type = b.entity_type
           AND e.normalized_label = b.normalized_label
        WHERE b.project_id = $1 AND b.status <> 'retired'
        "#,
    )
    .bind(project_id)
    .fetch_optional(&mut **transaction)
    .await?
    .flatten();
    metrics.push(snapshot_metric(
        &thresholds,
        ALERT_METRIC_PROGRESS_DEVIATION,
        deviation.unwrap_or(0.0),
    ));

    // ── 告警落库：有 warn/critical 才建；同一 (metric, status='open') 幂等去重，值刷新 ──
    for metric in &metrics {
        if metric.level == "none" {
            continue;
        }
        let detail = match metric.metric.as_str() {
            ALERT_METRIC_REVIEW_STALL_HOURS => format!(
                "最老待审笔记已等待 {:.1} 小时（阈值 warn {:.1} / critical {:.1}）",
                metric.value,
                warn_of(&thresholds, &metric.metric),
                critical_of(&thresholds, &metric.metric)
            ),
            ALERT_METRIC_RETURN_RATE => format!(
                "近 {} 条审批退回占比 {:.0}%（阈值 warn {:.0}% / critical {:.0}%）",
                RETURN_RATE_WINDOW,
                metric.value * 100.0,
                warn_of(&thresholds, &metric.metric) * 100.0,
                critical_of(&thresholds, &metric.metric) * 100.0
            ),
            ALERT_METRIC_BLUEPRINT_STAGNANT_DAYS => format!(
                "知识蓝图最近实证距今 {:.0} 天（阈值 warn {:.0} / critical {:.0}）",
                metric.value,
                warn_of(&thresholds, &metric.metric),
                critical_of(&thresholds, &metric.metric)
            ),
            ALERT_METRIC_PROGRESS_DEVIATION => format!(
                "蓝图待实证知识点占比 {:.0}%（阈值 warn {:.0}% / critical {:.0}%）",
                metric.value * 100.0,
                warn_of(&thresholds, &metric.metric) * 100.0,
                critical_of(&thresholds, &metric.metric) * 100.0
            ),
            _ => String::new(),
        };
        upsert_open_alert(
            transaction,
            project_id,
            &metric.metric,
            metric.value,
            &metric.level,
            &detail,
        )
        .await?;
    }

    Ok(AlertEvaluationSummary {
        evaluated_at: Utc::now(),
        metrics,
    })
}

fn warn_of(thresholds: &[AlertThresholdRead], metric: &str) -> f64 {
    thresholds
        .iter()
        .find(|row| row.metric == metric)
        .map(|row| row.warn_threshold)
        .unwrap_or_else(|| default_thresholds(metric).0)
}

fn critical_of(thresholds: &[AlertThresholdRead], metric: &str) -> f64 {
    thresholds
        .iter()
        .find(|row| row.metric == metric)
        .map(|row| row.critical_threshold)
        .unwrap_or_else(|| default_thresholds(metric).1)
}

/// 缺省阈值（导师面谈口径的保守起点，均可在前端调整）。
pub fn default_thresholds(metric: &str) -> (f64, f64) {
    match metric {
        ALERT_METRIC_REVIEW_STALL_HOURS => (72.0, 168.0),
        ALERT_METRIC_RETURN_RATE => (0.3, 0.5),
        ALERT_METRIC_BLUEPRINT_STAGNANT_DAYS => (14.0, 30.0),
        ALERT_METRIC_PROGRESS_DEVIATION => (0.7, 0.9),
        _ => (f64::MAX, f64::MAX),
    }
}

fn snapshot_metric(
    thresholds: &[AlertThresholdRead],
    metric: &str,
    value: f64,
) -> AlertMetricSnapshot {
    let (warn, critical) = default_thresholds(metric);
    let (warn, critical) = thresholds
        .iter()
        .find(|row| row.metric == metric && row.enabled)
        .map(|row| (row.warn_threshold, row.critical_threshold))
        .unwrap_or((warn, critical));
    let disabled = thresholds
        .iter()
        .any(|row| row.metric == metric && !row.enabled);
    let level = if disabled {
        "none"
    } else if value >= critical {
        "critical"
    } else if value >= warn {
        "warn"
    } else {
        "none"
    };
    AlertMetricSnapshot {
        metric: metric.to_owned(),
        value,
        level: level.to_owned(),
    }
}

/// 同指标已有 open 告警则刷新值/级别/明细，否则新建；acked 历史不复用。
pub async fn upsert_open_alert(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    metric: &str,
    metric_value: f64,
    level: &str,
    detail: &str,
) -> Result<(), ApiError> {
    let existing: Option<i32> = sqlx::query_scalar(
        r#"
        SELECT id FROM public.project_alerts
        WHERE project_id = $1 AND metric = $2 AND status = 'open'
        "#,
    )
    .bind(project_id)
    .bind(metric)
    .fetch_optional(&mut **transaction)
    .await?;
    if let Some(alert_id) = existing {
        sqlx::query(
            r#"
            UPDATE public.project_alerts
            SET metric_value = $3, level = $4, detail = $5, updated_at = now()
            WHERE id = $1 AND project_id = $2
            "#,
        )
        .bind(alert_id)
        .bind(project_id)
        .bind(metric_value)
        .bind(level)
        .bind(detail)
        .execute(&mut **transaction)
        .await?;
        return Ok(());
    }
    sqlx::query(
        r#"
        INSERT INTO public.project_alerts
            (project_id, metric, metric_value, level, status, detail)
        VALUES ($1, $2, $3, $4, 'open', $5)
        "#,
    )
    .bind(project_id)
    .bind(metric)
    .bind(metric_value)
    .bind(level)
    .bind(detail)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

/// 导师/负责人确认告警（闭环的"人工动作"侧）。
pub async fn acknowledge_alert(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    alert_id: i32,
    user_id: i32,
    note: Option<&str>,
) -> Result<(), ApiError> {
    let result = sqlx::query(
        r#"
        UPDATE public.project_alerts
        SET status = 'acknowledged', acknowledged_by = $3, acknowledged_at = now(),
            detail = detail || $4, updated_at = now()
        WHERE id = $1 AND project_id = $2 AND status = 'open'
        "#,
    )
    .bind(alert_id)
    .bind(project_id)
    .bind(user_id)
    .bind(note.map(|n| format!("；确认备注：{n}")).unwrap_or_default())
    .execute(&mut **transaction)
    .await?;
    if result.rows_affected() == 0 {
        return Err(ApiError::new(StatusCode::NOT_FOUND, "告警不存在或已确认"));
    }
    Ok(())
}

/// 指标读数强制可审计：open 告警在指标回落到 none 后自动关闭。
pub async fn close_resolved_alerts(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    summary: &AlertEvaluationSummary,
) -> Result<u64, ApiError> {
    let mut resolved = Vec::new();
    for metric in ALERT_METRICS {
        let snapshot = summary.metrics.iter().find(|m| m.metric == *metric);
        if snapshot.map(|m| m.level == "none").unwrap_or(true) {
            resolved.push(*metric);
        }
    }
    if resolved.is_empty() {
        return Ok(0);
    }
    let result = sqlx::query(
        r#"
        UPDATE public.project_alerts
        SET status = 'resolved', updated_at = now()
        WHERE project_id = $1 AND status = 'open' AND metric = ANY($2)
        "#,
    )
    .bind(project_id)
    .bind(&resolved)
    .execute(&mut **transaction)
    .await?;
    Ok(result.rows_affected())
}

/// 阈值更新（导师调整权限入口）：白名单校验 + warn ≤ critical。
pub async fn upsert_alert_threshold(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    user_id: i32,
    request: &AlertThresholdUpsertRequest,
) -> Result<AlertThresholdRead, ApiError> {
    if !is_alert_metric(&request.metric) {
        return Err(ApiError::new(
            StatusCode::BAD_REQUEST,
            format!(
                "未知指标 {}，可选：{}",
                request.metric,
                ALERT_METRICS.join(", ")
            ),
        ));
    }
    if !request.warn_threshold.is_finite()
        || !request.critical_threshold.is_finite()
        || request.warn_threshold < 0.0
        || request.critical_threshold < request.warn_threshold
    {
        return Err(ApiError::new(
            StatusCode::BAD_REQUEST,
            "阈值非法：要求 0 ≤ warn ≤ critical",
        ));
    }
    let row: AlertThresholdRead = sqlx::query_as(
        r#"
        INSERT INTO public.project_alert_thresholds
            (project_id, metric, warn_threshold, critical_threshold, enabled, updated_by)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (project_id, metric)
        DO UPDATE SET warn_threshold = $3, critical_threshold = $4, enabled = $5,
                      updated_by = $6, updated_at = now()
        RETURNING id, project_id, metric, warn_threshold, critical_threshold, enabled, updated_by, updated_at
        "#,
    )
    .bind(project_id)
    .bind(&request.metric)
    .bind(request.warn_threshold)
    .bind(request.critical_threshold)
    .bind(request.enabled)
    .bind(user_id)
    .fetch_one(&mut **transaction)
    .await?;
    Ok(row)
}

/// 评估 JSON 细节（审计 detail 用）。
pub fn evaluation_audit_detail(summary: &AlertEvaluationSummary) -> serde_json::Value {
    json!({
        "metrics": summary
            .metrics
            .iter()
            .map(|m| json!({"metric": m.metric, "value": (m.value * 1000.0).round() / 1000.0, "level": m.level}))
            .collect::<Vec<_>>(),
    })
}
