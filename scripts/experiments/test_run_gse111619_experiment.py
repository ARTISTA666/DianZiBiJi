from __future__ import annotations

import csv
import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "run_gse111619_experiment.py"
SPEC = importlib.util.spec_from_file_location("gse111619_experiment", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_run_experiment_waits_for_background_completion(monkeypatch) -> None:
    class FakeApi:
        client = SimpleNamespace(
            get=lambda _path: SimpleNamespace(is_success=True, status_code=200, text="\ufeffcsv-body")
        )

        def get(self, path):
            if path == "/projects":
                return [{"id": 7, "name": MODULE.PROJECT_NAME}]
            return {"id": 9, "status": "completed", "completed_cases": 1, "failed_cases": 0}

        @staticmethod
        def post(_path, **_kwargs):
            return {"id": 9, "status": "queued"}

    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

    run, csv_text = MODULE.run_experiment(
        FakeApi(),
        [{"question": "probe"}],
        "background probe",
        modes=("pure_llm",),
        repetitions=1,
    )

    assert run["status"] == "completed"
    assert csv_text == "csv-body"


def test_question_set_has_20_sequential_cases_and_gold_facts() -> None:
    cases = MODULE.load_cases(ROOT / "data" / "real" / "GSE111619" / "gse111619_questions.json")

    assert len(cases) == 20
    assert sum(len(case["facts"]) for case in cases) >= 50


def test_holdout_question_set_is_frozen_and_supports_relation_facts() -> None:
    path = ROOT / "data" / "real" / "GSE111619" / "gse111619_kg_holdout_questions.json"
    cases = MODULE.load_cases(path)

    assert len(cases) == 12
    assert MODULE.verify_holdout_freeze(path)["question_count"] == 12
    assert MODULE.fact_matches(MODULE.normalize("GSM3035187 对应 SRX3777458"), cases[0]["facts"][0])
    assert not MODULE.fact_matches(MODULE.normalize("GSM3035187 对应 SRX3777459"), cases[0]["facts"][0])
    assert [case["id"] for case in MODULE.select_cases(cases, "H02,H10")] == ["H02", "H10"]


def test_saved_internal_evaluation_recomputes_from_raw_csv() -> None:
    data_dir = ROOT / "data" / "real" / "GSE111619"
    cases = MODULE.load_cases(data_dir / "gse111619_kg_holdout_questions.json")
    result = MODULE.score_export(
        cases,
        (data_dir / "gse111619_kg_holdout_experiment.csv").read_text(encoding="utf-8-sig"),
    )
    summaries = {item["mode"]: item for item in result["mode_summary"]}

    plain = summaries["project_rag"]
    graph = summaries["kg_enhanced_rag"]
    assert (plain["hit_facts"], plain["total_facts"]) == (9, 32)
    assert (graph["hit_facts"], graph["total_facts"]) == (25, 32)
    assert (graph["hit_facts"] - plain["hit_facts"]) / plain["total_facts"] == 0.5
    assert result["paired_comparison"]["mean_fact_coverage_delta"] == 0.5
    assert graph["forbidden_fact_hits"] == 5
    assert plain["forbidden_fact_hits"] == 1


def test_scores_each_mode_without_treating_coverage_as_accuracy() -> None:
    cases = MODULE.load_cases(ROOT / "data" / "real" / "GSE111619" / "gse111619_questions.json")
    output = io.StringIO()
    fieldnames = [
        "question_index",
        "mode",
        "status",
        "query_log_id",
        "answer",
        "source_count",
        "graph_hit_count",
        "response_ms",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for index, case in enumerate(cases, start=1):
        all_facts = " ".join(fact["aliases"][0] for fact in case["facts"])
        writer.writerow({
            "question_index": index,
            "mode": "project_rag",
            "status": "completed",
            "query_log_id": index,
            "answer": f"{all_facts} [S1]",
            "source_count": 2,
            "graph_hit_count": 0,
            "response_ms": 100,
        })
        writer.writerow({
            "question_index": index,
            "mode": "kg_enhanced_rag",
            "status": "completed",
            "query_log_id": index + 20,
            "answer": "[S3][G5]",
            "source_count": 2,
            "graph_hit_count": 4,
            "response_ms": 120,
        })

    result = MODULE.score_export(cases, output.getvalue())

    summaries = {item["mode"]: item for item in result["mode_summary"]}
    assert summaries["project_rag"]["micro_fact_coverage"] == 1.0
    assert summaries["kg_enhanced_rag"]["micro_fact_coverage"] == 0.0
    assert summaries["project_rag"]["closed_set_exact_case_accuracy"] == 1.0
    assert summaries["kg_enhanced_rag"]["closed_set_exact_case_accuracy"] == 0.0
    assert result["metric"] == "deterministic alias-based gold-fact coverage"
    assert "accuracy" not in result["metric"].lower()
    citation_audit = result["citation_marker_audit"]
    assert citation_audit["source_marker_answer_rate"] == 1.0
    assert citation_audit["evidence_marker_answer_rate"] == 1.0
    assert citation_audit["kg_graph_marker_rate_when_context_available"] == 1.0
    assert len(citation_audit["invalid_source_marker_rows"]) == 20
    assert len(citation_audit["invalid_graph_marker_rows"]) == 20
    assert citation_audit["all_citation_indices_in_range"] is False
    paired = result["paired_comparison"]
    assert paired["kg_improved_cases"] == 0
    assert paired["kg_worse_cases"] == 20
    assert paired["kg_exact_only_cases"] == 0
    assert paired["plain_exact_only_cases"] == 20


def test_scores_five_modes_with_repetitions_without_inflating_macro_coverage() -> None:
    cases = MODULE.load_cases(
        ROOT / "data" / "real" / "GSE111619" / "gse111619_kg_holdout_questions.json"
    )[:1]
    output = io.StringIO()
    fieldnames = [
        "question_index",
        "mode",
        "repetition_index",
        "execution_order",
        "status",
        "query_log_id",
        "answer",
        "source_count",
        "graph_hit_count",
        "response_ms",
        "provider",
        "model",
        "prompt_version",
        "usage_json",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    answer = " ".join(
        alternative
        for fact in cases[0]["facts"]
        for group in fact["terms"]
        for alternative in group[:1]
    )
    execution_order = 0
    for repetition_index in (1, 2):
        for mode in MODULE.MODES:
            execution_order += 1
            writer.writerow(
                {
                    "question_index": 1,
                    "mode": mode,
                    "repetition_index": repetition_index,
                    "execution_order": execution_order,
                    "status": "completed",
                    "query_log_id": execution_order,
                    "answer": answer,
                    "source_count": 1,
                    "graph_hit_count": 1,
                    "response_ms": 100,
                    "provider": "deepseek",
                    "model": "test",
                    "prompt_version": "test-v1",
                    "usage_json": '{"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}',
                }
            )

    result = MODULE.score_export(cases, output.getvalue(), MODULE.MODES, repetitions=2)
    summaries = {item["mode"]: item for item in result["mode_summary"]}

    assert result["repetitions"] == 2
    assert summaries["project_rag"]["completed"] == 2
    assert summaries["project_rag"]["macro_fact_coverage"] == 1.0
    assert summaries["project_rag"]["total_tokens"] == 30
    assert result["comparisons_vs_project_rag"]["kg_enhanced_rag"]["paired_case_count"] == 2
