from __future__ import annotations

import importlib.util
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit" / "audit_rag_five_mode_bundle.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("audit_rag_five_mode_bundle", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _audit_with_report_copy(tmp_path: Path, mutate) -> dict:
    report_path = ROOT / "data/real/experiment-5/internal-five-mode-experiment-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    mutate(report)
    mutated_path = tmp_path / "mutated-report.json"
    mutated_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return MODULE.audit_bundle(
        mutated_path,
        ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv",
        ROOT / "data/real/experiment-5/run-config.json",
        ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json",
        ROOT / "docs/experiments/rag-experiment-5-internal-freeze-manifest-v2.json",
        ROOT,
    )


def _audit_with_csv_copy(tmp_path: Path, mutate, row_index: int = 0) -> dict:
    source_path = ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv"
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
    assert fieldnames
    mutate(rows[row_index])
    extra_fields = sorted(set().union(*(row.keys() for row in rows)) - set(fieldnames))
    fieldnames.extend(extra_fields)
    csv_path = tmp_path / "mutated-experiment.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return MODULE.audit_bundle(
        ROOT / "data/real/experiment-5/internal-five-mode-experiment-report.json",
        csv_path,
        ROOT / "data/real/experiment-5/run-config.json",
        ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json",
        ROOT / "docs/experiments/rag-experiment-5-internal-freeze-manifest-v2.json",
        ROOT,
    )


def test_internal_bundle_exposes_citation_and_freeze_failures() -> None:
    result = MODULE.audit_bundle(
        ROOT / "data/real/experiment-5/internal-five-mode-experiment-report.json",
        ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv",
        ROOT / "data/real/experiment-5/run-config.json",
        ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json",
        ROOT / "docs/experiments/rag-experiment-5-internal-freeze-manifest-v2.json",
        ROOT,
    )

    assert result["consistency_passed"] is False
    assert result["paper_ready"] is False
    paper_gate_check = next(
        item for item in result["checks"] if item["name"] == "paper_gate_consistent"
    )
    assert paper_gate_check["passed"] is True
    assert paper_gate_check["actual"]["paper_ready"] is False
    assert result["row_integrity"]["actual_rows"] == 180
    assert result["row_integrity"]["question_texts_bound"] is True
    assert result["row_integrity"]["runtime_bindings_bound"] is True
    assert len(result["recomputed_mode_summary"]) == 5
    assert len(result["recomputed_comparisons_vs_project_rag"]) == 4
    assert next(
        item for item in result["checks"] if item["name"] == "mode_summary_recomputed_matches_report"
    )["passed"]
    assert next(
        item for item in result["checks"] if item["name"] == "paired_comparisons_recomputed_match_report"
    )["passed"]
    assert next(item for item in result["checks"] if item["name"] == "csv_question_texts_bound")["passed"] is True
    assert next(item for item in result["checks"] if item["name"] == "csv_runtime_bindings_bound")["passed"] is True
    assert next(item for item in result["checks"] if item["name"] == "csv_retrieval_bindings_bound")["passed"] is False
    assert next(item for item in result["checks"] if item["name"] == "retrieval_gap_summary_valid")["passed"] is True
    assert result["row_integrity"]["retrieval_bindings_bound"] is False
    assert len(result["citation_audit"]["invalid_marker_rows"]) == 4
    failure = result["citation_audit"]["invalid_marker_rows"][0]
    assert {"question_index", "question_id", "mode", "repetition_index", "query_log_id"} <= set(failure)
    assert failure["question_id"].startswith("H")
    assert failure["query_log_id"] > 0
    assert result["citation_audit"]["by_mode"]["bm25_rag"]["invalid_marker_rows"] == 4
    assert "input_freeze_manifest_verifies" in [item["name"] for item in result["checks"] if not item["passed"]]
    assert "citation_audit_recomputed_matches_report" in [item["name"] for item in result["checks"] if not item["passed"]]
    assert "app_revision_is_bound" in result["paper_blockers"]
    assert "independent_human_review_present" in result["paper_blockers"]
    assert result["paper_blocker_archive_mapping"] == [
        {
            "check_name": "report_scope_is_internal_only",
            "archive_item": "范围声明（不属于八项最低清单）",
            "requirement": "明确区分内部开发证据与确认性证据",
        },
        {
            "check_name": "app_revision_is_bound",
            "archive_item": "8. 版本归档",
            "requirement": "代码 revision 与运行时版本可复核",
        },
        {
            "check_name": "external_freeze_inputs_present",
            "archive_item": "1. 数据绑定",
            "requirement": "语料快照、文件清单与哈希齐备",
        },
        {
            "check_name": "multi_project_question_set_ready",
            "archive_item": "2. 问题集绑定",
            "requirement": "至少 3 个项目、至少 60 题",
        },
        {
            "check_name": "independent_human_review_present",
            "archive_item": "6. 人工评价",
            "requirement": "双人盲评、签核与一致性统计齐备",
        },
        {
            "check_name": "confirmatory_evidence_package_present",
            "archive_item": "4. 逐案例证据",
            "requirement": "同批次 v1 证据包与逐案例证据齐备",
        },
    ]


