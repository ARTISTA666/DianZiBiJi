#!/usr/bin/env python3
"""Run the five-mode experiment after the tracked confirmatory preflight."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
from confirmatory_preflight import (  # noqa: E402
    MODES,
    PreflightError,
    PreflightResult,
    _authority_commitment,
    confirmatory_preflight,
    load_verified_questions,
)

RUNS_DIR = ROOT / "agent-work" / "runs"
FREEZE_DIR = ROOT / "agent-work" / "freeze" / "rag-experiment-5-rust-v2-gse291942-3projects-2026-08-29"
FREEZE_MANIFEST = FREEZE_DIR / "freeze-manifest.json"
API_BASE = "http://127.0.0.1:8001"
USERNAME = "admin"
PASSWORD_ENV = "FULL_SYSTEM_API_PASSWORD"

PROJECTS = {
    "gse111619": {"project_name": "GSE111619 真实数据验证项目", "seed": 2026081501, "question_file": "gse111619_questions_v2_draft.json"},
    "gse291942_arabidopsis_heat": {"project_name": "GSE291942 拟南芥高温胁迫 RNA-seq 验证项目", "seed": 2026081602, "question_file": "gse291942_arabidopsis_heat_questions_v2_draft.json"},
    "smithsonian_joseph_henry": {"project_name": "Smithsonian Joseph Henry 实验笔记本语料项目", "seed": 2026081503, "question_file": "smithsonian_joseph_henry_questions_v2_draft.json"},
}


def _preflight(key: str, *, summary_path: Path | None = None, reserved_output: Path | None = None) -> PreflightResult:
    return confirmatory_preflight(
        [key],
        root=ROOT,
        freeze_manifest_path=FREEZE_MANIFEST,
        runs_dir=RUNS_DIR,
        summary_path=summary_path,
        reserved_output=reserved_output,
    )


def verify_live_snapshot(api: "ApiClient", project_id: int, expected: dict[str, str], key: str) -> None:
    if set(expected) != {"corpus_snapshot_hash", "graph_snapshot_hash"}:
        raise PreflightError(f"live snapshot binding is incomplete for {key}")
    status = api.get(f"/projects/{project_id}/rag/status")
    actual = status.get("corpus_snapshot") if isinstance(status, dict) else None
    if not isinstance(actual, dict) or any(actual.get(field) != value for field, value in expected.items()):
        raise PreflightError(f"live corpus/graph snapshot mismatch before API run creation for {key}")


class ApiClient:
    def __init__(self) -> None:
        self.client = httpx.Client(base_url=API_BASE, timeout=900, follow_redirects=True, trust_env=False)
        password = os.environ.get(PASSWORD_ENV)
        if not password:
            self.client.close()
            raise RuntimeError(f"{PASSWORD_ENV} must be set for a confirmatory run")
        login = self.post("/auth/login", json={"username": USERNAME, "password": password})
        self.client.headers["Authorization"] = f"Bearer {login['access_token']}"

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        if not response.is_success:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text[:500]
            raise RuntimeError(f"{method} {path} failed ({response.status_code}): {detail}")
        return response.json()

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)


def as_list(payload: Any) -> list[Any]:
    return payload.get("items", []) if isinstance(payload, dict) else payload


def find_project(api: ApiClient, name: str) -> dict[str, Any]:
    for project in as_list(api.get("/projects")):
        if project["name"] == name:
            return project
    raise RuntimeError(f"project not found: {name}")


def create_confirmatory_experiment(
    api: ApiClient,
    key: str,
    project_id: int,
    run_name: str,
    seed: int,
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Sole experiment-create entrance; no caller-owned authorization is accepted."""
    first = _preflight(key, reserved_output=output_dir)
    load_verified_questions(first, key)
    verify_live_snapshot(api, project_id, first.snapshots[key], key)
    # The second GET is deliberately before the final local revalidation. The
    # remaining GET→POST graph race needs an API-side conditional create.
    verify_live_snapshot(api, project_id, first.snapshots[key], key)
    final = _preflight(key, reserved_output=output_dir)
    questions = load_verified_questions(final, key)
    run = api.post(
        f"/projects/{project_id}/rag/experiments",
        json={
            "name": run_name,
            "questions": questions,
            "modes": list(MODES),
            "repetitions": 1,
            "randomize_order": True,
            "random_seed": seed,
            "expected_corpus_snapshot_hash": first.snapshots[key]["corpus_snapshot_hash"],
            "expected_graph_snapshot_hash": first.snapshots[key]["graph_snapshot_hash"],
        },
    )
    return run, questions


def run_project(api: ApiClient, key: str, cfg: dict[str, Any], run_name: str) -> dict[str, Any]:
    """Run one project; no caller-supplied preflight capability is accepted."""
    _preflight(key)
    run_dir = RUNS_DIR / key
    run_dir.mkdir(parents=True, exist_ok=False)
    project = find_project(api, cfg["project_name"])
    run, questions = create_confirmatory_experiment(api, key, project["id"], run_name, cfg["seed"], run_dir)
    run_id = run["id"]
    deadline = time.monotonic() + 6 * 3600
    resumes = 0
    while run.get("status") in {"queued", "running", "interrupted"}:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"run {run_id} still running")
        if run.get("status") == "interrupted":
            api.post(f"/rag/experiments/{run_id}/resume")
            resumes += 1
            time.sleep(2)
        time.sleep(3)
        run = api.get(f"/rag/experiments/{run_id}")
    try:
        evidence = api.get(f"/rag/experiments/{run_id}/evidence.json")
    except RuntimeError as exc:
        evidence = {"export_error": str(exc)}
    response = api.client.get(f"/rag/experiments/{run_id}/export.csv")
    csv_text = response.text if response.is_success else ""
    (run_dir / f"run-{run_id}-metadata.json").write_text(json.dumps({"run": run, "project": project, "questions_count": len(questions), "run_name": run_name, "seed": cfg["seed"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / f"run-{run_id}-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    if csv_text:
        (run_dir / f"run-{run_id}-export.csv").write_text(csv_text, encoding="utf-8")
    summary = {"project": key, "run_id": run_id, "status": run.get("status"), "resumes": resumes, "evidence_exported": not isinstance(evidence, dict) or "export_error" not in evidence, "csv_rows": len(csv_text.splitlines()) - 1 if csv_text else 0, "saved_to": str(run_dir)}
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> int:
    which = sys.argv[1:] or list(PROJECTS)
    unknown = sorted(set(which) - set(PROJECTS))
    if unknown:
        print(f"unknown project key: {unknown}", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    summary_path = RUNS_DIR / f"pilot-summary-{stamp}.json"
    try:
        confirmatory_preflight(which, root=ROOT, freeze_manifest_path=FREEZE_MANIFEST, runs_dir=RUNS_DIR, summary_path=summary_path)
    except (PreflightError, OSError, subprocess.SubprocessError) as exc:
        print(f"confirmatory preflight failed: {exc}", file=sys.stderr)
        return 1
    api = ApiClient()
    results = []
    for key in which:
        try:
            results.append(run_project(api, key, PROJECTS[key], f"agent-pilot-{key}-{stamp}"))
        except Exception as exc:  # noqa: BLE001
            print(f"RUN FAILED for {key}: {exc}", file=sys.stderr)
            results.append({"project": key, "error": str(exc)})
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all("error" not in result for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
