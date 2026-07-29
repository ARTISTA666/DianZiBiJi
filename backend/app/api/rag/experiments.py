"""Experiment runs: scheduling, execution, lifecycle endpoints and CSV export."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import random
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_access
from app.api.rag import query as rag_query
from app.api.rag.common import (
    EXPERIMENT_MODES,
    GENERATION_MAX_TOKENS,
    GENERATION_TEMPERATURE,
    PROMPT_VERSION,
    _avg,
    _get_project_dataset,
    _require_rag_manager,
    _require_unblinded_rag_access,
)
from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.models.ai import AIExperimentRun, AIQueryEvaluation, AIQueryLog
from app.models.rag import RagDocumentChunk
from app.models.user import User
from app.schemas.ai import AIExperimentRunRead, AIExperimentRunRequest, AIQueryEvaluationRead
from app.services.audit import write_audit
from app.services.knowledge_graph import GRAPH_SCHEMA_VERSION

router = APIRouter(tags=["rag"])
_startup_experiment_tasks: set[asyncio.Task] = set()


def _ensure_no_active_experiment(db: Session) -> None:
    active = (
        db.query(AIExperimentRun)
        .filter(AIExperimentRun.status.in_(("queued", "running")))
        .order_by(AIExperimentRun.id)
        .first()
    )
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Experiment #{active.id} is already queued or running",
        )


async def _execute_experiment_run(db: Session, run: AIExperimentRun) -> None:
    summary = dict(run.summary_json or {})
    execution_plan = list(summary.get("execution_plan") or [])
    errors = list(summary.get("errors") or [])
    attempted_orders = {
        log.experiment_execution_order
        for log in db.query(AIQueryLog).filter(AIQueryLog.experiment_run_id == run.id).all()
        if log.experiment_execution_order is not None
    }
    attempted_orders.update(item["execution_order"] for item in errors if item.get("execution_order") is not None)
    fatal_error: dict | None = None
    for case in execution_plan:
        if case["execution_order"] in attempted_orders:
            continue
        try:
            # Called through the module so tests can monkeypatch the executor.
            await rag_query._execute_rag_query(
                db,
                project_id=run.project_id,
                user_id=run.created_by,
                query=case["question"],
                mode=case["mode"],
                experiment_run_id=run.id,
                experiment_case_index=case["question_index"],
                experiment_repetition_index=case["repetition_index"],
                experiment_execution_order=case["execution_order"],
            )
            run.completed_cases += 1
        except HTTPException as exc:
            run.failed_cases += 1
            errors.append({**case, "error": str(exc.detail)})
        except Exception as exc:
            db.rollback()
            run = db.get(AIExperimentRun, run.id)
            if run is None:
                raise
            run.failed_cases += 1
            fatal_error = {**case, "error": f"Unexpected {type(exc).__name__}: {exc}"}
            errors.append(fatal_error)
        run.summary_json = {
            **summary,
            "errors": errors,
            "fatal_error": fatal_error,
            "execution_plan": execution_plan,
            "unexecuted_cases": max(0, run.total_cases - run.completed_cases - run.failed_cases),
        }
        db.commit()
        if fatal_error:
            break

    logs = (
        db.query(AIQueryLog)
        .filter(AIQueryLog.experiment_run_id == run.id)
        .order_by(AIQueryLog.experiment_execution_order, AIQueryLog.id)
        .all()
    )
    run.summary_json = {
        **summary,
        "errors": errors,
        "fatal_error": fatal_error,
        "unexecuted_cases": max(0, run.total_cases - run.completed_cases - run.failed_cases),
        "execution_plan": execution_plan,
        "mode_stats": [
            {
                "mode": mode,
                "completed": sum(1 for log in logs if log.rag_mode == mode and not log.error_message),
                "failed": len(
                    {
                        log.experiment_execution_order
                        for log in logs
                        if log.rag_mode == mode and log.error_message and log.experiment_execution_order is not None
                    }
                    | {
                        item["execution_order"]
                        for item in errors
                        if item["mode"] == mode and item.get("execution_order") is not None
                    }
                ),
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
            for mode in run.modes_json
        ],
    }
    run.status = "failed" if fatal_error else ("completed" if run.failed_cases == 0 else "completed_with_errors")
    run.completed_at = datetime.now(timezone.utc)
    actor = db.get(User, run.created_by)
    if actor is not None:
        write_audit(
            db,
            actor=actor,
            action="run_rag_experiment",
            project_id=run.project_id,
            target_type="ai_experiment_run",
            target_id=run.id,
            detail={
                "total_cases": run.total_cases,
                "completed_cases": run.completed_cases,
                "failed_cases": run.failed_cases,
            },
        )
    db.commit()


async def _run_queued_experiment(run_id: int) -> None:
    db = SessionLocal()
    try:
        claimed = (
            db.query(AIExperimentRun)
            .filter(AIExperimentRun.id == run_id, AIExperimentRun.status == "queued")
            .update({AIExperimentRun.status: "running"}, synchronize_session=False)
        )
        db.commit()
        if claimed != 1:
            return
        run = db.get(AIExperimentRun, run_id)
        if run is not None:
            await _execute_experiment_run(db, run)
    except asyncio.CancelledError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        run = db.get(AIExperimentRun, run_id)
        if run is not None and run.status == "running":
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.summary_json = {
                **(run.summary_json or {}),
                "fatal_error": {"error": f"Unexpected {type(exc).__name__}: {exc}"},
                "unexecuted_cases": max(0, run.total_cases - run.completed_cases - run.failed_cases),
            }
            db.commit()
    finally:
        db.close()


def schedule_queued_experiments() -> None:
    db = SessionLocal()
    try:
        run_ids = [run_id for (run_id,) in db.query(AIExperimentRun.id).filter(AIExperimentRun.status == "queued")]
    finally:
        db.close()
    for run_id in run_ids:
        task = asyncio.create_task(_run_queued_experiment(run_id))
        _startup_experiment_tasks.add(task)
        task.add_done_callback(_startup_experiment_tasks.discard)


async def stop_experiment_tasks() -> None:
    tasks = list(_startup_experiment_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@router.post(
    "/projects/{project_id}/rag/experiments",
    response_model=AIExperimentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_rag_experiment(
    project_id: int,
    payload: AIExperimentRunRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIExperimentRunRead:
    require_project_access(project_id, db, user)
    _require_rag_manager(db, user, project_id)
    questions = [question.strip() for question in payload.questions if question.strip()]
    modes = list(dict.fromkeys(payload.modes))
    if not questions:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one question is required")
    if any(mode not in EXPERIMENT_MODES for mode in modes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Experiment modes must be one of: {', '.join(EXPERIMENT_MODES)}",
        )
    if _get_project_dataset(db, project_id) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RAG dataset is not initialized")
    _ensure_no_active_experiment(db)

    random_seed = payload.random_seed
    if random_seed is None:
        random_seed = random.SystemRandom().randrange(0, 2_147_483_648)
    execution_plan = [
        {
            "question_index": question_index,
            "question": question,
            "repetition_index": repetition_index,
            "mode": mode,
        }
        for question_index, question in enumerate(questions, start=1)
        for repetition_index in range(1, payload.repetitions + 1)
        for mode in modes
    ]
    if payload.randomize_order:
        random.Random(random_seed).shuffle(execution_plan)
    for execution_order, case in enumerate(execution_plan, start=1):
        case["execution_order"] = execution_order

    config_snapshot = _experiment_config_snapshot(db, project_id)
    config_snapshot["experiment_protocol"] = {
        "repetitions": payload.repetitions,
        "randomize_order": payload.randomize_order,
        "random_seed": random_seed,
        "execution_plan_hash": hashlib.sha256(
            json.dumps(execution_plan, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }

    run = AIExperimentRun(
        project_id=project_id,
        created_by=user.id,
        name=payload.name.strip(),
        status="queued",
        questions_json=questions,
        modes_json=modes,
        config_snapshot_json=config_snapshot,
        summary_json={
            "errors": [],
            "fatal_error": None,
            "unexecuted_cases": len(execution_plan),
            "execution_plan": execution_plan,
        },
        total_cases=len(execution_plan),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(_run_queued_experiment, run.id)
    return run


@router.get("/projects/{project_id}/rag/experiments", response_model=list[AIExperimentRunRead])
def list_rag_experiments(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AIExperimentRunRead]:
    require_project_access(project_id, db, user)
    _require_unblinded_rag_access(db, user, project_id)
    return (
        db.query(AIExperimentRun)
        .filter(AIExperimentRun.project_id == project_id)
        .order_by(AIExperimentRun.created_at.desc(), AIExperimentRun.id.desc())
        .limit(50)
        .all()
    )


@router.get("/rag/experiments/{run_id}", response_model=AIExperimentRunRead)
def get_rag_experiment(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIExperimentRunRead:
    run = db.get(AIExperimentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment run not found")
    require_project_access(run.project_id, db, user)
    _require_unblinded_rag_access(db, user, run.project_id)
    return run


@router.post(
    "/rag/experiments/{run_id}/resume",
    response_model=AIExperimentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_rag_experiment(
    run_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIExperimentRunRead:
    run = db.get(AIExperimentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment run not found")
    require_project_access(run.project_id, db, user)
    _require_rag_manager(db, user, run.project_id)
    if run.status != "interrupted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only interrupted experiments can resume")
    _ensure_no_active_experiment(db)
    run.status = "queued"
    run.completed_at = None
    db.commit()
    db.refresh(run)
    background_tasks.add_task(_run_queued_experiment, run.id)
    return run


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
    _require_unblinded_rag_access(db, user, run.project_id)
    return _experiment_export_response(run, db, f"rag-experiment-{run.id}.csv")


def _experiment_export_response(
    run: AIExperimentRun,
    db: Session,
    filename: str,
    review_protocol: str | None = None,
    extra_columns: dict[str, str] | None = None,
) -> StreamingResponse:
    extra_columns = extra_columns or {}
    logs = (
        db.query(AIQueryLog)
        .filter(AIQueryLog.experiment_run_id == run.id)
        .order_by(AIQueryLog.experiment_execution_order, AIQueryLog.id)
        .all()
    )
    evaluation_query = db.query(AIQueryEvaluation).filter(AIQueryEvaluation.query_log_id.in_([log.id for log in logs] or [0]))
    if review_protocol is not None:
        evaluation_query = evaluation_query.filter(AIQueryEvaluation.review_protocol == review_protocol)
    evaluation_rows = evaluation_query.all()
    evaluations_by_log: dict[int, list[AIQueryEvaluation]] = defaultdict(list)
    for evaluation in evaluation_rows:
        evaluations_by_log[evaluation.query_log_id].append(evaluation)
    log_by_case = {
        (log.experiment_case_index, log.experiment_repetition_index or 1, log.rag_mode): log
        for log in logs
    }
    errors = {
        (item["question_index"], item.get("repetition_index", 1), item["mode"]): item["error"]
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
            "repetition_index",
            "execution_order",
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
            "evaluations_json",
            "error",
            *extra_columns.keys(),
        ]
    )
    execution_plan = (run.summary_json or {}).get("execution_plan") or [
        {
            "question_index": question_index,
            "question": question,
            "repetition_index": 1,
            "mode": mode,
            "execution_order": None,
        }
        for question_index, question in enumerate(run.questions_json or [], start=1)
        for mode in run.modes_json or []
    ]
    for case in sorted(execution_plan, key=lambda item: item.get("execution_order") or 0):
        question_index = case["question_index"]
        question = case["question"]
        repetition_index = case.get("repetition_index", 1)
        mode = case["mode"]
        log = log_by_case.get((question_index, repetition_index, mode))
        evaluations = evaluations_by_log.get(log.id, []) if log else []
        case_error = log.error_message if log and log.error_message else errors.get((question_index, repetition_index, mode), "")
        mean_score = _avg([evaluation.score for evaluation in evaluations]) if evaluations else ""
        accurate_values = {evaluation.is_accurate for evaluation in evaluations}
        traceable_values = {evaluation.is_traceable for evaluation in evaluations}
        writer.writerow(
            [
                run.id,
                question_index,
                question,
                mode,
                repetition_index,
                log.experiment_execution_order if log else case.get("execution_order"),
                "completed" if log and not log.error_message else ("failed" if case_error else "not_executed"),
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
                mean_score,
                accurate_values.pop() if len(accurate_values) == 1 else "",
                traceable_values.pop() if len(traceable_values) == 1 else "",
                " | ".join(
                    f"evaluator#{evaluation.evaluator_user_id}: {evaluation.comment}"
                    for evaluation in evaluations
                    if evaluation.comment
                ),
                json.dumps(
                    [
                        AIQueryEvaluationRead.model_validate(evaluation).model_dump(mode="json")
                        for evaluation in evaluations
                    ],
                    ensure_ascii=False,
                ),
                case_error,
                *extra_columns.values(),
            ]
        )
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
        "app_revision": settings.app_revision,
        "generation_model": settings.normalized_deepseek_model,
        "generation_temperature": GENERATION_TEMPERATURE,
        "generation_max_tokens": GENERATION_MAX_TOKENS,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimension,
        "prompt_version": PROMPT_VERSION,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "retrieval_top_k": settings.rag_retrieval_top_k,
        "collection_retrieval_top_k": settings.rag_collection_retrieval_top_k,
        "vector_candidate_k": settings.rag_vector_candidate_k,
        "graph_top_k": settings.rag_graph_top_k,
        "graph_min_score": settings.rag_graph_min_score,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "indexed_chunk_count": len(chunk_hashes),
        "corpus_snapshot_hash": hashlib.sha256("|".join(chunk_hashes).encode("utf-8")).hexdigest(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "available_experiment_modes": list(EXPERIMENT_MODES),
    }