def test_invalid_citation_range_is_not_counted_as_valid(tmp_path: Path) -> None:
    answer = "事实 [G1-G2]"
    tokens = list(MODULE.CITATION_TOKEN_RE.finditer(answer))
    markers = MODULE.CITATION_RE.findall(answer)

    assert tokens[0].group(0) == "[G1-G2]"
    assert markers == []
    assert MODULE.CITATION_RE.fullmatch(tokens[0].group(0)) is None


def test_citation_audit_requires_exact_invalid_marker_identity() -> None:
    recomputed_invalid_rows = [
        {
            "question_id": "H04",
            "repetition_index": 1,
            "mode": "bm25_rag",
            "markers": ["[S1-S12]"],
        }
    ]
    recomputed_out_of_range_rows: list[dict] = []
    report_audit = {
        "invalid_source_marker_rows": [
            {
                "case_id": "H99",
                "repetition_index": 1,
                "mode": "bm25_rag",
                "markers": [12],
            }
        ],
        "invalid_graph_marker_rows": [],
        "all_citation_indices_in_range": True,
    }

    assert MODULE.citation_audit_matches_report(
        recomputed_invalid_rows,
        recomputed_out_of_range_rows,
        report_audit,
        recomputed_all_indices_in_range=False,
    ) is False


def test_citation_audit_rejects_nonempty_but_wrong_report_rows(tmp_path: Path) -> None:
    def mutate(report: dict) -> None:
        report["objective_evaluation"]["citation_marker_audit"]["invalid_source_marker_rows"] = [
            {
                "case_id": "H99",
                "repetition_index": 1,
                "mode": "bm25_rag",
                "markers": [12],
            }
        ]

    result = _audit_with_report_copy(tmp_path, mutate)
    assert result["citation_audit"]["reported_audit_mismatch"] is True


def test_citation_audit_requires_method_level_summary_binding() -> None:
    recomputed = {
        "completed_answer_count": 2,
        "answers_with_source_marker": 1,
        "answers_with_any_evidence_marker": 2,
        "kg_answers_with_graph_context": 1,
        "kg_answers_with_graph_marker": 1,
        "strict_source_marker_answer_rate": 0.5,
        "strict_evidence_marker_answer_rate": 1.0,
        "kg_graph_marker_rate_when_context_available": 1.0,
        "all_strict_citation_indices_in_range": True,
        "by_mode": {
            "bm25_rag": {
                "completed": 2,
                "with_source_marker": 1,
                "with_graph_marker": 0,
                "with_any_evidence_marker": 1,
                "invalid_marker_rows": 0,
                "invalid_source_marker_rows": 0,
                "invalid_graph_marker_rows": 0,
                "source_marker_answer_rate": 0.5,
                "graph_marker_answer_rate": 0.0,
                "evidence_marker_answer_rate": 0.5,
            }
        },
    }
    reported = json.loads(json.dumps(recomputed))
    reported["source_marker_answer_rate"] = 0.0
    reported["by_mode"]["bm25_rag"]["source_marker_answer_rate"] = 0.0

    mismatches = MODULE.citation_audit_summary_mismatches(recomputed, reported)

    assert {item["field"] for item in mismatches} >= {"source_marker_answer_rate"}
    assert any(item.get("mode") == "bm25_rag" for item in mismatches)


