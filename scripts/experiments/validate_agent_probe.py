#!/usr/bin/env python3
"""Run a small live Agent citation probe through the public API."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from import_gse111619_via_api import ApiClient, BENCHMARK_PROJECT_NAME


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "data" / "real" / "GSE111619" / "agent_probe_report.json"
TASK_TYPES = ("experiment_summary", "weekly_report", "stage_report", "graph_overview")


def find_project(api: ApiClient, name: str) -> dict[str, Any]:
    project = next((item for item in api.get("/projects") if item["name"] == name), None)
    if project is None:
        raise ValueError(f"Project not found: {name}")
    return project


def review_result(run: dict[str, Any]) -> dict[str, Any]:
    return (run.get("input_params_json") or {}).get("review_result") or {}


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    invalid_citations = [
        citation
        for run in runs
        for citation in review_result(run).get("invalid_citations", [])
    ]
    return {
        "completed_runs": sum(run.get("status") == "completed" for run in runs),
        "needs_review_runs": sum(run.get("status") == "needs_review" for run in runs),
        "failed_runs": sum(run.get("status") == "failed" for run in runs),
        "invalid_citations": len(invalid_citations),
        "invalid_citation_values": invalid_citations,
    }


def run_probe(api: ApiClient, project_name: str, task_types: tuple[str, ...]) -> dict[str, Any]:
    project = find_project(api, project_name)
    runs = [
        api.post(
            "/api/agents/generate",
            json={"project_id": project["id"], "task_type": task_type},
        )
        for task_type in task_types
    ]
    summary = summarize_runs(runs)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {"id": project["id"], "name": project["name"]},
        "task_types": list(task_types),
        **summary,
        "runs": [
            {
                "id": run.get("id"),
                "task_type": run.get("task_type"),
                "status": run.get("status"),
                "message": run.get("message"),
                "review_result": review_result(run),
            }
            for run in runs
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--username", default=os.environ.get("ELN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("ELN_PASSWORD"))
    parser.add_argument("--project-name", default=BENCHMARK_PROJECT_NAME)
    parser.add_argument("--task-types", default=",".join(TASK_TYPES))
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.password:
        raise SystemExit("Set ELN_PASSWORD or pass --password")
    task_types = tuple(item.strip() for item in args.task_types.split(",") if item.strip())
    invalid = sorted(set(task_types) - set(TASK_TYPES))
    if invalid or not task_types:
        raise SystemExit(f"Unsupported task types: {invalid or task_types}")

    api = ApiClient(args.api_base, args.username, args.password)
    try:
        report = run_probe(api, args.project_name, task_types)
    finally:
        api.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("completed_runs", "needs_review_runs", "failed_runs", "invalid_citations")}, ensure_ascii=False))
    raise SystemExit(0 if report["needs_review_runs"] == 0 and report["failed_runs"] == 0 and report["invalid_citations"] == 0 else 1)


if __name__ == "__main__":
    main()
