"""RAG question answering: the query endpoint and its execution pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_access
from app.api.rag.common import (
    BM25_PROMPT_VERSION,
    EMBEDDING_RAG_MODES,
    EXPERIMENT_MODES,
    GENERATION_MAX_TOKENS,
    GENERATION_TEMPERATURE,
    PROMPT_VERSION,
    PURE_LLM_PROMPT_VERSION,
    STRUCTURED_QUERY_VERSION,
    _audit_answer_citations,
    _elapsed_ms,
    _get_project_dataset,
    _has_graph_marker,
    _has_source_marker,
    _merge_usage,
    _require_compatible_embedding,
    _require_unblinded_rag_access,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.models.ai import AIQueryLog, RagMode
from app.models.user import User
from app.schemas.rag import RagQueryRequest, RagQueryResponse, RagSourceRead
from app.services.audit import write_audit
from app.services.deepseek import DeepSeekClient, DeepSeekConfigError, DeepSeekRequestError
from app.services.embedding import EmbeddingServiceError
from app.services.knowledge_graph import GRAPH_SCHEMA_VERSION, KnowledgeGraphService
from app.services.local_rag import LocalRagService
from app.services.prompts import PROMPTS

router = APIRouter(tags=["rag"])

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 2  # Max citation-repair loops before giving up
RETRIEVAL_FAILURE_PROMPT_VERSION = "rag-retrieval-failure-v1"
GRAPH_CONTEXT_BUDGET_FALLBACK = "Graph context exceeded prompt budget"
STRUCTURED_GRAPH_BUDGET_FALLBACK = (
    f"{GRAPH_CONTEXT_BUDGET_FALLBACK}; no safe structured context was available"
)


@dataclass
class QueryLogEntry:
    """Groups all parameters previously passed individually to ``_record_query_log``."""

    # --- required context ---
    project_id: int
    user_id: int
    question: str
    rag_mode: str
    graph_context: list[dict]
    sources: list[RagSourceRead]
    response_ms: int

    # --- optional generation artefacts ---
    answer: str | None = None
    conversation_id: str | None = None
    model_name: str | None = None
    provider: str = "deepseek"
    prompt_version: str = PROMPT_VERSION
    usage: dict | None = None
    fallback_reason: str | None = None
    citation_audit: dict | None = None
    error_message: str | None = None

    # --- experiment tracking ---
    experiment_run_id: int | None = None
    experiment_case_index: int | None = None
    experiment_repetition_index: int | None = None
    experiment_execution_order: int | None = None


@router.post("/projects/{project_id}/rag/query", response_model=RagQueryResponse)
async def query_project_rag(
    project_id: int,
    payload: RagQueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagQueryResponse:
    require_project_access(project_id, db, user)
    _require_unblinded_rag_access(db, user, project_id)
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query cannot be empty")
    if payload.mode not in RagMode:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported RAG mode: {payload.mode}")
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


# ---------------------------------------------------------------------------
# Sub-functions extracted from _execute_rag_query
# ---------------------------------------------------------------------------


async def _retrieve_sources(
    db: Session,
    project_id: int,
    query: str,
    mode: str,
) -> list:
    """Load RAG chunks from DB via BM25 or vector search depending on *mode*."""
    if mode in {RagMode.PURE_LLM.value, RagMode.STRUCTURED_QUERY.value}:
        return []
    try:
        service = LocalRagService()
        retrieved = (
            await service.retrieve_bm25(db, project_id, query)
            if mode == RagMode.BM25_RAG.value
            else await service.retrieve(db, project_id, query)
        )
    except EmbeddingServiceError as exc:
        logger.error("Embedding service failed during retrieval: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 服务暂时不可用，请稍后重试",
        ) from exc
    if not retrieved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No indexed project documents are available for retrieval",
        )
    return retrieved


def _retrieve_graph_context(
    db: Session,
    project_id: int,
    query: str,
    mode: str,
) -> tuple[list[dict], str | None, str, str]:
    """Query knowledge graph for relevant context and format it for prompts.

    Returns ``(graph_context, fallback_reason, rag_mode, graph_context_text)``.
    The formatted *graph_context_text* is produced internally so callers never
    need to interact with ``KnowledgeGraphService`` directly.
    """
    graph_service = KnowledgeGraphService()
    graph_context = (
        graph_service.find_relevant_context(db, project_id, query)
        if mode in {"auto", RagMode.STRUCTURED_QUERY.value, RagMode.KG_ENHANCED_RAG.value}
        else []
    )
    had_graph_context = bool(graph_context)
    fallback_reason: str | None = None
    if mode == RagMode.KG_ENHANCED_RAG.value and not graph_context:
        fallback_reason = (
            "No graph relation reached the relevance threshold; "
            "the explicit KG mode continued with project documents only"
        )
    elif mode == RagMode.STRUCTURED_QUERY.value and not graph_context:
        fallback_reason = "No structured graph relation matched the question"
    elif mode == "auto" and not graph_context:
        fallback_reason = "No graph relation reached the relevance threshold; used project RAG"
    graph_context_text = graph_service.format_context_for_prompt(graph_context, query=query)
    visible_graph_count = sum(
        line.startswith("- [G") for line in graph_context_text.splitlines()
    )
    graph_context = graph_context[:visible_graph_count]
    if had_graph_context and not graph_context:
        graph_context_text = ""
        if mode == "auto":
            fallback_reason = f"{GRAPH_CONTEXT_BUDGET_FALLBACK}; used project RAG"
        elif mode == RagMode.KG_ENHANCED_RAG.value:
            fallback_reason = (
                f"{GRAPH_CONTEXT_BUDGET_FALLBACK}; "
                "explicit KG mode continued with project documents only"
            )
        elif mode == RagMode.STRUCTURED_QUERY.value:
            fallback_reason = STRUCTURED_GRAPH_BUDGET_FALLBACK
    # Resolve "auto" after prompt budgeting so logs match visible evidence.
    if mode == "auto":
        rag_mode = RagMode.KG_ENHANCED_RAG.value if graph_context else RagMode.PROJECT_RAG.value
    else:
        rag_mode = mode
    return graph_context, fallback_reason, rag_mode, graph_context_text


def _retrieve_graph_context_with_bind(bind, project_id: int, query: str, mode: str):
    graph_db = Session(bind=bind)
    try:
        return _retrieve_graph_context(graph_db, project_id, query, mode)
    finally:
        graph_db.close()


def _build_prompts(
    rag_mode: str,
    source_context: str,
    graph_context_text: str,
    query: str,
    fallback_reason: str | None = None,
) -> tuple[str, str, str]:
    """Select and assemble prompts based on the resolved *rag_mode*.

    Uses the already-computed *rag_mode* so callers don't need to repeat
    mode-resolution logic.  *fallback_reason* is accepted for future prompt
    annotations (e.g. telling the LLM that graph context was unavailable).

    Returns ``(system_prompt, user_prompt, prompt_version)``.
    """
    if rag_mode == RagMode.PURE_LLM.value:
        system_prompt = PROMPTS["pure_llm"].system_prompt
        user_prompt = f"用户问题：{query}"
        prompt_version = PURE_LLM_PROMPT_VERSION
    elif rag_mode == RagMode.STRUCTURED_QUERY.value:
        system_prompt = PROMPTS["structured_query"].system_prompt
        user_prompt = (
            f"结构化图谱关系上下文：\n{graph_context_text}\n\n"
            f"用户问题：{query}"
        )
        prompt_version = STRUCTURED_QUERY_VERSION
    else:
        prompt_key = "bm25_rag" if rag_mode == RagMode.BM25_RAG.value else "project_rag"
        system_prompt = PROMPTS[prompt_key].system_prompt
        user_prompt = (
            f"{source_context}\n\n"
            f"{graph_context_text or '实验知识图谱上下文：本次未检索到达到阈值的相关关系。'}\n\n"
            f"用户问题：{query}"
        )
        prompt_version = PROMPTS[prompt_key].version
    return system_prompt, user_prompt, prompt_version


async def _repair_answer(
    client: DeepSeekClient,
    *,
    answer: str,
    system_prompt: str,
    user_prompt: str,
    citation_audit: dict,
    source_count: int,
    graph_count: int,
    usage: dict,
    result: dict,
) -> tuple[str, dict, dict, dict, bool]:
    """Run the citation repair loop (up to 2 attempts).

    Returns ``(answer, citation_audit, usage, result, repair_attempted)``.
    """
    def missing_marker_requirements() -> list[str]:
        missing: list[str] = []
        if source_count and not _has_source_marker(answer):
            missing.append("至少一个有效 [S数字]")
        if graph_count and not _has_graph_marker(answer):
            missing.append("至少一个有效 [G数字]")
        return missing

    repair_attempted = False
    for _ in range(MAX_REPAIR_ATTEMPTS):
        missing_markers = missing_marker_requirements()
        if not (citation_audit["has_evidence"] and (not citation_audit["passed"] or missing_markers)):
            break
        repair_attempted = True
        citation_audit["repair_attempted"] = True
        try:
            repair_result = await client.generate(
                system_prompt=system_prompt,
                user_prompt=(
                    f"{user_prompt}\n\n"
                    f"待修订回答：\n{answer}\n\n"
                    f"引用检查结果：{citation_audit['message']}\n"
                    f"缺失的强制引用：{'、'.join(missing_markers) or '无'}。\n"
                    "请只输出修订后的完整回答。只能使用上文真实存在的 [S数字] 和 [G数字] 编号；"
                    "如果上文提供了项目资料检索结果，修订后答案必须至少包含一个有效 [S数字]；"
                    "如果上文提供了知识图谱上下文，修订后答案必须至少包含一个有效 [G数字]；"
                    "不得使用 [G系统]、[G1-G2] 等非数字编号；"
                    "不得新增上文没有的事实；无法确认的内容应删除或明确写为无法确认。"
                ),
                temperature=0.0,
                max_tokens=GENERATION_MAX_TOKENS,
            )
        except (DeepSeekConfigError, DeepSeekRequestError) as exc:
            citation_audit["repair_error"] = str(exc)
            break
        answer = repair_result["answer"]
        usage = _merge_usage(usage, repair_result.get("usage") or {})
        result["model"] = repair_result.get("model") or result.get("model")
        result["request_id"] = repair_result.get("request_id") or result.get("request_id")
        citation_audit = _audit_answer_citations(answer, source_count, graph_count)
    if repair_attempted:
        citation_audit["repair_attempted"] = True
    return answer, citation_audit, usage, result, repair_attempted


def _build_structured_query_empty_response(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    query: str,
    rag_mode: str,
    fallback_reason: str | None,
    sources: list[RagSourceRead],
    graph_context: list[dict],
    started: float,
    experiment_run_id: int | None = None,
    experiment_case_index: int | None = None,
    experiment_repetition_index: int | None = None,
    experiment_execution_order: int | None = None,
) -> RagQueryResponse:
    """Build the early-return response for structured-query mode with no graph hits."""
    answer = (
        "结构化查询相关图谱关系超过当前上下文预算，未能安全纳入本次回答。"
        if fallback_reason == STRUCTURED_GRAPH_BUDGET_FALLBACK
        else "结构化查询未找到与该问题匹配的项目图谱关系。"
    )
    citation_audit = _audit_answer_citations(answer, 0, 0)
    response_ms = _elapsed_ms(started)
    query_log = _record_query_log(
        db,
        QueryLogEntry(
            project_id=project_id,
            user_id=user_id,
            question=query,
            answer=answer,
            rag_mode=rag_mode,
            graph_context=graph_context,
            sources=sources,
            response_ms=response_ms,
            provider="system",
            prompt_version=STRUCTURED_QUERY_VERSION,
            fallback_reason=fallback_reason,
            citation_audit=citation_audit,
            experiment_run_id=experiment_run_id,
            experiment_case_index=experiment_case_index,
            experiment_repetition_index=experiment_repetition_index,
            experiment_execution_order=experiment_execution_order,
        ),
    )
    return RagQueryResponse(
        answer=answer,
        sources=sources,
        graph_context=graph_context,
        rag_mode=rag_mode,
        query_log_id=query_log.id,
        response_ms=response_ms,
        provider="system",
        fallback_reason=fallback_reason,
        citation_audit=citation_audit,
    )


# ---------------------------------------------------------------------------
# Orchestration layer
# ---------------------------------------------------------------------------


async def _execute_rag_query(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    query: str,
    mode: str,
    experiment_run_id: int | None = None,
    experiment_case_index: int | None = None,
    experiment_repetition_index: int | None = None,
    experiment_execution_order: int | None = None,
) -> RagQueryResponse:
    settings = get_settings()
    dataset = _get_project_dataset(db, project_id)
    if mode not in {RagMode.PURE_LLM.value, RagMode.STRUCTURED_QUERY.value} and dataset is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RAG dataset is not initialized")
    if mode in EMBEDDING_RAG_MODES:
        _require_compatible_embedding(dataset)

    started = perf_counter()

    # 1. Retrieval phase – run RAG source retrieval (async) and KG context
    #    retrieval (sync → offloaded to a worker thread) in parallel so that
    #    total latency ≈ max(T_rag, T_kg) instead of T_rag + T_kg.
    graph_bind = db.get_bind()
    retrieved_result, graph_result = await asyncio.gather(
        _retrieve_sources(db, project_id, query, mode),
        asyncio.to_thread(
            _retrieve_graph_context_with_bind,
            graph_bind,
            project_id,
            query,
            mode,
        ),
        return_exceptions=True,
    )
    source_error = isinstance(retrieved_result, BaseException)
    graph_error = isinstance(graph_result, BaseException)
    if source_error or graph_error:
        error = retrieved_result if source_error else graph_result
        if not isinstance(error, Exception):
            raise error
        failed_sources = (
            []
            if source_error
            else [RagSourceRead(**item.as_source()) for item in retrieved_result]
        )
        error_message = (
            str(error.detail)
            if isinstance(error, HTTPException)
            else f"Unexpected {type(error).__name__}: {error}"
        )
        _record_query_failure(
            db,
            project_id=project_id,
            user_id=user_id,
            question=query,
            rag_mode=mode,
            sources=failed_sources,
            error_message=error_message,
            response_ms=_elapsed_ms(started),
            experiment_run_id=experiment_run_id,
            experiment_case_index=experiment_case_index,
            experiment_repetition_index=experiment_repetition_index,
            experiment_execution_order=experiment_execution_order,
        )
        raise error
    retrieved = retrieved_result
    graph_context, fallback_reason, rag_mode, graph_context_text = graph_result

    # 3. Build response artefacts
    sources = [RagSourceRead(**item.as_source()) for item in retrieved]
    source_context = LocalRagService.format_sources(retrieved)

    # 4. Short-circuit: structured query with no graph hits
    if mode == RagMode.STRUCTURED_QUERY.value and not graph_context:
        return _build_structured_query_empty_response(
            db,
            project_id=project_id,
            user_id=user_id,
            query=query,
            rag_mode=rag_mode,
            fallback_reason=fallback_reason,
            sources=sources,
            graph_context=graph_context,
            started=started,
            experiment_run_id=experiment_run_id,
            experiment_case_index=experiment_case_index,
            experiment_repetition_index=experiment_repetition_index,
            experiment_execution_order=experiment_execution_order,
        )

    # 5. Prompt assembly
    system_prompt, user_prompt, prompt_version = _build_prompts(
        rag_mode, source_context, graph_context_text, query,
        fallback_reason=fallback_reason,
    )

    # 6. LLM generation
    try:
        client = DeepSeekClient()
        result = await client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=GENERATION_TEMPERATURE,
            max_tokens=GENERATION_MAX_TOKENS,
        )
    except (DeepSeekConfigError, DeepSeekRequestError) as exc:
        _record_query_log(
            db,
            QueryLogEntry(
                project_id=project_id,
                user_id=user_id,
                question=query,
                rag_mode=rag_mode,
                graph_context=graph_context,
                sources=sources,
                response_ms=_elapsed_ms(started),
                model_name=settings.normalized_deepseek_model,
                prompt_version=prompt_version,
                fallback_reason=fallback_reason,
                error_message=str(exc),
                experiment_run_id=experiment_run_id,
                experiment_case_index=experiment_case_index,
                experiment_repetition_index=experiment_repetition_index,
                experiment_execution_order=experiment_execution_order,
            ),
        )
        db.commit()
        code = status.HTTP_503_SERVICE_UNAVAILABLE if isinstance(exc, DeepSeekConfigError) else status.HTTP_502_BAD_GATEWAY
        logger.error("DeepSeek generation failed (%s): %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=code,
            detail="AI 回答生成失败，请稍后重试",
        ) from exc

    answer = result["answer"]
    usage = result.get("usage") or {}
    citation_audit = _audit_answer_citations(answer, len(sources), len(graph_context))

    # 7. Citation repair
    answer, citation_audit, usage, result, _ = await _repair_answer(
        client,
        answer=answer,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        citation_audit=citation_audit,
        source_count=len(sources),
        graph_count=len(graph_context),
        usage=usage,
        result=result,
    )

    # 8. Record & respond
    response_ms = _elapsed_ms(started)
    query_log = _record_query_log(
        db,
        QueryLogEntry(
            project_id=project_id,
            user_id=user_id,
            question=query,
            answer=answer,
            rag_mode=rag_mode,
            graph_context=graph_context,
            sources=sources,
            response_ms=response_ms,
            conversation_id=result.get("request_id"),
            model_name=result.get("model"),
            prompt_version=prompt_version,
            usage=usage,
            fallback_reason=fallback_reason,
            citation_audit=citation_audit,
            experiment_run_id=experiment_run_id,
            experiment_case_index=experiment_case_index,
            experiment_repetition_index=experiment_repetition_index,
            experiment_execution_order=experiment_execution_order,
        ),
    )
    return RagQueryResponse(
        answer=answer,
        conversation_id=result.get("request_id"),
        sources=sources,
        graph_context=graph_context,
        rag_mode=rag_mode,
        query_log_id=query_log.id,
        response_ms=response_ms,
        provider="deepseek",
        model_name=result.get("model"),
        fallback_reason=fallback_reason,
        citation_audit=citation_audit,
    )


def _record_query_log(
    db: Session,
    entry: QueryLogEntry,
) -> AIQueryLog:
    settings = get_settings()
    source_payload = [source.model_dump() for source in entry.sources]
    retrieval_config = {
        "embedding_model": settings.embedding_model,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "retrieval_top_k": settings.rag_retrieval_top_k,
        "collection_retrieval_top_k": settings.rag_collection_retrieval_top_k,
        "vector_candidate_k": settings.rag_vector_candidate_k,
        "graph_top_k": settings.rag_graph_top_k,
        "graph_min_score": settings.rag_graph_min_score,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "generation_temperature": GENERATION_TEMPERATURE,
        "generation_max_tokens": GENERATION_MAX_TOKENS,
        "source_snapshot_hash": hashlib.sha256(
            repr([(item.get("chunk_id"), item.get("retrieval_score")) for item in source_payload]).encode("utf-8")
        ).hexdigest(),
        "citation_audit": entry.citation_audit,
    }
    log = AIQueryLog(
        project_id=entry.project_id,
        user_id=entry.user_id,
        question=entry.question,
        answer=entry.answer,
        rag_mode=entry.rag_mode,
        graph_hit_count=len(entry.graph_context),
        source_count=len(entry.sources),
        response_ms=entry.response_ms,
        conversation_id=entry.conversation_id,
        graph_context_json=entry.graph_context,
        sources_json=source_payload,
        provider=entry.provider,
        model_name=entry.model_name,
        prompt_version=entry.prompt_version,
        retrieval_config_json=retrieval_config,
        usage_json=entry.usage or {},
        fallback_reason=entry.fallback_reason,
        error_message=entry.error_message,
        experiment_run_id=entry.experiment_run_id,
        experiment_case_index=entry.experiment_case_index,
        experiment_repetition_index=entry.experiment_repetition_index,
        experiment_execution_order=entry.experiment_execution_order,
    )
    db.add(log)
    db.flush()
    return log


def _record_query_failure(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    question: str,
    rag_mode: str,
    sources: list[RagSourceRead],
    error_message: str,
    response_ms: int,
    experiment_run_id: int | None = None,
    experiment_case_index: int | None = None,
    experiment_repetition_index: int | None = None,
    experiment_execution_order: int | None = None,
) -> None:
    """Persist retrieval failures without hiding the original query error."""
    try:
        db.rollback()
        _record_query_log(
            db,
            QueryLogEntry(
                project_id=project_id,
                user_id=user_id,
                question=question,
                rag_mode=rag_mode,
                graph_context=[],
                sources=sources,
                response_ms=response_ms,
                provider="system",
                prompt_version=RETRIEVAL_FAILURE_PROMPT_VERSION,
                error_message=error_message,
                citation_audit=_audit_answer_citations("", len(sources), 0),
                experiment_run_id=experiment_run_id,
                experiment_case_index=experiment_case_index,
                experiment_repetition_index=experiment_repetition_index,
                experiment_execution_order=experiment_execution_order,
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to record RAG retrieval failure", exc_info=True)