def test_report_method_level_citation_summary_drift_is_detected(tmp_path: Path) -> None:
    def mutate(report: dict) -> None:
        report["objective_evaluation"]["citation_marker_audit"]["by_mode"]["bm25_rag"][
            "source_marker_answer_rate"
        ] = 0.0

    result = _audit_with_report_copy(tmp_path, mutate)
    mismatches = result["citation_audit"]["reported_summary_mismatches"]

    assert any(item.get("mode") == "bm25_rag" for item in mismatches)
    assert any(item["field"] == "source_marker_answer_rate" for item in mismatches)
    assert next(
        item for item in result["checks"] if item["name"] == "citation_audit_recomputed_matches_report"
    )["passed"] is False


def test_question_set_hash_is_calculated_from_bytes(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([{"id": "Q1"}], ensure_ascii=False), encoding="utf-8")

    assert MODULE.sha256_file(path) == __import__("hashlib").sha256(path.read_bytes()).hexdigest()


def test_mode_summary_report_drift_is_detected(tmp_path: Path) -> None:
    def mutate(report: dict) -> None:
        summary = report["objective_evaluation"]["mode_summary"][0]
        summary["hit_facts"] += 1

    result = _audit_with_report_copy(tmp_path, mutate)
    check = next(item for item in result["checks"] if item["name"] == "mode_summary_recomputed_matches_report")
    assert check["passed"] is False
    assert any(item["field"] == "hit_facts" for item in check["actual"])


def test_paired_comparison_report_drift_is_detected(tmp_path: Path) -> None:
    def mutate(report: dict) -> None:
        comparison = report["objective_evaluation"]["comparisons_vs_project_rag"]["kg_enhanced_rag"]
        comparison["mean_response_time_delta_ms"] += 1

    result = _audit_with_report_copy(tmp_path, mutate)
    check = next(item for item in result["checks"] if item["name"] == "paired_comparisons_recomputed_match_report")
    assert check["passed"] is False
    assert any(item["field"] == "mean_response_time_delta_ms" for item in check["actual"])


def test_csv_question_index_binding_failure_is_explicit(tmp_path: Path) -> None:
    result = _audit_with_csv_copy(tmp_path, lambda row: row.update(question_index="999"))

    assert result["consistency_passed"] is False
    assert result["row_integrity"]["question_indices_bound"] is False
    assert next(item for item in result["checks"] if item["name"] == "csv_question_indices_bound")["passed"] is False
    assert any(item["name"] == "row_2_question_index_bound" for item in result["checks"])


def test_csv_question_text_binding_failure_is_explicit(tmp_path: Path) -> None:
    result = _audit_with_csv_copy(tmp_path, lambda row: row.update(question="篡改后的题干"))

    assert result["consistency_passed"] is False
    assert result["row_integrity"]["question_texts_bound"] is False
    assert next(item for item in result["checks"] if item["name"] == "csv_question_texts_bound")["passed"] is False
    assert any(item["name"] == "row_2_question_text_matches" for item in result["checks"])


def test_csv_runtime_binding_failure_is_explicit(tmp_path: Path) -> None:
    result = _audit_with_csv_copy(tmp_path, lambda row: row.update(prompt_version="tampered-prompt-v0"))

    assert result["consistency_passed"] is False
    assert result["row_integrity"]["runtime_bindings_bound"] is False
    assert next(item for item in result["checks"] if item["name"] == "csv_runtime_bindings_bound")["passed"] is False
    assert any(item["name"] == "row_2_prompt_version_matches" for item in result["checks"])


def test_csv_retrieval_snapshot_binding_failure_is_explicit() -> None:
    result = MODULE.audit_bundle(
        ROOT / "data/real/experiment-5/internal-five-mode-experiment-report.json",
        ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv",
        ROOT / "data/real/experiment-5/run-config.json",
        ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json",
        ROOT / "docs/experiments/rag-experiment-5-internal-freeze-manifest-v2.json",
        ROOT,
    )

    assert result["consistency_passed"] is False
    assert result["row_integrity"]["retrieval_bindings_bound"] is False
    assert next(item for item in result["checks"] if item["name"] == "csv_retrieval_bindings_bound")["passed"] is False


