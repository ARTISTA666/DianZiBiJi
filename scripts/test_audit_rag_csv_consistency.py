from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_rag_csv_consistency.py"
SPEC = importlib.util.spec_from_file_location("audit_rag_csv_consistency", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    csv_path = tmp_path / "run.csv"
    evaluation_path = tmp_path / "evaluation.csv"
    fields = [
        "experiment_run_id", "question_index", "question", "mode", "status",
        "query_log_id", "answer", "source_count", "graph_hit_count", "response_ms",
        "fallback_reason", "sources_json", "graph_context_json", "usage_json", "error",
    ]
    rows = []
    for index, mode in enumerate(("project_rag", "kg_enhanced_rag"), start=1):
        rows.append({
            "experiment_run_id": "4", "question_index": "1", "question": "Q1",
            "mode": mode, "status": "completed", "query_log_id": str(100 + index),
            "answer": "answer", "source_count": "0", "graph_hit_count": "0",
            "response_ms": "100", "fallback_reason": "" if mode == "project_rag" else "fallback",
            "sources_json": "[]", "graph_context_json": "[]",
            "usage_json": json.dumps({"total_tokens": 10}), "error": "",
        })
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with evaluation_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["question_index", "query_log_id", "mode", "rule_based_task_completed", "human_reviewer_decision", "human_reviewer_comment"])
        writer.writeheader()
        writer.writerows({
            "question_index": row["question_index"], "query_log_id": row["query_log_id"],
            "mode": row["mode"], "rule_based_task_completed": "false",
            "human_reviewer_decision": "", "human_reviewer_comment": "",
        } for row in rows)
    return csv_path, evaluation_path


def test_matching_csv_and_evaluation_pass(tmp_path: Path) -> None:
    csv_path, evaluation_path = write_fixture(tmp_path)

    result = MODULE.audit(csv_path, evaluation_path)

    assert result["passed"] is True
    assert result["summary"]["rows"] == 2
    assert result["summary"]["fallback_count"]["kg_enhanced_rag"] == 1


def test_duplicate_query_log_id_fails_closed(tmp_path: Path) -> None:
    csv_path, evaluation_path = write_fixture(tmp_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    rows[1]["query_log_id"] = rows[0]["query_log_id"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    result = MODULE.audit(csv_path, evaluation_path)

    assert result["passed"] is False
    assert any("duplicate query_log_id" in failure for failure in result["failures"])


def test_filled_human_review_is_reported(tmp_path: Path) -> None:
    csv_path, evaluation_path = write_fixture(tmp_path)
    rows = list(csv.DictReader(evaluation_path.open(encoding="utf-8")))
    rows[0]["human_reviewer_decision"] = "yes"
    with evaluation_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    result = MODULE.audit(csv_path, evaluation_path)

    assert result["passed"] is True
    assert result["summary"]["human_review_fields_filled"] == 1


def test_out_of_range_citation_fails_closed(tmp_path: Path) -> None:
    csv_path, evaluation_path = write_fixture(tmp_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    rows[0]["answer"] = "事实 [S7]"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    result = MODULE.audit(csv_path, evaluation_path)

    assert result["passed"] is False
    assert any("citation index out of range" in failure for failure in result["failures"])


def test_evidence_count_mismatch_fails_closed(tmp_path: Path) -> None:
    csv_path, evaluation_path = write_fixture(tmp_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    rows[0]["source_count"] = "5"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    result = MODULE.audit(csv_path, evaluation_path)

    assert result["passed"] is False
    assert any("source_count does not match" in failure for failure in result["failures"])


def test_malformed_citation_range_fails_closed(tmp_path: Path) -> None:
    csv_path, evaluation_path = write_fixture(tmp_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    rows[0]["answer"] = "事实 [S1-S2]"
    rows[0]["source_count"] = "2"
    rows[0]["sources_json"] = "[{}, {}]"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    result = MODULE.audit(csv_path, evaluation_path)

    assert result["passed"] is False
    assert any("citation syntax invalid" in failure for failure in result["failures"])
