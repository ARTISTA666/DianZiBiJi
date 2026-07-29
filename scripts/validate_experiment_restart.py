#!/usr/bin/env python3
"""Kill the isolated backend mid-experiment, then verify explicit resume."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time

import httpx


TERMINAL = {"completed", "completed_with_errors", "failed", "interrupted"}


def latest_e2e_project(projects: list[dict] | dict) -> dict:
    items = projects.get("items") if isinstance(projects, dict) else projects
    if not isinstance(items, list):
        raise RuntimeError("Invalid projects response")
    candidates = [
        item
        for item in items
        if isinstance(item, dict)
        and str(item.get("name", "")).startswith("系统级自动化测试项目")
    ]
    if not candidates:
        raise RuntimeError("No E2E project found")
    return max(candidates, key=lambda item: item["id"])


def wait_for_status(client: httpx.Client, run_id: int, wanted: set[str], timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/rag/experiments/{run_id}")
        if response.status_code == 200:
            run = response.json()
            if run["status"] in wanted:
                return run
        time.sleep(0.1)
    raise TimeoutError(f"Experiment #{run_id} did not reach {sorted(wanted)}")


def wait_for_ready(client: httpx.Client, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if client.get("/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise TimeoutError("Backend did not become ready after restart")


def write_report(report: dict, output: Path | None = None) -> str:
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if output is not None:
        output.write_text(payload + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:18000")
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--compose-project", default="eln-e2e")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    compose = ["docker", "compose", "-p", args.compose_project, "-f", str(args.compose_file)]

    with httpx.Client(base_url=args.api_base, timeout=15, trust_env=False) as client:
        login = client.post("/auth/login", json={"username": args.username, "password": args.password})
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        projects = client.get("/projects").json()
        project = latest_e2e_project(projects)
        initialized = client.post(f"/projects/{project['id']}/rag/init")
        initialized.raise_for_status()
        queued = client.post(
            f"/projects/{project['id']}/rag/experiments",
            json={
                "name": "E2E restart recovery probe",
                "questions": ["E2E_DELAY restart probe"],
                "modes": ["pure_llm"],
                "random_seed": 20260716,
            },
        )
        queued.raise_for_status()
        run_id = queued.json()["id"]
        wait_for_status(client, run_id, {"running"}, 10)

        subprocess.run([*compose, "kill", "-s", "SIGKILL", "backend"], check=True, capture_output=True, text=True)
        subprocess.run([*compose, "up", "-d", "--no-deps", "backend"], check=True, capture_output=True, text=True)
        wait_for_ready(client)
        interrupted = wait_for_status(client, run_id, {"interrupted"}, 10)
        if interrupted["summary_json"].get("unexecuted_cases") != 1:
            raise RuntimeError("Interrupted run did not retain its unexecuted case")

        resumed = client.post(f"/rag/experiments/{run_id}/resume")
        resumed.raise_for_status()
        completed = wait_for_status(client, run_id, TERMINAL - {"interrupted"}, 30)
        if completed["status"] != "completed" or completed["completed_cases"] != 1:
            raise RuntimeError(f"Resumed run did not complete: {completed}")
        print(
            write_report(
                {
                    "run_id": run_id,
                    "interrupted": True,
                    "resumed_status": completed["status"],
                },
                args.output,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
