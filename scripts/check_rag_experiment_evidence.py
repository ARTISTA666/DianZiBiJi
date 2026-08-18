#!/usr/bin/env python3
"""Validate the internal consistency of a RAG experiment evidence package."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rag-evidence-package-v1"
STATISTICS_SCHEMA_VERSION = "rag-evidence-statistics-v1"
STABLE_RETRIEVAL_FIELDS = (
    "embedding_model",
    "index_version",
    "graph_schema_version",
    "retrieval_strategy",
    "retrieval_top_k",
    "collection_retrieval_top_k",
    "vector_candidate_k",
    "graph_top_k",
    "chunk_size",
    "chunk_overlap",
    "graph_min_score",
    "retrieval_min_score",
)
MAX_QUESTION_CHARS = 4_000
ALLOWED_MODES = {
    "pure_llm",
    "bm25_rag",
    "project_rag",
    "structured_query",
    "kg_enhanced_rag",
}
EXPERIMENT_STATUSES = {
    "queued",
    "running",
    "interrupted",
    "completed",
    "completed_with_errors",
    "failed",
}
NON_TERMINAL_STATUSES = {"queued", "running"}
SHA256_HEX_LENGTH = 64
RUN_FAILURE_CODES = {"creator_user_missing", "input_binding_drift", "worker_error"}
CASE_FAILURE_CODES = {"query_error"}
_CITATION_MARKER_RE = re.compile(r"(?i)\[([SG])([^\]]*)\]")
_VALID_SOURCE_MARKER_RE = re.compile(r"(?i)\[S\d+\]")
_VALID_GRAPH_MARKER_RE = re.compile(r"(?i)\[G\d+\]")
_REQUIRED_CITATION_WORDS = (
    "表明",
    "显示",
    "结果",
    "提高",
    "降低",
    "显著",
    "因此",
    "结论",
    "为",
    "是",
)


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _finite_nonnegative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value >= 0
    )


def execution_plan_sha256(plan: list[Any]) -> str:
    encoded = json.dumps(plan, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def questions_sha256(questions: list[Any]) -> str:
    encoded = json.dumps(questions, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _has_syntactic_marker(answer: str, kind: str) -> bool:
    pattern = _VALID_SOURCE_MARKER_RE if kind == "S" else _VALID_GRAPH_MARKER_RE
    return pattern.search(answer) is not None


def _paragraph_requires_citation(paragraph: str) -> bool:
    has_measurement = any(character.isascii() and character.isdigit() for character in paragraph)
    has_claim_word = any(word in paragraph for word in _REQUIRED_CITATION_WORDS)
    return len(paragraph) >= 8 and (has_measurement or has_claim_word)


def is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == SHA256_HEX_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def rust_value_display(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def citation_audit_snapshot(
    answer: str, source_count: int, graph_count: int
) -> tuple[int, list[str], bool, bool]:
    citations = list(_CITATION_MARKER_RE.finditer(answer))
    invalid_citations: list[str] = []
    for citation in citations:
        kind = citation.group(1).upper()
        raw_index = citation.group(2)
        index = (
            int(raw_index)
            if raw_index and all("0" <= character <= "9" for character in raw_index)
            else None
        )
        limit = source_count if kind == "S" else graph_count
        if index is None or not 1 <= index <= limit:
            invalid_citations.append(f"[{kind}{raw_index}]")
    has_evidence = source_count > 0 or graph_count > 0
    passed = not invalid_citations and (bool(citations) or not has_evidence)
    if has_evidence:
        if source_count > 0 and not _has_syntactic_marker(answer, "S"):
            passed = False
        if graph_count > 0 and not _has_syntactic_marker(answer, "G"):
            passed = False
        uncited_key_facts = sum(
            1
            for paragraph in (part.strip() for part in answer.split("\n\n"))
            if _paragraph_requires_citation(paragraph)
            and not _has_syntactic_marker(paragraph, "S")
            and not _has_syntactic_marker(paragraph, "G")
        )
        if uncited_key_facts > 0:
            passed = False
    return len(citations), invalid_citations, has_evidence, passed


def validate_case_citation_audit(
    case: dict[str, Any], order: Any, failures: list[str]
) -> None:
    answer = case.get("answer")
    audit = case.get("citation_audit")
    if not isinstance(answer, str):
        return
    if not isinstance(audit, dict):
        failures.append(f"case {order} citation_audit must be an object")
        return
    sources = case.get("sources")
    graph_context = case.get("graph_context")
    if not isinstance(sources, list):
        failures.append(f"case {order} sources must be an array for citation audit")
        return
    if not isinstance(graph_context, list):
        failures.append(f"case {order} graph_context must be an array for citation audit")
        return
    expected_count, expected_invalid, expected_has_evidence, expected_passed = citation_audit_snapshot(
        answer, len(sources), len(graph_context)
    )
    if expected_invalid:
        failures.append(
            f"case {order} has invalid citation markers: {', '.join(expected_invalid)}"
        )
    if audit.get("citation_count") != expected_count:
        failures.append(f"case {order} citation_audit citation_count does not match answer")
    if audit.get("invalid_citations") != expected_invalid:
        failures.append(f"case {order} citation_audit invalid_citations does not match answer")
    if audit.get("has_evidence") != expected_has_evidence:
        failures.append(f"case {order} citation_audit has_evidence does not match evidence arrays")
    if audit.get("passed") != expected_passed:
        failures.append(
            f"case {order} citation_audit passed does not match recomputed answer evidence"
        )
    for field in ("passed", "has_evidence", "repair_attempted"):
        if not isinstance(audit.get(field), bool):
            failures.append(f"case {order} citation_audit.{field} must be a boolean")
    if not isinstance(audit.get("citation_count"), int) or isinstance(
        audit.get("citation_count"), bool
    ):
        failures.append(f"case {order} citation_audit.citation_count must be an integer")
    if not isinstance(audit.get("invalid_citations"), list) or any(
        not isinstance(value, str) for value in audit.get("invalid_citations", [])
    ):
        failures.append(f"case {order} citation_audit.invalid_citations must be string array")
    if not isinstance(audit.get("message"), str) or not audit["message"].strip():
        failures.append(f"case {order} citation_audit.message must be a non-empty string")


def validate_case_telemetry(case: dict[str, Any], order: Any, failures: list[str]) -> None:
    response_ms = case.get("response_ms")
    if not _nonnegative_int(response_ms):
        failures.append(f"case {order} response_ms must be a nonnegative integer")

    for field in ("provider", "prompt_version"):
        value = case.get(field)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"case {order} {field} must be a non-empty string")

    for field in ("model", "fallback_reason"):
        value = case.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            failures.append(f"case {order} {field} must be null or a non-empty string")

    for field in ("retrieval_config", "usage"):
        if not isinstance(case.get(field), dict):
            failures.append(f"case {order} {field} must be an object")


def validate_case_evidence_arrays(case: dict[str, Any], order: Any, failures: list[str]) -> None:
    for field in ("sources", "graph_context"):
        value = case.get(field)
        if not isinstance(value, list):
            failures.append(f"case {order} {field} must be an array")
        elif any(not isinstance(item, dict) for item in value):
            failures.append(f"case {order} {field} items must be objects")


def validate_case_evidence_identity(case: dict[str, Any], order: Any, failures: list[str]) -> None:
    evidence_requirements = {
        "sources": ("chunk_id", "file_id"),
        "graph_context": ("relation_id", "source_entity_id", "target_entity_id"),
    }
    for array_field, required_fields in evidence_requirements.items():
        evidence = case.get(array_field)
        if not isinstance(evidence, list):
            continue
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                continue
            for field in required_fields:
                if not _positive_int(item.get(field)):
                    failures.append(
                        f"case {order} {array_field}[{index}] {field} must be a positive integer"
                    )


def validate_case_evidence_counts(case: dict[str, Any], order: Any, failures: list[str]) -> None:
    for count_field, array_field in (
        ("source_count", "sources"),
        ("graph_hit_count", "graph_context"),
    ):
        count = case.get(count_field)
        if not _nonnegative_int(count):
            failures.append(f"case {order} {count_field} must be a nonnegative integer")
            continue
        evidence = case.get(array_field)
        if isinstance(evidence, list) and count != len(evidence):
            failures.append(
                f"case {order} {count_field} does not match {array_field} length"
            )


def validate_case_retrieval_binding(
    case: dict[str, Any],
    experiment: dict[str, Any],
    order: Any,
    failures: list[str],
) -> None:
    if case.get("query_log_id") is None:
        return
    retrieval_config = case.get("retrieval_config")
    if not isinstance(retrieval_config, dict):
        return
    for field in ("embedding_model", "index_version", "graph_schema_version"):
        expected = {
            "embedding_model": experiment.get("embedding_model"),
            "index_version": experiment.get("rag_index_version"),
            "graph_schema_version": experiment.get("graph_schema_version"),
        }[field]
        actual = retrieval_config.get(field)
        if expected is None and field == "graph_schema_version":
            continue
        if not isinstance(actual, str) or not actual.strip():
            failures.append(f"case {order} retrieval_config.{field} must be a non-empty string")
        elif isinstance(expected, str) and actual != expected:
            failures.append(f"case {order} retrieval_config.{field} does not match experiment binding")

    for field in ("retrieval_strategy",):
        value = retrieval_config.get(field)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"case {order} retrieval_config.{field} must be a non-empty string")
    for field in (
        "retrieval_top_k",
        "collection_retrieval_top_k",
        "effective_retrieval_top_k",
        "vector_candidate_k",
        "graph_top_k",
        "effective_graph_top_k",
    ):
        if not _positive_int(retrieval_config.get(field)):
            failures.append(f"case {order} retrieval_config.{field} must be a positive integer")
    if not _positive_int(retrieval_config.get("chunk_size")):
        failures.append(f"case {order} retrieval_config.chunk_size must be a positive integer")
    if not _nonnegative_int(retrieval_config.get("chunk_overlap")):
        failures.append(f"case {order} retrieval_config.chunk_overlap must be a nonnegative integer")
    for field in ("graph_min_score", "retrieval_min_score"):
        if not _finite_nonnegative_number(retrieval_config.get(field)):
            failures.append(
                f"case {order} retrieval_config.{field} must be a finite nonnegative number"
            )


def _metric_summary(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


def _unique_strings(values: list[Any]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value.strip()})


def derive_statistics(package: dict[str, Any]) -> dict[str, Any]:
    """Derive paper-facing descriptive statistics from cases only.

    This function intentionally does not infer accuracy or correctness.  It
    reports archive counts, evidence-container counts, citation-audit fields,
    latency summaries for completed cases, and the runtime bindings recorded in
    each logged case.  The output is deterministic and can be regenerated from
    the evidence package without a database or model call.
    """

    cases = package.get("cases") if isinstance(package.get("cases"), list) else []
    case_objects = [case for case in cases if isinstance(case, dict)]
    status_counts: dict[str, int] = {}
    failure_counts: dict[str, int] = {}
    mode_cases: dict[str, list[dict[str, Any]]] = {}
    source_items = 0
    graph_items = 0
    source_evidence_cases = 0
    graph_evidence_cases = 0
    audited_cases = 0
    passed_cases = 0
    invalid_marker_count = 0
    citation_count = 0
    latency_by_mode: dict[str, list[int]] = {}
    embedding_models: list[Any] = []
    index_versions: list[Any] = []
    retrieval_strategies: list[Any] = []
    parameter_snapshots: list[dict[str, Any]] = []

    for case in case_objects:
        status = case.get("status")
        if isinstance(status, str):
            status_counts[status] = status_counts.get(status, 0) + 1
        failure_code = case.get("failure_code")
        if isinstance(failure_code, str):
            failure_counts[failure_code] = failure_counts.get(failure_code, 0) + 1
        mode = case.get("mode")
        if isinstance(mode, str):
            mode_cases.setdefault(mode, []).append(case)

        sources = case.get("sources")
        graph_context = case.get("graph_context")
        source_length = len(sources) if isinstance(sources, list) else 0
        graph_length = len(graph_context) if isinstance(graph_context, list) else 0
        source_items += source_length
        graph_items += graph_length
        source_evidence_cases += int(source_length > 0)
        graph_evidence_cases += int(graph_length > 0)

        answer = case.get("answer")
        if (
            isinstance(answer, str)
            and isinstance(sources, list)
            and isinstance(graph_context, list)
        ):
            expected_count, expected_invalid, _, expected_passed = citation_audit_snapshot(
                answer, source_length, graph_length
            )
            audited_cases += 1
            passed_cases += int(expected_passed)
            invalid_marker_count += len(expected_invalid)
            citation_count += expected_count

        if status == "completed" and _nonnegative_int(case.get("response_ms")):
            latency_by_mode.setdefault(str(mode), []).append(case["response_ms"])

        retrieval_config = case.get("retrieval_config")
        if case.get("query_log_id") is not None and isinstance(retrieval_config, dict):
            embedding_models.append(retrieval_config.get("embedding_model"))
            index_versions.append(retrieval_config.get("index_version"))
            retrieval_strategies.append(retrieval_config.get("retrieval_strategy"))
            parameter_snapshots.append(
                {
                    field: retrieval_config.get(field)
                    for field in (
                        "embedding_model",
                        "index_version",
                        "retrieval_strategy",
                        "retrieval_top_k",
                        "effective_retrieval_top_k",
                        "vector_candidate_k",
                        "graph_top_k",
                        "effective_graph_top_k",
                        "graph_min_score",
                        "retrieval_min_score",
                    )
                }
            )

    unique_snapshots = sorted(
        {json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for snapshot in parameter_snapshots}
    )
    return {
        "schema_version": STATISTICS_SCHEMA_VERSION,
        "observed_case_count": len(case_objects),
        "status_counts": dict(sorted(status_counts.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
        "evidence": {
            "source_items": source_items,
            "graph_items": graph_items,
            "source_evidence_cases": source_evidence_cases,
            "graph_evidence_cases": graph_evidence_cases,
        },
        "citation_audit": {
            "audited_cases": audited_cases,
            "passed_cases": passed_cases,
            "failed_cases": audited_cases - passed_cases,
            "citation_count": citation_count,
            "invalid_marker_count": invalid_marker_count,
        },
        "modes": {
            mode: {
                "total_cases": len(mode_cases[mode]),
                "completed_cases": sum(case.get("status") == "completed" for case in mode_cases[mode]),
                "failed_cases": sum(case.get("status") == "failed" for case in mode_cases[mode]),
                "latency_ms": _metric_summary(latency_by_mode.get(mode, [])),
            }
            for mode in sorted(mode_cases)
        },
        "runtime_bindings": {
            "embedding_models": _unique_strings(embedding_models),
            "index_versions": _unique_strings(index_versions),
            "retrieval_strategies": _unique_strings(retrieval_strategies),
            "parameter_snapshots": [json.loads(value) for value in unique_snapshots],
        },
    }


def regenerated_execution_plan(protocol: dict[str, Any], questions: list[Any], modes: list[Any]) -> list[dict[str, Any]]:
    repetitions = protocol.get("repetitions")
    random_seed = protocol.get("random_seed")
    randomize_order = protocol.get("randomize_order")
    if (
        not isinstance(repetitions, int)
        or isinstance(repetitions, bool)
        or not 1 <= repetitions <= 10
        or not isinstance(random_seed, int)
        or isinstance(random_seed, bool)
        or not isinstance(randomize_order, bool)
    ):
        raise ValueError("experiment protocol is missing valid repetitions, random_seed, or randomize_order")
    if not questions:
        raise ValueError("experiment.questions must not be empty")
    if any(not isinstance(question, str) for question in questions):
        raise ValueError("experiment.questions must contain strings")
    if any(not question.strip() for question in questions):
        raise ValueError("experiment.questions must contain non-empty strings")
    if any(len(question) > MAX_QUESTION_CHARS for question in questions):
        raise ValueError(f"experiment.questions must not exceed {MAX_QUESTION_CHARS:,} characters")
    if len(set(questions)) != len(questions):
        raise ValueError("experiment.questions must not contain duplicates")
    if not modes:
        raise ValueError("experiment.modes must not be empty")
    if any(not isinstance(mode, str) for mode in modes):
        raise ValueError("experiment.modes must contain strings")
    if len(modes) > 5 or any(mode not in ALLOWED_MODES for mode in modes):
        raise ValueError("experiment.modes contains an unsupported mode")
    if len(set(modes)) != len(modes):
        raise ValueError("experiment.modes must not contain duplicates")
    plan: list[dict[str, Any]] = []
    for question_index, question in enumerate(questions, start=1):
        for repetition_index in range(1, repetitions + 1):
            for mode in modes:
                plan.append(
                    {
                        "question_index": question_index,
                        "question": question,
                        "repetition_index": repetition_index,
                        "mode": mode,
                    }
                )
    if randomize_order:
        plan.sort(
            key=lambda item: hashlib.sha256(
                f"{random_seed}:{rust_value_display(item['question_index'])}:{rust_value_display(item['repetition_index'])}:{rust_value_display(item['mode'])}:{rust_value_display(item['question'])}".encode("utf-8")
            ).digest()
        )
    for execution_order, item in enumerate(plan, start=1):
        item["execution_order"] = execution_order
    return plan


def validate(package: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if package.get("schema_version") != SCHEMA_VERSION:
        failures.append(f"schema_version must be {SCHEMA_VERSION}")

    experiment = package.get("experiment")
    config = package.get("config_snapshot")
    summary = package.get("summary")
    cases = package.get("cases")
    if not isinstance(experiment, dict):
        failures.append("experiment must be an object")
        experiment = {}
    if not isinstance(config, dict):
        failures.append("config_snapshot must be an object")
        config = {}
    if not isinstance(summary, dict):
        failures.append("summary must be an object")
        summary = {}
    if not isinstance(cases, list):
        failures.append("cases must be an array")
        cases = []

    terminal_status = experiment.get("status")
    if terminal_status not in EXPERIMENT_STATUSES:
        failures.append(f"unsupported experiment status: {terminal_status!r}")
    elif terminal_status in NON_TERMINAL_STATUSES:
        failures.append(f"non-terminal experiment status cannot be archived: {terminal_status}")

    totals = {}
    for key in ("total_cases", "completed_cases", "failed_cases"):
        value = experiment.get(key)
        if not _nonnegative_int(value):
            failures.append(f"experiment.{key} must be a nonnegative integer")
        else:
            totals[key] = value
    if totals.get("completed_cases", 0) + totals.get("failed_cases", 0) != package.get(
        "case_count"
    ):
        failures.append("experiment completed/failed counts do not match case_count")
    if not _nonnegative_int(package.get("case_count")):
        failures.append("case_count must be a nonnegative integer")
    elif package["case_count"] != len(cases):
        failures.append("case_count does not match cases length")
    if (
        _nonnegative_int(package.get("case_count"))
        and _nonnegative_int(experiment.get("total_cases"))
        and package["case_count"] > experiment["total_cases"]
    ):
        failures.append("case_count cannot exceed experiment.total_cases")
    if experiment.get("status") in {"completed", "completed_with_errors"}:
        if package.get("case_count") != experiment.get("total_cases"):
            failures.append("completed experiment must include every planned case")

    protocol = config.get("experiment_protocol")
    if not isinstance(protocol, dict):
        failures.append("config_snapshot.experiment_protocol must be an object")
        protocol = {}
    for key in (
        "repetitions",
        "randomize_order",
        "random_seed",
        "execution_plan_hash",
    ):
        if experiment.get(key) != protocol.get(key):
            failures.append(f"{key} does not match config_snapshot.experiment_protocol")

    questions = experiment.get("questions")
    modes = experiment.get("modes")
    if not isinstance(questions, list):
        failures.append("experiment.questions must be an array")
        questions = []
    if not isinstance(modes, list):
        failures.append("experiment.modes must be an array")
        modes = []

    for key in ("questions_sha256", "corpus_snapshot_hash", "rag_index_version"):
        if experiment.get(key) != config.get(key):
            failures.append(f"{key} does not match config_snapshot")
    if "graph_schema_version" in config or experiment.get("graph_schema_version") is not None:
        if experiment.get("graph_schema_version") != config.get("graph_schema_version"):
            failures.append("graph_schema_version does not match config_snapshot")
        for field, source in (
            ("experiment.graph_schema_version", experiment),
            ("config_snapshot.graph_schema_version", config),
        ):
            value = source.get("graph_schema_version")
            if not isinstance(value, str) or not value.strip():
                failures.append(f"{field} must be a non-empty string")
    for key in ("embedding_model", "generation_model"):
        expected = experiment.get(key)
        actual = config.get(key)
        if not isinstance(expected, str) or not expected.strip():
            failures.append(f"experiment.{key} must be a non-empty string")
        if not isinstance(actual, str) or not actual.strip():
            failures.append(f"config_snapshot.{key} must be a non-empty string")
        elif isinstance(expected, str) and expected != actual:
            failures.append(f"{key} does not match config_snapshot")
    if not is_sha256_hex(experiment.get("questions_sha256")):
        failures.append("experiment.questions_sha256 must be a lowercase SHA-256 hex digest")
    elif questions and experiment.get("questions_sha256") != questions_sha256(questions):
        failures.append("experiment.questions_sha256 does not match experiment.questions")
    dataset_backed = any(
        isinstance(mode, str) and mode not in {"pure_llm", "structured_query"}
        for mode in modes
    )
    if dataset_backed:
        if not is_sha256_hex(experiment.get("corpus_snapshot_hash")):
            failures.append(
                "dataset-backed experiment must include a lowercase corpus_snapshot_hash"
            )
        if not isinstance(experiment.get("rag_index_version"), str) or not experiment[
            "rag_index_version"
        ].strip():
            failures.append("dataset-backed experiment must include rag_index_version")
    elif experiment.get("corpus_snapshot_hash") is not None:
        failures.append("non-dataset experiment must not claim a corpus_snapshot_hash")

    errors = summary.get("errors", [])
    if not isinstance(errors, list):
        failures.append("summary.errors must be an array")
        errors = []

    fatal_error = summary.get("fatal_error")
    if terminal_status == "failed":
        if not isinstance(fatal_error, dict):
            failures.append("failed experiment must include summary.fatal_error")
        elif not isinstance(fatal_error.get("error"), str) or not fatal_error["error"].strip():
            failures.append("summary.fatal_error.error must be a non-empty string")
        else:
            if fatal_error.get("failure_scope") != "run":
                failures.append("summary.fatal_error.failure_scope must be run")
            if fatal_error.get("failure_code") not in RUN_FAILURE_CODES:
                failures.append(
                    "summary.fatal_error.failure_code must be a registered run failure code"
                )
    elif fatal_error is not None:
        failures.append("summary.fatal_error may only be present for a failed experiment")

    expected_unexecuted = None
    if all(_nonnegative_int(totals.get(key)) for key in ("total_cases", "completed_cases", "failed_cases")):
        expected_unexecuted = (
            totals["total_cases"] - totals["completed_cases"] - totals["failed_cases"]
        )
        if expected_unexecuted < 0:
            failures.append("experiment completed/failed counts exceed total_cases")
        elif summary.get("unexecuted_cases") != expected_unexecuted:
            failures.append("summary.unexecuted_cases does not match experiment counts")

    if terminal_status == "completed":
        if experiment.get("failed_cases") != 0:
            failures.append("completed experiment must have zero failed_cases")
        if expected_unexecuted not in (None, 0):
            failures.append("completed experiment must have zero unexecuted_cases")
        if errors:
            failures.append("completed experiment must not include summary.errors")
    elif terminal_status == "completed_with_errors":
        if not _nonnegative_int(experiment.get("failed_cases")) or experiment.get("failed_cases") == 0:
            failures.append("completed_with_errors experiment must have at least one failed case")
        if expected_unexecuted not in (None, 0):
            failures.append("completed_with_errors experiment must have zero unexecuted_cases")
        if not errors:
            failures.append("completed_with_errors experiment must include summary.errors")

    plan = summary.get("execution_plan", [])
    if not isinstance(plan, list):
        failures.append("summary.execution_plan must be an array")
        plan = []
    else:
        actual_plan_hash = execution_plan_sha256(plan)
        if protocol.get("execution_plan_hash") != actual_plan_hash:
            failures.append("execution_plan_hash does not match summary.execution_plan hash")
        try:
            regenerated_plan = regenerated_execution_plan(protocol, questions, modes)
        except ValueError as error:
            failures.append(str(error))
        else:
            if plan != regenerated_plan:
                failures.append("summary.execution_plan does not match regenerated execution plan")
            if experiment.get("total_cases") != len(regenerated_plan):
                failures.append("experiment.total_cases does not match regenerated execution plan length")

    execution_orders: list[int] = []
    cases_by_order: dict[int, dict[str, Any]] = {}
    plan_by_order: dict[int, dict[str, Any]] = {}
    query_log_ids: set[int] = set()
    stable_retrieval_bindings: set[str] = set()
    for index, item in enumerate(plan):
        if not isinstance(item, dict):
            failures.append(f"summary.execution_plan[{index}] must be an object")
            continue
        order = item.get("execution_order")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            failures.append(f"summary.execution_plan[{index}] must include a positive execution_order")
        elif order in plan_by_order:
            failures.append(f"duplicate execution plan order: {order}")
        else:
            plan_by_order[order] = item
    completed_count = 0
    failed_count = 0
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            failures.append(f"cases[{index}] must be an object")
            continue
        order = case.get("execution_order")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            failures.append(f"cases[{index}].execution_order must be a positive integer")
        elif order in cases_by_order:
            failures.append(f"duplicate execution_order: {order}")
        else:
            execution_orders.append(order)
            cases_by_order[order] = case
        status = case.get("status")
        query_log_id = case.get("query_log_id")
        if query_log_id is None:
            if status != "failed":
                failures.append(f"completed case {order} must include query_log_id")
        elif not isinstance(query_log_id, int) or isinstance(query_log_id, bool) or query_log_id < 1:
            failures.append(f"case {order} query_log_id must be a positive integer or null")
        elif query_log_id in query_log_ids:
            failures.append(f"duplicate query_log_id: {query_log_id}")
        else:
            query_log_ids.add(query_log_id)
        if status == "completed":
            completed_count += 1
            if case.get("error") is not None:
                failures.append(f"completed case {order} has an error")
            if not isinstance(case.get("answer"), str) or not case["answer"].strip():
                failures.append(f"completed case {order} must include a non-empty answer")
            if case.get("failure_scope") is not None or case.get("failure_code") is not None:
                failures.append(f"completed case {order} must not include failure metadata")
        elif status == "failed":
            failed_count += 1
            if not isinstance(case.get("error"), str) or not case["error"].strip():
                failures.append(f"failed case {order} must include an error")
            if case.get("failure_scope") != "case":
                failures.append(f"failed case {order} failure_scope must be case")
            if case.get("failure_code") not in CASE_FAILURE_CODES:
                failures.append(f"failed case {order} has an unregistered failure_code")
        else:
            failures.append(f"case {order} has unsupported status")
        validate_case_evidence_arrays(case, order, failures)
        validate_case_evidence_identity(case, order, failures)
        validate_case_evidence_counts(case, order, failures)
        validate_case_telemetry(case, order, failures)
        validate_case_retrieval_binding(case, experiment, order, failures)
        retrieval_config = case.get("retrieval_config")
        if case.get("query_log_id") is not None and isinstance(retrieval_config, dict):
            stable_retrieval_bindings.add(
                json.dumps(
                    {field: retrieval_config.get(field) for field in STABLE_RETRIEVAL_FIELDS},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        if case.get("query_log_id") is not None and case.get("model") is not None:
            if case.get("model") != experiment.get("generation_model"):
                failures.append(
                    f"case {order} model does not match experiment generation_model"
                )
        validate_case_citation_audit(case, order, failures)
        if isinstance(order, int) and order in plan_by_order:
            plan_item = plan_by_order[order]
            for key in ("question_index", "question", "mode", "repetition_index"):
                if case.get(key) != plan_item.get(key):
                    failures.append(f"case {order} does not match execution plan field: {key}")
        elif isinstance(order, int):
            failures.append(f"case has no matching execution plan item: execution_order {order}")

    if execution_orders != sorted(execution_orders):
        failures.append("cases must be ordered by execution_order")
    if experiment.get("status") in {"completed", "completed_with_errors"}:
        expected_orders = list(range(1, len(cases) + 1))
        if execution_orders != expected_orders:
            failures.append("completed experiment execution_order values must be contiguous")
        if sorted(plan_by_order) != expected_orders:
            failures.append("completed experiment execution plan must be contiguous")
    if completed_count != experiment.get("completed_cases"):
        failures.append("case statuses do not match experiment.completed_cases")
    if failed_count != experiment.get("failed_cases"):
        failures.append("case statuses do not match experiment.failed_cases")
    if len(stable_retrieval_bindings) > 1:
        failures.append("logged cases do not share a stable retrieval parameter binding")

    summary_error_orders: set[int] = set()
    for index, error in enumerate(errors):
        if not isinstance(error, dict):
            failures.append(f"summary.errors[{index}] must be an object")
            continue
        order = error.get("execution_order")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            failures.append(f"summary.errors[{index}] must include a positive execution_order")
            continue
        if order in summary_error_orders:
            failures.append(f"duplicate summary error: execution_order {order}")
        summary_error_orders.add(order)
        case = cases_by_order.get(order)
        if case is None:
            failures.append(f"summary error has no matching case: execution_order {order}")
            continue
        if case.get("status") != "failed":
            failures.append(f"summary error maps to non-failed case: execution_order {order}")
        if case.get("error") != error.get("error"):
            failures.append(f"summary error does not match case error: execution_order {order}")
        if case.get("failure_scope") != error.get("failure_scope"):
            failures.append(
                f"summary error does not match case failure_scope: execution_order {order}"
            )
        if case.get("failure_code") != error.get("failure_code"):
            failures.append(
                f"summary error does not match case failure_code: execution_order {order}"
            )
        if error.get("failure_scope") != "case":
            failures.append(f"summary error failure_scope must be case: execution_order {order}")
        if error.get("failure_code") not in CASE_FAILURE_CODES:
            failures.append(
                f"summary error has an unregistered failure_code: execution_order {order}"
            )
        for key in ("question_index", "question", "mode", "repetition_index"):
            if case.get(key) != error.get(key):
                failures.append(f"summary error does not match case field: {key} at execution_order {order}")

    failed_case_orders = {
        order for order, case in cases_by_order.items() if case.get("status") == "failed"
    }
    for order in sorted(failed_case_orders - summary_error_orders):
        failures.append(f"failed case has no summary error: execution_order {order}")

    return failures


def check_file(package_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    value = json.loads(package_path.read_text(encoding="utf-8"))
    failures = validate(value) if isinstance(value, dict) else ["evidence package must be a JSON object"]
    result = {
        "passed": not failures,
        "package": str(package_path),
        "schema_version": value.get("schema_version") if isinstance(value, dict) else None,
        "case_count": value.get("case_count") if isinstance(value, dict) else None,
        "failures": failures,
        "statistics": derive_statistics(value) if isinstance(value, dict) else None,
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check_file(args.package, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
