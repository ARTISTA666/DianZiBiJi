#!/usr/bin/env python3
"""Evaluate retrieval-only evidence through the deployed Rust API."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from evaluate_retrieval import (
    Evidence,
    fact_ids,
    load_questions,
    normalize_match_text,
)


API_MODES = {
    "bm25": "bm25_rag",
    "hybrid_rag": "project_rag",
    "graph_enhanced_rag": "kg_enhanced_rag",
}
CORPUS_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CANONICALIZATION_VERSION = "rust-retrieval-canonical-v1"
CANONICALIZATION_PYTHON = "CPython 3.12.13"
FIXED_COVERAGE_CUTOFFS = (1, 3, 5, 10)


def _canonicalize(value: Any) -> Any:
    """Return the exact custom canonicalization used by this evaluator.

    This is a repository-defined format, not a standards-based canonicalizer. Dictionaries are sorted by their
    Unicode code-point keys; strings are NFC-normalized; JSON numbers use the
    host Python encoder's finite, shortest representation; booleans and null
    retain their JSON spellings.  NaN and infinity are rejected.
    """
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str) or not key.isascii():
                raise ValueError("canonical JSON object keys must be ASCII schema keys")
        return {
            key: _canonicalize(value[key])
            for key in sorted(value)
        }
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON rejects non-finite numbers")
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    if platform.python_implementation() != "CPython" or platform.python_version() != "3.12.13":
        raise RuntimeError(
            "rust-retrieval-canonical-v1 requires CPython 3.12.13; "
            f"got {platform.python_implementation()} {platform.python_version()}"
        )
    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


_VOLATILE_KEY_PARTS = (
    "query_log",
    "trace_id",
    "timestamp",
    "generated_at",
    "response_ms",
    "latency",
    "duration",
)


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_volatile(item)
            for key, item in value.items()
            if not any(part in key.lower() for part in _VOLATILE_KEY_PARTS)
        }
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return _canonicalize(value)


def load_and_freeze_questions(path: Path, freeze_path: Path) -> tuple[list[dict[str, Any]], str]:
    """Read, hash, and freeze the exact question bytes before API work starts."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    freeze_path.parent.mkdir(parents=True, exist_ok=True)
    freeze_path.write_bytes(raw)
    try:
        questions = load_questions(freeze_path)
    except Exception:
        freeze_path.unlink(missing_ok=True)
        raise
    return questions, digest


