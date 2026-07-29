"""Verify database objects required by OCR review and multi-reviewer scoring."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


OCR_COLUMNS = {
    "id",
    "file_id",
    "project_id",
    "created_by",
    "file_hash",
    "raw_text",
    "corrected_text",
    "extraction_method",
    "character_count",
    "truncated",
    "review_status",
    "reviewed_by",
    "created_at",
    "reviewed_at",
}
EVALUATION_COLUMNS = {
    "id",
    "query_log_id",
    "evaluator_user_id",
    "score",
    "is_accurate",
    "is_traceable",
    "comment",
    "review_protocol",
    "created_at",
    "updated_at",
}
EXPECTED_EVALUATION_UNIQUE = ("query_log_id", "evaluator_user_id")
EXPECTED_EVALUATION_UNIQUE_NAME = "uq_ai_query_evaluation_log_evaluator"
LEGACY_EVALUATION_UNIQUE_NAME = "uq_ai_query_evaluation_log"


def check(check_id: str, passed: bool, detail: dict | None = None) -> dict:
    return {"id": check_id, "passed": passed, "detail": detail or {}}


def build_report(inspector, dialect_name: str) -> dict:
    tables = set(inspector.get_table_names())
    checks = [
        check("ocr_table_exists", "file_ocr_results" in tables),
        check("evaluation_table_exists", "ai_query_evaluations" in tables),
    ]

    if "file_ocr_results" in tables:
        actual_columns = {column["name"] for column in inspector.get_columns("file_ocr_results")}
        missing = sorted(OCR_COLUMNS - actual_columns)
        checks.append(check("ocr_columns_complete", not missing, {"missing_columns": missing}))

    if "ai_query_evaluations" in tables:
        actual_columns = {column["name"] for column in inspector.get_columns("ai_query_evaluations")}
        missing = sorted(EVALUATION_COLUMNS - actual_columns)
        checks.append(check("evaluation_columns_complete", not missing, {"missing_columns": missing}))

        constraints = inspector.get_unique_constraints("ai_query_evaluations")
        normalized_constraints = [
            {
                "name": constraint.get("name"),
                "columns": tuple(constraint.get("column_names") or []),
            }
            for constraint in constraints
        ]
        expected_present = any(
            constraint["name"] == EXPECTED_EVALUATION_UNIQUE_NAME
            and constraint["columns"] == EXPECTED_EVALUATION_UNIQUE
            for constraint in normalized_constraints
        )
        legacy_present = any(
            constraint["name"] == LEGACY_EVALUATION_UNIQUE_NAME
            for constraint in normalized_constraints
        )
        checks.append(
            check(
                "multi_reviewer_unique_constraint_present",
                expected_present,
                {"expected_name": EXPECTED_EVALUATION_UNIQUE_NAME},
            )
        )
        checks.append(
            check(
                "legacy_single_reviewer_constraint_absent",
                not legacy_present,
                {"legacy_name": LEGACY_EVALUATION_UNIQUE_NAME},
            )
        )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "dialect": dialect_name,
        "ok": all(item["passed"] for item in checks),
        "checks": checks,
    }


def main() -> int:
    from app.core.database import engine
    from app.models import FileOcrResult  # noqa: F401

    report = build_report(inspect(engine), engine.dialect.name)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
