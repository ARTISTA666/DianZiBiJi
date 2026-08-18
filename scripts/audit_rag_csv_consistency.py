#!/usr/bin/env python3
"""Audit a historical RAG CSV against its rule-based evaluation sheet."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


MODES = ("project_rag", "kg_enhanced_rag")
CITATION_TOKEN_RE = re.compile(r"\[([SG])([^\]]*)\]", re.IGNORECASE)
CITATION_RE = re.compile(r"\[([SG])(\d+)\]", re.IGNORECASE)
REQUIRED_CSV_FIELDS = {
    "experiment_run_id",
    "question_index",
    "question",
    "mode",
    "status",
    "query_log_id",
    "answer",
    "source_count",
    "graph_hit_count",
    "response_ms",
    "fallback_reason",
    "sources_json",
    "graph_context_json",
    "usage_json",
    "error",
}
REQUIRED_EVALUATION_FIELDS = {
    "question_index",
    "query_log_id",
    "mode",
    "rule_based_task_completed",
    "human_reviewer_decision",
    "human_reviewer_comment",
}


def load_csv(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), set(reader.fieldnames or ())


def audit(csv_path: Path, evaluation_path: Path) -> dict[str, Any]:
    failures: list[str] = []
    rows, fields = load_csv(csv_path)
    missing = REQUIRED_CSV_FIELDS - fields
    for field in sorted(missing):
        failures.append(f"CSV field missing: {field}")

    evaluation_rows, evaluation_fields = load_csv(evaluation_path)
    for field in sorted(REQUIRED_EVALUATION_FIELDS - evaluation_fields):
        failures.append(f"evaluation field missing: {field}")

    query_log_ids: set[int] = set()
    question_modes: set[tuple[str, str]] = set()
    summary: dict[str, Any] = {
        "rows": len(rows),
        "modes": {mode: 0 for mode in MODES},
        "completed": {mode: 0 for mode in MODES},
        "fallback_count": {mode: 0 for mode in MODES},
        "source_json_valid": 0,
        "graph_json_valid": 0,
        "error_rows": 0,
        "human_review_fields_filled": 0,
        "citation_marker_rows": {mode: 0 for mode in MODES},
        "citation_marker_rate": {mode: 0.0 for mode in MODES},
        "legacy_marker_rows": {mode: 0 for mode in MODES},
        "legacy_marker_rate": {mode: 0.0 for mode in MODES},
        "citation_markers": {"S": 0, "G": 0},
    }
    for index, row in enumerate(rows, start=2):
        sources: Any = []
        graph_context: Any = []
        mode = row.get("mode", "")
        if mode not in MODES:
            failures.append(f"row {index} has unsupported mode: {mode}")
        else:
            summary["modes"][mode] += 1
        question_index = row.get("question_index", "")
        question_mode = (question_index, mode)
        if question_mode in question_modes:
            failures.append(f"duplicate question/mode pair: {question_index}/{mode}")
        question_modes.add(question_mode)
        try:
            query_log_id = int(row.get("query_log_id", ""))
            if query_log_id < 1:
                raise ValueError
        except ValueError:
            failures.append(f"row {index} query_log_id must be a positive integer")
        else:
            if query_log_id in query_log_ids:
                failures.append(f"duplicate query_log_id: {query_log_id}")
            query_log_ids.add(query_log_id)
        for field in ("source_count", "graph_hit_count", "response_ms"):
            try:
                if float(row.get(field, "")) < 0:
                    raise ValueError
            except ValueError:
                failures.append(f"row {index} {field} must be nonnegative")
        if row.get("status") == "completed":
            if mode in MODES:
                summary["completed"][mode] += 1
        elif row.get("status"):
            failures.append(f"row {index} has unsupported status: {row['status']}")
        if row.get("fallback_reason"):
            if mode in MODES:
                summary["fallback_count"][mode] += 1
        if row.get("error"):
            summary["error_rows"] += 1
        try:
            sources = json.loads(row.get("sources_json") or "[]")
            if not isinstance(sources, list):
                failures.append(f"row {index} sources_json must be an array")
            elif int(float(row.get("source_count", "-1"))) != len(sources):
                failures.append(f"row {index} source_count does not match sources_json length")
            summary["source_json_valid"] += 1
        except json.JSONDecodeError:
            failures.append(f"row {index} sources_json is invalid JSON")
        except ValueError:
            pass
        try:
            graph_context = json.loads(row.get("graph_context_json") or "[]")
            if not isinstance(graph_context, list):
                failures.append(f"row {index} graph_context_json must be an array")
            elif int(float(row.get("graph_hit_count", "-1"))) != len(graph_context):
                failures.append(f"row {index} graph_hit_count does not match graph_context_json length")
        except json.JSONDecodeError:
            failures.append(f"row {index} graph_context_json is invalid JSON")
        except ValueError:
            pass
        else:
            summary["graph_json_valid"] += 1
        answer = row.get("answer") or ""
        citation_tokens = list(CITATION_TOKEN_RE.finditer(answer))
        markers = [(kind.upper(), value) for kind, value in CITATION_RE.findall(answer)]
        for token in citation_tokens:
            if not CITATION_RE.fullmatch(token.group(0)):
                failures.append(f"row {index} citation syntax invalid: {token.group(0)}")
        if markers and mode in MODES:
            summary["citation_marker_rows"][mode] += 1
        for kind, value in markers:
            kind = kind.upper()
            number = int(value)
            limit = len(sources) if kind == "S" and isinstance(sources, list) else len(graph_context) if kind == "G" and isinstance(graph_context, list) else 0
            if number < 1 or number > limit:
                failures.append(f"row {index} citation index out of range: [{kind}{number}] (limit {limit})")
            summary["citation_markers"][kind] += 1
        if mode == "project_rag" and any(kind == "G" for kind, _ in markers):
            failures.append(f"row {index} project_rag answer contains graph citation")
        if mode in MODES and ("[S" in answer or "[G" in answer):
            summary["legacy_marker_rows"][mode] += 1

    csv_keys = {(row.get("question_index", ""), row.get("mode", ""), row.get("query_log_id", "")) for row in rows}
    evaluation_keys = {(row.get("question_index", ""), row.get("mode", ""), row.get("query_log_id", "")) for row in evaluation_rows}
    if csv_keys != evaluation_keys:
        failures.append("evaluation sheet keys do not match CSV keys")
    for row in evaluation_rows:
        if row.get("human_reviewer_decision", "").strip() or row.get("human_reviewer_comment", "").strip():
            summary["human_review_fields_filled"] += 1
    for mode in MODES:
        total = summary["modes"][mode]
        summary["citation_marker_rate"][mode] = (
            summary["citation_marker_rows"][mode] / total if total else 0.0
        )
        summary["legacy_marker_rate"][mode] = (
            summary["legacy_marker_rows"][mode] / total if total else 0.0
        )

    result = {
        "passed": not failures,
        "csv": str(csv_path),
        "evaluation": str(evaluation_path),
        "failures": failures,
        "summary": summary,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.csv, args.evaluation)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
