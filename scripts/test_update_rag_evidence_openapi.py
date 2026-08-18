from __future__ import annotations

import copy
import importlib.util
import json
import sys


SCRIPT = __import__("pathlib").Path(__file__).with_name("update_rag_evidence_openapi.py")
SPEC = importlib.util.spec_from_file_location("update_rag_evidence_openapi", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def document() -> dict:
    return {
        "openapi": "3.1.0",
        "paths": {
            MODULE.EVIDENCE_PATH: {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {}}
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "ExistingSchema": {"type": "object", "properties": {"keep": {"type": "string"}}}
            }
        },
    }


def test_update_document_exposes_contract_without_dropping_existing_schemas() -> None:
    original = document()

    updated = MODULE.update_document(copy.deepcopy(original))

    assert (
        updated["paths"][MODULE.EVIDENCE_PATH]["get"]["responses"]["200"]
        ["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/RagEvidencePackage"}
    )
    assert updated["paths"][MODULE.EVIDENCE_PATH]["get"]["responses"]["409"] == {
        "description": "Evidence export unavailable until the run reaches a supported terminal state",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
            }
        },
    }
    assert updated["paths"][MODULE.EVIDENCE_PATH]["get"]["responses"]["403"] == {
        "description": "Independent reviewers cannot access unblinded evidence exports",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
            }
        },
    }
    assert updated["components"]["schemas"]["ApiErrorResponse"] == {
        "type": "object",
        "title": "ApiErrorResponse",
        "required": ["detail"],
        "properties": {"detail": {"type": "string"}},
        "additionalProperties": False,
    }
    assert updated["components"]["schemas"]["ExistingSchema"] == original["components"]["schemas"]["ExistingSchema"]
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["failure_scope"]["anyOf"][0]["enum"] == ["case"]
    assert updated["components"]["schemas"]["RagEvidenceRunFatalError"]["properties"]["failure_scope"]["enum"] == ["run"]
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["sources"]["items"] == {
        "$ref": "#/components/schemas/RagEvidenceSource"
    }
    assert updated["components"]["schemas"]["RagEvidenceSource"]["properties"]["chunk_id"] == {
        "type": "integer",
        "minimum": 1,
    }
    assert updated["components"]["schemas"]["RagEvidenceGraphContext"]["required"] == [
        "relation_id",
        "source_entity_id",
        "target_entity_id",
    ]
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["retrieval_config"] == {
        "$ref": "#/components/schemas/RagEvidenceRetrievalConfig"
    }
    assert updated["components"]["schemas"]["RagEvidenceRetrievalConfig"]["properties"]["retrieval_top_k"] == {
        "type": "integer",
        "minimum": 1,
    }
    assert updated["components"]["schemas"]["RagEvidenceRetrievalConfig"]["properties"]["graph_schema_version"] == {
        "type": "string"
    }
    assert updated["components"]["schemas"]["RagEvidenceExperiment"]["properties"]["graph_schema_version"] == {
        "anyOf": [{"type": "string"}, {"type": "null"}]
    }
    assert updated["components"]["schemas"]["RagEvidenceExperiment"]["required"] == [
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
        "rag_index_version",
        "graph_schema_version",
    ]
    assert updated["components"]["schemas"]["RagEvidenceExperiment"]["properties"]["status"] == {
        "type": "string",
        "enum": [
            "queued",
            "running",
            "interrupted",
            "completed",
            "completed_with_errors",
            "failed",
        ],
    }
    assert updated["components"]["schemas"]["RagEvidenceExperiment"]["properties"]["name"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 255,
    }
    assert updated["components"]["schemas"]["RagEvidenceExperiment"]["properties"]["questions"] == {
        "type": "array",
        "minItems": 1,
        "maxItems": 50,
        "uniqueItems": True,
        "items": {"type": "string", "minLength": 1, "maxLength": 4000},
    }
    assert updated["components"]["schemas"]["RagEvidenceExperiment"]["properties"]["modes"] == {
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
    }
    assert updated["components"]["schemas"]["RagEvidenceExperiment"]["properties"]["repetitions"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 10,
    }
    assert updated["components"]["schemas"]["RagEvidenceExperiment"]["properties"]["execution_plan_hash"] == {
        "type": "string",
        "pattern": "^[0-9a-f]{64}$",
    }
    assert updated["components"]["schemas"]["RagEvidenceSummary"]["required"] == [
        "fatal_error",
        "errors",
        "execution_plan",
        "unexecuted_cases",
    ]
    assert updated["components"]["schemas"]["RagEvidenceCase"]["required"] == [
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
    ]
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["question_index"] == {
        "type": "integer",
        "minimum": 1,
    }
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["query_log_id"] == {
        "anyOf": [
            {"type": "integer", "minimum": 1},
            {"type": "null"},
        ]
    }
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["question"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 4000,
    }
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["mode"] == {
        "type": "string",
        "enum": [
            "pure_llm",
            "bm25_rag",
            "project_rag",
            "structured_query",
            "kg_enhanced_rag",
        ],
    }
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["repetition_index"] == {
        "type": "integer",
        "minimum": 1,
    }
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["execution_order"] == {
        "type": "integer",
        "minimum": 1,
    }
    assert updated["components"]["schemas"]["RagEvidenceCase"]["properties"]["response_ms"] == {
        "type": "integer",
        "minimum": 0,
    }

    retrieval = updated["paths"][MODULE.RUST_RETRIEVAL_PATH]["post"]
    assert retrieval["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RagRetrievalRequest"
    }
    assert retrieval["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RagRetrievalResponse"
    }
    request = updated["components"]["schemas"]["RagRetrievalRequest"]
    assert request["required"] == [
        "query",
        "mode",
        "expected_corpus_snapshot_hash",
        "expected_graph_snapshot_hash",
    ]
    assert request["properties"]["mode"]["enum"] == [
        "bm25_rag",
        "project_rag",
        "kg_enhanced_rag",
    ]
    response = updated["components"]["schemas"]["RagRetrievalResponse"]
    assert response["required"] == [
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
    ]
    assert response["properties"]["sources"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/RagSourceRead"},
    }
    assert response["properties"]["effective_retrieval_config"] == {
        "type": "object",
        "additionalProperties": True,
    }
    source = updated["components"]["schemas"]["RagSourceRead"]
    for field in ("content", "content_sha256", "file_hash", "chunk_index"):
        assert field in source["properties"]
    graph = updated["components"]["schemas"]["RagGraphContextRead"]
    for field in (
        "source_normalized_label",
        "source_natural_key",
        "target_normalized_label",
        "target_natural_key",
        "relation_properties",
    ):
        assert field in graph["properties"]
    corpus = updated["components"]["schemas"]["RagCorpusSnapshotRead"]
    for field in ("graph_snapshot_hash", "graph_entity_count", "graph_relation_count"):
        assert field in corpus["required"]
        assert field in corpus["properties"]
    assert updated["paths"][MODULE.RUST_RETRIEVAL_PATH]["post"]["parameters"][0] == {
        "name": "project_id",
        "in": "path",
        "required": True,
        "schema": {"type": "integer"},
    }


def test_update_document_is_idempotent() -> None:
    once = MODULE.update_document(document())
    twice = MODULE.update_document(copy.deepcopy(once))

    assert json.dumps(twice, ensure_ascii=False, separators=(",", ":")) == json.dumps(
        once, ensure_ascii=False, separators=(",", ":")
    )
