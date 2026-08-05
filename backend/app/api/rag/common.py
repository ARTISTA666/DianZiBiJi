"""Shared constants, permission guards and small helpers for the RAG API."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from time import perf_counter

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import can_evaluate_project, can_manage_project
from app.models.ai import RagMode
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.rag import ProjectRagDataset
from app.models.user import User
from app.schemas.ai import AIQueryEvaluationRequest
from app.schemas.rag import RagStatusRead
from app.services.citation_audit import audit_citations
from app.services.prompts import PROMPTS

PROMPT_VERSION = PROMPTS["project_rag"].version
PURE_LLM_PROMPT_VERSION = PROMPTS["pure_llm"].version
BM25_PROMPT_VERSION = PROMPTS["bm25_rag"].version
STRUCTURED_QUERY_VERSION = PROMPTS["structured_query"].version
GENERATION_TEMPERATURE = 0.1
GENERATION_MAX_TOKENS = 1800
EXPERIMENT_MODES = tuple(mode.value for mode in RagMode if mode is not RagMode.AUTO)
FINAL_MATURITY_GATE_REPORT = Path(__file__).resolve().parents[4] / "docs" / "experiments" / "final-maturity-gate-latest.json"
REQUIRED_FINAL_MATURITY_CHECKS = {
    "internal release-candidate gate passed",
    "production configuration was checked in production mode",
    "external confirmatory human-review freeze passed",
    "long soak evidence passed",
    "real TLS deployment evidence passed",
    "offsite encrypted backup evidence passed",
    "final maturity evidence manifest verified",
}


def _final_maturity_gate_passed() -> bool:
    try:
        payload = json.loads(FINAL_MATURITY_GATE_REPORT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not (
        isinstance(payload, dict)
        and payload.get("passed") is True
        and isinstance(payload.get("generated_at"), str)
        and payload.get("scope") == "final maturity gate for confirmatory human review"
        and payload.get("failures") == []
    ):
        return False
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        return False
    check_names = {item.get("name") for item in checks if isinstance(item, dict)}
    return REQUIRED_FINAL_MATURITY_CHECKS.issubset(check_names) and all(
        isinstance(item, dict) and item.get("passed") is True for item in checks
    )


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _require_rag_manager(db: Session, user: User, project_id: int) -> None:
    if not can_manage_project(db, user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project manage permission required")


def _require_rag_evaluator(db: Session, user: User, project_id: int) -> None:
    if not can_evaluate_project(db, user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI evaluation permission required")


def _require_independent_evaluator(db: Session, user: User, project_id: int) -> None:
    _require_rag_evaluator(db, user, project_id)
    if can_manage_project(db, user, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project managers cannot submit method-masked ratings",
        )


def _is_evaluator_only(db: Session, user: User, project_id: int) -> bool:
    return can_evaluate_project(db, user, project_id) and not can_manage_project(db, user, project_id)


def _require_unblinded_rag_access(db: Session, user: User, project_id: int) -> None:
    if _is_evaluator_only(db, user, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Independent evaluators must use the blind-review API",
        )


def _validate_evaluation_comment(payload: AIQueryEvaluationRequest) -> None:
    if (not payload.is_accurate or not payload.is_traceable) and not (payload.comment or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A comment is required for inaccurate or untraceable answers",
        )


def _commit_evaluation(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        message = str(error)
        is_duplicate_evaluation = (
            constraint_name == "uq_ai_query_evaluation_log_evaluator"
            or "uq_ai_query_evaluation_log_evaluator" in message
            or (
                "ai_query_evaluations.query_log_id" in message
                and "ai_query_evaluations.evaluator_user_id" in message
            )
        )
        if is_duplicate_evaluation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This review has already been submitted",
            ) from error
        raise


def _audit_answer_citations(answer: str, source_count: int, graph_count: int) -> dict:
    allowed = {
        "S": set(range(1, source_count + 1)),
        "G": set(range(1, graph_count + 1)),
    }
    result = audit_citations(answer, allowed, flags=re.IGNORECASE)
    # Apply RAG-specific message wording (core logic is shared)
    invalid = result["invalid_citations"]
    has_evidence = result["has_evidence"]
    citation_count = result["citation_count"]
    if invalid:
        result["message"] = f"发现 {len(invalid)} 个不存在的证据编号：{'、'.join(invalid)}。"
    elif has_evidence and not citation_count:
        result["message"] = "回答没有引用任何已检索证据，需要人工复核。"
    elif citation_count:
        result["message"] = f"引用校验通过，共核对 {citation_count} 个证据编号。"
    else:
        result["message"] = "该回答没有可引用的项目证据。"
    return result


def _has_source_marker(answer: str) -> bool:
    return bool(re.search(r"\[S\d+\]", answer, re.IGNORECASE))


def _has_graph_marker(answer: str) -> bool:
    return bool(re.search(r"\[G\d+\]", answer, re.IGNORECASE))


def _merge_usage(*items: dict | None) -> dict:
    merged: dict = {}
    for item in items:
        for key, value in (item or {}).items():
            if isinstance(value, (int, float)) and isinstance(merged.get(key, 0), (int, float)):
                merged[key] = merged.get(key, 0) + value
            elif key not in merged:
                merged[key] = value
    return merged


def _get_project_dataset(db: Session, project_id: int) -> ProjectRagDataset | None:
    return db.query(ProjectRagDataset).filter(ProjectRagDataset.project_id == project_id).first()


def _build_status(project_id: int, db: Session) -> RagStatusRead:
    dataset = _get_project_dataset(db, project_id)
    pending_sync_count = (
        db.query(StoredFile)
        .filter(
            StoredFile.project_id == project_id,
            StoredFile.file_category == FileCategory.KNOWLEDGE_DOCUMENT,
            StoredFile.status == FileStatus.APPROVED,
            StoredFile.knowledge_sync_status == KnowledgeSyncStatus.PENDING_SYNC.value,
        )
        .count()
    )
    failed_sync_count = (
        db.query(StoredFile)
        .filter(
            StoredFile.project_id == project_id,
            StoredFile.file_category == FileCategory.KNOWLEDGE_DOCUMENT,
            StoredFile.knowledge_sync_status == KnowledgeSyncStatus.FAILED.value,
        )
        .count()
    )
    synced_count = (
        db.query(StoredFile)
        .filter(
            StoredFile.project_id == project_id,
            StoredFile.file_category == FileCategory.KNOWLEDGE_DOCUMENT,
            StoredFile.knowledge_sync_status == KnowledgeSyncStatus.SYNCED.value,
        )
        .count()
    )
    return RagStatusRead(
        initialized=dataset is not None,
        dataset=dataset,
        pending_sync_count=pending_sync_count,
        failed_sync_count=failed_sync_count,
        synced_count=synced_count,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def _avg(values: list[int]) -> float:
    if not values:
        return 0
    return round(sum(values) / len(values), 2)


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0
    return round(count / total, 4)