def test_retrieval_binding_gap_summary_is_method_and_field_scoped() -> None:
    result = MODULE.audit_bundle(
        ROOT / "data/real/experiment-5/internal-five-mode-experiment-report.json",
        ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv",
        ROOT / "data/real/experiment-5/run-config.json",
        ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json",
        ROOT / "docs/experiments/rag-experiment-5-internal-freeze-manifest-v2.json",
        ROOT,
    )

    gaps = result["row_integrity"]["retrieval_binding_gaps"]
    assert gaps["pure_llm"] == {
        "required_fields": [],
        "row_count": 36,
        "rows_with_complete_snapshot": 36,
        "rows_with_any_gap": 0,
        "missing_by_field": {},
        "mismatch_by_field": {},
    }
    assert gaps["bm25_rag"]["row_count"] == 36
    assert gaps["bm25_rag"]["missing_by_field"]["corpus_snapshot_hash"] == 36
    assert gaps["bm25_rag"]["rows_with_any_gap"] == 36
    assert gaps["project_rag"]["missing_by_field"]["embedding_model"] == 36
    assert gaps["structured_query"]["missing_by_field"]["graph_schema_version"] == 36
    assert gaps["kg_enhanced_rag"]["missing_by_field"]["graph_min_score"] == 36


def test_retrieval_binding_gap_summary_counts_nonempty_drift(tmp_path: Path) -> None:
    def mutate(row: dict[str, str]) -> None:
        row.update(corpus_snapshot_hash="wrong-corpus-hash")

    source_path = ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv"
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    bm25_row_index = next(index for index, row in enumerate(rows) if row["mode"] == "bm25_rag")
    result = _audit_with_csv_copy(tmp_path, mutate, bm25_row_index)
    gap = result["row_integrity"]["retrieval_binding_gaps"]["bm25_rag"]

    assert gap["row_count"] == 36
    assert gap["rows_with_any_gap"] == 36
    assert gap["missing_by_field"]["corpus_snapshot_hash"] == 35
    assert gap["mismatch_by_field"]["corpus_snapshot_hash"] == 1


def test_retrieval_gap_summary_validator_reports_impossible_partition() -> None:
    result = MODULE.audit_bundle(
        ROOT / "data/real/experiment-5/internal-five-mode-experiment-report.json",
        ROOT / "data/real/experiment-5/internal-five-mode-experiment.csv",
        ROOT / "data/real/experiment-5/run-config.json",
        ROOT / "data/real/GSE111619/gse111619_kg_holdout_questions.json",
        ROOT / "docs/experiments/rag-experiment-5-internal-freeze-manifest-v2.json",
        ROOT,
    )
    gaps = json.loads(json.dumps(result["row_integrity"]["retrieval_binding_gaps"]))
    gaps["bm25_rag"]["rows_with_complete_snapshot"] = 35
    gaps["bm25_rag"]["missing_by_field"]["corpus_snapshot_hash"] = 37

    violations = MODULE.retrieval_gap_summary_violations(gaps)

    assert {item["kind"] for item in violations} >= {
        "row_partition",
        "field_count_exceeds_any_gap_rows",
    }


def test_csv_repetition_and_method_binding_failures_are_explicit(tmp_path: Path) -> None:
    def mutate(row: dict[str, str]) -> None:
        row.update(repetition_index="0", mode="unknown_mode")

    result = _audit_with_csv_copy(tmp_path, mutate)

    assert result["consistency_passed"] is False
    assert result["row_integrity"]["repetition_indices_bound"] is False
    assert result["row_integrity"]["methods_bound"] is False
    assert next(item for item in result["checks"] if item["name"] == "csv_repetition_indices_bound")["passed"] is False
    assert next(item for item in result["checks"] if item["name"] == "csv_methods_bound")["passed"] is False
    assert any(item["name"] == "row_2_mode_supported" for item in result["checks"])
