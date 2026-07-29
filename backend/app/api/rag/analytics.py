"""Query log listing and evaluation analytics endpoints."""

from __future__ import annotations

import itertools
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_access
from app.api.rag.common import (
    EXPERIMENT_MODES,
    _avg,
    _rate,
    _require_unblinded_rag_access,
)
from app.core.database import get_db
from app.models.ai import AIQueryEvaluation, AIQueryLog
from app.models.user import User
from app.schemas.ai import (
    AIQueryAgreementMetric,
    AIQueryAnalyticsRead,
    AIQueryEvaluationRead,
    AIQueryLogRead,
    AIQueryModeStats,
)

router = APIRouter(tags=["rag"])


@router.get("/projects/{project_id}/rag/query-logs", response_model=list[AIQueryLogRead])
def list_project_query_logs(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AIQueryLogRead]:
    require_project_access(project_id, db, user)
    _require_unblinded_rag_access(db, user, project_id)
    logs = (
        db.query(AIQueryLog)
        .filter(AIQueryLog.project_id == project_id)
        .order_by(AIQueryLog.created_at.desc(), AIQueryLog.id.desc())
        .limit(200)
        .all()
    )
    evaluation_rows = (
        db.query(AIQueryEvaluation)
        .filter(AIQueryEvaluation.query_log_id.in_([log.id for log in logs] or [0]))
        .all()
    )
    evaluations_by_log: dict[int, list[AIQueryEvaluation]] = defaultdict(list)
    for evaluation in evaluation_rows:
        evaluations_by_log[evaluation.query_log_id].append(evaluation)
    return [_query_log_read(log, evaluations_by_log.get(log.id, []), user.id) for log in logs]


