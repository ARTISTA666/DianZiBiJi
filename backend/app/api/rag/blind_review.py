"""Method-masked (blind) human review endpoints and helpers."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import can_manage_project, get_current_user, require_project_access
from app.api.rag import common
from app.api.rag.common import (
    _is_evaluator_only,
    _require_independent_evaluator,
    _require_rag_manager,
    _sha256_file,
    _commit_evaluation,
    _validate_evaluation_comment,
)
from app.api.rag.experiments import _experiment_export_response
from app.core.config import get_settings
from app.core.database import get_db
from app.models.ai import AIExperimentRun, AIQueryEvaluation, AIQueryLog, ReviewProtocol
from app.models.user import User
from app.schemas.ai import (
    AIQueryEvaluationRequest,
    BlindReviewBatchRead,
    BlindReviewEvaluationRead,
    BlindReviewEvidenceRead,
    BlindReviewItemRead,
)
from app.services.audit import write_audit

router = APIRouter(tags=["rag"])


def _blind_id(project_id: int, log_id: int) -> str:
    key = get_settings().secret_key.encode("utf-8")
    message = f"rag-blind-review:{project_id}:{log_id}".encode("utf-8")
    return "B" + hmac.new(key, message, hashlib.sha256).hexdigest()[:12].upper()


def _blind_batch_id(project_id: int, run_id: int) -> str:
    key = get_settings().secret_key.encode("utf-8")
    message = f"rag-blind-review-batch:{project_id}:{run_id}".encode("utf-8")
    return "R" + hmac.new(key, message, hashlib.sha256).hexdigest()[:12].upper()


def _neutralize_answer(answer: str | None, source_count: int) -> str | None:
    if answer is None:
        return None

    def replace_marker(match: re.Match[str]) -> str:
        marker_type = match.group(1).upper()
        marker_index = int(match.group(2))
        evidence_index = marker_index if marker_type == "S" else source_count + marker_index
        return f"[E{evidence_index}]"

    neutral = re.sub(r"\[([SG])(\d+)\]", replace_marker, answer, flags=re.IGNORECASE)
    return _neutralize_method_labels(neutral)


def _neutralize_method_labels(value: str) -> str:
    replacements = (
        (r"BM25\s*检索", "系统"),
        (r"纯\s*(?:LLM|大模型)", "系统"),
        (r"项目(?:级)?\s*RAG", "系统"),
        (r"结构化查询", "系统"),
        (r"\bBM25(?:[_ -]?RAG)?\b", "系统"),
        (r"\bpure[_ -]?llm\b", "系统"),
        (r"\bproject[_ -]?rag\b", "系统"),
        (r"\bstructured[_ -]?query\b", "系统"),
        (r"\bkg[_ -]?(?:enhanced[_ -]?)?rag\b", "系统"),
        (r"\bRAG\b", "系统"),
        (r"知识图谱增强", "系统"),
        (r"知识图谱", "证据"),
        (r"图谱关系", "证据"),
        (r"图谱", "证据"),
        (r"向量检索", "检索"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return value


def _neutralize_blind_text(value: str, filenames: list[str]) -> str:
    neutral = re.sub(r"\[([SG])\d+\]", "[证据]", value, flags=re.IGNORECASE)
    neutral = _neutralize_method_labels(neutral)
    for filename in sorted({item.strip() for item in filenames if item.strip()}, key=len, reverse=True):
        neutral = re.sub(re.escape(filename), "项目资料", neutral, flags=re.IGNORECASE)
    return neutral


def _blind_evidence(log: AIQueryLog) -> list[BlindReviewEvidenceRead]:
    evidence: list[BlindReviewEvidenceRead] = []
    sources = log.sources_json or []
    filenames = [str(source.get("filename") or "").strip() for source in sources]
    for source in sources:
        filename = str(source.get("filename") or "项目资料").strip()
        snippet = str(source.get("snippet") or "").strip()
        content = f"{filename}：{snippet}" if snippet else "项目证据"
        content = _neutralize_blind_text(content, filenames)
        evidence.append(BlindReviewEvidenceRead(evidence_id=f"E{len(evidence) + 1}", content=content))
    for relation in log.graph_context_json or []:
        source_label = str(relation.get("source_label") or "").strip()
        relation_label = str(relation.get("relation_label") or relation.get("relation_type") or "相关").strip()
        target_label = str(relation.get("target_label") or "").strip()
        content = " ".join(part for part in (source_label, relation_label, target_label) if part)
        content = _neutralize_blind_text(content, filenames)
        evidence.append(BlindReviewEvidenceRead(evidence_id=f"E{len(evidence) + 1}", content=content))
    return evidence


def _blind_evaluation(log: AIQueryLog, user: User, db: Session) -> AIQueryEvaluation | None:
    return (
        db.query(AIQueryEvaluation)
        .filter(
            AIQueryEvaluation.query_log_id == log.id,
            AIQueryEvaluation.evaluator_user_id == user.id,
        )
        .first()
    )


def _blind_review_item(log: AIQueryLog, user: User, db: Session) -> BlindReviewItemRead:
    evaluation = _blind_evaluation(log, user, db)
    sources = log.sources_json or []
    filenames = [str(source.get("filename") or "").strip() for source in sources]
    answer = _neutralize_answer(log.answer, len(sources))
    return BlindReviewItemRead(
        blind_id=_blind_id(log.project_id, log.id),
        question=_neutralize_blind_text(log.question, filenames),
        answer=_neutralize_blind_text(answer, filenames) if answer is not None else None,
        evidence=_blind_evidence(log),
        evaluation=(
            BlindReviewEvaluationRead(
                score=evaluation.score,
                is_accurate=evaluation.is_accurate,
                is_traceable=evaluation.is_traceable,
                comment=evaluation.comment,
                updated_at=evaluation.updated_at,
            )
            if evaluation
            else None
        ),
    )


def _find_blind_review_log(project_id: int, blind_id: str, db: Session) -> AIQueryLog | None:
    logs = db.query(AIQueryLog).filter(AIQueryLog.project_id == project_id).all()
    return next(
        (log for log in logs if hmac.compare_digest(_blind_id(project_id, log.id), blind_id.upper())),
        None,
    )


def _find_blind_review_run(project_id: int, batch_id: str, db: Session) -> AIExperimentRun | None:
    normalized_batch_id = batch_id.upper()
    if not re.fullmatch(r"R[A-F0-9]{12}", normalized_batch_id):
        return None
    runs = db.query(AIExperimentRun).filter(AIExperimentRun.project_id == project_id).all()
    return next(
        (
            run
            for run in runs
            if hmac.compare_digest(_blind_batch_id(project_id, run.id), normalized_batch_id)
        ),
        None,
    )


def _method_masked_completion(log_ids: list[int], db: Session) -> tuple[int, int, list[set[int]]]:
    evaluations = (
        db.query(AIQueryEvaluation)
        .filter(
            AIQueryEvaluation.query_log_id.in_(log_ids or [0]),
            AIQueryEvaluation.review_protocol == ReviewProtocol.METHOD_MASKED.value,
        )
        .all()
    )
    evaluator_counts: dict[int, set[int]] = defaultdict(set)
    for evaluation in evaluations:
        evaluator_counts[evaluation.query_log_id].add(evaluation.evaluator_user_id)
    completed = sum(1 for log_id in log_ids if len(evaluator_counts[log_id]) >= 2)
    reviewer_sets = [evaluator_counts[log_id] for log_id in log_ids if len(evaluator_counts[log_id]) >= 2]
    return completed, len(log_ids), reviewer_sets


@router.get(
    "/projects/{project_id}/rag/blind-review/batches",
    response_model=list[BlindReviewBatchRead],
)
def list_blind_review_batches(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BlindReviewBatchRead]:
    require_project_access(project_id, db, user)
    is_manager = can_manage_project(db, user, project_id)
    is_independent_evaluator = _is_evaluator_only(db, user, project_id)
    if not (is_manager or is_independent_evaluator):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI evaluation permission required")
    runs = (
        db.query(AIExperimentRun)
        .filter(AIExperimentRun.project_id == project_id)
        .order_by(AIExperimentRun.created_at.desc(), AIExperimentRun.id.desc())
        .all()
    )
    batches: list[BlindReviewBatchRead] = []
    for run in runs:
        logs = (
            db.query(AIQueryLog)
            .filter(
                AIQueryLog.experiment_run_id == run.id,
                AIQueryLog.error_message.is_(None),
            )
            .all()
        )
        log_ids = [log.id for log in logs]
        if is_manager:
            completed, _total, _reviewer_sets = _method_masked_completion(log_ids, db)
        else:
            completed = (
                db.query(AIQueryEvaluation)
                .filter(
                    AIQueryEvaluation.query_log_id.in_(log_ids or [0]),
                    AIQueryEvaluation.evaluator_user_id == user.id,
                    AIQueryEvaluation.review_protocol == ReviewProtocol.METHOD_MASKED.value,
                )
                .count()
            )
        batches.append(
            BlindReviewBatchRead(
                batch_id=_blind_batch_id(project_id, run.id),
                total_items=run.total_cases or len(logs),
                completed_items=completed,
            )
        )
    return batches


@router.get(
    "/projects/{project_id}/rag/blind-review/items",
    response_model=list[BlindReviewItemRead],
)
def list_blind_review_items(
    project_id: int,
    batch_id: str | None = None,
    pending_only: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BlindReviewItemRead]:
    require_project_access(project_id, db, user)
    _require_independent_evaluator(db, user, project_id)
    query = db.query(AIQueryLog).filter(
        AIQueryLog.project_id == project_id,
        AIQueryLog.error_message.is_(None),
    )
    if batch_id is not None:
        run = _find_blind_review_run(project_id, batch_id, db)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review batch not found")
        query = query.filter(AIQueryLog.experiment_run_id == run.id)
    logs = query.all()
    items = [_blind_review_item(log, user, db) for log in logs]
    if pending_only:
        items = [item for item in items if item.evaluation is None]
    return sorted(items, key=lambda item: item.blind_id)


@router.post(
    "/projects/{project_id}/rag/blind-review/items/{blind_id}/evaluation",
    response_model=BlindReviewEvaluationRead,
)
def evaluate_blind_review_item(
    project_id: int,
    blind_id: str,
    payload: AIQueryEvaluationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlindReviewEvaluationRead:
    require_project_access(project_id, db, user)
    _require_independent_evaluator(db, user, project_id)
    _validate_evaluation_comment(payload)
    if not re.fullmatch(r"B[A-F0-9]{12}", blind_id.upper()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blind-review item not found")
    log = _find_blind_review_log(project_id, blind_id, db)
    if log is None or log.error_message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blind-review item not found")
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
    evaluation.score = payload.score
    evaluation.is_accurate = payload.is_accurate
    evaluation.is_traceable = payload.is_traceable
    evaluation.comment = payload.comment
    evaluation.review_protocol = ReviewProtocol.METHOD_MASKED.value
    write_audit(
        db,
        actor=user,
        action="evaluate_ai_query_blind",
        project_id=project_id,
        target_type="ai_query_log",
        target_id=log.id,
        detail={
            "blind_id": blind_id.upper(),
            "score": payload.score,
            "is_accurate": payload.is_accurate,
            "is_traceable": payload.is_traceable,
            "review_protocol": ReviewProtocol.METHOD_MASKED.value,
        },
    )
    _commit_evaluation(db)
    db.refresh(evaluation)
    return BlindReviewEvaluationRead(
        score=evaluation.score,
        is_accurate=evaluation.is_accurate,
        is_traceable=evaluation.is_traceable,
        comment=evaluation.comment,
        updated_at=evaluation.updated_at,
    )


@router.get("/projects/{project_id}/rag/blind-review/batches/{batch_id}/export.csv")
def export_blind_review_batch(
    project_id: int,
    batch_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    require_project_access(project_id, db, user)
    _require_rag_manager(db, user, project_id)
    # Read the gate helpers through the module so tests can monkeypatch them.
    if not common._final_maturity_gate_passed():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Final maturity gate has not passed; confirmatory human-review export is blocked",
        )
    run = _find_blind_review_run(project_id, batch_id, db)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review batch not found")
    if run.status != "completed" or run.failed_cases or run.completed_cases < run.total_cases:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Blind-review batch experiment is not cleanly completed: "
                f"status={run.status}, completed={run.completed_cases}/{run.total_cases}, failed={run.failed_cases}"
            ),
        )
    logs = (
        db.query(AIQueryLog)
        .filter(
            AIQueryLog.experiment_run_id == run.id,
            AIQueryLog.error_message.is_(None),
        )
        .all()
    )
    seen_review_items: set[tuple[int | None, str]] = set()
    for log in logs:
        key = (log.experiment_case_index, log.rag_mode)
        if key in seen_review_items:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Blind-review batch contains repeated question/mode items",
            )
        seen_review_items.add(key)
    log_ids = [log.id for log in logs]
    completed, total, reviewer_sets = _method_masked_completion(log_ids, db)
    if total == 0 or completed < total:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Blind-review batch is not complete: {completed}/{total} items have two method-masked ratings",
        )
    if reviewer_sets and any(reviewer_set != reviewer_sets[0] for reviewer_set in reviewer_sets[1:]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Blind-review batch uses inconsistent reviewer sets",
        )
    filename = "confirmatory-human-review-export.csv"
    final_gate_sha256 = _sha256_file(common.FINAL_MATURITY_GATE_REPORT)
    write_audit(
        db,
        actor=user,
        action="export_blind_review_batch",
        project_id=project_id,
        target_type="ai_experiment_run",
        target_id=run.id,
        detail={
            "batch_id": batch_id.upper(),
            "filename": filename,
            "final_maturity_gate_sha256": final_gate_sha256,
            "total_items": total,
            "reviewer_user_ids": sorted(reviewer_sets[0]) if reviewer_sets else [],
            "review_protocol": ReviewProtocol.METHOD_MASKED.value,
        },
    )
    db.commit()
    return _experiment_export_response(
        run,
        db,
        filename,
        review_protocol=ReviewProtocol.METHOD_MASKED.value,
        extra_columns={
            "review_batch_id": batch_id.upper(),
            "export_protocol": "confirmatory_human_review_v1",
            "final_maturity_gate_sha256": final_gate_sha256 or "",
        },
    )
