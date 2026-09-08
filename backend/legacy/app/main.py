from contextlib import asynccontextmanager
from collections import deque
import json
import logging
import os
from pathlib import Path
import re
from threading import Lock
from time import perf_counter, time
import uuid

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import agents, audit, auth, files, groups, knowledge_graph, maturity, notes, ocr, projects, rag, search, templates, users
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import *  # noqa: F403
from app.services.deepseek import aclose as close_llm_client
from app.services.deepseek import usage_snapshot as llm_usage_snapshot
from app.services.seed import ensure_seed_data, recover_interrupted_experiment_runs

settings = get_settings()
STORAGE_ROOT = settings.storage_root
startup_logger = logging.getLogger("eln.startup")
startup_logger.setLevel(logging.INFO)
request_logger = logging.getLogger("eln.request")
request_logger.setLevel(logging.INFO)
started_at = time()
metrics_lock = Lock()
metrics = {
    "in_flight": 0,
    "total_requests": 0,
    "status_counts": {},
    "total_duration_ms": 0.0,
    "max_duration_ms": 0,
    "latency_samples_ms": deque(maxlen=500),
}


def _record_request(status_code: int, duration_ms: int) -> None:
    family = f"{status_code // 100}xx"
    with metrics_lock:
        metrics["total_requests"] += 1
        metrics["total_duration_ms"] += duration_ms
        metrics["max_duration_ms"] = max(metrics["max_duration_ms"], duration_ms)
        metrics["latency_samples_ms"].append(duration_ms)
        status_counts = metrics["status_counts"]
        status_counts[family] = status_counts.get(family, 0) + 1


def _metrics_snapshot() -> dict:
    with metrics_lock:
        samples = sorted(metrics["latency_samples_ms"])
        total = int(metrics["total_requests"])
        p95_index = max(0, min(len(samples) - 1, int(len(samples) * 0.95) - 1)) if samples else 0
        return {
            "status": "ok",
            "revision": settings.app_revision,
            "uptime_seconds": round(time() - started_at, 3),
            "in_flight": metrics["in_flight"],
            "total_requests": total,
            "status_counts": dict(sorted(metrics["status_counts"].items())),
            "avg_duration_ms": round(metrics["total_duration_ms"] / total, 2) if total else 0,
            "p95_duration_ms": samples[p95_index] if samples else 0,
            "max_duration_ms": metrics["max_duration_ms"],
            "latency_sample_count": len(samples),
            "llm": llm_usage_snapshot(),
        }


def _metrics_prometheus(snapshot: dict) -> str:
    """Render the JSON snapshot as Prometheus text exposition format."""
    llm = snapshot.get("llm") or {}
    lines = [
        "# HELP eln_uptime_seconds Seconds since the process started.",
        "# TYPE eln_uptime_seconds gauge",
        f"eln_uptime_seconds {snapshot['uptime_seconds']}",
        "# HELP eln_requests_in_flight Requests currently being processed.",
        "# TYPE eln_requests_in_flight gauge",
        f"eln_requests_in_flight {snapshot['in_flight']}",
        "# HELP eln_requests_total Total HTTP requests processed.",
        "# TYPE eln_requests_total counter",
        f"eln_requests_total {snapshot['total_requests']}",
        "# HELP eln_requests_by_status_total HTTP requests grouped by status family.",
        "# TYPE eln_requests_by_status_total counter",
    ]
    for family, count in snapshot["status_counts"].items():
        lines.append(f'eln_requests_by_status_total{{family="{family}"}} {count}')
    lines += [
        "# HELP eln_request_duration_ms Request latency summary in milliseconds.",
        "# TYPE eln_request_duration_ms summary",
        f'eln_request_duration_ms{{stat="avg"}} {snapshot["avg_duration_ms"]}',
        f'eln_request_duration_ms{{stat="p95"}} {snapshot["p95_duration_ms"]}',
        f'eln_request_duration_ms{{stat="max"}} {snapshot["max_duration_ms"]}',
        "# HELP eln_llm_requests_total LLM completion requests issued.",
        "# TYPE eln_llm_requests_total counter",
        f"eln_llm_requests_total {llm.get('requests', 0)}",
        "# HELP eln_llm_failures_total LLM completion requests that failed.",
        "# TYPE eln_llm_failures_total counter",
        f"eln_llm_failures_total {llm.get('failures', 0)}",
        "# HELP eln_llm_tokens_total LLM token usage by kind.",
        "# TYPE eln_llm_tokens_total counter",
        f'eln_llm_tokens_total{{kind="prompt"}} {llm.get("prompt_tokens", 0)}',
        f'eln_llm_tokens_total{{kind="completion"}} {llm.get("completion_tokens", 0)}',
        f'eln_llm_tokens_total{{kind="total"}} {llm.get("total_tokens", 0)}',
    ]
    return "\n".join(lines) + "\n"


def _reset_metrics_for_tests() -> None:
    with metrics_lock:
        metrics["in_flight"] = 0
        metrics["total_requests"] = 0
        metrics["status_counts"] = {}
        metrics["total_duration_ms"] = 0.0
        metrics["max_duration_ms"] = 0
        metrics["latency_samples_ms"].clear()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_runtime()
    startup_logger.info(
        json.dumps(
            {
                "event": "startup",
                "app_env": settings.app_env,
                "revision": settings.app_revision,
                "seed_demo_data": settings.seed_demo_data,
            },
            separators=(",", ":"),
        )
    )
    db = SessionLocal()
    try:
        recover_interrupted_experiment_runs(db)
        ensure_seed_data(db, settings)
    finally:
        db.close()
    rag.schedule_queued_experiments()
    try:
        yield
    finally:
        await rag.stop_experiment_tasks()
        await close_llm_client()


app = FastAPI(title="智能电子实验笔记系统 API", version="0.1.0", lifespan=lifespan)

logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_request(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied) else uuid.uuid4().hex
    started = perf_counter()
    with metrics_lock:
        metrics["in_flight"] += 1
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started) * 1000)
        _record_request(500, duration_ms)
        request_logger.exception(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": duration_ms,
                },
                separators=(",", ":"),
            )
        )
        raise
    finally:
        with metrics_lock:
            metrics["in_flight"] = max(0, metrics["in_flight"] - 1)
    duration_ms = round((perf_counter() - started) * 1000)
    _record_request(response.status_code, duration_ms)
    response.headers["X-Request-ID"] = request_id
    request_logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
            separators=(",", ":"),
        )
    )
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
def runtime_metrics(request: Request):
    snapshot = _metrics_snapshot()
    accept = request.headers.get("accept", "")
    if "application/json" not in accept and ("text/plain" in accept or "openmetrics" in accept):
        return PlainTextResponse(_metrics_prometheus(snapshot), media_type="text/plain; version=0.0.4")
    return snapshot


@app.get("/ready")
def ready() -> dict:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable") from exc
    finally:
        db.close()
    if not STORAGE_ROOT.is_dir() or not os.access(STORAGE_ROOT, os.W_OK):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Storage unavailable")
    return {"status": "ready", "database": "ok", "storage": "ok", "revision": settings.app_revision}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(groups.router)
app.include_router(projects.router)
app.include_router(templates.router)
app.include_router(notes.router)
app.include_router(files.router)
app.include_router(knowledge_graph.router)
app.include_router(maturity.router)
app.include_router(rag.router)
app.include_router(agents.router)
app.include_router(search.router)
app.include_router(ocr.router)
app.include_router(audit.router)