@router.get("/projects/{project_id}/rag/analytics", response_model=AIQueryAnalyticsRead)
def get_project_query_analytics(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIQueryAnalyticsRead:
    require_project_access(project_id, db, user)
    _require_unblinded_rag_access(db, user, project_id)
    logs = db.query(AIQueryLog).filter(AIQueryLog.project_id == project_id).all()
    evaluations = (
        db.query(AIQueryEvaluation)
        .filter(AIQueryEvaluation.query_log_id.in_([log.id for log in logs] or [0]))
        .all()
    )
    return _build_query_analytics(project_id, logs, evaluations)


def _query_log_read(
    log: AIQueryLog,
    evaluations: list[AIQueryEvaluation],
    current_user_id: int,
) -> AIQueryLogRead:
    ordered_evaluations = sorted(evaluations, key=lambda item: (item.evaluator_user_id, item.id))
    current_evaluation = next(
        (evaluation for evaluation in ordered_evaluations if evaluation.evaluator_user_id == current_user_id),
        None,
    )
    return AIQueryLogRead(
        id=log.id,
        project_id=log.project_id,
        user_id=log.user_id,
        question=log.question,
        answer=log.answer,
        rag_mode=log.rag_mode,
        graph_hit_count=log.graph_hit_count,
        source_count=log.source_count,
        response_ms=log.response_ms,
        conversation_id=log.conversation_id,
        graph_context_json=log.graph_context_json or [],
        sources_json=log.sources_json or [],
        provider=log.provider,
        model_name=log.model_name,
        prompt_version=log.prompt_version,
        retrieval_config_json=log.retrieval_config_json or {},
        usage_json=log.usage_json or {},
        fallback_reason=log.fallback_reason,
        error_message=log.error_message,
        experiment_run_id=log.experiment_run_id,
        experiment_case_index=log.experiment_case_index,
        experiment_repetition_index=log.experiment_repetition_index,
        experiment_execution_order=log.experiment_execution_order,
        created_at=log.created_at,
        evaluation=(
            AIQueryEvaluationRead.model_validate(current_evaluation)
            if current_evaluation
            else None
        ),
        evaluations=[
            AIQueryEvaluationRead.model_validate(evaluation)
            for evaluation in ordered_evaluations
        ],
    )


def _build_query_analytics(
    project_id: int,
    logs: list[AIQueryLog],
    evaluations: list[AIQueryEvaluation],
) -> AIQueryAnalyticsRead:
    total_queries = len(logs)
    evaluated_log_ids = {evaluation.query_log_id for evaluation in evaluations}
    evaluated_queries = len(evaluated_log_ids)
    mode_stats = [_build_mode_stats(mode, logs, evaluations) for mode in EXPERIMENT_MODES]
    return AIQueryAnalyticsRead(
        project_id=project_id,
        total_queries=total_queries,
        evaluated_queries=evaluated_queries,
        evaluation_count=len(evaluations),
        evaluator_count=len({evaluation.evaluator_user_id for evaluation in evaluations}),
        evaluation_rate=_rate(evaluated_queries, total_queries),
        project_rag_queries=sum(1 for log in logs if log.rag_mode == "project_rag"),
        kg_enhanced_queries=sum(1 for log in logs if log.rag_mode == "kg_enhanced_rag"),
        failed_queries=sum(1 for log in logs if log.error_message),
        avg_response_ms=_avg([log.response_ms for log in logs]),
        avg_score=_avg([evaluation.score for evaluation in evaluations]) if evaluations else None,
        accurate_rate=_rate(sum(1 for evaluation in evaluations if evaluation.is_accurate), len(evaluations))
        if evaluations
        else None,
        traceable_rate=_rate(sum(1 for evaluation in evaluations if evaluation.is_traceable), len(evaluations))
        if evaluations
        else None,
        avg_graph_hit_count=_avg([log.graph_hit_count for log in logs]),
        avg_source_count=_avg([log.source_count for log in logs]),
        mode_stats=mode_stats,
        accuracy_agreement=_build_agreement(evaluations, "is_accurate"),
        traceability_agreement=_build_agreement(evaluations, "is_traceable"),
    )


def _build_mode_stats(
    mode: str,
    logs: list[AIQueryLog],
    evaluations: list[AIQueryEvaluation],
) -> AIQueryModeStats:
    mode_logs = [log for log in logs if log.rag_mode == mode]
    mode_log_ids = {log.id for log in mode_logs}
    mode_evaluations = [
        evaluation for evaluation in evaluations if evaluation.query_log_id in mode_log_ids
    ]
    return AIQueryModeStats(
        rag_mode=mode,
        total_queries=len(mode_logs),
        evaluated_queries=len({evaluation.query_log_id for evaluation in mode_evaluations}),
        avg_score=_avg([evaluation.score for evaluation in mode_evaluations]) if mode_evaluations else None,
        accurate_rate=_rate(sum(1 for evaluation in mode_evaluations if evaluation.is_accurate), len(mode_evaluations))
        if mode_evaluations
        else None,
        traceable_rate=_rate(sum(1 for evaluation in mode_evaluations if evaluation.is_traceable), len(mode_evaluations))
        if mode_evaluations
        else None,
        avg_graph_hit_count=_avg([log.graph_hit_count for log in mode_logs]),
        avg_source_count=_avg([log.source_count for log in mode_logs]),
        avg_response_ms=_avg([log.response_ms for log in mode_logs]),
    )


def _build_agreement(
    evaluations: list[AIQueryEvaluation],
    attribute: str,
) -> AIQueryAgreementMetric:
    by_log: dict[int, list[AIQueryEvaluation]] = defaultdict(list)
    for evaluation in evaluations:
        by_log[evaluation.query_log_id].append(evaluation)
    pairs: list[tuple[bool, bool]] = []
    for items in by_log.values():
        ordered = sorted(items, key=lambda item: item.evaluator_user_id)
        for left, right in itertools.combinations(ordered, 2):
            pairs.append((bool(getattr(left, attribute)), bool(getattr(right, attribute))))
    if not pairs:
        return AIQueryAgreementMetric()
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_true = sum(left for left, _ in pairs) / len(pairs)
    right_true = sum(right for _, right in pairs) / len(pairs)
    expected = left_true * right_true + (1 - left_true) * (1 - right_true)
    kappa = 1.0 if expected == 1.0 else (observed - expected) / (1 - expected)
    return AIQueryAgreementMetric(
        paired_ratings=len(pairs),
        agreement_rate=round(observed, 4),
        cohens_kappa=round(kappa, 4),
    )