class EvaluationFailure(ValueError):
    """A fail-closed evaluation error with an auditable stage and values."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        error_type: str = "validation_error",
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.error_type = error_type
        self.expected = expected
        self.actual = actual


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_json(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = client.request(method, path, **kwargs)
    try:
        payload = response.json()
    except ValueError as error:
        raise EvaluationFailure(
            f"Rust API returned non-JSON {response.status_code} for {path}",
            stage=f"{method} {path}",
            error_type="api_protocol_error",
        ) from error
    if response.is_error:
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        raise EvaluationFailure(
            f"Rust API {method} {path} failed with {response.status_code}: {detail}",
            stage=f"{method} {path}",
            error_type="api_rejected_request",
            actual=payload,
        )
    if not isinstance(payload, dict):
        raise EvaluationFailure(
            f"Rust API returned a non-object for {path}",
            stage=f"{method} {path}",
            error_type="api_protocol_error",
            actual=payload,
        )
    return payload


def _require(
    condition: bool,
    message: str,
    *,
    stage: str,
    error_type: str = "validation_error",
    expected: Any = None,
    actual: Any = None,
) -> None:
    if not condition:
        raise EvaluationFailure(
            message,
            stage=stage,
            error_type=error_type,
            expected=expected,
            actual=actual,
        )


def _stable_document_id(source: dict[str, Any]) -> str:
    identity = {
        "file_hash": source["file_hash"],
        "chunk_index": source["chunk_index"],
        "content_sha256": source["content_sha256"],
    }
    return f"document:{sha256_json(identity)}"


def _stable_graph_id(relation: dict[str, Any]) -> str:
    identity = {
        "source": {
            "entity_type": relation["source_entity_type"],
            "natural_key": relation["source_natural_key"],
            "normalized_label": relation["source_normalized_label"],
        },
        "relation_type": relation["relation_type"],
        "target": {
            "entity_type": relation["target_entity_type"],
            "natural_key": relation["target_natural_key"],
            "normalized_label": relation["target_normalized_label"],
        },
        "confidence": relation["confidence"],
        "properties": relation.get("relation_properties") or {},
    }
    return f"graph:{sha256_json(identity)}"


def _fact_match_trace(
    text: str, question: dict[str, Any], rank: int, evidence_id: str
) -> list[dict[str, Any]]:
    haystack = normalize_match_text(text)
    trace: list[dict[str, Any]] = []
    for fact_id, fact in zip(fact_ids(question), question["facts"], strict=True):
        for alias in fact["aliases"]:
            normalized_alias = normalize_match_text(str(alias))
            if normalized_alias and normalized_alias in haystack:
                trace.append(
                    {
                        "fact_id": fact_id,
                        "alias": str(alias),
                        "evidence_presentation_rank": rank,
                        "evidence_id": evidence_id,
                    }
                )
                break
    return trace


def _source_evidence(source: dict[str, Any], rank: int, question: dict[str, Any]) -> tuple[str, Evidence, dict[str, Any]]:
    required = ("filename", "file_hash", "chunk_index", "content", "content_sha256")
    missing = [field for field in required if field not in source]
    _require(not missing, f"retrieval source is missing {', '.join(missing)}", stage="evidence_validation")
    content = source["content"]
    content_hash = source["content_sha256"]
    _require(isinstance(content, str), "retrieval source content must be text", stage="evidence_validation")
    _require(
        isinstance(content_hash, str) and CORPUS_SHA256_RE.fullmatch(content_hash),
        "retrieval source content_sha256 is invalid",
        stage="evidence_validation",
    )
    _require(
        hashlib.sha256(content.encode("utf-8")).hexdigest() == content_hash,
        "retrieval source content_sha256 does not match content",
        stage="evidence_validation",
    )
    _require(
        isinstance(source["file_hash"], str) and CORPUS_SHA256_RE.fullmatch(source["file_hash"]),
        "retrieval source file_hash is invalid",
        stage="evidence_validation",
    )
    _require(isinstance(source["chunk_index"], int) and not isinstance(source["chunk_index"], bool), "retrieval source chunk_index is invalid", stage="evidence_validation")
    evidence_id = _stable_document_id(source)
    trace = _fact_match_trace(content, question, rank, evidence_id)
    evidence = Evidence(evidence_id, "document_chunk", content, str(source["filename"]))
    projection = {
        "evidence_presentation_rank": rank,
        "evidence_id": evidence_id,
        "evidence_type": "document_chunk",
        "text": content,
        "text_sha256": content_hash,
        "source": str(source["filename"]),
        "file_hash": source["file_hash"],
        "chunk_index": source["chunk_index"],
        "content_sha256": content_hash,
        "vector_score": source.get("vector_score"),
        "lexical_score": source.get("lexical_score"),
        "retrieval_score": source.get("retrieval_score"),
        "match_trace": trace,
    }
    return evidence_id, evidence, projection


def _graph_evidence(relation: dict[str, Any], rank: int, question: dict[str, Any]) -> tuple[str, Evidence, dict[str, Any]]:
    required = (
        "source_entity_type",
        "source_natural_key",
        "source_normalized_label",
        "relation_type",
        "target_entity_type",
        "target_natural_key",
        "target_normalized_label",
        "confidence",
    )
    missing = [field for field in required if field not in relation]
    _require(not missing, f"graph evidence is missing {', '.join(missing)}", stage="evidence_validation")
    properties = relation.get("relation_properties") or {}
    _require(isinstance(properties, dict), "graph relation_properties must be an object", stage="evidence_validation")
    text = _graph_match_text(relation)
    evidence_id = _stable_graph_id(relation)
    trace = _fact_match_trace(text, question, rank, evidence_id)
    evidence = Evidence(
        evidence_id,
        "graph_relation",
        text,
        f"{relation.get('source_label', relation['source_normalized_label'])} -> {relation.get('target_label', relation['target_normalized_label'])}",
    )
    projection = {
        "evidence_presentation_rank": rank,
        "evidence_id": evidence_id,
        "evidence_type": "graph_relation",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source": evidence.source,
        "source_label": relation.get("source_label", relation["source_normalized_label"]),
        "relation_label": relation.get("relation_label", ""),
        "target_label": relation.get("target_label", relation["target_normalized_label"]),
        "relation_roles": list(relation.get("relation_roles") or []),
        "source_identity": {
            "entity_type": relation["source_entity_type"],
            "natural_key": relation["source_natural_key"],
            "normalized_label": relation["source_normalized_label"],
        },
        "relation_type": relation["relation_type"],
        "target_identity": {
            "entity_type": relation["target_entity_type"],
            "natural_key": relation["target_natural_key"],
            "normalized_label": relation["target_normalized_label"],
        },
        "confidence": relation["confidence"],
        "relation_properties": properties,
        "match_trace": trace,
    }
    return evidence_id, evidence, projection


def _graph_match_text(relation: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in (
            relation.get("source_label", relation["source_normalized_label"]),
            relation["relation_type"],
            relation.get("relation_label", ""),
            relation.get("target_label", relation["target_normalized_label"]),
            " ".join(str(role) for role in relation.get("relation_roles") or []),
        )
        if value
    )


def response_evidence(payload: dict[str, Any], mode: str) -> tuple[list[str], dict[str, Evidence]]:
    """Build stable IDs for a response; strict full-evidence checks happen in the snapshot builder."""
    ranking: list[str] = []
    evidence_by_id: dict[str, Evidence] = {}
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        if all(field in source for field in ("file_hash", "chunk_index", "content", "content_sha256")):
            evidence_id = _stable_document_id(source)
        else:
            # Kept only for direct legacy helper callers; evaluator paths fail closed.
            evidence_id = f"legacy:{mode}:source:{source.get('chunk_id') or source.get('file_id') or len(ranking) + 1}"
        evidence_by_id[evidence_id] = Evidence(
            evidence_id=evidence_id,
            evidence_type="document_chunk",
            text=str(source.get("content") or source.get("snippet") or ""),
            source=str(source.get("filename") or source.get("file_id") or "unknown"),
        )
        ranking.append(evidence_id)
    for relation in payload.get("graph_context", []):
        if not isinstance(relation, dict):
            continue
        if all(field in relation for field in ("source_natural_key", "source_normalized_label", "target_natural_key", "target_normalized_label", "confidence")):
            evidence_id = _stable_graph_id(relation)
        else:
            evidence_id = f"legacy:{mode}:graph:{relation.get('relation_id') or len(ranking) + 1}"
        text = " → ".join(str(relation.get(key) or "") for key in ("source_label", "relation_label", "target_label"))
        evidence_by_id[evidence_id] = Evidence(evidence_id, "graph_relation", text, f"relation:{relation.get('relation_id') or len(ranking) + 1}")
        ranking.append(evidence_id)
    return ranking, evidence_by_id


def build_evidence_snapshot(payload: dict[str, Any], mode: str, question: dict[str, Any]) -> dict[str, Any]:
    stage = "response_contract"
    for field, expected in (
        ("retrieval_only", True),
        ("generation_invoked", False),
        ("llm_query_rewrite_invoked", False),
        ("citation_repair_invoked", False),
    ):
        _require(payload.get(field) is expected, f"retrieval response violates {field}= {expected}", stage=stage)
    _require("query_log_id" not in payload, "retrieval-only response must not contain query_log_id", stage=stage)
    _require(isinstance(payload.get("effective_retrieval_config"), dict), "effective retrieval config is missing", stage=stage)
    config = payload["effective_retrieval_config"]
    for field in ("normalized_query", "bm25_expanded_query", "bm25_expanded_terms"):
        _require(field in config, f"effective retrieval config is missing {field}", stage=stage)

    ordered: list[dict[str, Any]] = []
    evidences: dict[str, Evidence] = {}
    for rank, source in enumerate(payload.get("sources", []), start=1):
        _require(isinstance(source, dict), "retrieval source is not an object", stage=stage)
        evidence_id, evidence, projection = _source_evidence(source, rank, question)
        evidences[evidence_id] = evidence
        ordered.append(projection)
    graph_offset = len(ordered)
    for index, relation in enumerate(payload.get("graph_context", []), start=1):
        _require(isinstance(relation, dict), "graph evidence is not an object", stage=stage)
        rank = graph_offset + index
        evidence_id, evidence, projection = _graph_evidence(relation, rank, question)
        evidences[evidence_id] = evidence
        ordered.append(projection)
    canonical_config = _strip_volatile(config)
    snapshot = {
        "raw_response": copy.deepcopy(payload),
        "ordered_evidence": ordered,
        "canonical_projection": {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "question_id": question["id"],
            "question": question["question"],
            "mode": mode,
            "ordered_evidence": ordered,
            "effective_retrieval_config": canonical_config,
            "snapshot": {
                key: payload[key]
                for key in (
                    "corpus_snapshot_hash",
                    "graph_snapshot_hash",
                    "corpus_chunk_count",
                    "graph_entity_count",
                    "graph_relation_count",
                )
                if key in payload
            },
        },
    }
    # Metrics are deliberately recomputed later from the persisted raw and
    # canonical material; no in-memory ranking object is an evidence source.
    return snapshot


def validate_corpus_identity(
    status: dict[str, Any],
    runtime: dict[str, Any],
    retrieval_config: dict[str, Any],
    expected_corpus_sha256: str,
    expected_chunk_count: int,
) -> dict[str, Any]:
    snapshot = status.get("corpus_snapshot")
    _require(isinstance(snapshot, dict), "Rust RAG status is missing corpus_snapshot identity", stage="identity_gate")
    required = (
        "dataset_id",
        "corpus_snapshot_hash",
        "corpus_chunk_count",
        "rag_index_version",
        "embedding_model",
        "graph_snapshot_hash",
        "graph_entity_count",
        "graph_relation_count",
    )
    missing = [field for field in required if field not in snapshot]
    _require(not missing, f"Rust RAG status is missing corpus identity field(s): {', '.join(missing)}", stage="identity_gate")
    dataset = status.get("dataset")
    _require(isinstance(dataset, dict), "Rust RAG status is missing active dataset identity", stage="identity_gate")
    dataset_id = snapshot["dataset_id"]
    _require(isinstance(dataset_id, int) and not isinstance(dataset_id, bool) and dataset_id >= 1, "Rust RAG status returned an invalid dataset id", stage="identity_gate")
    _require(dataset.get("id") == dataset_id, "Rust RAG dataset id does not match corpus snapshot identity", stage="identity_gate")

    corpus_hash = snapshot["corpus_snapshot_hash"]
    _require(isinstance(corpus_hash, str) and CORPUS_SHA256_RE.fullmatch(corpus_hash), "Rust RAG status returned an invalid corpus snapshot hash", stage="identity_gate")
    _require(isinstance(expected_corpus_sha256, str) and CORPUS_SHA256_RE.fullmatch(expected_corpus_sha256), "caller supplied an invalid corpus snapshot hash", stage="identity_gate")
    _require(corpus_hash == expected_corpus_sha256, "corpus snapshot hash does not match the Rust API", stage="identity_gate", expected=expected_corpus_sha256, actual=corpus_hash)

    chunk_count = snapshot["corpus_chunk_count"]
    _require(isinstance(chunk_count, int) and not isinstance(chunk_count, bool) and chunk_count >= 1, "Rust RAG status returned an invalid corpus chunk count", stage="identity_gate")
    _require(isinstance(expected_chunk_count, int) and not isinstance(expected_chunk_count, bool) and expected_chunk_count >= 1, "caller supplied an invalid corpus chunk count", stage="identity_gate")
    _require(chunk_count == expected_chunk_count, "corpus chunk count does not match the Rust API", stage="identity_gate", expected=expected_chunk_count, actual=chunk_count)

    graph_hash = snapshot["graph_snapshot_hash"]
    _require(isinstance(graph_hash, str) and CORPUS_SHA256_RE.fullmatch(graph_hash), "Rust RAG status returned an invalid graph snapshot hash", stage="identity_gate")
    for field in ("graph_entity_count", "graph_relation_count"):
        _require(isinstance(snapshot[field], int) and not isinstance(snapshot[field], bool) and snapshot[field] >= 0, f"Rust RAG status returned an invalid {field}", stage="identity_gate")

    index_version = snapshot["rag_index_version"]
    _require(isinstance(index_version, str) and index_version.strip(), "Rust RAG status returned an invalid RAG index version", stage="identity_gate")
    _require(index_version == retrieval_config.get("rag_index_version"), "RAG index version does not match the Rust API", stage="identity_gate")
    embedding_model = snapshot["embedding_model"]
    _require(isinstance(embedding_model, str) and embedding_model.strip(), "Rust RAG status returned an invalid embedding model", stage="identity_gate")
    _require(dataset.get("embedding_model") == embedding_model == runtime.get("embedding_model") == retrieval_config.get("embedding_model"), "Rust RAG embedding identity does not match runtime/configuration", stage="identity_gate")
    return {
        "dataset_id": dataset_id,
        "corpus_snapshot_hash": corpus_hash,
        "corpus_chunk_count": chunk_count,
        "rag_index_version": index_version,
        "embedding_model": embedding_model,
        "graph_snapshot_hash": graph_hash,
        "graph_entity_count": snapshot["graph_entity_count"],
        "graph_relation_count": snapshot["graph_relation_count"],
    }


def build_retrieval_request(question: str, api_mode: str, identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": question,
        "mode": api_mode,
        "expected_corpus_snapshot_hash": identity["corpus_snapshot_hash"],
        "expected_graph_snapshot_hash": identity["graph_snapshot_hash"],
    }


def _retrieval_snapshot_check(
    payload: dict[str, Any] | None,
    expected: dict[str, Any],
    *,
    counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = payload if isinstance(payload, dict) else {}
    expected_hashes = {
        "corpus_snapshot_hash": expected.get("corpus_snapshot_hash"),
        "graph_snapshot_hash": expected.get("graph_snapshot_hash"),
    }
    actual = {
        "corpus_snapshot_hash": response.get("actual_corpus_snapshot_hash"),
        "graph_snapshot_hash": response.get("actual_graph_snapshot_hash"),
    }
    used = {
        "corpus_snapshot_hash": response.get("used_corpus_snapshot_hash"),
        "graph_snapshot_hash": response.get("used_graph_snapshot_hash"),
    }
    return {
        "expected": expected_hashes,
        "actual": actual,
        "used": used,
        "equality": {
            "expected_actual": expected_hashes == actual,
            "expected_used": expected_hashes == used,
            "actual_used": actual == used,
        },
        "counts": counts or {
            key: response.get(key)
            for key in ("corpus_chunk_count", "graph_entity_count", "graph_relation_count")
        },
    }


def validate_retrieval_snapshot(
    payload: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    """Fail closed unless API actual and used hashes bind to this request."""
    check = _retrieval_snapshot_check(payload, expected)
    for field in (
        "actual_corpus_snapshot_hash",
        "actual_graph_snapshot_hash",
        "used_corpus_snapshot_hash",
        "used_graph_snapshot_hash",
    ):
        _require(
            field in payload,
            f"retrieval response is missing required snapshot field {field}",
            stage="retrieval_snapshot_gate",
            error_type="snapshot_protocol_error",
            expected=check["expected"],
            actual=check,
        )
        _require(
            isinstance(payload[field], str) and CORPUS_SHA256_RE.fullmatch(payload[field]),
            f"retrieval response {field} is not a valid SHA-256 hash",
            stage="retrieval_snapshot_gate",
            error_type="snapshot_protocol_error",
            expected=check["expected"],
            actual=check,
        )
    _require(
        all(check["equality"].values()),
        "retrieval response snapshot actual/used hashes do not equal expected hashes",
        stage="retrieval_snapshot_gate",
        error_type="snapshot_drift",
        expected=check["expected"],
        actual=check,
    )
    return check


def _fact_ranks(
    projection: dict[str, Any], question: dict[str, Any]
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    expected_ids = fact_ids(question)
    expected_id_set = set(expected_ids)
    ranks: dict[str, int] = {}
    for evidence in projection["ordered_evidence"]:
        for match in evidence["match_trace"]:
            _require(match["fact_id"] in expected_id_set, "trace references unknown fact", stage="offline_rebuild")
            _require(match["evidence_id"] == evidence["evidence_id"], "trace evidence ID mismatch", stage="offline_rebuild")
            _require(match["evidence_presentation_rank"] == evidence["evidence_presentation_rank"], "trace evidence rank mismatch", stage="offline_rebuild")
            ranks.setdefault(match["fact_id"], evidence["evidence_presentation_rank"])
    trace: list[dict[str, Any]] = []
    for fact_id in expected_ids:
        match_at_min_rank = next(
            (
                {
                    "fact_id": fact_id,
                    "matched_alias": match["alias"],
                    "min_evidence_presentation_rank": ranks[fact_id],
                    "stable_evidence_id": match["evidence_id"],
                }
                for evidence in projection["ordered_evidence"]
                for match in evidence["match_trace"]
                if match["fact_id"] == fact_id
                and fact_id in ranks
                and match["evidence_presentation_rank"] == ranks[fact_id]
            ),
            None,
        )
        if match_at_min_rank is None:
            trace.append(
                {
                    "fact_id": fact_id,
                    "matched_alias": None,
                    "min_evidence_presentation_rank": None,
                    "stable_evidence_id": None,
                }
            )
        else:
            trace.append(match_at_min_rank)
    return ranks, trace


def _metric_row(mode: str, question: dict[str, Any], projection: dict[str, Any]) -> dict[str, Any]:
    ranks, trace = _fact_ranks(projection, question)
    gold_count = len(fact_ids(question))
    return_limit = len(projection["ordered_evidence"])
    coverage = {
        f"GoldFactAliasHitCoverage@{cutoff}": round(
            sum(rank <= cutoff for rank in ranks.values()) / gold_count, 6
        )
        for cutoff in FIXED_COVERAGE_CUTOFFS
    }
    coverage["GoldFactAliasHitCoverage@returned_set"] = round(
        sum(rank <= return_limit for rank in ranks.values()) / gold_count, 6
    )
    first_rank = min(ranks.values(), default=None)
    coverage["first_alias_hit_rr"] = round(1.0 / first_rank, 6) if first_rank else 0.0
    dcg = sum(1.0 / math.log2(rank + 1) for rank in ranks.values())
    coverage["rank_discounted_fact_alias_coverage"] = round(dcg / gold_count, 6)
    return {
        "mode": mode,
        "question_id": question["id"],
        "Lq": return_limit,
        "returned_set_size": return_limit,
        "fact_match_trace": trace,
        **coverage,
    }


def calculate_fact_metrics(
    snapshots: list[dict[str, Any]], questions: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    question_by_id = {question["id"]: question for question in questions}
    per_query = [
        _metric_row(
            snapshot["canonical_projection"]["mode"],
            question_by_id[snapshot["canonical_projection"]["question_id"]],
            snapshot["canonical_projection"],
        )
        for snapshot in snapshots
    ]
    aggregate: list[dict[str, Any]] = []
    for mode in API_MODES:
        rows = [row for row in per_query if row["mode"] == mode]
        if not rows:
            continue
        aggregate.append(
            {
                "mode": mode,
                **{
                    key: round(sum(row[key] for row in rows) / len(rows), 6)
                    for key in (
                        "GoldFactAliasHitCoverage@1",
                        "GoldFactAliasHitCoverage@3",
                        "GoldFactAliasHitCoverage@5",
                        "GoldFactAliasHitCoverage@10",
                        "GoldFactAliasHitCoverage@returned_set",
                        "first_alias_hit_rr",
                        "rank_discounted_fact_alias_coverage",
                    )
                },
            }
        )
    return aggregate, per_query


def canonical_result_material(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonicalization_version": report["canonicalization_version"],
        "canonicalization_python": report["canonicalization_python"],
        "questions_sha256": report["questions_sha256"],
        "corpus": report["corpus"],
        "configuration": report["configuration"],
        "metric_contract": report.get("metric_contract", {}),
        "canonical_projections": [
            snapshot["canonical_projection"] for snapshot in report["evidence_snapshots"]
        ],
        "aggregate": report["aggregate"],
        "per_query": report["per_query"],
    }


def compute_result_sha256(material_path: Path) -> str:
    """Hash independently persisted canonical material, never an object graph."""
    try:
        material = json.loads(material_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationFailure(
            f"cannot read canonical result material: {error}",
            stage="result_hash_round_trip",
            error_type="canonical_material_unreadable",
        ) from error
    _require(
        isinstance(material, dict),
        "canonical result material must be a JSON object",
        stage="result_hash_round_trip",
    )
    return sha256_json(material)


def verify_result_material_hash(material_path: Path, expected_sha256: str) -> str:
    actual_sha256 = compute_result_sha256(material_path)
    _require(
        actual_sha256 == expected_sha256,
        "canonical result material tampered after it was persisted",
        stage="result_hash_round_trip",
        error_type="canonical_material_tampered",
        expected=expected_sha256,
        actual=actual_sha256,
    )
    return actual_sha256


def same_deployment_repeatability_verified(
    expected_result_sha256: str, actual_result_sha256: str
) -> bool:
    """A second-pass flag is true only for an explicit exact hash match."""
    return bool(expected_result_sha256) and expected_result_sha256 == actual_result_sha256


def _validate_persisted_projection(
    projection: dict[str, Any], question: dict[str, Any]
) -> None:
    """Rebuild the match trace from persisted text before computing metrics."""
    ranks = [evidence.get("evidence_presentation_rank") for evidence in projection["ordered_evidence"]]
    _require(
        ranks == list(range(1, len(ranks) + 1)) and len(set(ranks)) == len(ranks),
        "evidence presentation ranks must be continuous and unique",
        stage="offline_rebuild",
    )
    for evidence in projection["ordered_evidence"]:
        evidence_rank = evidence["evidence_presentation_rank"]
        if evidence["evidence_type"] == "document_chunk":
            actual_content_hash = hashlib.sha256(evidence["text"].encode("utf-8")).hexdigest()
            _require(
                actual_content_hash == evidence["content_sha256"] == evidence["text_sha256"],
                "persisted document content hash mismatch",
                stage="offline_rebuild",
            )
            _require(
                _stable_document_id(
                    {
                        "file_hash": evidence["file_hash"],
                        "chunk_index": evidence["chunk_index"],
                        "content_sha256": evidence["content_sha256"],
                    }
                ) == evidence["evidence_id"],
                "persisted document stable ID mismatch",
                stage="offline_rebuild",
            )
        else:
            graph_identity = {
                "source_entity_type": evidence["source_identity"]["entity_type"],
                "source_natural_key": evidence["source_identity"]["natural_key"],
                "source_normalized_label": evidence["source_identity"]["normalized_label"],
                "relation_type": evidence["relation_type"],
                "target_entity_type": evidence["target_identity"]["entity_type"],
                "target_natural_key": evidence["target_identity"]["natural_key"],
                "target_normalized_label": evidence["target_identity"]["normalized_label"],
                "confidence": evidence["confidence"],
                "relation_properties": evidence["relation_properties"],
            }
            _require(
                hashlib.sha256(evidence["text"].encode("utf-8")).hexdigest() == evidence["text_sha256"],
                "persisted graph match text hash mismatch",
                stage="offline_rebuild",
            )
            _require(
                _stable_graph_id(graph_identity) == evidence["evidence_id"],
                "persisted graph stable ID mismatch",
                stage="offline_rebuild",
            )
        expected_trace = _fact_match_trace(
            evidence["text"], question, evidence_rank, evidence["evidence_id"]
        )
        _require(
            evidence["match_trace"] == expected_trace,
            "persisted fact trace does not match normalized evidence text",
            stage="offline_rebuild",
            expected=expected_trace,
            actual=evidence["match_trace"],
        )
    _validate_fact_trace(_fact_ranks(projection, question)[1], question)


def _validate_fact_trace(trace: list[dict[str, Any]], question: dict[str, Any]) -> None:
    expected_ids = fact_ids(question)
    _require(
        [item.get("fact_id") for item in trace] == expected_ids,
        "fact trace must contain exactly one row per gold fact in question order",
        stage="offline_rebuild",
    )
    for item in trace:
        matched = item["matched_alias"] is not None
        _require(
            (item["min_evidence_presentation_rank"] is not None) == matched
            and (item["stable_evidence_id"] is not None) == matched,
            "unmatched fact trace fields must be null",
            stage="offline_rebuild",
        )


def _validate_persisted_snapshot(snapshot: dict[str, Any], question: dict[str, Any]) -> None:
    """Verify raw response, canonical projection, hashes, and offline trace."""
    raw = snapshot.get("raw_response")
    projection = snapshot.get("canonical_projection")
    _require(
        isinstance(raw, dict) and isinstance(projection, dict),
        "persisted snapshot is incomplete",
        stage="offline_rebuild",
    )
    rebuilt = build_evidence_snapshot(raw, projection["mode"], question)
    _require(
        rebuilt["canonical_projection"] == projection,
        "raw response and canonical projection disagree",
        stage="offline_rebuild",
    )
    _validate_persisted_projection(projection, question)


def validate_complete_batch(
    questions: list[dict[str, Any]],
    persisted_snapshots: list[dict[str, Any]],
    snapshot_checks: list[dict[str, Any]],
) -> None:
    """Apply G5B's exact question × method completeness gate."""
    expected_keys = {
        (question["id"], mode) for question in questions for mode in API_MODES
    }
    _require(
        all(
            isinstance(row, dict)
            and isinstance(row.get("run"), str)
            and isinstance(row.get("question_id"), str)
            and row.get("mode") in API_MODES
            and isinstance(row.get("expected"), dict)
            and isinstance(row.get("actual"), dict)
            and isinstance(row.get("used"), dict)
            and isinstance(row.get("equality"), dict)
            and set(row["equality"]) == {"expected_actual", "expected_used", "actual_used"}
            and all(isinstance(value, bool) for value in row["equality"].values())
            and isinstance(row.get("counts"), dict)
            and isinstance(row.get("utc"), str)
            and row.get("verdict") in {"pass", "fail"}
            for row in snapshot_checks
        ),
        "snapshot-checks rows do not match the required persisted schema",
        stage="snapshot_checks_gate",
    )
    check_keys = {(row["question_id"], row["mode"]) for row in snapshot_checks}
    _require(
        len(snapshot_checks) == len(expected_keys)
        and check_keys == expected_keys
        and all(row.get("verdict") == "pass" for row in snapshot_checks)
        and all(all(row["equality"].values()) for row in snapshot_checks),
        "snapshot-checks must be exactly one passing row per question and method",
        stage="snapshot_checks_gate",
    )
    snapshot_keys = {
        (
            item["canonical_projection"]["question_id"],
            item["canonical_projection"]["mode"],
        )
        for item in persisted_snapshots
    }
    _require(
        len(persisted_snapshots) == len(expected_keys)
        and snapshot_keys == expected_keys,
        "evidence snapshots must be exactly one per question and method",
        stage="evidence_snapshot_gate",
    )


