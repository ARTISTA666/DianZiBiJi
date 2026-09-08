from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gates" / "check_rag_experiment_evidence.py"
SPEC = importlib.util.spec_from_file_location("check_rag_experiment_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def package() -> dict:
    value = {
        "schema_version": "rag-evidence-package-v1",
        "experiment": {
            "id": 12,
            "status": "completed_with_errors",
            "questions": ["问题一"],
            "modes": ["project_rag", "kg_enhanced_rag"],
            "total_cases": 2,
            "completed_cases": 1,
            "failed_cases": 1,
            "repetitions": 1,
            "randomize_order": False,
            "random_seed": 42,
            "execution_plan_hash": "a" * 64,
            "embedding_model": "rust-hash-512-v1",
            "generation_model": "model-v1",
            "questions_sha256": "b" * 64,
            "corpus_snapshot_hash": "c" * 64,
            "rag_index_version": "structured-v1",
            "graph_schema_version": "kg-v3-numbered-list-expansion",
        },
        "config_snapshot": {
            "embedding_model": "rust-hash-512-v1",
            "generation_model": "model-v1",
            "questions_sha256": "b" * 64,
            "corpus_snapshot_hash": "c" * 64,
            "rag_index_version": "structured-v1",
            "graph_schema_version": "kg-v3-numbered-list-expansion",
            "experiment_protocol": {
                "repetitions": 1,
                "randomize_order": False,
                "random_seed": 42,
                "execution_plan_hash": "a" * 64,
            },
        },
        "summary": {
            "unexecuted_cases": 0,
            "execution_plan": [
                {
                    "question_index": 1,
                    "question": "问题一",
                    "repetition_index": 1,
                    "mode": "project_rag",
                    "execution_order": 1,
                },
                {
                    "question_index": 1,
                    "question": "问题一",
                    "repetition_index": 1,
                    "mode": "kg_enhanced_rag",
                    "execution_order": 2,
                },
            ],
            "errors": [
                {
                        "question_index": 1,
                        "question": "问题一",
                    "mode": "kg_enhanced_rag",
                    "repetition_index": 1,
                    "execution_order": 2,
                    "error": "timeout",
                    "failure_scope": "case",
                    "failure_code": "query_error",
                }
            ]
        },
        "case_count": 2,
        "cases": [
            {
                "query_log_id": 99,
                "question_index": 1,
                "question": "问题一",
                "mode": "project_rag",
                "repetition_index": 1,
                "execution_order": 1,
                "status": "completed",
                "failure_scope": None,
                "failure_code": None,
                "answer": "回答 [S1]",
                "error": None,
                "source_count": 1,
                "graph_hit_count": 0,
                "sources": [
                    {
                        "chunk_id": 17,
                        "file_id": 3,
                        "filename": "evidence.txt",
                        "snippet": "evidence",
                    }
                ],
                "graph_context": [],
                "retrieval_config": {
                    "embedding_model": "rust-hash-512-v1",
                    "index_version": "structured-v1",
                    "graph_schema_version": "kg-v3-numbered-list-expansion",
                    "retrieval_strategy": "rrf-v1",
                    "retrieval_top_k": 12,
                    "collection_retrieval_top_k": 18,
                    "effective_retrieval_top_k": 12,
                    "vector_candidate_k": 24,
                    "graph_top_k": 8,
                    "effective_graph_top_k": 8,
                    "chunk_size": 700,
                    "chunk_overlap": 80,
                    "graph_min_score": 0.35,
                    "retrieval_min_score": 0.2,
                },
                "usage": {},
                "response_ms": 12,
                "provider": "local",
                "model": "model-v1",
                "prompt_version": "rag-v1",
                "fallback_reason": None,
                "citation_audit": {
                    "passed": True,
                    "citation_count": 1,
                    "invalid_citations": [],
                    "has_evidence": True,
                    "message": "引用校验通过，共核对 1 个证据编号。",
                    "repair_attempted": False,
                },
            },
            {
                "query_log_id": None,
                "question_index": 1,
                "question": "问题一",
                "mode": "kg_enhanced_rag",
                "repetition_index": 1,
                "execution_order": 2,
                "status": "failed",
                "failure_scope": "case",
                "failure_code": "query_error",
                "answer": None,
                "error": "timeout",
                "source_count": 0,
                "graph_hit_count": 0,
                "sources": [],
                "graph_context": [],
                "retrieval_config": {},
                "usage": {},
                "response_ms": 0,
                "provider": "system",
                "model": None,
                "prompt_version": "rag-retrieval-failure-v1",
                "fallback_reason": None,
                "citation_audit": {},
            },
        ],
    }
    plan_hash = MODULE.execution_plan_sha256(value["summary"]["execution_plan"])
    value["experiment"]["execution_plan_hash"] = plan_hash
    value["config_snapshot"]["experiment_protocol"]["execution_plan_hash"] = plan_hash
    value["experiment"]["questions_sha256"] = MODULE.questions_sha256(
        value["experiment"]["questions"]
    )
    value["config_snapshot"]["questions_sha256"] = value["experiment"]["questions_sha256"]
    return value


def test_validates_complete_package() -> None:
    assert MODULE.validate(package()) == []


def test_rejects_unknown_experiment_status() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["status"] = "succeeded"

    failures = MODULE.validate(invalid)

    assert any("unsupported experiment status" in failure for failure in failures)


def test_rejects_graph_schema_version_drift() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["graph_schema_version"] = "kg-v2"

    failures = MODULE.validate(invalid)

    assert any("graph_schema_version does not match config_snapshot" in failure for failure in failures)


def test_rejects_protocol_summary_field_drift() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["randomize_order"] = True

    failures = MODULE.validate(invalid)

    assert any("randomize_order" in failure for failure in failures)


def test_rejects_missing_protocol_summary_field() -> None:
    invalid = deepcopy(package())
    invalid["experiment"].pop("repetitions")

    failures = MODULE.validate(invalid)

    assert any("repetitions" in failure for failure in failures)


def test_rejects_input_binding_drift() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["questions_sha256"] = "d" * 64

    failures = MODULE.validate(invalid)

    assert any("questions_sha256" in failure for failure in failures)


def test_rejects_dataset_run_without_corpus_snapshot() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["corpus_snapshot_hash"] = None
    invalid["config_snapshot"]["corpus_snapshot_hash"] = None

    failures = MODULE.validate(invalid)

    assert any("corpus_snapshot_hash" in failure for failure in failures)


def test_rejects_non_terminal_experiment_status() -> None:
    for status in ("queued", "running"):
        invalid = deepcopy(package())
        invalid["experiment"]["status"] = status

        failures = MODULE.validate(invalid)

        assert any("non-terminal" in failure for failure in failures)


def test_rejects_completed_run_with_failures_or_unexecuted_cases() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["status"] = "completed"

    failures = MODULE.validate(invalid)

    assert any("completed experiment" in failure for failure in failures)


def test_rejects_completed_with_errors_run_without_failures() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["status"] = "completed_with_errors"
    invalid["experiment"]["failed_cases"] = 0
    invalid["cases"].pop()
    invalid["case_count"] = 1
    invalid["summary"]["errors"] = []
    invalid["summary"]["unexecuted_cases"] = 1

    failures = MODULE.validate(invalid)

    assert any("completed_with_errors" in failure for failure in failures)


def test_rejects_case_denominator_mismatch() -> None:
    invalid = deepcopy(package())
    invalid["case_count"] = 1

    failures = MODULE.validate(invalid)

    assert any("case_count" in failure for failure in failures)


def test_rejects_completed_case_without_query_log_id() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["query_log_id"] = None

    failures = MODULE.validate(invalid)

    assert any("completed case" in failure and "query_log_id" in failure for failure in failures)


def test_rejects_completed_case_without_answer() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["answer"] = None

    failures = MODULE.validate(invalid)

    assert any("completed case" in failure and "answer" in failure for failure in failures)


def test_rejects_malformed_case_telemetry() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["response_ms"] = -1
    invalid["cases"][0]["provider"] = ""
    invalid["cases"][0]["prompt_version"] = None
    invalid["cases"][0]["retrieval_config"] = []
    invalid["cases"][0]["usage"] = "not-an-object"

    failures = MODULE.validate(invalid)

    assert any("response_ms" in failure for failure in failures)
    assert any("provider" in failure for failure in failures)
    assert any("prompt_version" in failure for failure in failures)
    assert any("retrieval_config" in failure for failure in failures)
    assert any("usage" in failure for failure in failures)


def test_rejects_malformed_failed_case_evidence_arrays() -> None:
    invalid = deepcopy(package())
    invalid["cases"][1]["sources"] = {}
    invalid["cases"][1]["graph_context"] = "not-an-array"

    failures = MODULE.validate(invalid)

    assert any("sources" in failure and "array" in failure for failure in failures)
    assert any("graph_context" in failure and "array" in failure for failure in failures)


def test_rejects_logged_case_retrieval_binding_drift() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["retrieval_config"]["embedding_model"] = "different-model"
    invalid["cases"][0]["retrieval_config"].pop("index_version")

    failures = MODULE.validate(invalid)

    assert any("retrieval_config.embedding_model" in failure for failure in failures)
    assert any("retrieval_config.index_version" in failure for failure in failures)


def test_rejects_logged_case_without_retrieval_parameter_snapshot() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["retrieval_config"].pop("retrieval_strategy")

    failures = MODULE.validate(invalid)

    assert any("retrieval_config.retrieval_strategy" in failure for failure in failures)


def test_rejects_logged_cases_with_different_retrieval_parameter_bindings() -> None:
    invalid = deepcopy(package())
    invalid["cases"].append(deepcopy(invalid["cases"][0]))
    invalid["cases"][1]["query_log_id"] = 100
    invalid["cases"][1]["execution_order"] = 2
    invalid["cases"][1]["mode"] = "kg_enhanced_rag"
    invalid["cases"][1]["retrieval_config"]["retrieval_top_k"] = 24

    failures = MODULE.validate(invalid)

    assert any("stable retrieval parameter binding" in failure for failure in failures)


def test_derives_reproducible_case_statistics() -> None:
    statistics = MODULE.derive_statistics(package())

    assert statistics["schema_version"] == "rag-evidence-statistics-v1"
    assert statistics["observed_case_count"] == 2
    assert statistics["status_counts"] == {"completed": 1, "failed": 1}
    assert statistics["evidence"]["source_items"] == 1
    assert statistics["evidence"]["graph_items"] == 0
    assert statistics["citation_audit"]["audited_cases"] == 1
    assert statistics["citation_audit"]["passed_cases"] == 1
    assert statistics["modes"]["project_rag"]["completed_cases"] == 1
    assert statistics["modes"]["kg_enhanced_rag"]["failed_cases"] == 1
    assert statistics["modes"]["project_rag"]["latency_ms"]["median"] == 12
    assert statistics["runtime_bindings"]["embedding_models"] == ["rust-hash-512-v1"]
    assert statistics["runtime_bindings"]["index_versions"] == ["structured-v1"]


def test_derived_statistics_ignore_tampered_audit_snapshot() -> None:
    original = MODULE.derive_statistics(package())
    tampered = deepcopy(package())
    tampered["cases"][0]["citation_audit"].update(
        {"citation_count": 0, "invalid_citations": ["[S99]"], "passed": False}
    )

    assert MODULE.derive_statistics(tampered) == original


def test_rejects_evidence_count_drift() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["source_count"] = 2

    failures = MODULE.validate(invalid)

    assert any("source_count" in failure and "sources" in failure for failure in failures)


def test_rejects_untraceable_evidence_objects() -> None:
    invalid_source = deepcopy(package())
    invalid_source["cases"][0]["sources"][0].pop("chunk_id")

    source_failures = MODULE.validate(invalid_source)

    assert any("sources" in failure and "chunk_id" in failure for failure in source_failures)

    invalid_graph = deepcopy(package())
    invalid_graph["cases"][1]["graph_hit_count"] = 1
    invalid_graph["cases"][1]["graph_context"] = [{}]

    graph_failures = MODULE.validate(invalid_graph)

    assert any(
        "graph_context" in failure and "relation_id" in failure
        for failure in graph_failures
    )


def test_rejects_model_snapshot_binding_drift() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["embedding_model"] = "different-embedding-model"

    failures = MODULE.validate(invalid)

    assert any("embedding_model" in failure and "config_snapshot" in failure for failure in failures)


def test_rejects_logged_case_generation_model_drift() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["model"] = "different-generation-model"

    failures = MODULE.validate(invalid)

    assert any("case 1 model" in failure and "generation_model" in failure for failure in failures)


def test_rejects_logged_case_graph_schema_version_drift() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["retrieval_config"]["graph_schema_version"] = "kg-v2"

    failures = MODULE.validate(invalid)

    assert any(
        "case 1 retrieval_config.graph_schema_version" in failure
        for failure in failures
    )


def test_rejects_invalid_or_duplicate_query_log_ids() -> None:
    for query_log_ids in ([0, None], [True, None], ["99", None], [99, 99]):
        invalid = deepcopy(package())
        invalid["cases"][0]["query_log_id"] = query_log_ids[0]
        invalid["cases"][1]["query_log_id"] = query_log_ids[1]

        failures = MODULE.validate(invalid)

        assert any("query_log_id" in failure for failure in failures)


def test_rejects_duplicate_execution_orders() -> None:
    invalid = deepcopy(package())
    invalid["cases"][1]["execution_order"] = 1

    failures = MODULE.validate(invalid)

    assert any("execution_order" in failure for failure in failures)


def test_rejects_failed_case_without_error() -> None:
    invalid = deepcopy(package())
    invalid["cases"][1]["error"] = None

    failures = MODULE.validate(invalid)

    assert any("failed case" in failure for failure in failures)


def test_rejects_duplicate_summary_errors() -> None:
    invalid = deepcopy(package())
    invalid["summary"]["errors"].append(deepcopy(invalid["summary"]["errors"][0]))

    failures = MODULE.validate(invalid)

    assert any("duplicate summary error" in failure for failure in failures)


def test_rejects_failed_case_without_summary_error() -> None:
    invalid = deepcopy(package())
    invalid["summary"]["errors"] = []

    failures = MODULE.validate(invalid)

    assert any("summary error" in failure and "failed case" in failure for failure in failures)


def test_rejects_summary_error_metadata_drift() -> None:
    invalid = deepcopy(package())
    invalid["summary"]["errors"][0]["mode"] = "bm25_rag"

    failures = MODULE.validate(invalid)

    assert any("summary error does not match case field" in failure for failure in failures)


def test_rejects_failed_run_without_fatal_error() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["status"] = "failed"

    failures = MODULE.validate(invalid)

    assert any("fatal_error" in failure for failure in failures)


def test_accepts_failed_run_with_fatal_error_and_unexecuted_cases() -> None:
    valid = deepcopy(package())
    valid["experiment"]["status"] = "failed"
    valid["experiment"]["completed_cases"] = 0
    valid["experiment"]["failed_cases"] = 0
    valid["case_count"] = 0
    valid["cases"] = []
    valid["summary"]["errors"] = []
    valid["summary"]["unexecuted_cases"] = 2
    valid["summary"]["fatal_error"] = {
        "error": "Creator user no longer exists",
        "failure_scope": "run",
        "failure_code": "creator_user_missing",
    }

    assert MODULE.validate(valid) == []


def test_rejects_run_failure_without_structured_scope_and_code() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["status"] = "failed"
    invalid["experiment"]["completed_cases"] = 0
    invalid["experiment"]["failed_cases"] = 0
    invalid["case_count"] = 0
    invalid["cases"] = []
    invalid["summary"]["errors"] = []
    invalid["summary"]["unexecuted_cases"] = 2
    invalid["summary"]["fatal_error"] = {
        "error": "Experiment input binding drift detected",
        "failure_scope": "case",
        "failure_code": "query_error",
    }

    failures = MODULE.validate(invalid)

    assert any("failure_scope" in failure for failure in failures)


def test_accepts_input_binding_drift_as_a_run_level_failure() -> None:
    valid = deepcopy(package())
    valid["experiment"]["status"] = "failed"
    valid["experiment"]["completed_cases"] = 0
    valid["experiment"]["failed_cases"] = 0
    valid["case_count"] = 0
    valid["cases"] = []
    valid["summary"]["errors"] = []
    valid["summary"]["unexecuted_cases"] = 2
    valid["summary"]["fatal_error"] = {
        "error": "Experiment input binding drift detected: corpus snapshot changed",
        "failure_scope": "run",
        "failure_code": "input_binding_drift",
    }

    assert MODULE.validate(valid) == []


def test_rejects_case_failure_marked_as_run_level() -> None:
    invalid = deepcopy(package())
    invalid["cases"][1]["failure_scope"] = "run"
    invalid["cases"][1]["failure_code"] = "input_binding_drift"
    invalid["summary"]["errors"][0]["failure_scope"] = "run"
    invalid["summary"]["errors"][0]["failure_code"] = "input_binding_drift"

    failures = MODULE.validate(invalid)

    assert any("failure_scope" in failure for failure in failures)


def test_rejects_malformed_fatal_error() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["status"] = "failed"
    invalid["summary"]["fatal_error"] = {"error": " "}

    failures = MODULE.validate(invalid)

    assert any("fatal_error.error" in failure for failure in failures)


def test_rejects_fatal_error_on_non_failed_run() -> None:
    invalid = deepcopy(package())
    invalid["summary"]["fatal_error"] = {"error": "worker stopped"}

    failures = MODULE.validate(invalid)

    assert any("only be present" in failure for failure in failures)


def test_rejects_protocol_hash_drift() -> None:
    invalid = deepcopy(package())
    invalid["config_snapshot"]["experiment_protocol"]["execution_plan_hash"] = "b" * 64

    failures = MODULE.validate(invalid)

    assert any("execution_plan_hash" in failure for failure in failures)


def test_rejects_execution_plan_content_with_synchronized_stale_hash() -> None:
    invalid = deepcopy(package())
    invalid["summary"]["execution_plan"][0]["mode"] = "bm25_rag"

    failures = MODULE.validate(invalid)

    assert any("hash does not match" in failure for failure in failures)


def test_rejects_plan_drift_even_when_hashes_are_rewritten() -> None:
    invalid = deepcopy(package())
    invalid["summary"]["execution_plan"][0]["mode"] = "bm25_rag"
    plan_hash = MODULE.execution_plan_sha256(invalid["summary"]["execution_plan"])
    invalid["experiment"]["execution_plan_hash"] = plan_hash
    invalid["config_snapshot"]["experiment_protocol"]["execution_plan_hash"] = plan_hash

    failures = MODULE.validate(invalid)

    assert any("regenerated execution plan" in failure for failure in failures)


def test_rejects_total_cases_drift_from_regenerated_plan() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["total_cases"] = 3

    failures = MODULE.validate(invalid)

    assert any("total_cases" in failure and "regenerated" in failure for failure in failures)


def test_rejects_empty_questions_or_modes() -> None:
    for field in ("questions", "modes"):
        invalid = deepcopy(package())
        invalid["experiment"][field] = []
        invalid["experiment"]["total_cases"] = 0
        invalid["experiment"]["completed_cases"] = 0
        invalid["experiment"]["failed_cases"] = 0
        invalid["case_count"] = 0
        invalid["cases"] = []
        invalid["summary"]["unexecuted_cases"] = 0
        invalid["summary"]["execution_plan"] = []
        invalid["summary"]["errors"] = []
        plan_hash = MODULE.execution_plan_sha256([])
        invalid["experiment"]["execution_plan_hash"] = plan_hash
        invalid["config_snapshot"]["experiment_protocol"]["execution_plan_hash"] = plan_hash

        failures = MODULE.validate(invalid)

        assert any(field in failure for failure in failures)


def test_rejects_duplicate_or_malformed_questions() -> None:
    for questions in (["问题一", "问题一"], [" "], [123]):
        invalid = deepcopy(package())
        invalid["experiment"]["questions"] = questions

        failures = MODULE.validate(invalid)

        assert any("experiment.questions" in failure for failure in failures)


def test_rejects_malformed_modes_without_raising() -> None:
    for modes in (["project_rag", "project_rag"], [123], [["project_rag"]]):
        invalid = deepcopy(package())
        invalid["experiment"]["modes"] = modes

        failures = MODULE.validate(invalid)

        assert any("experiment.modes" in failure for failure in failures)


def test_rejects_overlong_question() -> None:
    invalid = deepcopy(package())
    invalid["experiment"]["questions"] = ["x" * 4_001]

    failures = MODULE.validate(invalid)

    assert any("4,000" in failure for failure in failures)


def test_rejects_zero_repetitions() -> None:
    invalid = deepcopy(package())
    invalid["config_snapshot"]["experiment_protocol"]["repetitions"] = 0

    failures = MODULE.validate(invalid)

    assert any("repetitions" in failure for failure in failures)


def test_rebuilds_randomized_execution_plan() -> None:
    protocol = {"repetitions": 2, "random_seed": 42, "randomize_order": True}

    plan = MODULE.regenerated_execution_plan(
        protocol,
        ["问题一", "问题二"],
        ["project_rag", "kg_enhanced_rag"],
    )

    assert len(plan) == 8
    assert [item["execution_order"] for item in plan] == list(range(1, 9))
    assert len({(item["question_index"], item["repetition_index"], item["mode"]) for item in plan}) == 8


def test_randomized_plan_matches_rust_value_display_for_special_characters() -> None:
    plan = MODULE.regenerated_execution_plan(
        {"repetitions": 1, "random_seed": 42, "randomize_order": True},
        ["问题:一", '问题"二'],
        ["project_rag", "kg_enhanced_rag"],
    )

    assert [
        (item["question_index"], item["mode"])
        for item in plan
    ] == [
        (2, "project_rag"),
        (2, "kg_enhanced_rag"),
        (1, "kg_enhanced_rag"),
        (1, "project_rag"),
    ]


def test_rejects_case_metadata_drift_from_execution_plan() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["mode"] = "bm25_rag"

    failures = MODULE.validate(invalid)

    assert any("execution plan" in failure for failure in failures)


def test_rejects_completed_package_with_missing_plan_case() -> None:
    invalid = deepcopy(package())
    invalid["cases"].pop()
    invalid["case_count"] = 1
    invalid["experiment"]["failed_cases"] = 0

    failures = MODULE.validate(invalid)

    assert any("every planned case" in failure for failure in failures)


def test_accepts_interrupted_package_with_unexecuted_cases() -> None:
    partial = deepcopy(package())
    partial["experiment"]["status"] = "interrupted"
    partial["experiment"]["completed_cases"] = 1
    partial["experiment"]["failed_cases"] = 0
    partial["case_count"] = 1
    partial["cases"].pop()
    partial["summary"]["errors"] = []
    partial["summary"]["unexecuted_cases"] = 1

    assert MODULE.validate(partial) == []


def test_rejects_unexecuted_case_count_drift() -> None:
    invalid = deepcopy(package())
    invalid["summary"]["unexecuted_cases"] = 1

    failures = MODULE.validate(invalid)

    assert any("unexecuted_cases" in failure for failure in failures)


def test_rejects_citation_audit_field_drift() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["citation_audit"]["citation_count"] = 0

    failures = MODULE.validate(invalid)

    assert any("citation_audit" in failure for failure in failures)


def test_rejects_out_of_range_citation_marker() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["answer"] = "回答 [S2]"

    failures = MODULE.validate(invalid)

    assert any("invalid citation" in failure for failure in failures)


def test_rejects_range_citation_marker_even_when_recorded_as_invalid() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["answer"] = "回答 [S1-S2]"
    invalid["cases"][0]["citation_audit"].update(
        {
            "passed": False,
            "citation_count": 1,
            "invalid_citations": ["[S1-S2]"],
            "message": "发现 1 个不存在的证据编号：[S1-S2]。",
        }
    )

    failures = MODULE.validate(invalid)

    assert any("invalid citation" in failure for failure in failures)


def test_rejects_false_negative_citation_audit() -> None:
    invalid = deepcopy(package())
    invalid["cases"][0]["citation_audit"]["passed"] = False
    invalid["cases"][0]["citation_audit"]["message"] = "人工复核"

    failures = MODULE.validate(invalid)

    assert any("citation_audit passed" in failure for failure in failures)


def test_accepts_production_audit_for_uncited_key_fact_paragraph() -> None:
    valid = deepcopy(package())
    valid["cases"][0]["answer"] = "实验结果显示系统有提升。\n\n来源：[S1]"
    valid["cases"][0]["citation_audit"]["passed"] = False
    valid["cases"][0]["citation_audit"]["message"] = "关键事实段落缺少同段引用"

    assert MODULE.validate(valid) == []


def test_cli_writes_machine_readable_result(tmp_path: Path) -> None:
    package_path = tmp_path / "evidence.json"
    output_path = tmp_path / "check.json"
    package_path.write_text(json.dumps(package(), ensure_ascii=False), encoding="utf-8")

    result = MODULE.check_file(package_path, output_path)

    assert result["passed"] is True
    assert json.loads(output_path.read_text(encoding="utf-8")) == result
