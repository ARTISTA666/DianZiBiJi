#!/usr/bin/env python3
"""Audit the internal five-mode RAG experiment bundle for paper evidence use."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
for _sub in ("gates", "freeze", "experiments", "data", "render", "ops", "audit"):
    _p = str(_SCRIPTS_ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import argparse
import csv
import hashlib
import itertools
import json
import math
import re
import subprocess
import statistics
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freeze_preregistration import verify_manifest
from rag_experiment_contract import (
    MODES,
    PAPER_BLOCKER_ARCHIVE_MAPPING,
    RETRIEVAL_SNAPSHOT_FIELDS,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "data/real/experiment-5/internal-five-mode-experiment-report.json"
DEFAULT_CSV = ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv"
DEFAULT_CONFIG = ROOT / "data/real/experiment-5/run-config.json"
DEFAULT_QUESTIONS = ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json"
DEFAULT_FREEZE = ROOT / "docs/experiments/rag-experiment-5-internal-freeze-manifest-v2.json"
DEFAULT_VALIDATION = ROOT / "data/real/experiment-5/internal-five-mode-validation.json"
DEFAULT_OUTPUT = ROOT / "docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json"

CITATION_TOKEN_RE = re.compile(r"\[([SG])([^\]]*)\]", re.IGNORECASE)
CITATION_RE = re.compile(r"\[([SG])(\d+)\]", re.IGNORECASE)


def normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[\s,，_*`]+", "", normalized)


def fact_matches(answer: str, fact: dict[str, Any]) -> bool:
    if fact.get("aliases"):
        return any(normalize(alias) in answer for alias in fact["aliases"])
    position_groups: list[list[tuple[int, int]]] = []
    for alternatives in fact["terms"]:
        positions: list[tuple[int, int]] = []
        for alternative in alternatives:
            needle = normalize(alternative)
            start = answer.find(needle)
            while needle and start >= 0:
                positions.append((start, start + len(needle)))
                start = answer.find(needle, start + 1)
        if not positions:
            return False
        position_groups.append(positions)
    max_span = int(fact.get("max_span", 120))
    return any(
        max(end for _, end in combination) - min(start for start, _ in combination) <= max_span
        for combination in itertools.product(*position_groups)
    )


def exact_sign_test(positive: int, negative: int) -> float:
    discordant = positive + negative
    if not discordant:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(positive, negative) + 1))
    return min(1.0, 2 * tail / (2**discordant))


def p95(values: list[int]) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _citation_marker_atoms(rows: list[dict[str, Any]], marker_kind: str | None = None) -> set[tuple[str, Any, Any, Any, str]]:
    atoms: set[tuple[str, Any, Any, Any, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        question_id = row.get("question_id", row.get("case_id"))
        repetition_index = row.get("repetition_index")
        mode = row.get("mode")
        raw_markers = row.get("markers", [])
        if not raw_markers and "marker" in row:
            raw_markers = [row["marker"]]
        if not isinstance(raw_markers, list):
            raw_markers = [raw_markers]
        for raw_marker in raw_markers:
            if isinstance(raw_marker, int) and marker_kind in {"S", "G"}:
                marker = f"[{marker_kind}{raw_marker}]"
            else:
                marker = str(raw_marker)
            match = CITATION_RE.fullmatch(marker)
            kind = match.group(1).upper() if match else marker[1:2].upper() if marker.startswith("[") else ""
            if marker_kind is not None and kind != marker_kind:
                continue
            atoms.add((kind, question_id, repetition_index, mode, marker))
    return atoms


def citation_audit_matches_report(
    recomputed_invalid_rows: list[dict[str, Any]],
    recomputed_out_of_range_rows: list[dict[str, Any]],
    report_audit: dict[str, Any],
    *,
    recomputed_all_indices_in_range: bool,
) -> bool:
    recomputed_atoms = _citation_marker_atoms(recomputed_invalid_rows) | _citation_marker_atoms(
        recomputed_out_of_range_rows
    )
    reported_atoms = _citation_marker_atoms(report_audit.get("invalid_source_marker_rows", []), "S") | _citation_marker_atoms(
        report_audit.get("invalid_graph_marker_rows", []), "G"
    )
    return (
        recomputed_atoms == reported_atoms
        and report_audit.get("all_citation_indices_in_range") == recomputed_all_indices_in_range
    )


def parse_usage(row: dict[str, str]) -> dict[str, Any]:
    try:
        value = json.loads(row.get("usage_json") or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def rounded_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, float) and isinstance(expected, (float, int)):
        return round(actual, 4) == round(float(expected), 4)
    return actual == expected


def citation_audit_summary_mismatches(
    recomputed: dict[str, Any], reported: dict[str, Any]
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    global_fields = {
        "completed_answer_count": "completed_answer_count",
        "answers_with_source_marker": "answers_with_source_marker",
        "answers_with_any_evidence_marker": "answers_with_any_evidence_marker",
        "kg_answers_with_graph_context": "kg_answers_with_graph_context",
        "kg_answers_with_graph_marker": "kg_answers_with_graph_marker",
        "strict_source_marker_answer_rate": "source_marker_answer_rate",
        "strict_evidence_marker_answer_rate": "evidence_marker_answer_rate",
        "kg_graph_marker_rate_when_context_available": "kg_graph_marker_rate_when_context_available",
        "all_strict_citation_indices_in_range": "all_citation_indices_in_range",
    }
    for recomputed_field, reported_field in global_fields.items():
        recomputed_value = recomputed.get(recomputed_field)
        reported_value = reported.get(reported_field)
        if not rounded_equal(recomputed_value, reported_value):
            mismatches.append(
                {
                    "field": reported_field,
                    "recomputed": recomputed_value,
                    "reported": reported_value,
                }
            )

    recomputed_by_mode = recomputed.get("by_mode", {})
    reported_by_mode = reported.get("by_mode", {})
    if set(recomputed_by_mode) != set(reported_by_mode):
        mismatches.append(
            {
                "field": "by_mode.keys",
                "recomputed": sorted(recomputed_by_mode),
                "reported": sorted(reported_by_mode),
            }
        )
    mode_fields = {
        "completed": "completed",
        "with_source_marker": "with_source_marker",
        "with_graph_marker": "with_graph_marker",
        "with_any_evidence_marker": "with_any_evidence_marker",
        "invalid_marker_rows": "invalid_marker_rows",
        "invalid_source_marker_rows": "invalid_source_marker_rows",
        "invalid_graph_marker_rows": "invalid_graph_marker_rows",
        "source_marker_answer_rate": "source_marker_answer_rate",
        "graph_marker_answer_rate": "graph_marker_answer_rate",
        "evidence_marker_answer_rate": "evidence_marker_answer_rate",
    }
    for mode in sorted(set(recomputed_by_mode) | set(reported_by_mode)):
        recomputed_values = recomputed_by_mode.get(mode, {})
        reported_values = reported_by_mode.get(mode, {})
        for recomputed_field, reported_field in mode_fields.items():
            recomputed_value = recomputed_values.get(recomputed_field)
            if recomputed_field == "invalid_marker_rows":
                reported_value = sum(
                    int(reported_values.get(field, 0) or 0)
                    for field in ("invalid_source_marker_rows", "invalid_graph_marker_rows")
                )
            else:
                reported_value = reported_values.get(reported_field)
            if not rounded_equal(recomputed_value, reported_value):
                mismatches.append(
                    {
                        "mode": mode,
                        "field": reported_field,
                        "recomputed": recomputed_value,
                        "reported": reported_value,
                    }
                )
    return mismatches


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_or_string(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    *,
    severity: str = "required",
    actual: Any = None,
    expected: Any = True,
) -> None:
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "severity": severity,
            "actual": actual,
            "expected": expected,
        }
    )


def retrieval_gap_summary_violations(
    gaps: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return deterministic violations for method-scoped retrieval gap summaries."""
    violations: list[dict[str, Any]] = []
    if not isinstance(gaps, dict):
        return [{"kind": "summary_not_object"}]
    for mode in MODES:
        gap = gaps.get(mode)
        fields = RETRIEVAL_SNAPSHOT_FIELDS[mode]
        if not isinstance(gap, dict):
            violations.append({"kind": "mode_summary_not_object", "mode": mode})
            continue
        required_fields = gap.get("required_fields")
        if tuple(required_fields or ()) != fields:
            violations.append(
                {
                    "kind": "required_fields_mismatch",
                    "mode": mode,
                    "expected": list(fields),
                    "actual": required_fields,
                }
            )
        row_count = gap.get("row_count")
        complete = gap.get("rows_with_complete_snapshot")
        any_gap = gap.get("rows_with_any_gap")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (row_count, complete, any_gap)
        ):
            violations.append({"kind": "row_count_invalid", "mode": mode})
            continue
        if complete + any_gap != row_count:
            violations.append(
                {
                    "kind": "row_partition",
                    "mode": mode,
                    "row_count": row_count,
                    "complete": complete,
                    "any_gap": any_gap,
                }
            )
        for count_name in ("missing_by_field", "mismatch_by_field"):
            counts = gap.get(count_name)
            if not isinstance(counts, dict) or set(counts) != set(fields):
                violations.append(
                    {
                        "kind": "field_keys_mismatch",
                        "mode": mode,
                        "count_name": count_name,
                        "expected": list(fields),
                        "actual": sorted(counts) if isinstance(counts, dict) else counts,
                    }
                )
                continue
            for field in fields:
                count = counts[field]
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    violations.append(
                        {"kind": "field_count_invalid", "mode": mode, "field": field, "count_name": count_name}
                    )
                    continue
                if count > row_count:
                    violations.append(
                        {
                            "kind": "field_count_exceeds_row_count",
                            "mode": mode,
                            "field": field,
                            "count_name": count_name,
                            "count": count,
                            "row_count": row_count,
                        }
                    )
                if count > any_gap:
                    violations.append(
                        {
                            "kind": "field_count_exceeds_any_gap_rows",
                            "mode": mode,
                            "field": field,
                            "count_name": count_name,
                            "count": count,
                            "any_gap": any_gap,
                        }
                    )
    return violations


