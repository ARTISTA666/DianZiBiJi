"""Unblinded per-query human evaluation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_access
from app.api.rag.common import (
    _require_rag_evaluator,
    _require_unblinded_rag_access,
    _commit_evaluation,
    _validate_evaluation_comment,
)
from app.core.database import get_db
from app.models.ai import AIQueryEvaluation, AIQueryLog, ReviewProtocol
from app.models.user import User
from app.schemas.ai import AIQueryEvaluationRead, AIQueryEvaluationRequest
from app.services.audit import write_audit

router = APIRouter(tags=["rag"])


@router.post("/rag/query-logs/{log_id}/evaluation", response_model=AIQueryEvaluationRead)
def upsert_query_evaluation(
    log_id: int,
    payload: AIQueryEvaluationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIQueryEvaluationRead:
    log = db.get(AIQueryLog, log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query log not found")
    require_project_access(log.project_id, db, user)
    _require_rag_evaluator(db, user, log.project_id)
    _require_unblinded_rag_access(db, user, log.project_id)
    _validate_evaluation_comment(payload)
    evaluation = (
        db.query(AIQueryEvaluation)
        .filter(
            AIQueryEvaluation.query_log_id == log.id,
            AIQueryEvaluation.evaluator_user_id == user.id,
        )
        .first()
    )
    if evaluation is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This review has already been submitted",
        )
    if evaluation is None:
        evaluation = AIQueryEvaluation(query_log_id=log.id, evaluator_user_id=user.id)
        db.add(evaluation)
    evaluation.evaluator_user_id = user.id
    evaluation.score = payload.score
    evaluation.is_accurate = payload.is_accurate
    evaluation.is_traceable = payload.is_traceable
    evaluation.comment = payload.comment
    evaluation.review_protocol = ReviewProtocol.UNBLINDED.value
    write_audit(
        db,
        actor=user,
        action="evaluate_ai_query",
        project_id=log.project_id,
        target_type="ai_query_log",
        target_id=log.id,
        detail={
            "score": payload.score,
            "is_accurate": payload.is_accurate,
            "is_traceable": payload.is_traceable,
            "review_protocol": ReviewProtocol.UNBLINDED.value,
        },
    )
    _commit_evaluation(db)
    db.refresh(evaluation)
    return evaluation
