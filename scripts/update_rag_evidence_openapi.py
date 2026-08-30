#!/usr/bin/env python3
"""Overlay the RAG evidence contract onto an existing OpenAPI baseline.

This is not a full Rust DTO-to-OpenAPI generator.  It reads the checked-in
``backend/openapi.json`` baseline and deterministically updates only the
evidence-export and retrieval-only contract fragments.  Existing status
schemas and unrelated paths are preserved rather than generated here.  The
Rust route/DTO contract tests remain authoritative for the complete API.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path


OPENAPI_PATH = Path(__file__).resolve().parents[1] / "backend" / "openapi.json"
EVIDENCE_PATH = "/rag/experiments/{run_id}/evidence.json"
RUST_RETRIEVAL_PATH = "/projects/{project_id}/rag/retrieve"
EXPERIMENT_PATH = "/projects/{project_id}/rag/experiments"


def nullable_string_enum(values: list[str]) -> dict[str, object]:
    return {"anyOf": [{"type": "string", "enum": values}, {"type": "null"}]}


def nullable_string() -> dict[str, object]:
    return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def nullable_integer() -> dict[str, object]:
    return {"anyOf": [{"type": "integer"}, {"type": "null"}]}


def open_object(title: str) -> dict[str, object]:
    return {"type": "object", "additionalProperties": True, "title": title}


def api_error_schema() -> dict[str, object]:
    return {
        "type": "object",
        "title": "ApiErrorResponse",
        "required": ["detail"],
        "properties": {"detail": {"type": "string"}},
        "additionalProperties": False,
    }


def evidence_schemas() -> dict[str, dict[str, object]]:
    return {
        "ApiErrorResponse": api_error_schema(),
        "RagEvidencePackage": {
            "type": "object",
            "title": "RagEvidencePackage",
            "required": [
                "schema_version",
                "experiment",
                "config_snapshot",
                "summary",
                "case_count",
                "cases",
            ],
            "properties": {
                "schema_version": {
                    "type": "string",
                    "enum": ["rag-evidence-package-v1"],
                },
                "experiment": {
                    "$ref": "#/components/schemas/RagEvidenceExperiment"
                },
                "config_snapshot": open_object("Rag Evidence Config Snapshot"),
                "summary": {"$ref": "#/components/schemas/RagEvidenceSummary"},
                "case_count": {"type": "integer", "minimum": 0},
                "cases": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/RagEvidenceCase"},
                },
            },
        },
        "RagEvidenceExperiment": {
            "type": "object",
            "title": "RagEvidenceExperiment",
            "additionalProperties": True,
            "required": [
                "id",
                "project_id",
                "created_by",
                "name",
                "status",
                "questions",
                "modes",
                "total_cases",
                "completed_cases",
                "failed_cases",
                "created_at",
                "completed_at",
                "repetitions",
                "randomize_order",
                "random_seed",
                "execution_plan_hash",
                "embedding_model",
                "generation_model",
                "questions_sha256",
                "corpus_snapshot_hash",
                "graph_snapshot_hash",
                "rag_index_version",
                "graph_schema_version",
            ],
            "properties": {
                "id": {"type": "integer"},
                "project_id": {"type": "integer"},
                "created_by": {"type": "integer"},
                "name": {"type": "string", "minLength": 1, "maxLength": 255},
                "status": {
                    "type": "string",
                    "enum": [
                        "queued",
                        "running",
                        "interrupted",
                        "completed",
                        "completed_with_errors",
                        "failed",
                    ],
                },
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1, "maxLength": 4000},
                },
                "modes": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "enum": [
                            "pure_llm",
                            "bm25_rag",
                            "project_rag",
                            "structured_query",
                            "kg_enhanced_rag",
                        ],
                    },
                },
                "total_cases": {"type": "integer", "minimum": 0},
                "completed_cases": {"type": "integer", "minimum": 0},
                "failed_cases": {"type": "integer", "minimum": 0},
                "created_at": {"type": "string", "format": "date-time"},
                "completed_at": {
                    "anyOf": [{"type": "string", "format": "date-time"}, {"type": "null"}]
                },
                "repetitions": {"type": "integer", "minimum": 1, "maximum": 10},
                "randomize_order": {"type": "boolean"},
                "random_seed": {"type": "integer"},
                "execution_plan_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "embedding_model": {"type": "string"},
                "generation_model": {"type": "string"},
                "questions_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "corpus_snapshot_hash": {
                    "anyOf": [
                        {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        {"type": "null"},
                    ]
                },
                "graph_snapshot_hash": {
                    "anyOf": [
                        {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        {"type": "null"},
                    ]
                },
                "rag_index_version": nullable_string(),
                "graph_schema_version": nullable_string(),
            },
        },
        "RagEvidenceSource": {
            "type": "object",
            "title": "RagEvidenceSource",
            "additionalProperties": True,
            "required": ["chunk_id", "file_id"],
            "properties": {
                "chunk_id": {"type": "integer", "minimum": 1},
                "file_id": {"type": "integer", "minimum": 1},
                "filename": nullable_string(),
                "dify_document_id": nullable_string(),
                "snippet": nullable_string(),
                "vector_score": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "lexical_score": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "retrieval_score": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            },
        },
        "RagEvidenceGraphContext": {
            "type": "object",
            "title": "RagEvidenceGraphContext",
            "additionalProperties": True,
            "required": ["relation_id", "source_entity_id", "target_entity_id"],
            "properties": {
                "relation_id": {"type": "integer", "minimum": 1},
                "relation_type": {"type": "string"},
                "relation_label": {"type": "string"},
                "source_entity_id": {"type": "integer", "minimum": 1},
                "source_label": {"type": "string"},
                "source_entity_type": {"type": "string"},
                "source_entity_type_label": {"type": "string"},
                "target_entity_id": {"type": "integer", "minimum": 1},
                "target_label": {"type": "string"},
                "target_entity_type": {"type": "string"},
                "target_entity_type_label": {"type": "string"},
                "confidence": {"type": "number"},
                "retrieval_score": {"type": "number"},
                "relation_roles": {"type": "array", "items": {"type": "string"}},
            },
        },
        "RagEvidenceRetrievalConfig": {
            "type": "object",
            "title": "RagEvidenceRetrievalConfig",
            "additionalProperties": True,
            "properties": {
                "embedding_model": {"type": "string"},
                "index_version": {"type": "string"},
                "graph_schema_version": {"type": "string"},
                "retrieval_strategy": {"type": "string"},
                "retrieval_top_k": {"type": "integer", "minimum": 1},
                "collection_retrieval_top_k": {"type": "integer", "minimum": 1},
                "effective_retrieval_top_k": {"type": "integer", "minimum": 1},
                "vector_candidate_k": {"type": "integer", "minimum": 1},
                "graph_top_k": {"type": "integer", "minimum": 1},
                "effective_graph_top_k": {"type": "integer", "minimum": 1},
                "chunk_size": {"type": "integer", "minimum": 1},
                "chunk_overlap": {"type": "integer", "minimum": 0},
                "graph_min_score": {"type": "number", "minimum": 0},
                "retrieval_min_score": {"type": "number", "minimum": 0},
                "retrieval_applied": {"type": "boolean"},
                "graph_retrieval_applied": {"type": "boolean"},
                "citation_audit": open_object("Rag Evidence Citation Audit"),
            },
        },
        "RagEvidenceCase": {
            "type": "object",
            "title": "RagEvidenceCase",
            "additionalProperties": True,
            "required": [
                "query_log_id",
                "question_index",
                "question",
                "mode",
                "repetition_index",
                "execution_order",
                "status",
                "failure_scope",
                "failure_code",
                "answer",
                "source_count",
                "graph_hit_count",
                "response_ms",
                "provider",
                "model",
                "prompt_version",
                "fallback_reason",
                "error",
                "sources",
                "graph_context",
                "retrieval_config",
                "usage",
                "citation_audit",
                "created_at",
            ],
            "properties": {
                "query_log_id": {
                    "anyOf": [
                        {"type": "integer", "minimum": 1},
                        {"type": "null"},
                    ]
                },
                "question_index": {"type": "integer", "minimum": 1},
                "question": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4000,
                },
                "mode": {
                    "type": "string",
                    "enum": [
                        "pure_llm",
                        "bm25_rag",
                        "project_rag",
                        "structured_query",
                        "kg_enhanced_rag",
                    ],
                },
                "repetition_index": {"type": "integer", "minimum": 1},
                "execution_order": {"type": "integer", "minimum": 1},
                "status": {"type": "string", "enum": ["completed", "failed"]},
                "failure_scope": nullable_string_enum(["case"]),
                "failure_code": nullable_string_enum(["query_error"]),
                "answer": nullable_string(),
                "source_count": {"type": "integer", "minimum": 0},
                "graph_hit_count": {"type": "integer", "minimum": 0},
                "response_ms": {"type": "integer", "minimum": 0},
                "provider": {"type": "string"},
                "model": nullable_string(),
                "prompt_version": nullable_string(),
                "fallback_reason": nullable_string(),
                "error": nullable_string(),
                "sources": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/RagEvidenceSource"},
                },
                "graph_context": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/RagEvidenceGraphContext"},
                },
                "retrieval_config": {
                    "$ref": "#/components/schemas/RagEvidenceRetrievalConfig"
                },
                "usage": open_object("Rag Evidence Usage"),
                "citation_audit": open_object("Rag Evidence Citation Audit"),
                "created_at": nullable_string(),
            },
        },
        "RagEvidenceRunFatalError": {
            "type": "object",
            "title": "RagEvidenceRunFatalError",
            "required": ["error", "failure_scope", "failure_code"],
            "properties": {
                "error": {"type": "string"},
                "failure_scope": {"type": "string", "enum": ["run"]},
                "failure_code": {
                    "type": "string",
                    "enum": ["creator_user_missing", "input_binding_drift", "worker_error"],
                },
            },
        },
        "RagEvidenceSummaryError": {
            "type": "object",
            "title": "RagEvidenceSummaryError",
            "required": ["error", "failure_scope", "failure_code"],
            "properties": {
                "case_index": nullable_integer(),
                "question_index": nullable_integer(),
                "mode": nullable_string(),
                "repetition_index": nullable_integer(),
                "error": {"type": "string"},
                "failure_scope": {"type": "string", "enum": ["case", "run"]},
                "failure_code": {
                    "type": "string",
                    "enum": ["query_error", "creator_user_missing", "input_binding_drift", "worker_error"],
                },
            },
        },
        "RagEvidenceSummary": {
            "type": "object",
            "title": "RagEvidenceSummary",
            "additionalProperties": True,
            "required": ["fatal_error", "errors", "execution_plan", "unexecuted_cases"],
            "properties": {
                "fatal_error": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/RagEvidenceRunFatalError"},
                        {"type": "null"},
                    ]
                },
                "errors": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/RagEvidenceSummaryError"},
                },
                "execution_plan": {"type": "array", "items": open_object("Rag Evidence Plan Case")},
                "unexecuted_cases": {"type": "integer", "minimum": 0},
            },
        },
    }


def snapshot_hash_schema() -> dict[str, object]:
    return {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def rust_retrieval_schemas() -> dict[str, dict[str, object]]:
    """Schema for the Rust retrieval-only evidence boundary.

    Keep this beside the updater rather than hand-editing generated JSON.  The
    Rust response is intentionally explicit about identity and no-generation
    flags; source/graph payloads retain the stable content fields needed by
    the offline evidence verifier.
    """
    nullable_hash = {"anyOf": [snapshot_hash_schema(), {"type": "null"}]}
    nullable_number = {"anyOf": [{"type": "number"}, {"type": "null"}]}
    nullable_string_value = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    source = {
        "type": "object",
        "title": "RagSourceRead",
        "properties": {
            "chunk_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "file_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "filename": nullable_string_value,
            "dify_document_id": nullable_string_value,
            "snippet": nullable_string_value,
            "vector_score": nullable_number,
            "lexical_score": nullable_number,
            "retrieval_score": nullable_number,
            "content": nullable_string_value,
            "content_sha256": nullable_hash,
            "file_hash": nullable_hash,
            "chunk_index": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        },
    }
    graph = {
        "type": "object",
        "title": "RagGraphContextRead",
        "required": [
            "relation_id",
            "relation_type",
            "relation_label",
            "source_entity_id",
            "source_label",
            "source_normalized_label",
            "source_natural_key",
            "source_entity_type",
            "source_entity_type_label",
            "target_entity_id",
            "target_label",
            "target_normalized_label",
            "target_natural_key",
            "target_entity_type",
            "target_entity_type_label",
            "confidence",
            "retrieval_score",
            "relation_roles",
            "relation_properties",
        ],
        "properties": {
            "relation_id": {"type": "integer"},
            "relation_type": {"type": "string"},
            "relation_label": {"type": "string"},
            "source_entity_id": {"type": "integer"},
            "source_label": {"type": "string"},
            "source_normalized_label": {"type": "string"},
            "source_natural_key": {"type": "string"},
            "source_entity_type": {"type": "string"},
            "source_entity_type_label": {"type": "string"},
            "target_entity_id": {"type": "integer"},
            "target_label": {"type": "string"},
            "target_normalized_label": {"type": "string"},
            "target_natural_key": {"type": "string"},
            "target_entity_type": {"type": "string"},
            "target_entity_type_label": {"type": "string"},
            "confidence": {"type": "number"},
            "retrieval_score": {"type": "number"},
            "relation_roles": {"type": "array", "items": {"type": "string"}},
            "relation_properties": {"type": "object", "additionalProperties": True},
        },
    }
    corpus = {
        "type": "object",
        "title": "RagCorpusSnapshotRead",
        "required": [
            "dataset_id",
            "corpus_snapshot_hash",
            "corpus_chunk_count",
            "rag_index_version",
            "embedding_model",
            "graph_snapshot_hash",
            "graph_entity_count",
            "graph_relation_count",
        ],
        "properties": {
            "dataset_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "corpus_snapshot_hash": nullable_hash,
            "corpus_chunk_count": {"type": "integer", "minimum": 0},
            "rag_index_version": {"type": "string"},
            "embedding_model": nullable_string_value,
            "graph_snapshot_hash": nullable_hash,
            "graph_entity_count": {"type": "integer", "minimum": 0},
            "graph_relation_count": {"type": "integer", "minimum": 0},
        },
    }
    return {
        "RagRetrievalRequest": {
            "type": "object",
            "title": "RagRetrievalRequest",
            "required": [
                "query",
                "mode",
                "expected_corpus_snapshot_hash",
                "expected_graph_snapshot_hash",
            ],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 4000},
                "mode": {
                    "type": "string",
                    "enum": ["bm25_rag", "project_rag", "kg_enhanced_rag"],
                },
                "expected_corpus_snapshot_hash": snapshot_hash_schema(),
                "expected_graph_snapshot_hash": snapshot_hash_schema(),
            },
        },
        "RagRetrievalResponse": {
            "type": "object",
            "title": "RagRetrievalResponse",
            "required": [
                "retrieval_only",
                "generation_invoked",
                "llm_query_rewrite_invoked",
                "citation_repair_invoked",
                "mode",
                "sources",
                "graph_context",
                "effective_retrieval_config",
                "actual_corpus_snapshot_hash",
                "actual_graph_snapshot_hash",
                "used_corpus_snapshot_hash",
                "used_graph_snapshot_hash",
                "corpus_snapshot_hash",
                "graph_snapshot_hash",
                "corpus_chunk_count",
                "graph_entity_count",
                "graph_relation_count",
            ],
            "properties": {
                "retrieval_only": {"type": "boolean"},
                "generation_invoked": {"type": "boolean"},
                "llm_query_rewrite_invoked": {"type": "boolean"},
                "citation_repair_invoked": {"type": "boolean"},
                "mode": {"type": "string", "enum": ["bm25_rag", "project_rag", "kg_enhanced_rag"]},
                "sources": {"type": "array", "items": {"$ref": "#/components/schemas/RagSourceRead"}},
                "graph_context": {"type": "array", "items": {"$ref": "#/components/schemas/RagGraphContextRead"}},
                "effective_retrieval_config": {"type": "object", "additionalProperties": True},
                "actual_corpus_snapshot_hash": snapshot_hash_schema(),
                "actual_graph_snapshot_hash": snapshot_hash_schema(),
                "used_corpus_snapshot_hash": snapshot_hash_schema(),
                "used_graph_snapshot_hash": snapshot_hash_schema(),
                "corpus_snapshot_hash": snapshot_hash_schema(),
                "graph_snapshot_hash": snapshot_hash_schema(),
                "corpus_chunk_count": {"type": "integer", "minimum": 0},
                "graph_entity_count": {"type": "integer", "minimum": 0},
                "graph_relation_count": {"type": "integer", "minimum": 0},
            },
        },
        "RagSourceRead": source,
        "RagGraphContextRead": graph,
        "RagCorpusSnapshotRead": corpus,
    }


def rust_retrieval_operation() -> dict[str, object]:
    return {
        "post": {
            "tags": ["rag"],
            "summary": "Retrieval-only RAG evidence",
            "operationId": "retrieve_project_rag_projects__project_id__rag_retrieve_post",
            "security": [{"HTTPBearer": []}],
            "parameters": [
                {
                    "name": "project_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/RagRetrievalRequest"}}
                },
            },
            "responses": {
                "200": {
                    "description": "Retrieval evidence without generation",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/RagRetrievalResponse"}}
                    },
                },
                "409": {
                    "description": "Snapshot identity drift",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}}},
                },
                "422": {
                    "description": "Invalid retrieval-only request",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}}},
                },
            },
        }
    }


def update_experiment_contract(document: dict) -> None:
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    request = schemas.get("AIExperimentRunRequest")
    operation = document.get("paths", {}).get(EXPERIMENT_PATH, {}).get("post")
    # Keep this overlay composable with minimal OpenAPI fixtures and callers
    # that have not loaded the experiment contract yet.
    if request is None or operation is None:
        return
    hash_schema = {
        "anyOf": [
            {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            {"type": "null"},
        ]
    }
    properties = request.setdefault("properties", {})
    for name in ("expected_corpus_snapshot_hash", "expected_graph_snapshot_hash"):
        existing = properties.get(name)
        if isinstance(existing, dict):
            # Preserve generated titles/descriptions so rerunning this
            # evidence overlay is byte-for-byte stable on the checked-in
            # Rust contract.
            existing["anyOf"] = copy.deepcopy(hash_schema["anyOf"])
        else:
            properties[name] = copy.deepcopy(hash_schema)
    operation.setdefault("responses", {})["409"] = {
        "description": "Experiment snapshot drift",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
            }
        },
    }


def update_document(document: dict) -> dict:
    operation = document["paths"][EVIDENCE_PATH]["get"]
    operation["responses"]["200"]["content"]["application/json"]["schema"] = {
        "$ref": "#/components/schemas/RagEvidencePackage"
    }
    operation["responses"]["409"] = {
        "description": "Evidence export unavailable until the run reaches a supported terminal state",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
            }
        },
    }
    operation["responses"]["403"] = {
        "description": "Independent reviewers cannot access unblinded evidence exports",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
            }
        },
    }
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    schemas.update(evidence_schemas())
    document.setdefault("paths", {})[RUST_RETRIEVAL_PATH] = rust_retrieval_operation()
    schemas.update(rust_retrieval_schemas())
    update_experiment_contract(document)
    return document


def main() -> None:
    document = update_document(json.loads(OPENAPI_PATH.read_text(encoding="utf-8")))
    OPENAPI_PATH.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
