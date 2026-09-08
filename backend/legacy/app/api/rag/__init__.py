"""Project RAG API package.

The original monolithic ``app/api/rag.py`` was split by domain:

- ``common``: shared constants, permission guards and small helpers
- ``datasets``: dataset initialization / status / file sync endpoints
- ``query``: the question-answering endpoint and execution pipeline
- ``evaluations``: unblinded per-query human evaluation
- ``blind_review``: method-masked (blind) human review endpoints
- ``experiments``: experiment scheduling, execution and CSV export
- ``analytics``: query log listing and evaluation analytics

This module aggregates the sub-routers into a single ``router`` and
re-exports the names used by ``app.main`` and the test suite.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.rag import (
    analytics,
    blind_review,
    common,
    datasets,
    evaluations,
    experiments,
    query,
)
from app.api.rag.common import REQUIRED_FINAL_MATURITY_CHECKS
from app.api.rag.experiments import schedule_queued_experiments, stop_experiment_tasks

router = APIRouter(tags=["rag"])
for module in (datasets, query, evaluations, blind_review, experiments, analytics):
    router.include_router(module.router)

__all__ = [
    "REQUIRED_FINAL_MATURITY_CHECKS",
    "analytics",
    "blind_review",
    "common",
    "datasets",
    "evaluations",
    "experiments",
    "query",
    "router",
    "schedule_queued_experiments",
    "stop_experiment_tasks",
]
