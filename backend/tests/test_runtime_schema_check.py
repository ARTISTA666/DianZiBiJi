from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sqlalchemy import inspect

from app.core.database import Base
from app.models import *  # noqa: F403


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_runtime_schema.py"
SPEC = importlib.util.spec_from_file_location("verify_runtime_schema", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_current_models_pass_runtime_schema_check(db_engine) -> None:
    Base.metadata.create_all(bind=db_engine)

    dialect_name = db_engine.dialect.name
    report = MODULE.build_report(inspect(db_engine), dialect_name)

    assert report["ok"] is True
    assert all(item["passed"] for item in report["checks"])


class LegacyInspector:
    def get_table_names(self):
        return ["file_ocr_results", "ai_query_evaluations"]

    def get_columns(self, table_name):
        if table_name == "file_ocr_results":
            names = MODULE.OCR_COLUMNS
        else:
            names = MODULE.EVALUATION_COLUMNS
        return [{"name": name} for name in names]

    def get_unique_constraints(self, _table_name):
        return [
            {
                "name": MODULE.LEGACY_EVALUATION_UNIQUE_NAME,
                "column_names": ["query_log_id"],
            }
        ]


def test_legacy_single_reviewer_constraint_is_reported() -> None:
    report = MODULE.build_report(LegacyInspector(), "postgresql")
    by_id = {item["id"]: item for item in report["checks"]}

    assert report["ok"] is False
    assert by_id["multi_reviewer_unique_constraint_present"]["passed"] is False
    assert by_id["legacy_single_reviewer_constraint_absent"]["passed"] is False
