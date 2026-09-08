"""Run a read-only live validation of method-masked human review boundaries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


FORBIDDEN_MARKERS = (
    '"rag_mode"',
    '"query_log_id"',
    '"model_name"',
    '"relation_id"',
    "[G1]",
    "图谱关系",
)


def request_status(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    return response


def run_validation(base_url: str, project_id: int, evaluator_user_id: int, manager_user_id: int) -> dict:
    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.models.ai import AIQueryEvaluation
    from app.models.project import Project, ProjectMember
    from app.models.user import User

    with SessionLocal() as db:
        project = db.get(Project, project_id)
        evaluator = db.get(User, evaluator_user_id)
        manager = db.get(User, manager_user_id)
        membership = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == evaluator_user_id,
            )
            .one_or_none()
        )
        if project is None or evaluator is None or manager is None or membership is None:
            raise RuntimeError("Project, evaluator, manager or membership is missing")
        if not membership.can_read or not membership.can_evaluate or membership.can_manage:
            raise RuntimeError("Evaluator membership is not read-only method-masked review")
        if project.owner_user_id == evaluator_user_id:
            raise RuntimeError("Project owner cannot be used as an independent evaluator")
        evaluations_before = db.query(AIQueryEvaluation).count()

    evaluator_headers = {"Authorization": f"Bearer {create_access_token(str(evaluator_user_id))}"}
    manager_headers = {"Authorization": f"Bearer {create_access_token(str(manager_user_id))}"}
    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        raw_logs = request_status(
            client,
            "GET",
            f"/projects/{project_id}/rag/query-logs",
            headers=evaluator_headers,
        )
        analytics = request_status(
            client,
            "GET",
            f"/projects/{project_id}/rag/analytics",
            headers=evaluator_headers,
        )
        experiments = request_status(
            client,
            "GET",
            f"/projects/{project_id}/rag/experiments",
            headers=evaluator_headers,
        )
        query_attempt = request_status(
            client,
            "POST",
            f"/projects/{project_id}/rag/query",
            headers=evaluator_headers,
            json={"query": "只读权限检查", "mode": "project_rag"},
        )
        batches_response = request_status(
            client,
            "GET",
            f"/projects/{project_id}/rag/blind-review/batches",
            headers=evaluator_headers,
        )
        if batches_response.status_code != 200:
            raise RuntimeError(f"Blind batches failed: {batches_response.text}")
        batches = batches_response.json()
        if not batches:
            raise RuntimeError("No blind-review batches are available")
        batch = next((item for item in batches if item["total_items"] > 0), None)
        if batch is None or not re.fullmatch(r"R[A-F0-9]{12}", batch["batch_id"]):
            raise RuntimeError("No valid non-empty blind-review batch is available")
        items_response = request_status(
            client,
            "GET",
            f"/projects/{project_id}/rag/blind-review/items",
            headers=evaluator_headers,
            params={"batch_id": batch["batch_id"], "pending_only": "false"},
        )
        if items_response.status_code != 200:
            raise RuntimeError(f"Blind items failed: {items_response.text}")
        items = items_response.json()
        if len(items) != batch["total_items"]:
            raise RuntimeError("Blind item count does not match the selected batch")
        if any(set(item) != {"blind_id", "question", "answer", "evidence", "evaluation"} for item in items):
            raise RuntimeError("Blind item response contains unexpected fields")
        if any(not re.fullmatch(r"B[A-F0-9]{12}", item["blind_id"]) for item in items):
            raise RuntimeError("Blind item identifier format is invalid")
        serialized_items = json.dumps(items, ensure_ascii=False)
        leaked_markers = [marker for marker in FORBIDDEN_MARKERS if marker in serialized_items]
        if leaked_markers:
            raise RuntimeError("Blind response leaked markers: " + ", ".join(leaked_markers))

        manager_blind = request_status(
            client,
            "GET",
            f"/projects/{project_id}/rag/blind-review/batches",
            headers=manager_headers,
        )
        manager_raw = request_status(
            client,
            "GET",
            f"/projects/{project_id}/rag/query-logs",
            headers=manager_headers,
        )

    expected_statuses = {
        "evaluator_raw_logs": raw_logs.status_code,
        "evaluator_analytics": analytics.status_code,
        "evaluator_experiments": experiments.status_code,
        "evaluator_query_attempt": query_attempt.status_code,
        "evaluator_blind_batches": batches_response.status_code,
        "evaluator_blind_items": items_response.status_code,
        "manager_blind_batches": manager_blind.status_code,
        "manager_raw_logs": manager_raw.status_code,
    }
    expected = {
        "evaluator_raw_logs": 403,
        "evaluator_analytics": 403,
        "evaluator_experiments": 403,
        "evaluator_query_attempt": 403,
        "evaluator_blind_batches": 200,
        "evaluator_blind_items": 200,
        "manager_blind_batches": 403,
        "manager_raw_logs": 200,
    }
    if expected_statuses != expected:
        raise RuntimeError(f"Unexpected permission results: {expected_statuses}")

    with SessionLocal() as db:
        evaluations_after = db.query(AIQueryEvaluation).count()
    if evaluations_after != evaluations_before:
        raise RuntimeError("Read-only validation changed the human evaluation count")

    return {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "read-only method-masked review boundary; no ratings submitted",
        "project_id": project_id,
        "evaluator_user_id": evaluator_user_id,
        "manager_user_id": manager_user_id,
        "evaluator_membership": {
            "can_read": membership.can_read,
            "can_write": membership.can_write,
            "can_review": membership.can_review,
            "can_evaluate": membership.can_evaluate,
            "can_manage": membership.can_manage,
            "is_project_owner": False,
        },
        "http_statuses": expected_statuses,
        "batch_count": len(batches),
        "selected_batch_item_count": len(items),
        "leaked_markers": leaked_markers,
        "evaluation_count_before": evaluations_before,
        "evaluation_count_after": evaluations_after,
        "ratings_submitted": 0,
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--project-id", type=int, default=3)
    parser.add_argument("--evaluator-user-id", type=int, default=2)
    parser.add_argument("--manager-user-id", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/storage/validation/blind-review-runtime-2026-07-12.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_validation(
        args.base_url,
        args.project_id,
        args.evaluator_user_id,
        args.manager_user_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
