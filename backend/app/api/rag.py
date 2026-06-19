from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import can_manage_project, can_review_project, get_current_user, require_project_access
from app.core.config import get_settings
from app.core.database import get_db
from app.models.ai import AIExperimentRun, AIQueryEvaluation, AIQueryLog
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.rag import ProjectRagDataset, RagDocumentChunk, RagFileSync, RagSyncStatus
from app.models.user import User
from app.schemas.ai import (
    AIExperimentRunRead,
    AIExperimentRunRequest,
    AIQueryAnalyticsRead,
    AIQueryEvaluationRead,
    AIQueryEvaluationRequest,
    AIQueryLogRead,
    AIQueryModeStats,
)
from app.schemas.rag import RagQueryRequest, RagQueryResponse, RagSourceRead, RagStatusRead
from app.services.audit import write_audit
from app.services.deepseek import DeepSeekClient, DeepSeekConfigError, DeepSeekRequestError
from app.services.embedding import EmbeddingServiceError
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.local_rag import LocalRagService

router = APIRouter(tags=["rag"])
PROMPT_VERSION = "rag-v3-local-hybrid-kg-citations"


def _require_rag_manager(db: Session, user: User, project_id: int) -> None:
    if not (can_review_project(db, user, project_id) or can_manage_project(db, user, project_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review or manage permission required")


def _get_project_dataset(db: Session, project_id: int) -> ProjectRagDataset | None:
    return db.query(ProjectRagDataset).filter(ProjectRagDataset.project_id == project_id).first()


@router.post("/projects/{project_id}/rag/init", response_model=RagStatusRead)
async def init_project_rag(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagStatusRead:
    settings = get_settings()
    project = require_project_access(project_id, db, user)
    _require_rag_manager(db, user, project_id)
    existing = _get_project_dataset(db, project_id)
    if existing is None:
        db.add(
            ProjectRagDataset(
                project_id=project_id,
                dify_dataset_id=f"local-project-{project_id}",
                dify_dataset_name=f"ELN Project {project.id} - {project.name}",
                provider="local_deepseek",
                embedding_model=settings.embedding_model,
                generation_model=settings.normalized_deepseek_model,
                created_by=user.id,
            )
        )
    else:
        existing.provider = "local_deepseek"
        existing.embedding_model = settings.embedding_model
        existing.generation_model = settings.normalized_deepseek_model
    write_audit(
        db,
        actor=user,
        action="init_local_rag",
        project_id=project_id,
        target_type="project",
        target_id=project_id,
        detail={
            "embedding_model": settings.embedding_model,
            "generation_model": settings.normalized_deepseek_model,
        },
    )
    db.commit()
    return _build_status(project_id, db)


@router.get("/projects/{project_id}/rag/status", response_model=RagStatusRead)
def get_project_rag_status(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagStatusRead:
    require_project_access(project_id, db, user)
    return _build_status(project_id, db)


@router.post("/files/{file_id}/rag/sync", response_model=RagStatusRead)
async def sync_file_to_rag(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagStatusRead:
    record = db.get(StoredFile, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    require_project_access(record.project_id, db, user)
    _require_rag_manager(db, user, record.project_id)
    if record.file_category != FileCategory.KNOWLEDGE_DOCUMENT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only knowledge documents can be indexed")
    if record.status != FileStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved documents can be indexed")
    dataset = _get_project_dataset(db, record.project_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RAG dataset is not initialized")

    sync = db.query(RagFileSync).filter(RagFileSync.file_id == record.id).first()
    if sync is None:
        sync = RagFileSync(
            file_id=record.id,
            project_id=record.project_id,
            dify_dataset_id=dataset.dify_dataset_id,
        )
        db.add(sync)
        db.flush()
    sync.sync_status = RagSyncStatus.PENDING.value
    sync.sync_message = "Extracting, chunking and embedding document"
    record.knowledge_sync_status = KnowledgeSyncStatus.PENDING_SYNC.value
    record.knowledge_sync_message = sync.sync_message
    db.commit()

    try:
        chunk_count = await LocalRagService().index_file(db, record)
    except (EmbeddingServiceError, FileNotFoundError, ValueError) as exc:
        sync.sync_status = RagSyncStatus.FAILED.value
        sync.sync_message = str(exc)
        record.knowledge_sync_status = KnowledgeSyncStatus.FAILED.value
        record.knowledge_sync_message = str(exc)
        write_audit(
            db,
            actor=user,
            action="index_rag_document_failed",
            project_id=record.project_id,
            target_type="file",
            target_id=record.id,
            detail={"error": str(exc)},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    sync.dify_document_id = f"local-file-{record.id}"
    sync.chunk_count = chunk_count
    sync.content_hash = record.file_hash
    sync.sync_status = RagSyncStatus.SYNCED.value
    sync.sync_message = f"Indexed {chunk_count} chunks with {dataset.embedding_model}"
    sync.synced_at = now
    record.knowledge_sync_status = KnowledgeSyncStatus.SYNCED.value
    record.knowledge_sync_message = sync.sync_message
    record.knowledge_synced_at = now
    write_audit(
        db,
        actor=user,
        action="index_rag_document",
        project_id=record.project_id,
        target_type="file",
        target_id=record.id,
        detail={"chunk_count": chunk_count, "embedding_model": dataset.embedding_model},
    )
    db.commit()
    return _build_status(record.project_id, db)


@router.post("/projects/{project_id}/rag/query", response_model=RagQueryResponse)
async def query_project_rag(
    project_id: int,
    payload: RagQueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagQueryResponse:
    require_project_access(project_id, db, user)
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query cannot be empty")
    response = await _execute_rag_query(
        db,
        project_id=project_id,
        user_id=user.id,
        query=query,
        mode=payload.mode,
    )
    write_audit(
        db,
        actor=user,
        action="query_local_rag",
        project_id=project_id,
        target_type="ai_query_log",
        target_id=response.query_log_id,
        detail={
            "rag_mode": response.rag_mode,
            "source_count": len(response.sources),
            "graph_context_count": len(response.graph_context),
            "model": response.model_name,
            "fallback_reason": response.fallback_reason,
        },
    )
    db.commit()
    return response


async def _execute_rag_query(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    query: str,
    mode: str,
    experiment_run_id: int | None = None,
    experiment_case_index: int | None = None,
) -> RagQueryResponse:
    settings = get_settings()
    if _get_project_dataset(db, project_id) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RAG dataset is not initialized")

    started = perf_counter()
    try:
        retrieved = await LocalRagService().retrieve(db, project_id, query)
    except EmbeddingServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if not retrieved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No indexed project documents are available for retrieval",
        )

    graph_service = KnowledgeGraphService()
    graph_context = [] if mode == "project_rag" else graph_service.find_relevant_context(db, project_id, query)
    fallback_reason = None
    if mode == "kg_enhanced_rag" and not graph_context:
        fallback_reason = (
            "No graph relation reached the relevance threshold; "
            "the explicit KG mode continued with project documents only"
        )
    elif mode == "auto" and not graph_context:
        fallback_reason = "No graph relation reached the relevance threshold; used project RAG"
    rag_mode = (
        mode
        if mode in {"project_rag", "kg_enhanced_rag"}
        else ("kg_enhanced_rag" if graph_context else "project_rag")
    )
    sources = [RagSourceRead(**item.as_source()) for item in retrieved]
    source_context = LocalRagService.format_sources(retrieved)
    graph_context_text = graph_service.format_context_for_prompt(graph_context)
    system_prompt = (
        "你是科研电子实验笔记系统中的问答助手。只能依据提供的项目资料和知识图谱回答。"
        "不得补充上下文中不存在的实验事实。每个关键事实必须标注依据："
        "资料事实使用 [S编号]，图谱关系使用 [G编号]，同时依赖两类证据时同时标注。"
        "证据不足时明确回答无法确认。"
    )
    user_prompt = (
        f"{source_context}\n\n"
        f"{graph_context_text or '实验知识图谱上下文：本次未检索到达到阈值的相关关系。'}\n\n"
        f"用户问题：{query}"
    )

    try:
        result = await DeepSeekClient().generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=1800,
        )
    except (DeepSeekConfigError, DeepSeekRequestError) as exc:
        _record_query_log(
            db,
            project_id=project_id,
            user_id=user_id,
            question=query,
            rag_mode=rag_mode,
            graph_context=graph_context,
            sources=sources,
            response_ms=_elapsed_ms(started),
            model_name=settings.normalized_deepseek_model,
            fallback_reason=fallback_reason,
            error_message=str(exc),
            experiment_run_id=experiment_run_id,
            experiment_case_index=experiment_case_index,
        )
        db.commit()
        code = status.HTTP_503_SERVICE_UNAVAILABLE if isinstance(exc, DeepSeekConfigError) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    response_ms = _elapsed_ms(started)
    query_log = _record_query_log(
        db,
        project_id=project_id,
        user_id=user_id,
        question=query,
        answer=result["answer"],
        rag_mode=rag_mode,
        graph_context=graph_context,
        sources=sources,
        response_ms=response_ms,
        conversation_id=result.get("request_id"),
        model_name=result.get("model"),
        usage=result.get("usage") or {},
        fallback_reason=fallback_reason,
        experiment_run_id=experiment_run_id,
        experiment_case_index=experiment_case_index,
    )
    return RagQueryResponse(
        answer=result["answer"],
        conversation_id=result.get("request_id"),
        sources=sources,
        graph_context=graph_context,
        rag_mode=rag_mode,
        query_log_id=query_log.id,
        response_ms=response_ms,
        provider="deepseek",
        model_name=result.get("model"),
        fallback_reason=fallback_reason,
    )


@router.get("/projects/{project_id}/rag/query-logs", response_model=list[AIQueryLogRead])
def list_project_query_logs(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AIQueryLogRead]:
    require_project_access(project_id, db, user)
    logs = (
        db.query(AIQueryLog)
        .filter(AIQueryLog.project_id == project_id)
        .order_by(AIQueryLog.created_at.desc(), AIQueryLog.id.desc())
        .limit(200)
        .all()
    )
    evaluations = {
        evaluation.query_log_id: evaluation
        for evaluation in db.query(AIQueryEvaluation)
        .filter(AIQueryEvaluation.query_log_id.in_([log.id for log in logs] or [0]))
        .all()
    }
    return [_query_log_read(log, evaluations.get(log.id)) for log in logs]


@router.get("/projects/{project_id}/rag/analytics", response_model=AIQueryAnalyticsRead)
def get_project_query_analytics(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIQueryAnalyticsRead:
    require_project_access(project_id, db, user)
    logs = db.query(AIQueryLog).filter(AIQueryLog.project_id == project_id).all()
    evaluations = {
        evaluation.query_log_id: evaluation
        for evaluation in db.query(AIQueryEvaluation)
        .filter(AIQueryEvaluation.query_log_id.in_([log.id for log in logs] or [0]))
        .all()
    }
    return _build_query_analytics(project_id, logs, evaluations)


@router.post("/projects/{project_id}/rag/experiments", response_model=AIExperimentRunRead)
async def run_rag_experiment(
    project_id: int,
    payload: AIExperimentRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIExperimentRunRead:
    require_project_access(project_id, db, user)
    _require_rag_manager(db, user, project_id)
    questions = [question.strip() for question in payload.questions if question.strip()]
    modes = list(dict.fromkeys(payload.modes))
    if not questions:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one question is required")
    if any(mode not in {"project_rag", "kg_enhanced_rag"} for mode in modes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Experiment modes must be project_rag or kg_enhanced_rag",
        )
    if _get_project_dataset(db, project_id) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RAG dataset is not initialized")

    run = AIExperimentRun(
        project_id=project_id,
        created_by=user.id,
        name=payload.name.strip(),
        status="running",
        questions_json=questions,
        modes_json=modes,
        config_snapshot_json=_experiment_config_snapshot(db, project_id),
        total_cases=len(questions) * len(modes),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    errors: list[dict] = []
    for question_index, question in enumerate(questions, start=1):
        for mode in modes:
            try:
                await _execute_rag_query(
                    db,
                    project_id=project_id,
                    user_id=user.id,
                    query=question,
                    mode=mode,
                    experiment_run_id=run.id,
                    experiment_case_index=question_index,
                )
                run.completed_cases += 1
            except HTTPException as exc:
                run.failed_cases += 1
                errors.append(
                    {
                        "question_index": question_index,
                        "question": question,
                        "mode": mode,
                        "error": str(exc.detail),
                    }
                )
            db.commit()

    logs = (
        db.query(AIQueryLog)
        .filter(AIQueryLog.experiment_run_id == run.id)
        .order_by(AIQueryLog.experiment_case_index, AIQueryLog.rag_mode)
        .all()
    )
    run.summary_json = {
        "errors": errors,
        "mode_stats": [
            {
                "mode": mode,
                "completed": sum(1 for log in logs if log.rag_mode == mode and not log.error_message),
                "failed": sum(1 for log in logs if log.rag_mode == mode and log.error_message)
                + sum(1 for item in errors if item["mode"] == mode),
                "avg_response_ms": _avg(
                    [log.response_ms for log in logs if log.rag_mode == mode and not log.error_message]
                ),
                "avg_source_count": _avg(
                    [log.source_count for log in logs if log.rag_mode == mode and not log.error_message]
                ),
                "avg_graph_hit_count": _avg(
                    [log.graph_hit_count for log in logs if log.rag_mode == mode and not log.error_message]
                ),
            }
            for mode in modes
        ],
    }
    run.status = "completed" if run.failed_cases == 0 else "completed_with_errors"
    run.completed_at = datetime.now(timezone.utc)
    write_audit(
        db,
        actor=user,
        action="run_rag_experiment",
        project_id=project_id,
        target_type="ai_experiment_run",
        target_id=run.id,
        detail={
            "total_cases": run.total_cases,
            "completed_cases": run.completed_cases,
            "failed_cases": run.failed_cases,
        },
    )
    db.commit()
    db.refresh(run)
    return run


@router.get("/projects/{project_id}/rag/experiments", response_model=list[AIExperimentRunRead])
def list_rag_experiments(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AIExperimentRunRead]:
    require_project_access(project_id, db, user)
    return (
        db.query(AIExperimentRun)
        .filter(AIExperimentRun.project_id == project_id)
        .order_by(AIExperimentRun.created_at.desc(), AIExperimentRun.id.desc())
        .limit(50)
        .all()
    )


@router.get("/rag/experiments/{run_id}/export.csv")
def export_rag_experiment(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    run = db.get(AIExperimentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment run not found")
    require_project_access(run.project_id, db, user)
    logs = (
        db.query(AIQueryLog)
        .filter(AIQueryLog.experiment_run_id == run.id)
        .order_by(AIQueryLog.experiment_case_index, AIQueryLog.rag_mode)
        .all()
    )
    evaluations = {
        evaluation.query_log_id: evaluation
        for evaluation in db.query(AIQueryEvaluation)
        .filter(AIQueryEvaluation.query_log_id.in_([log.id for log in logs] or [0]))
        .all()
    }
    log_by_case = {(log.experiment_case_index, log.rag_mode): log for log in logs}
    errors = {
        (item["question_index"], item["mode"]): item["error"]
        for item in (run.summary_json or {}).get("errors", [])
    }
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "experiment_run_id",
            "question_index",
            "question",
            "mode",
            "status",
            "query_log_id",
            "answer",
            "source_count",
            "graph_hit_count",
            "response_ms",
            "provider",
            "model",
            "prompt_version",
            "fallback_reason",
            "sources_json",
            "graph_context_json",
            "usage_json",
            "evaluation_score",
            "is_accurate",
            "is_traceable",
            "evaluation_comment",
            "error",
        ]
    )
    for question_index, question in enumerate(run.questions_json or [], start=1):
        for mode in run.modes_json or []:
            log = log_by_case.get((question_index, mode))
            evaluation = evaluations.get(log.id) if log else None
            writer.writerow(
                [
                    run.id,
                    question_index,
                    question,
                    mode,
                    "completed" if log and not log.error_message else "failed",
                    log.id if log else "",
                    log.answer if log else "",
                    log.source_count if log else 0,
                    log.graph_hit_count if log else 0,
                    log.response_ms if log else 0,
                    log.provider if log else "",
                    log.model_name if log else "",
                    log.prompt_version if log else PROMPT_VERSION,
                    log.fallback_reason if log and log.fallback_reason else "",
                    json.dumps(log.sources_json or [], ensure_ascii=False) if log else "[]",
                    json.dumps(log.graph_context_json or [], ensure_ascii=False) if log else "[]",
                    json.dumps(log.usage_json or {}, ensure_ascii=False) if log else "{}",
                    evaluation.score if evaluation else "",
                    evaluation.is_accurate if evaluation else "",
                    evaluation.is_traceable if evaluation else "",
                    evaluation.comment if evaluation and evaluation.comment else "",
                    log.error_message if log and log.error_message else errors.get((question_index, mode), ""),
                ]
            )
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="rag-experiment-{run.id}.csv"'},
    )


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
    _require_rag_manager(db, user, log.project_id)
    evaluation = db.query(AIQueryEvaluation).filter(AIQueryEvaluation.query_log_id == log.id).first()
    if evaluation is None:
        evaluation = AIQueryEvaluation(query_log_id=log.id, evaluator_user_id=user.id)
        db.add(evaluation)
    evaluation.evaluator_user_id = user.id
    evaluation.score = payload.score
    evaluation.is_accurate = payload.is_accurate
    evaluation.is_traceable = payload.is_traceable
    evaluation.comment = payload.comment
    write_audit(
        db,
        actor=user,
        action="evaluate_ai_query",
        project_id=log.project_id,
        target_type="ai_query_log",
        target_id=log.id,
        detail={"score": payload.score, "is_accurate": payload.is_accurate, "is_traceable": payload.is_traceable},
    )
    db.commit()
    db.refresh(evaluation)
    return evaluation


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


def _experiment_config_snapshot(db: Session, project_id: int) -> dict:
    settings = get_settings()
    chunk_hashes = [
        content_hash
        for (content_hash,) in db.query(RagDocumentChunk.content_hash)
        .filter(RagDocumentChunk.project_id == project_id)
        .order_by(RagDocumentChunk.id)
        .all()
    ]
    return {
        "provider": "deepseek",
        "generation_model": settings.normalized_deepseek_model,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimension,
        "prompt_version": PROMPT_VERSION,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "retrieval_top_k": settings.rag_retrieval_top_k,
        "vector_candidate_k": settings.rag_vector_candidate_k,
        "graph_top_k": settings.rag_graph_top_k,
        "graph_min_score": settings.rag_graph_min_score,
        "indexed_chunk_count": len(chunk_hashes),
        "corpus_snapshot_hash": hashlib.sha256("|".join(chunk_hashes).encode("utf-8")).hexdigest(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def _record_query_log(
    db: Session,
    project_id: int,
    user_id: int,
    question: str,
    rag_mode: str,
    graph_context: list[dict],
    sources: list[RagSourceRead],
    response_ms: int,
    answer: str | None = None,
    conversation_id: str | None = None,
    model_name: str | None = None,
    usage: dict | None = None,
    fallback_reason: str | None = None,
    error_message: str | None = None,
    experiment_run_id: int | None = None,
    experiment_case_index: int | None = None,
) -> AIQueryLog:
    settings = get_settings()
    source_payload = [source.model_dump() for source in sources]
    retrieval_config = {
        "embedding_model": settings.embedding_model,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "retrieval_top_k": settings.rag_retrieval_top_k,
        "vector_candidate_k": settings.rag_vector_candidate_k,
        "graph_top_k": settings.rag_graph_top_k,
        "graph_min_score": settings.rag_graph_min_score,
        "source_snapshot_hash": hashlib.sha256(
            repr([(item.get("chunk_id"), item.get("retrieval_score")) for item in source_payload]).encode("utf-8")
        ).hexdigest(),
    }
    log = AIQueryLog(
        project_id=project_id,
        user_id=user_id,
        question=question,
        answer=answer,
        rag_mode=rag_mode,
        graph_hit_count=len(graph_context),
        source_count=len(sources),
        response_ms=response_ms,
        conversation_id=conversation_id,
        graph_context_json=graph_context,
        sources_json=source_payload,
        provider="deepseek",
        model_name=model_name,
        prompt_version=PROMPT_VERSION,
        retrieval_config_json=retrieval_config,
        usage_json=usage or {},
        fallback_reason=fallback_reason,
        error_message=error_message,
        experiment_run_id=experiment_run_id,
        experiment_case_index=experiment_case_index,
    )
    db.add(log)
    db.flush()
    return log


def _query_log_read(log: AIQueryLog, evaluation: AIQueryEvaluation | None) -> AIQueryLogRead:
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
        created_at=log.created_at,
        evaluation=AIQueryEvaluationRead.model_validate(evaluation) if evaluation else None,
    )


def _build_query_analytics(
    project_id: int,
    logs: list[AIQueryLog],
    evaluations: dict[int, AIQueryEvaluation],
) -> AIQueryAnalyticsRead:
    total_queries = len(logs)
    evaluated_queries = len(evaluations)
    mode_stats = [_build_mode_stats(mode, logs, evaluations) for mode in ("project_rag", "kg_enhanced_rag")]
    return AIQueryAnalyticsRead(
        project_id=project_id,
        total_queries=total_queries,
        evaluated_queries=evaluated_queries,
        evaluation_rate=_rate(evaluated_queries, total_queries),
        project_rag_queries=sum(1 for log in logs if log.rag_mode == "project_rag"),
        kg_enhanced_queries=sum(1 for log in logs if log.rag_mode == "kg_enhanced_rag"),
        failed_queries=sum(1 for log in logs if log.error_message),
        avg_response_ms=_avg([log.response_ms for log in logs]),
        avg_score=_avg([evaluation.score for evaluation in evaluations.values()]) if evaluations else None,
        accurate_rate=_rate(sum(1 for evaluation in evaluations.values() if evaluation.is_accurate), evaluated_queries)
        if evaluated_queries
        else None,
        traceable_rate=_rate(sum(1 for evaluation in evaluations.values() if evaluation.is_traceable), evaluated_queries)
        if evaluated_queries
        else None,
        avg_graph_hit_count=_avg([log.graph_hit_count for log in logs]),
        avg_source_count=_avg([log.source_count for log in logs]),
        mode_stats=mode_stats,
    )


def _build_mode_stats(
    mode: str,
    logs: list[AIQueryLog],
    evaluations: dict[int, AIQueryEvaluation],
) -> AIQueryModeStats:
    mode_logs = [log for log in logs if log.rag_mode == mode]
    mode_evaluations = [evaluation for log in mode_logs if (evaluation := evaluations.get(log.id)) is not None]
    return AIQueryModeStats(
        rag_mode=mode,
        total_queries=len(mode_logs),
        evaluated_queries=len(mode_evaluations),
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


def _avg(values: list[int]) -> float:
    if not values:
        return 0
    return round(sum(values) / len(values), 2)


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0
    return round(count / total, 4)