def _append_snapshot_check(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


def _failure_payload(error: BaseException, stage: str = "evaluation") -> dict[str, Any]:
    if isinstance(error, EvaluationFailure):
        return {
            "utc": utc_now(),
            "stage": error.stage,
            "error_type": error.error_type,
            "expected": error.expected,
            "actual": error.actual,
            "message": str(error),
            "invalid": True,
        }
    return {
        "utc": utc_now(),
        "stage": stage,
        "error_type": "unexpected_error",
        "expected": None,
        "actual": None,
        "message": str(error),
        "invalid": True,
    }


def write_failure(output: Path, error: BaseException, stage: str = "evaluation") -> Path:
    path = output.parent / "failure.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_failure_payload(error, stage), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _identity_diff(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {"expected": expected.get(key), "actual": actual.get(key)}
        for key in sorted(set(expected) | set(actual))
        if expected.get(key) != actual.get(key)
    }


def _evaluate(args: argparse.Namespace) -> dict[str, Any]:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    checks_path = args.output.parent / "snapshot-checks.jsonl"
    checks_path.write_text("", encoding="utf-8")
    frozen_questions_path = args.output.parent / "questions-frozen.json"
    questions, questions_sha256 = load_and_freeze_questions(args.questions, frozen_questions_path)
    try:
        retrieval_config = json.loads(args.retrieval_config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationFailure(str(error), stage="configuration_gate") from error
    _require(isinstance(retrieval_config, dict), "--retrieval-config must contain a JSON object", stage="configuration_gate")
    for key in ("embedding_backend", "embedding_model", "embedding_dimension", "rag_index_version"):
        _require(key in retrieval_config, f"--retrieval-config must include {key}", stage="configuration_gate")

    headers = {"Authorization": f"Bearer {args.token}"}
    base_url = args.base_url.rstrip("/")
    evidence_snapshots: list[dict[str, Any]] = []
    with httpx.Client(base_url=base_url, headers=headers, timeout=args.timeout) as client:
        metrics = request_json(client, "GET", "/metrics")
        runtime = metrics.get("runtime")
        _require(isinstance(runtime, dict), "deployed Rust API did not expose runtime embedding metadata", stage="runtime_gate")
        _require(runtime.get("api_runtime") == "rust-axum", "deployed API is not identified as rust-axum", stage="runtime_gate")
        for key in ("embedding_backend", "embedding_model", "embedding_dimension"):
            _require(runtime.get(key) == retrieval_config.get(key), f"runtime {key} does not match retrieval configuration", stage="runtime_gate", expected=retrieval_config.get(key), actual=runtime.get(key))

        initial_status = request_json(client, "GET", f"/projects/{args.project_id}/rag/status")
        corpus_identity = validate_corpus_identity(initial_status, runtime, retrieval_config, args.corpus_sha256, args.corpus_chunk_count)
        for question in questions:
            question_status = request_json(client, "GET", f"/projects/{args.project_id}/rag/status")
            question_identity = validate_corpus_identity(question_status, runtime, retrieval_config, args.corpus_sha256, args.corpus_chunk_count)
            diff = _identity_diff(corpus_identity, question_identity)
            if diff:
                error = EvaluationFailure("snapshot drift before question", stage="question_snapshot_gate", error_type="snapshot_drift", expected=corpus_identity, actual=question_identity)
                for mode in API_MODES:
                    _append_snapshot_check(checks_path, {"run": args.output.stem, "question_id": question["id"], "mode": mode, "expected": corpus_identity, "actual": question_identity, "counts": {}, "utc": utc_now(), "verdict": "fail"})
                raise error
            for mode, api_mode in API_MODES.items():
                request = build_retrieval_request(question["question"], api_mode, question_identity)
                payload: dict[str, Any] | None = None
                try:
                    payload = request_json(client, "POST", f"/projects/{args.project_id}/rag/retrieve", json=request)
                    snapshot_check = validate_retrieval_snapshot(payload, question_identity)
                    for field in ("corpus_chunk_count", "graph_entity_count", "graph_relation_count"):
                        _require(payload.get(field) == question_identity[field], f"retrieval response {field} does not match expected snapshot count", stage="retrieval_snapshot_gate", error_type="snapshot_drift", expected=question_identity[field], actual=payload.get(field))
                    snapshot = build_evidence_snapshot(payload, mode, question)
                except BaseException as error:
                    check = _retrieval_snapshot_check(
                        payload,
                        question_identity,
                    )
                    check.update({"run": args.output.stem, "question_id": question["id"], "mode": mode, "utc": utc_now(), "verdict": "fail"})
                    _append_snapshot_check(checks_path, check)
                    raise
                snapshot_check["counts"] = {
                    key: payload.get(key)
                    for key in ("corpus_chunk_count", "graph_entity_count", "graph_relation_count")
                }
                snapshot_check.update({"run": args.output.stem, "question_id": question["id"], "mode": mode, "utc": utc_now(), "verdict": "pass"})
                _append_snapshot_check(checks_path, snapshot_check)
                evidence_snapshots.append(snapshot)

        final_status = request_json(client, "GET", f"/projects/{args.project_id}/rag/status")
        final_identity = validate_corpus_identity(final_status, runtime, retrieval_config, args.corpus_sha256, args.corpus_chunk_count)
        diff = _identity_diff(corpus_identity, final_identity)
        _require(not diff, "snapshot drift after evaluation batch", stage="batch_snapshot_gate", error_type="snapshot_drift", expected=corpus_identity, actual=final_identity)

    # Persist the complete raw responses and canonical projections before any
    # metric is calculated.  The next step deliberately reopens this JSON so
    # aggregate/per-query values cannot depend on an in-memory response.
    snapshots_path = args.output.parent / "evidence-snapshots.json"
    snapshots_path.write_text(
        json.dumps(evidence_snapshots, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    persisted_snapshots = json.loads(snapshots_path.read_text(encoding="utf-8"))
    _require(isinstance(persisted_snapshots, list), "persisted evidence snapshots are not a list", stage="offline_rebuild")
    offline_questions = load_questions(frozen_questions_path)
    _require(
        hashlib.sha256(frozen_questions_path.read_bytes()).hexdigest() == questions_sha256,
        "frozen question bytes changed during evaluation",
        stage="offline_rebuild",
    )
    _require(
        offline_questions == questions,
        "frozen questions do not reproduce the questions used for the API calls",
        stage="offline_rebuild",
    )
    question_by_id = {question["id"]: question for question in offline_questions}
    for snapshot in persisted_snapshots:
        _require(isinstance(snapshot, dict), "persisted evidence snapshot is not an object", stage="offline_rebuild")
        projection = snapshot["canonical_projection"]
        question = question_by_id[projection["question_id"]]
        _validate_persisted_snapshot(snapshot, question)
    aggregate, per_query = calculate_fact_metrics(persisted_snapshots, offline_questions)
    snapshot_checks = [
        json.loads(line)
        for line in checks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    validate_complete_batch(offline_questions, persisted_snapshots, snapshot_checks)
    report: dict[str, Any] = {
        "generated_at": utc_now(),
        "api_runtime": "rust-axum",
        "runtime": runtime,
        "base_url": base_url,
        "project_id": args.project_id,
        "questions_file": str(frozen_questions_path),
        "questions_source_file": str(args.questions),
        "questions_sha256": questions_sha256,
        "question_count": len(questions),
        "fact_count": sum(len(question["facts"]) for question in questions),
        "canonicalization_version": CANONICALIZATION_VERSION,
        "canonicalization_python": CANONICALIZATION_PYTHON,
        "corpus": corpus_identity,
        "configuration": retrieval_config,
        "metric_contract": {
            "primary": "GoldFactAliasHitCoverage@returned_set",
            "fixed_cutoffs": [f"GoldFactAliasHitCoverage@{cutoff}" for cutoff in FIXED_COVERAGE_CUTOFFS],
            "secondary": {
                "first_alias_hit_rr": "1 / minimum evidence_presentation_rank over hit gold facts, or 0 if no fact is hit",
                "rank_discounted_fact_alias_coverage": "sum(1 / log2(minimum evidence_presentation_rank + 1)) / gold_fact_count",
            },
            "aggregation": "macro-by-question",
            "actual_Lq": "Each question records its actual returned-set size Lq; methods may have different Lq.",
            "kg_presentation": "KG evidence is appended after document evidence and receives presentation ranks; this is not a unified relevance score or equal-budget comparison.",
            "standard_ir_metric_claim": False,
            "same_evidence_rank_for_multiple_facts": True,
        },
        "aggregate": aggregate,
        "per_query": per_query,
        "evidence_snapshots": persisted_snapshots,
        "evidence_snapshots_file": str(snapshots_path),
        "snapshot_checks": snapshot_checks,
        "snapshot_checks_file": str(checks_path),
    }
    # Write/read the complete report once before hashing.  This makes the
    # result identity depend on serialized canonical evidence, not on the
    # pre-serialization Python object graph.
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    persisted_report = json.loads(args.output.read_text(encoding="utf-8"))
    canonical_material_path = args.output.parent / "canonical-result-material.json"
    canonical_material_path.write_text(
        json.dumps(canonical_result_material(persisted_report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    persisted_material = json.loads(canonical_material_path.read_text(encoding="utf-8"))
    result_sha256 = compute_result_sha256(canonical_material_path)
    if args.expected_result_sha256:
        if args.expected_result_sha256 != result_sha256:
            raise EvaluationFailure(f"result hash mismatch: expected {args.expected_result_sha256}, got {result_sha256}", stage="result_hash_gate", expected=args.expected_result_sha256, actual=result_sha256)
    persisted_report["same_deployment_repeatability_verified"] = same_deployment_repeatability_verified(
        args.expected_result_sha256, result_sha256
    )
    persisted_report["canonical_result_material"] = persisted_material
    persisted_report["result_sha256"] = result_sha256
    args.output.write_text(json.dumps(persisted_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    final_report = json.loads(args.output.read_text(encoding="utf-8"))
    final_material = json.loads(canonical_material_path.read_text(encoding="utf-8"))
    _require(compute_result_sha256(canonical_material_path) == final_report["result_sha256"], "result hash did not survive canonical material round-trip", stage="result_hash_round_trip")
    _require(
        final_report["canonical_result_material"] == final_material,
        "final report canonical_result_material differs from independent material file",
        stage="result_material_consistency",
    )
    print(json.dumps({"result_sha256": final_report["result_sha256"], "canonicalization_version": CANONICALIZATION_VERSION}))
    return final_report


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return _evaluate(args)
    except BaseException as error:
        write_failure(args.output, error)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--retrieval-config", type=Path, required=True)
    parser.add_argument("--corpus-sha256", required=True)
    parser.add_argument("--corpus-chunk-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-result-sha256", default="")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.corpus_chunk_count < 1:
        parser.error("--corpus-chunk-count must be positive")
    return args


if __name__ == "__main__":
    evaluate(parse_args())
