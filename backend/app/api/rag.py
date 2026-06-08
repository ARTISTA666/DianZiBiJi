from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import can_manage_project, can_review_project, get_current_user, require_project_access
from app.core.database import get_db
from app.models.ai import AIQueryEvaluation, AIQueryLog
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.rag import ProjectRagDataset, RagFileSync, RagSyncStatus
from app.models.user import User
from app.schemas.ai import AIQueryAnalyticsRead, AIQueryEvaluationRead, AIQueryEvaluationRequest, AIQueryLogRead, AIQueryModeStats
from app.schemas.rag import RagQueryRequest, RagQueryResponse, RagSourceRead, RagStatusRead
from app.services.audit import write_audit
from app.services.dify import DifyClient, DifyConfigError, DifyRequestError, extract_dify_document_id, extract_dify_sources
from app.services.knowledge_graph import KnowledgeGraphService

router = APIRouter(tags=["rag"])


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
    project = require_project_access(project_id, db, user)
    _require_rag_manager(db, user, project_id)
    existing = _get_project_dataset(db, project_id)
    if existing is None:
        dataset_name = f"ELN Project {project.id} - {project.name}"
        try:
            payload = await DifyClient().create_dataset(dataset_name)
        except DifyConfigError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except DifyRequestError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        dataset_id = payload.get("id")
        if not dataset_id:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Dify did not return a dataset id")
        db.add(
            ProjectRagDataset(
                project_id=project_id,
                dify_dataset_id=str(dataset_id),
                dify_dataset_name=dataset_name,
                created_by=user.id,
            )
        )
        write_audit(db, actor=user, action="init_rag_dataset", project_id=project_id, target_type="project", target_id=project_id)
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only knowledge documents can be synced")
    if record.status != FileStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved documents can be synced")
    dataset = _get_project_dataset(db, record.project_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RAG dataset is not initialized")

    sync = db.query(RagFileSync).filter(RagFileSync.file_id == record.id).first()
    if sync is None:
        sync = RagFileSync(file_id=record.id, project_id=record.project_id, dify_dataset_id=dataset.dify_dataset_id)
        db.add(sync)
        db.flush()
    sync.sync_status = RagSyncStatus.PENDING.value
    sync.sync_message = "Syncing to Dify"
    record.knowledge_sync_status = KnowledgeSyncStatus.PENDING_SYNC.value
    record.knowledge_sync_message = "Syncing to Dify knowledge base"
    db.commit()

    try:
        payload = await DifyClient().upload_document_file(dataset.dify_dataset_id, record.storage_path, record.original_filename)
        document_id = extract_dify_document_id(payload)
        if not document_id:
            raise DifyRequestError("Dify did not return a document id")
    except (DifyConfigError, DifyRequestError) as exc:
        sync.sync_status = RagSyncStatus.FAILED.value
        sync.sync_message = str(exc)
        record.knowledge_sync_status = KnowledgeSyncStatus.FAILED.value
        record.knowledge_sync_message = str(exc)
        write_audit(db, actor=user, action="sync_rag_document_failed", project_id=record.project_id, target_type="file", target_id=record.id)
        db.commit()
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE if isinstance(exc, DifyConfigError) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    sync.dify_document_id = document_id
    sync.sync_status = RagSyncStatus.SYNCED.value
    sync.sync_message = "Synced to Dify"
    sync.synced_at = now
    record.knowledge_sync_status = KnowledgeSyncStatus.SYNCED.value
    record.knowledge_sync_message = "Synced to Dify knowledge base"
    record.knowledge_synced_at = now
    write_audit(db, actor=user, action="sync_rag_document", project_id=record.project_id, target_type="file", target_id=record.id)
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
    dataset = _get_project_dataset(db, project_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RAG dataset is not initialized")
    graph_service = KnowledgeGraphService()
    graph_context = (
        []
        if payload.mode == "project_rag"
        else graph_service.find_relevant_context(db, project_id, query)
    )
    if payload.mode == "kg_enhanced_rag" and not graph_context:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Knowledge graph context is not available for this project",
        )
    graph_context_text = graph_service.format_context_for_prompt(graph_context)
    started = perf_counter()
    rag_mode = "kg_enhanced_rag" if graph_context else "project_rag"
    try:
        result = await DifyClient().chat(
            query,
            user_id=f"eln-user-{user.id}",
            dataset_id=dataset.dify_dataset_id,
            graph_context=graph_context_text,
        )
    except DifyConfigError as exc:
        response_ms = _elapsed_ms(started)
        _record_query_log(
            db,
            project_id=project_id,
            user_id=user.id,
            question=query,
            rag_mode=rag_mode,
            graph_context=graph_context,
            sources=[],
            response_ms=response_ms,
            error_message=str(exc),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except DifyRequestError as exc:
        response_ms = _elapsed_ms(started)
        _record_query_log(
            db,
            project_id=project_id,
            user_id=user.id,
            question=query,
            rag_mode=rag_mode,
            graph_context=graph_context,
            sources=[],
            response_ms=response_ms,
            error_message=str(exc),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    response_ms = _elapsed_ms(started)
    sources = _resolve_sources(db, extract_dify_sources(result), project_id)
    query_log = _record_query_log(
        db,
        project_id=project_id,
        user_id=user.id,
        question=query,
        answer=str(result.get("answer") or ""),
        rag_mode=rag_mode,
        graph_context=graph_context,
        sources=sources,
        response_ms=response_ms,
        conversation_id=result.get("conversation_id"),
    )
    write_audit(
        db,
        actor=user,
        action="query_rag",
        project_id=project_id,
        target_type="project",
        target_id=project_id,
        detail={"graph_context_count": len(graph_context), "rag_mode": rag_mode, "query_log_id": query_log.id},
    )
    db.commit()
    return RagQueryResponse(
        answer=str(result.get("answer") or ""),
        conversation_id=result.get("conversation_id"),
        sources=sources,
        graph_context=graph_context,
        rag_mode=rag_mode,
        query_log_id=query_log.id,
        response_ms=response_ms,
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
        .limit(80)
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


def _resolve_sources(db: Session, raw_sources: list[dict], project_id: int) -> list[RagSourceRead]:
    sources: list[RagSourceRead] = []
    for raw in raw_sources:
        document_id = raw.get("document_id")
        sync = None
        file_record = None
        if document_id:
            sync = (
                db.query(RagFileSync)
                .filter(RagFileSync.project_id == project_id, RagFileSync.dify_document_id == str(document_id))
                .first()
            )
        if sync:
            file_record = db.get(StoredFile, sync.file_id)
        sources.append(
            RagSourceRead(
                file_id=file_record.id if file_record else None,
                filename=file_record.original_filename if file_record else raw.get("document_name"),
                dify_document_id=str(document_id) if document_id else None,
                snippet=raw.get("content"),
            )
        )
    return sources


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


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
    error_message: str | None = None,
) -> AIQueryLog:
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
        sources_json=[source.model_dump() for source in sources],
        error_message=error_message,
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
        error_message=log.error_message,
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