def git_metadata(root: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def audit_bundle(
    report_path: Path,
    csv_path: Path,
    config_path: Path,
    questions_path: Path,
    freeze_path: Path,
    root: Path = ROOT,
    validation_path: Path = DEFAULT_VALIDATION,
) -> dict[str, Any]:
    report = load_json(report_path)
    config = load_json(config_path)
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    if not isinstance(questions, list):
        raise ValueError("question set must be an array")
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    validation = load_json(validation_path) if validation_path.is_file() else {}

    checks: list[dict[str, Any]] = []
    report_freeze = report.get("question_set_freeze", {})
    question_hash = sha256_file(questions_path)
    add_check(
        checks,
        "question_set_sha256",
        question_hash == report_freeze.get("sha256"),
        actual=question_hash,
        expected=report_freeze.get("sha256"),
    )
    add_check(
        checks,
        "question_count_matches_freeze",
        len(questions) == report_freeze.get("question_count"),
        actual=len(questions),
        expected=report_freeze.get("question_count"),
    )
    selected_ids = report.get("selected_case_ids", [])
    question_ids = [item.get("id") for item in questions]
    add_check(
        checks,
        "selected_question_ids_match",
        selected_ids == question_ids,
        actual=selected_ids,
        expected=question_ids,
    )
    fact_count = sum(len(item.get("facts", [])) for item in questions)
    add_check(
        checks,
        "gold_fact_count_matches_freeze",
        fact_count == report_freeze.get("gold_relation_or_fact_count"),
        actual=fact_count,
        expected=report_freeze.get("gold_relation_or_fact_count"),
    )

    report_methods = report.get("methods", [])
    config_methods = [item.get("id") for item in config.get("methods", [])]
    method_configs = {
        item.get("id"): item for item in config.get("methods", []) if isinstance(item, dict) and item.get("id")
    }
    add_check(
        checks,
        "method_order_matches_run_config",
        report_methods == config_methods == list(MODES),
        actual=report_methods,
        expected=list(MODES),
    )
    add_check(
        checks,
        "repetition_count_matches",
        report.get("repetitions") == config.get("execution", {}).get("repetitions"),
        actual=report.get("repetitions"),
        expected=config.get("execution", {}).get("repetitions"),
    )
    add_check(
        checks,
        "random_seed_matches",
        report.get("random_seed") == config.get("execution", {}).get("random_seed"),
        actual=report.get("random_seed"),
        expected=config.get("execution", {}).get("random_seed"),
    )

    run = report.get("experiment_run", {})
    config_snapshot = run.get("config_snapshot_json", {})
    for config_section, snapshot_fields in (
        (
            "generation",
            {
                "provider": "provider",
                "model": "generation_model",
                "temperature": "generation_temperature",
                "max_tokens": "generation_max_tokens",
            },
        ),
        (
            "retrieval",
            {
                "chunk_size": "chunk_size",
                "chunk_overlap": "chunk_overlap",
                "retrieval_top_k": "retrieval_top_k",
                "collection_retrieval_top_k": "collection_retrieval_top_k",
                "vector_candidate_k": "vector_candidate_k",
                "graph_top_k": "graph_top_k",
                "graph_min_score": "graph_min_score",
            },
        ),
    ):
        for config_key, snapshot_key in snapshot_fields.items():
            actual = config.get(config_section, {}).get(config_key)
            expected = config_snapshot.get(snapshot_key)
            add_check(
                checks,
                f"{config_section}.{config_key}_matches_snapshot",
                actual == expected,
                actual=actual,
                expected=expected,
            )

    freeze_report = verify_manifest(freeze_path, root)
    add_check(
        checks,
        "input_freeze_manifest_verifies",
        freeze_report["ok"],
        actual=freeze_report["ok"],
        expected=True,
    )

    expected_repetitions = int(report.get("repetitions", 0))
    expected_rows = len(MODES) * expected_repetitions * len(selected_ids)
    keys = []
    query_log_ids: list[int] = []
    question_indices_bound = True
    question_texts_bound = True
    repetition_indices_bound = True
    methods_bound = True
    runtime_bindings_bound = True
    retrieval_bindings_bound = True
    retrieval_snapshot = dict(config_snapshot)
    retrieval_binding_gaps: dict[str, dict[str, Any]] = {
        mode: {
            "required_fields": list(RETRIEVAL_SNAPSHOT_FIELDS.get(mode, ())),
            "row_count": 0,
            "rows_with_complete_snapshot": 0,
            "rows_with_any_gap": 0,
            "missing_by_field": {field: 0 for field in RETRIEVAL_SNAPSHOT_FIELDS.get(mode, ())},
            "mismatch_by_field": {field: 0 for field in RETRIEVAL_SNAPSHOT_FIELDS.get(mode, ())},
        }
        for mode in MODES
    }
    citation_summary: dict[str, Any] = {
        "completed_answer_count": len(rows),
        "answers_with_source_marker": 0,
        "answers_with_any_evidence_marker": 0,
        "kg_answers_with_graph_context": 0,
        "kg_answers_with_graph_marker": 0,
        "invalid_marker_rows": [],
        "out_of_range_marker_rows": [],
        "reported_audit_mismatch": False,
        "reported_summary_mismatches": [],
        "by_mode": {
            mode: {
                "completed": 0,
                "with_source_marker": 0,
                "with_graph_marker": 0,
                "with_any_evidence_marker": 0,
                "invalid_marker_rows": 0,
                "invalid_source_marker_rows": 0,
                "invalid_graph_marker_rows": 0,
            }
            for mode in MODES
        },
    }
    case_results_by_key: dict[tuple[int, int, str], dict[str, Any]] = {}
    recomputed_mode_stats: dict[str, dict[str, Any]] = {
        mode: {
            "completed": 0,
            "failed": 0,
            "hit_facts": 0,
            "total_facts": 0,
            "coverage_sum": 0.0,
            "forbidden_fact_hits": 0,
            "exact_correct_cases": 0,
            "case_runs": 0,
            "source_count_sum": 0,
            "graph_hit_count_sum": 0,
            "response_ms": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for mode in MODES
    }
    source_json_valid = 0
    graph_json_valid = 0
    for row_number, row in enumerate(rows, start=2):
        try:
            question_index = int(row.get("question_index", "0"))
        except (TypeError, ValueError):
            question_index = None
            question_indices_bound = False
            add_check(
                checks,
                f"row_{row_number}_question_index_integer",
                False,
                actual=row.get("question_index"),
                expected="integer",
            )
        try:
            repetition_index = int(row.get("repetition_index", "0"))
        except (TypeError, ValueError):
            repetition_index = None
            repetition_indices_bound = False
            add_check(
                checks,
                f"row_{row_number}_repetition_index_integer",
                False,
                actual=row.get("repetition_index"),
                expected="integer",
            )
        mode = row.get("mode", "")
        mode_supported = mode in recomputed_mode_stats
        if not mode_supported:
            methods_bound = False
            runtime_bindings_bound = False
            add_check(checks, f"row_{row_number}_mode_supported", False, actual=mode, expected=list(MODES))
        else:
            method_config = method_configs.get(mode, {})
            expected_provider = config.get("generation", {}).get("provider") if method_config.get("generation") else "system"
            expected_model = config.get("generation", {}).get("model") if method_config.get("generation") else ""
            expected_prompt_version = method_config.get("prompt_version")
            for field, expected in (
                ("provider", expected_provider),
                ("model", expected_model),
                ("prompt_version", expected_prompt_version),
            ):
                matches = row.get(field, "") == expected
                if not matches:
                    runtime_bindings_bound = False
                    add_check(
                        checks,
                        f"row_{row_number}_{field}_matches",
                        False,
                        actual=row.get(field),
                        expected=expected,
                    )
            required_retrieval_fields = RETRIEVAL_SNAPSHOT_FIELDS.get(mode, ())
            missing_retrieval_fields = [
                field for field in required_retrieval_fields if row.get(field, "") == ""
            ]
            retrieval_mismatches = [
                {
                    "field": field,
                    "actual": row.get(field),
                    "expected": retrieval_snapshot.get(field),
                }
                for field in required_retrieval_fields
                if row.get(field, "") != str(retrieval_snapshot.get(field))
                and field not in missing_retrieval_fields
            ]
            retrieval_gap = retrieval_binding_gaps[mode]
            retrieval_gap["row_count"] += 1
            for field in missing_retrieval_fields:
                retrieval_gap["missing_by_field"][field] += 1
            for mismatch in retrieval_mismatches:
                retrieval_gap["mismatch_by_field"][mismatch["field"]] += 1
            if missing_retrieval_fields or retrieval_mismatches:
                retrieval_gap["rows_with_any_gap"] += 1
            else:
                retrieval_gap["rows_with_complete_snapshot"] += 1
            if missing_retrieval_fields or retrieval_mismatches:
                retrieval_bindings_bound = False
                add_check(
                    checks,
                    f"row_{row_number}_retrieval_snapshot_bound",
                    False,
                    actual={"missing": missing_retrieval_fields, "mismatches": retrieval_mismatches},
                    expected={field: retrieval_snapshot.get(field) for field in required_retrieval_fields},
                )
        question_index_valid = question_index is not None and 1 <= question_index <= len(questions)
        repetition_index_valid = repetition_index is not None and 1 <= repetition_index <= expected_repetitions
        if not question_index_valid:
            question_indices_bound = False
            question_texts_bound = False
            add_check(
                checks,
                f"row_{row_number}_question_index_bound",
                False,
                actual=question_index,
                expected=f"integer in [1, {len(questions)}]",
            )
        elif not isinstance(questions[question_index - 1], dict):
            question_texts_bound = False
            add_check(
                checks,
                f"row_{row_number}_question_text_matches",
                False,
                actual="question entry is not an object",
                expected="question entry object with exact question text",
            )
        else:
            expected_question_text = questions[question_index - 1].get("question")
            question_text_matches = isinstance(expected_question_text, str) and row.get("question") == expected_question_text
            if not question_text_matches:
                question_texts_bound = False
                add_check(
                    checks,
                    f"row_{row_number}_question_text_matches",
                    False,
                    actual=row.get("question"),
                    expected=expected_question_text,
                )
        if not repetition_index_valid:
            repetition_indices_bound = False
            add_check(
                checks,
                f"row_{row_number}_repetition_index_bound",
                False,
                actual=repetition_index,
                expected=f"integer in [1, {expected_repetitions}]",
            )
        keys.append((question_index or 0, repetition_index or 0, mode))
        try:
            query_log_id = int(row.get("query_log_id", "0"))
        except (TypeError, ValueError):
            query_log_id = 0
        query_log_ids.append(query_log_id)
        if mode_supported and question_index_valid:
            stats = recomputed_mode_stats[mode]
            question = questions[question_index - 1]
            answer = normalize(row.get("answer") or "")
            hit_facts = [fact["label"] for fact in question.get("facts", []) if fact_matches(answer, fact)]
            forbidden_facts = [fact["label"] for fact in question.get("forbidden_facts", []) if fact_matches(answer, fact)]
            total_facts = len(question.get("facts", []))
            coverage = len(hit_facts) / total_facts if total_facts else 0.0
            exact_correct = row.get("status") == "completed" and len(hit_facts) == total_facts and not forbidden_facts
            usage = parse_usage(row)
            stats["completed"] += row.get("status") == "completed"
            stats["failed"] += row.get("status") != "completed"
            stats["hit_facts"] += len(hit_facts)
            stats["total_facts"] += total_facts
            stats["coverage_sum"] += coverage
            stats["forbidden_fact_hits"] += len(forbidden_facts)
            stats["exact_correct_cases"] += exact_correct
            stats["case_runs"] += 1
            try:
                source_count = int(float(row.get("source_count", "0")))
            except (TypeError, ValueError):
                source_count = 0
            try:
                graph_hit_count = int(float(row.get("graph_hit_count", "0")))
            except (TypeError, ValueError):
                graph_hit_count = 0
            stats["source_count_sum"] += source_count
            stats["graph_hit_count_sum"] += graph_hit_count
            if row.get("status") == "completed":
                try:
                    response_ms = int(float(row.get("response_ms", "0")))
                except (TypeError, ValueError):
                    response_ms = 0
                stats["response_ms"].append(response_ms)
            stats["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            stats["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            stats["total_tokens"] += int(usage.get("total_tokens") or 0)
            case_results_by_key[(question_index, repetition_index, mode)] = {
                "fact_coverage": round(coverage, 4),
                "closed_set_exact_correct": bool(exact_correct),
                "response_ms": response_ms if row.get("status") == "completed" else 0,
            }
        try:
            sources = json.loads(row.get("sources_json") or "[]")
        except json.JSONDecodeError:
            sources = None
        try:
            graph_context = json.loads(row.get("graph_context_json") or "[]")
        except json.JSONDecodeError:
            graph_context = None
        try:
            source_count = int(float(row.get("source_count", "-1")))
        except (TypeError, ValueError):
            source_count = -1
        try:
            graph_hit_count = int(float(row.get("graph_hit_count", "-1")))
        except (TypeError, ValueError):
            graph_hit_count = -1
        if not isinstance(sources, list) or source_count != len(sources):
            add_check(
                checks,
                f"row_{row_number}_source_count_matches",
                False,
                actual=row.get("source_count"),
                expected=len(sources) if isinstance(sources, list) else "JSON list",
            )
        else:
            source_json_valid += 1
        if not isinstance(graph_context, list) or graph_hit_count != len(graph_context):
            add_check(
                checks,
                f"row_{row_number}_graph_count_matches",
                False,
                actual=row.get("graph_hit_count"),
                expected=len(graph_context) if isinstance(graph_context, list) else "JSON list",
            )
        else:
            graph_json_valid += 1
        if not isinstance(sources, list):
            sources = []
        if not isinstance(graph_context, list):
            graph_context = []
        mode_summary = citation_summary["by_mode"].get(mode)
        if mode_summary is None:
            continue
        mode_summary["completed"] += row.get("status") == "completed"
        answer = row.get("answer") or ""
        tokens = list(CITATION_TOKEN_RE.finditer(answer))
        markers = [(kind.upper(), value) for kind, value in CITATION_RE.findall(answer)]
        invalid_token_matches = [token for token in tokens if not CITATION_RE.fullmatch(token.group(0))]
        invalid_tokens = [token.group(0) for token in invalid_token_matches]
        if invalid_tokens:
            mode_summary["invalid_marker_rows"] += 1
            citation_summary["invalid_marker_rows"].append(
                {
                    "row": row_number,
                    "question_index": question_index,
                    "question_id": questions[question_index - 1].get("id") if question_index_valid else None,
                    "mode": mode,
                    "repetition_index": repetition_index,
                    "query_log_id": query_log_id,
                    "markers": invalid_tokens,
                    "source_count": len(sources),
                    "graph_hit_count": len(graph_context),
                }
            )
        if markers:
            citation_summary["answers_with_any_evidence_marker"] += 1
            mode_summary["with_any_evidence_marker"] += 1
        if any(kind == "S" for kind, _ in markers):
            citation_summary["answers_with_source_marker"] += 1
            mode_summary["with_source_marker"] += 1
        if any(kind == "G" for kind, _ in markers):
            mode_summary["with_graph_marker"] += 1
        if mode == "kg_enhanced_rag" and graph_context:
            citation_summary["kg_answers_with_graph_context"] += 1
        if mode == "kg_enhanced_rag" and any(kind == "G" for kind, _ in markers):
            citation_summary["kg_answers_with_graph_marker"] += 1
        for kind, value in markers:
            limit = len(sources) if kind == "S" else len(graph_context)
            if int(value) < 1 or int(value) > limit:
                citation_summary["out_of_range_marker_rows"].append(
                    {
                        "row": row_number,
                        "question_index": question_index,
                        "question_id": questions[question_index - 1].get("id") if question_index_valid else None,
                        "mode": mode,
                        "repetition_index": repetition_index,
                        "query_log_id": query_log_id,
                        "marker": f"[{kind}{value}]",
                        "limit": limit,
                    }
                )

    retrieval_gap_violations = retrieval_gap_summary_violations(retrieval_binding_gaps)
    run_row_checks = {
        "expected_rows": expected_rows,
        "actual_rows": len(rows),
        "unique_case_keys": len(set(keys)),
        "completed_rows": sum(row.get("status") == "completed" for row in rows),
        "failed_rows": sum(row.get("status") != "completed" for row in rows),
        "unique_positive_query_log_ids": len(query_log_ids) == len(set(query_log_ids)) and all(value > 0 for value in query_log_ids),
        "question_indices_bound": question_indices_bound,
        "question_texts_bound": question_texts_bound,
        "repetition_indices_bound": repetition_indices_bound,
        "methods_bound": methods_bound,
        "runtime_bindings_bound": runtime_bindings_bound,
        "retrieval_bindings_bound": retrieval_bindings_bound,
        "retrieval_binding_gaps": retrieval_binding_gaps,
        "retrieval_gap_summary_violations": retrieval_gap_violations,
        "case_key_domain_valid": (
            question_indices_bound
            and repetition_indices_bound
            and methods_bound
            and len(set(keys)) == expected_rows
        ),
        "source_json_valid_rows": source_json_valid,
        "graph_json_valid_rows": graph_json_valid,
    }
    run_row_checks["ok"] = (
        run_row_checks["expected_rows"] == run_row_checks["actual_rows"]
        and run_row_checks["unique_case_keys"] == expected_rows
        and run_row_checks["completed_rows"] == expected_rows
        and run_row_checks["unique_positive_query_log_ids"]
        and run_row_checks["question_indices_bound"]
        and run_row_checks["question_texts_bound"]
        and run_row_checks["repetition_indices_bound"]
        and run_row_checks["methods_bound"]
        and run_row_checks["runtime_bindings_bound"]
        and run_row_checks["retrieval_bindings_bound"]
        and not run_row_checks["retrieval_gap_summary_violations"]
        and run_row_checks["case_key_domain_valid"]
        and source_json_valid == len(rows)
        and graph_json_valid == len(rows)
    )
    add_check(checks, "csv_question_indices_bound", question_indices_bound, actual=question_indices_bound, expected=True)
    add_check(checks, "csv_question_texts_bound", question_texts_bound, actual=question_texts_bound, expected=True)
    add_check(checks, "csv_repetition_indices_bound", repetition_indices_bound, actual=repetition_indices_bound, expected=True)
    add_check(checks, "csv_methods_bound", methods_bound, actual=methods_bound, expected=True)
    add_check(checks, "csv_runtime_bindings_bound", runtime_bindings_bound, actual=runtime_bindings_bound, expected=True)
    add_check(checks, "csv_retrieval_bindings_bound", retrieval_bindings_bound, actual=retrieval_bindings_bound, expected=True)
    add_check(
        checks,
        "retrieval_gap_summary_valid",
        not retrieval_gap_violations,
        actual=retrieval_gap_violations,
        expected="canonical fields, bounded counts, and complete/any-gap partition",
    )
    add_check(
        checks,
        "csv_case_key_domain_valid",
        run_row_checks["case_key_domain_valid"],
        actual=run_row_checks["case_key_domain_valid"],
        expected=True,
    )
    add_check(checks, "csv_row_integrity", run_row_checks["ok"], actual=run_row_checks, expected="complete unique planned rows")

    recomputed_mode_summary: list[dict[str, Any]] = []
    for mode in MODES:
        stats = recomputed_mode_stats[mode]
        completed = int(stats["completed"])
        case_runs = int(stats["case_runs"])
        precision_denominator = stats["hit_facts"] + stats["forbidden_fact_hits"]
        precision = stats["hit_facts"] / precision_denominator if precision_denominator else 0.0
        recall = stats["hit_facts"] / stats["total_facts"] if stats["total_facts"] else 0.0
        recomputed_mode_summary.append(
            {
                "mode": mode,
                "completed": completed,
                "failed": int(stats["failed"]),
                "hit_facts": int(stats["hit_facts"]),
                "total_facts": int(stats["total_facts"]),
                "micro_fact_coverage": round(recall, 4),
                "macro_fact_coverage": round(stats["coverage_sum"] / case_runs, 4) if case_runs else 0.0,
                "forbidden_fact_hits": int(stats["forbidden_fact_hits"]),
                "closed_set_fact_precision": round(precision, 4),
                "closed_set_fact_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
                "closed_set_exact_correct_cases": int(stats["exact_correct_cases"]),
                "closed_set_exact_case_accuracy": round(stats["exact_correct_cases"] / case_runs, 4) if case_runs else 0.0,
                "avg_source_count": round(stats["source_count_sum"] / case_runs, 4) if case_runs else 0.0,
                "avg_graph_hit_count": round(stats["graph_hit_count_sum"] / case_runs, 4) if case_runs else 0.0,
                "mean_response_ms": round(statistics.fmean(stats["response_ms"]), 2) if stats["response_ms"] else 0.0,
                "p95_response_ms": p95(stats["response_ms"]),
                "prompt_tokens": int(stats["prompt_tokens"]),
                "completion_tokens": int(stats["completion_tokens"]),
                "total_tokens": int(stats["total_tokens"]),
            }
        )
    reported_mode_summary = report.get("objective_evaluation", {}).get("mode_summary", [])
    mode_summary_mismatch = []
    for recomputed, reported in zip(recomputed_mode_summary, reported_mode_summary, strict=False):
        for field in (
            "completed", "failed", "hit_facts", "total_facts", "micro_fact_coverage", "macro_fact_coverage",
            "forbidden_fact_hits", "closed_set_fact_precision", "closed_set_fact_f1", "closed_set_exact_correct_cases",
            "closed_set_exact_case_accuracy", "avg_source_count", "avg_graph_hit_count", "mean_response_ms",
            "p95_response_ms", "prompt_tokens", "completion_tokens", "total_tokens",
        ):
            if not rounded_equal(recomputed.get(field), reported.get(field)):
                mode_summary_mismatch.append({"mode": recomputed["mode"], "field": field, "recomputed": recomputed.get(field), "reported": reported.get(field)})
    add_check(
        checks,
        "mode_summary_recomputed_matches_report",
        not mode_summary_mismatch and len(reported_mode_summary) == len(recomputed_mode_summary),
        actual=mode_summary_mismatch,
        expected="all mode summary fields match recomputation",
    )

    reported_comparisons = report.get("objective_evaluation", {}).get("comparisons_vs_project_rag", {})
    recomputed_comparisons: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        if mode == "project_rag":
            continue
        paired = [
            (case_results_by_key[(question_index, repetition_index, mode)], case_results_by_key[(question_index, repetition_index, "project_rag")])
            for question_index in range(1, len(questions) + 1)
            for repetition_index in range(1, int(report.get("repetitions", 0)) + 1)
            if (question_index, repetition_index, mode) in case_results_by_key
            and (question_index, repetition_index, "project_rag") in case_results_by_key
        ]
        deltas = [comparison[0]["fact_coverage"] - comparison[1]["fact_coverage"] for comparison in paired]
        comparison_exact_only = sum(comparison[0]["closed_set_exact_correct"] and not comparison[1]["closed_set_exact_correct"] for comparison in paired)
        project_exact_only = sum(comparison[1]["closed_set_exact_correct"] and not comparison[0]["closed_set_exact_correct"] for comparison in paired)
        recomputed_comparisons[mode] = {
            "paired_case_count": len(paired),
            "mean_fact_coverage_delta": round(statistics.fmean(deltas), 4) if deltas else 0.0,
            "improved_cases": sum(delta > 0 for delta in deltas),
            "tied_cases": sum(delta == 0 for delta in deltas),
            "worse_cases": sum(delta < 0 for delta in deltas),
            "coverage_sign_test_two_sided_p": round(
                exact_sign_test(sum(delta > 0 for delta in deltas), sum(delta < 0 for delta in deltas)),
                6,
            ),
            "comparison_exact_only_cases": comparison_exact_only,
            "project_exact_only_cases": project_exact_only,
            "mcnemar_exact_two_sided_p": round(exact_sign_test(comparison_exact_only, project_exact_only), 6),
            "mean_response_time_delta_ms": round(statistics.fmean(comparison[0]["response_ms"] - comparison[1]["response_ms"] for comparison in paired), 2) if paired else 0.0,
        }
    comparison_mismatch = []
    for mode, recomputed in recomputed_comparisons.items():
        reported = reported_comparisons.get(mode, {})
        for field in recomputed:
            if not rounded_equal(recomputed[field], reported.get(field)):
                comparison_mismatch.append({"mode": mode, "field": field, "recomputed": recomputed[field], "reported": reported.get(field)})
    add_check(
        checks,
        "paired_comparisons_recomputed_match_report",
        not comparison_mismatch and set(reported_comparisons) == set(recomputed_comparisons),
        actual=comparison_mismatch,
        expected="paired comparison fields match recomputation",
    )

    report_audit = report.get("objective_evaluation", {}).get("citation_marker_audit", {})
    recomputed_all_indices_in_range = not (
        citation_summary["invalid_marker_rows"] or citation_summary["out_of_range_marker_rows"]
    )
    citation_summary["reported_audit_mismatch"] = not citation_audit_matches_report(
        citation_summary["invalid_marker_rows"],
        citation_summary["out_of_range_marker_rows"],
        report_audit,
        recomputed_all_indices_in_range=recomputed_all_indices_in_range,
    )
    citation_summary.update(
        {
            "strict_source_marker_answer_rate": round(
                citation_summary["answers_with_source_marker"] / len(rows), 4
            ) if rows else 0.0,
            "strict_evidence_marker_answer_rate": round(
                citation_summary["answers_with_any_evidence_marker"] / len(rows), 4
            ) if rows else 0.0,
            "kg_graph_marker_rate_when_context_available": round(
                citation_summary["kg_answers_with_graph_marker"]
                / citation_summary["kg_answers_with_graph_context"],
                4,
            ) if citation_summary["kg_answers_with_graph_context"] else 0.0,
            "all_strict_citation_indices_in_range": recomputed_all_indices_in_range,
        }
    )
    for values in citation_summary["by_mode"].values():
        completed = values["completed"]
        values.update(
            {
                "source_marker_answer_rate": round(values["with_source_marker"] / completed, 4)
                if completed
                else 0.0,
                "graph_marker_answer_rate": round(values["with_graph_marker"] / completed, 4)
                if completed
                else 0.0,
                "evidence_marker_answer_rate": round(values["with_any_evidence_marker"] / completed, 4)
                if completed
                else 0.0,
            }
        )
    invalid_by_mode = {
        mode: {
            "invalid_source_marker_rows": set(),
            "invalid_graph_marker_rows": set(),
        }
        for mode in citation_summary["by_mode"]
    }
    for failure in citation_summary["invalid_marker_rows"]:
        mode = failure["mode"]
        counts = invalid_by_mode[mode]
        identity = (
            failure["row"],
            failure["question_id"],
            failure["repetition_index"],
            failure["mode"],
        )
        kinds = {
            marker[1:2].upper()
            for marker in failure["markers"]
            if marker.startswith("[")
        }
        if "S" in kinds:
            counts["invalid_source_marker_rows"].add(identity)
        if "G" in kinds:
            counts["invalid_graph_marker_rows"].add(identity)
    for failure in citation_summary["out_of_range_marker_rows"]:
        mode = failure["mode"]
        counts = invalid_by_mode[mode]
        identity = (
            failure["row"],
            failure["question_id"],
            failure["repetition_index"],
            failure["mode"],
        )
        kind = failure["marker"][1:2].upper() if failure["marker"].startswith("[") else ""
        if kind == "S":
            counts["invalid_source_marker_rows"].add(identity)
        if kind == "G":
            counts["invalid_graph_marker_rows"].add(identity)
    for mode, counts in invalid_by_mode.items():
        citation_summary["by_mode"][mode].update(
            {field: len(identities) for field, identities in counts.items()}
        )
    citation_summary["reported_summary_mismatches"] = citation_audit_summary_mismatches(
        citation_summary, report_audit
    )
    add_check(
        checks,
        "citation_audit_recomputed_matches_report",
        report_audit.get("completed_answer_count") == citation_summary["completed_answer_count"]
        and report_audit.get("answers_with_source_marker") == citation_summary["answers_with_source_marker"]
        and report_audit.get("answers_with_any_evidence_marker") == citation_summary["answers_with_any_evidence_marker"]
        and not citation_summary["reported_audit_mismatch"]
        and not citation_summary["reported_summary_mismatches"]
        and recomputed_all_indices_in_range,
        actual={
            "recomputed": citation_summary,
            "reported": report_audit,
        },
        expected="matching strict citation audit",
    )

    add_check(
        checks,
        "report_scope_is_internal_only",
        report.get("evidence_level") == "internal development evidence; not an independent blind evaluation",
        severity="paper_blocker",
        actual=report.get("evidence_level"),
        expected="confirmatory evidence",
    )
    add_check(
        checks,
        "app_revision_is_bound",
        config_snapshot.get("app_revision") not in (None, "", "unversioned"),
        severity="paper_blocker",
        actual=config_snapshot.get("app_revision"),
        expected="versioned revision",
    )
    blocking_inputs = config.get("blocking_inputs", [])
    missing_blockers = [path for path in blocking_inputs if not (root / path).is_file()]
    add_check(
        checks,
        "external_freeze_inputs_present",
        not missing_blockers,
        severity="paper_blocker",
        actual=missing_blockers,
        expected="all blocking inputs present",
    )
    add_check(
        checks,
        "multi_project_question_set_ready",
        len(selected_ids) >= 60,
        severity="paper_blocker",
        actual={"project_count": 1, "question_count": len(selected_ids)},
        expected={"project_count": ">=3", "question_count": ">=60"},
    )
    human_fields = ("evaluation_score", "is_accurate", "is_traceable", "evaluation_comment")
    filled_human_fields = sum(bool(row.get(field, "").strip()) for row in rows for field in human_fields)
    add_check(
        checks,
        "independent_human_review_present",
        filled_human_fields > 0,
        severity="paper_blocker",
        actual={"filled_fields": filled_human_fields, "rows": len(rows)},
        expected="two independent signed reviews",
    )
    add_check(
        checks,
        "confirmatory_evidence_package_present",
        False,
        severity="paper_blocker",
        actual="internal CSV/report only",
        expected="rag-evidence-package-v1",
    )

    consistency_checks = [item for item in checks if item["severity"] == "required"]
    paper_checks = [item for item in checks if item["severity"] == "paper_blocker"]
    consistency_passed = all(item["passed"] for item in consistency_checks)
    paper_blockers = [item["name"] for item in paper_checks if not item["passed"]]
    paper_ready = consistency_passed and not paper_blockers
    paper_gate_consistent = (
        consistency_passed == all(item["passed"] for item in consistency_checks)
        and paper_ready == (consistency_passed and not paper_blockers)
        and paper_blockers == [item["name"] for item in paper_checks if not item["passed"]]
    )
    add_check(
        checks,
        "paper_gate_consistent",
        paper_gate_consistent,
        actual={
            "consistency_passed": consistency_passed,
            "paper_ready": paper_ready,
            "paper_blockers": paper_blockers,
        },
        expected="top-level paper gate fields match severity-derived checks",
    )
    failed_check_names = sorted(item["name"] for item in checks if not item["passed"])
    paper_blocker_failed_names = [
        item["name"] for item in paper_checks if not item["passed"]
    ]
    failure_summary = {
        "failed_check_count": len(failed_check_names),
        "failed_check_names": failed_check_names,
        "paper_blocker_failed_names": paper_blocker_failed_names,
        "paper_blockers_match": paper_blockers == paper_blocker_failed_names,
    }
    paper_blocker_archive_mapping = [
        {
            "check_name": check_name,
            "archive_item": archive_item,
            "requirement": requirement,
        }
        for check_name, archive_item, requirement in PAPER_BLOCKER_ARCHIVE_MAPPING
    ]
    return {
        "schema_version": "rag-internal-five-mode-bundle-audit-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "internal developer-authored automatic experiment; not independent confirmation",
        "inputs": {
            "report": relative_or_string(report_path, root),
            "csv": relative_or_string(csv_path, root),
            "run_config": relative_or_string(config_path, root),
            "questions": relative_or_string(questions_path, root),
            "freeze_manifest": relative_or_string(freeze_path, root),
            "validation": relative_or_string(validation_path, root),
        },
        "git": git_metadata(root),
        "consistency_passed": consistency_passed,
        "paper_ready": paper_ready,
        "paper_blockers": paper_blockers,
        "failure_summary": failure_summary,
        "paper_blocker_archive_mapping": paper_blocker_archive_mapping,
        "row_integrity": run_row_checks,
        "citation_audit": citation_summary,
        "recomputed_mode_summary": recomputed_mode_summary,
        "recomputed_comparisons_vs_project_rag": recomputed_comparisons,
        "validation_snapshot": {
            "present": bool(validation),
            "path": relative_or_string(validation_path, root),
            "warning_count": len(validation.get("warnings", [])) if isinstance(validation, dict) else 0,
        },
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-paper-ready", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = audit_bundle(args.report, args.csv, args.config, args.questions, args.freeze, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "consistency_passed": result["consistency_passed"],
                "paper_ready": result["paper_ready"],
                "paper_blockers": result["paper_blockers"],
            },
            ensure_ascii=False,
        )
    )
    if not result["consistency_passed"]:
        return 1
    return 0 if result["paper_ready"] or not args.require_paper_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
