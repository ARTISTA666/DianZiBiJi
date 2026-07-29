from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import freeze_system_evidence as SYSTEM_FREEZE  # noqa: E402

SCRIPT = ROOT / "scripts" / "release_maturity_gate.py"
SPEC = importlib.util.spec_from_file_location("release_maturity_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
from freeze_preregistration import build_manifest, sha256_file, write_manifest  # noqa: E402


COMMIT = "a" * 40


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def write_lockfiles(root: Path) -> dict[str, Path]:
    lockfiles = {
        "backend/Cargo.lock": root / "backend" / "Cargo.lock",
        "frontend/package-lock.json": root / "frontend" / "package-lock.json",
    }
    for relative_path, path in lockfiles.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"locked: {relative_path}\n", encoding="utf-8")
    return lockfiles


def system_manifest(files: list[Path], root: Path, commit: str = COMMIT) -> dict:
    lockfiles = write_lockfiles(root)
    manifest = build_manifest(files, root)
    manifest.update(
        {
            "schema": SYSTEM_FREEZE.SYSTEM_MANIFEST_SCHEMA,
            "schema_version": SYSTEM_FREEZE.SYSTEM_MANIFEST_SCHEMA_VERSION,
            "generator": SYSTEM_FREEZE.SYSTEM_MANIFEST_GENERATOR,
            "generator_version": SYSTEM_FREEZE.SYSTEM_MANIFEST_GENERATOR_VERSION,
            "provenance": {
                "git_commit": commit,
                "git_worktree_clean": True,
                "lockfiles": {
                    relative_path: {"sha256": sha256_file(path)}
                    for relative_path, path in lockfiles.items()
                },
            },
        }
    )
    return manifest


def retrieval_report(recall10: float = 0.95) -> dict:
    return {
        "question_count": 20,
        "fact_count": 56,
        "corpus": {"chunk_count": 984},
        "aggregate": [
            {"mode": "hybrid_rag", "Recall@10": 0.80, "nDCG@10": 0.70},
            {"mode": "graph_enhanced_rag", "Recall@10": recall10, "nDCG@10": 0.75},
        ],
    }


def experiment_report(coverage: float = 0.90, forbidden: int = 0, missing_mode: str | None = None, failed_mode: str | None = None) -> dict:
    modes = ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"]
    mode_summary = [
        {
            "mode": mode,
            "completed": 12,
            "failed": 1 if mode == failed_mode else 0,
            "micro_fact_coverage": coverage if mode == "kg_enhanced_rag" else 0.50,
            "closed_set_exact_case_accuracy": 0.75 if mode == "kg_enhanced_rag" else 0.40,
            "forbidden_fact_hits": forbidden if mode == "kg_enhanced_rag" else 0,
        }
        for mode in modes
        if mode != missing_mode
    ]
    return {
        "methods": [mode for mode in modes if mode != missing_mode],
        "objective_evaluation": {
            "mode_summary": mode_summary,
            "citation_marker_audit": {
                "all_citation_indices_in_range": True,
                "source_marker_answer_rate": 0.1,
                "kg_graph_marker_rate_when_context_available": 1.0,
                "by_mode": {
                    "pure_llm": {"source_marker_answer_rate": 0.0, "graph_marker_answer_rate": 0.0},
                    "kg_enhanced_rag": {"source_marker_answer_rate": 1.0, "graph_marker_answer_rate": 1.0},
                },
            },
        }
    }


def system_evidence_report(unexpected: int = 0, f1: float = 1.0) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": now,
        "runtime": {
            "ok": True,
            "captured_at": now,
            "metrics": {"ok": True, "payload": {"total_requests": 12, "p95_duration_ms": 10}},
        },
        "load_smoke": {"ok": True, "requests": 90, "successful": 90, "errors": [], "p95_ms": 100},
        "restart_recovery": {"ok": True, "run_id": 7, "interrupted": True, "resumed_status": "completed"},
        "soak_smoke": {"ok": True, "summary": {"cycles": 2, "p95_ms": 100}},
        "npm_audit": {"ok": True, "vulnerabilities": {"total": 0}},
        "production_config": {"ok": True, "status": "passed"},
        "secret_hygiene": {"ok": True, "leaks": []},
        "secret_rotation": {"ok": True, "checks": []},
        "backup_policy": {"ok": True, "checks": []},
        "monitoring_alerts": {"ok": True, "checks": []},
        "reverse_proxy": {"ok": True, "checks": []},
        "playwright": {
            "captured_at": now,
            "stats": {"expected": 4, "unexpected": unexpected, "skipped": 0},
            "tests": [
                {"title": "登录并完成笔记审批", "status": "passed"},
                {"title": "图片 OCR、人工校对、入库、问答和五方法实验形成闭环", "status": "passed"},
                {"title": "独立评价人只能在盲评页面提交评价", "status": "passed"},
                {"title": "系统管理员完成账号、小组和审计闭环", "status": "passed"},
            ],
        },
        "knowledge_graph": {"f1": f1},
        "backup": {"ok": True, "dump_readable": True},
        "restore_drill": {"ok": True, "database": {"public_table_count": 12}, "storage": {"restored": True}},
    }


def agent_report(**overrides: object) -> dict:
    report = {
        "task_types": ["experiment_summary", "weekly_report", "stage_report", "graph_overview"],
        "completed_runs": 4,
        "failed_runs": 0,
        "needs_review_runs": 0,
        "invalid_citations": 0,
    }
    report.update(overrides)
    return report


def test_default_gate_inputs_use_the_frozen_main_artifacts() -> None:
    assert MODULE.DEFAULT_RETRIEVAL_REPORT.parent.name == "main-retrieval-evaluation"
    assert MODULE.DEFAULT_EXPERIMENT_REPORT.name == "main_v8_kg_holdout_experiment_report.json"
    assert MODULE.DEFAULT_AGENT_REPORT.name == "main_v8_agent_probe_report.json"
    assert MODULE.DEFAULT_EVIDENCE_MANIFEST == SYSTEM_FREEZE.DEFAULT_OUTPUT
    assert MODULE.DEFAULT_EVIDENCE_MANIFEST == ROOT / "output" / "release-evidence" / "maturity-evidence-manifest.json"


def test_gate_fails_closed_when_evidence_manifest_is_not_supplied(tmp_path: Path) -> None:
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    assert report["passed"] is False
    assert "maturity evidence manifest" in {item["name"] for item in report["failures"]}
    assert report["source_revision"] is None


def test_gate_fails_current_maturity_blockers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "DEFAULT_SYSTEM_EVIDENCE_REPORT", tmp_path / "missing-system.json")
    monkeypatch.setattr(MODULE, "DEFAULT_AGENT_REPORT", tmp_path / "missing-agent.json")
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report(recall10=0.77)),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report(coverage=0.78, forbidden=5)),
            agent_report=None,
            system_evidence_report=None,
            evidence_manifest=None,
        )
    )

    failure_names = {item["name"] for item in report["failures"]}
    assert "graph Recall@10" in failure_names
    assert "kg micro fact coverage" in failure_names
    assert "kg forbidden fact hits" in failure_names
    assert "agent live maturity evidence" in failure_names
    assert "system evidence report" in failure_names


def test_gate_reports_corrupt_retrieval_without_crashing(tmp_path: Path) -> None:
    retrieval = tmp_path / "retrieval.json"
    retrieval.write_text("{not json", encoding="utf-8")

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=retrieval,
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    assert "retrieval report" in {item["name"] for item in report["failures"]}


def test_gate_reports_non_object_experiment_without_crashing(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment.json"
    experiment.write_text("[]", encoding="utf-8")

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=experiment,
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    assert "experiment report" in {item["name"] for item in report["failures"]}


def test_gate_reports_malformed_retrieval_structure_without_crashing(tmp_path: Path) -> None:
    malformed = retrieval_report()
    malformed["aggregate"] = [{"mode": "hybrid_rag", "Recall@10": 0.8, "nDCG@10": 0.7}]

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", malformed),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    assert "retrieval evidence structure" in {item["name"] for item in report["failures"]}


def test_gate_reports_malformed_experiment_structure_without_crashing(tmp_path: Path) -> None:
    malformed = {"objective_evaluation": {"mode_summary": "not rows"}}

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", malformed),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    assert "RAG experiment evidence structure" in {item["name"] for item in report["failures"]}


def test_gate_auto_uses_default_agent_report_when_present(tmp_path: Path, monkeypatch) -> None:
    default_agent = write_json(
        tmp_path / "agent_probe_report.json",
        agent_report(),
    )
    monkeypatch.setattr(MODULE, "DEFAULT_AGENT_REPORT", default_agent)

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=None,
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    assert all(item["passed"] for item in report["groups"]["agent"])
    assert report["inputs"]["agent_report"] == str(default_agent)


def test_gate_fails_when_agent_has_failed_runs(tmp_path: Path) -> None:
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report(failed_runs=1)),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    assert "agent failed runs" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_agent_task_coverage_is_incomplete(tmp_path: Path) -> None:
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report(task_types=["experiment_summary"])),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    assert "agent required task coverage" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_experiment_missing_required_method(tmp_path: Path) -> None:
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report(missing_mode="bm25_rag")),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    coverage_failure = next(item for item in report["failures"] if item["name"] == "experiment required method coverage")
    assert coverage_failure["actual"] == ["bm25_rag"]


def test_gate_fails_when_any_required_experiment_method_failed(tmp_path: Path) -> None:
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report(failed_mode="project_rag")),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=None,
        )
    )

    failed_modes = next(item for item in report["failures"] if item["name"] == "experiment required methods failed cases")
    assert failed_modes["actual"] == ["project_rag"]


def test_gate_fails_when_playwright_has_unexpected_failures(tmp_path: Path) -> None:
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report(unexpected=1)),
            evidence_manifest=None,
        )
    )

    assert "playwright unexpected tests" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_playwright_stats_claim_tests_without_raw_results(tmp_path: Path) -> None:
    system = system_evidence_report()
    system["playwright"]["tests"] = []
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    failure_names = {item["name"] for item in report["failures"]}
    assert "playwright result count" in failure_names
    assert "playwright all test results passed" in failure_names


def test_gate_rejects_stale_runtime_and_browser_evidence(tmp_path: Path) -> None:
    system = system_evidence_report()
    system["generated_at"] = "2020-01-01T00:00:00+00:00"
    system["runtime"]["captured_at"] = "2020-01-01T00:00:00+00:00"
    system["playwright"]["captured_at"] = "2020-01-01T00:00:00+00:00"
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    failure_names = {item["name"] for item in report["failures"]}
    assert {
        "system evidence freshness hours",
        "runtime evidence freshness hours",
        "playwright evidence freshness hours",
    }.issubset(failure_names)


def test_evidence_age_hours_does_not_round_just_over_limit() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    generated_at = (now - timedelta(hours=168, seconds=1)).isoformat()

    assert MODULE.evidence_age_hours(generated_at, now=now) > 168


def test_evidence_age_hours_rejects_future_timestamps() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    generated_at = (now + timedelta(seconds=1)).isoformat()

    assert MODULE.evidence_age_hours(generated_at, now=now) > MODULE.THRESHOLDS["system_evidence_max_age_hours"]


def test_gate_requires_each_critical_playwright_flow(tmp_path: Path) -> None:
    system = system_evidence_report()
    system["playwright"]["tests"][0]["title"] = "无关但通过的占位流程"
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    flow_failure = next(
        item for item in report["failures"] if item["name"] == "playwright critical flow coverage"
    )
    assert flow_failure["actual"] == ["登录并完成笔记审批"]


def test_gate_fails_when_production_config_was_skipped(tmp_path: Path) -> None:
    system = system_evidence_report()
    system["production_config"] = {
        "ok": True,
        "status": "skipped_non_production",
        "app_env": "development",
    }
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    assert "production config preflight" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_runtime_metrics_are_missing(tmp_path: Path) -> None:
    system = system_evidence_report()
    system["runtime"].pop("metrics")
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    assert "runtime metrics endpoint" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_restore_drill_is_missing(tmp_path: Path) -> None:
    system = system_evidence_report()
    system.pop("restore_drill")
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    assert "restore drill verified" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_restart_recovery_is_missing(tmp_path: Path) -> None:
    system = system_evidence_report()
    system.pop("restart_recovery")
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    assert "experiment restart recovery" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_monitoring_alerts_are_missing(tmp_path: Path) -> None:
    system = system_evidence_report()
    system.pop("monitoring_alerts")
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    assert "monitoring alerts" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_secret_rotation_runbook_is_missing(tmp_path: Path) -> None:
    system = system_evidence_report()
    system.pop("secret_rotation")
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    assert "secret rotation runbook" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_backup_policy_is_missing(tmp_path: Path) -> None:
    system = system_evidence_report()
    system.pop("backup_policy")
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    assert "backup policy runbook" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_reverse_proxy_check_is_missing(tmp_path: Path) -> None:
    system = system_evidence_report()
    system.pop("reverse_proxy")
    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system),
            evidence_manifest=None,
        )
    )

    assert "reverse proxy TLS template" in {item["name"] for item in report["failures"]}


def test_gate_fails_when_evidence_manifest_does_not_verify(tmp_path: Path) -> None:
    stale = write_json(tmp_path / "stale.json", {"value": "before"})
    manifest = tmp_path / "manifest.json"
    write_manifest(build_manifest([stale], tmp_path), manifest)
    stale.write_text(json.dumps({"value": "after"}), encoding="utf-8")

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=manifest,
        )
    )

    assert "maturity evidence manifest verified" in {item["name"] for item in report["failures"]}
    assert report["source_revision"] is None


def test_gate_reports_corrupt_manifest_without_crashing(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{not json", encoding="utf-8")

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=manifest,
        )
    )

    assert "maturity evidence manifest verified" in {item["name"] for item in report["failures"]}


def test_gate_reports_non_object_manifest_entries_without_crashing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    write_lockfiles(tmp_path)
    monkeypatch.setattr(
        SYSTEM_FREEZE,
        "git_checkout_state",
        lambda *_args, **_kwargs: {"git_commit": COMMIT, "worktree_clean": True},
    )
    manifest = write_json(
        tmp_path / "manifest.json",
        {"format_version": 2, "path_base": "root_argument", "files": [1]},
    )

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=manifest,
        )
    )

    assert "maturity evidence manifest verified" in {item["name"] for item in report["failures"]}


def test_gate_passes_with_manifest_covering_gate_inputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(
        SYSTEM_FREEZE,
        "git_checkout_state",
        lambda *_args, **_kwargs: {"git_commit": COMMIT, "worktree_clean": True},
    )
    retrieval = write_json(tmp_path / "retrieval.json", retrieval_report())
    experiment = write_json(tmp_path / "experiment.json", experiment_report())
    agent = write_json(tmp_path / "agent.json", agent_report())
    system = write_json(tmp_path / "system.json", system_evidence_report())
    extras = [write_json(tmp_path / f"extra-{index}.json", {"index": index}) for index in range(6)]
    manifest = write_json(
        tmp_path / "manifest.json",
        system_manifest([retrieval, experiment, agent, system, *extras], tmp_path),
    )

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=retrieval,
            experiment_report=experiment,
            agent_report=agent,
            system_evidence_report=system,
            evidence_manifest=manifest,
        )
    )

    assert report["passed"] is True
    assert report["source_revision"] == COMMIT


def test_release_gate_rejects_manifest_from_different_checkout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    files = [write_json(tmp_path / f"evidence-{index}.json", {"index": index}) for index in range(10)]
    manifest = write_json(tmp_path / "manifest.json", system_manifest(files, tmp_path))
    monkeypatch.setattr(
        SYSTEM_FREEZE,
        "git_checkout_state",
        lambda *_args, **_kwargs: {"git_commit": "b" * 40, "worktree_clean": True},
    )

    checks = MODULE.evidence_manifest_checks(manifest, files[:4])

    provenance_check = next(
        item for item in checks if item["name"] == "maturity evidence manifest matches current checkout"
    )
    assert provenance_check["passed"] is False


def test_release_gate_rejects_dirty_checkout_provenance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    files = [write_json(tmp_path / f"evidence-{index}.json", {"index": index}) for index in range(10)]
    manifest = write_json(tmp_path / "manifest.json", system_manifest(files, tmp_path))
    monkeypatch.setattr(
        SYSTEM_FREEZE,
        "git_checkout_state",
        lambda *_args, **_kwargs: {"git_commit": COMMIT, "worktree_clean": False},
    )

    checks = MODULE.evidence_manifest_checks(manifest, files[:4])

    provenance_check = next(
        item for item in checks if item["name"] == "maturity evidence manifest matches current checkout"
    )
    assert provenance_check["passed"] is False


def test_release_gate_rejects_changed_lockfile_provenance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    files = [write_json(tmp_path / f"evidence-{index}.json", {"index": index}) for index in range(10)]
    manifest = write_json(tmp_path / "manifest.json", system_manifest(files, tmp_path))
    monkeypatch.setattr(
        SYSTEM_FREEZE,
        "git_checkout_state",
        lambda *_args, **_kwargs: {"git_commit": COMMIT, "worktree_clean": True},
    )
    (tmp_path / "frontend" / "package-lock.json").write_text("changed lock graph\n", encoding="utf-8")

    checks = MODULE.evidence_manifest_checks(manifest, files[:4])

    provenance_check = next(
        item for item in checks if item["name"] == "maturity evidence manifest matches current checkout"
    )
    assert provenance_check["passed"] is False


def test_release_gate_does_not_publish_malformed_verified_source_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    files = [write_json(tmp_path / f"evidence-{index}.json", {"index": index}) for index in range(10)]
    manifest = write_json(tmp_path / "manifest.json", build_manifest(files, tmp_path))
    monkeypatch.setattr(
        MODULE,
        "verify_system_evidence_manifest",
        lambda *_args, **_kwargs: {
            "ok": True,
            "file_count": 10,
            "provenance": {"ok": True, "expected_git_commit": "a" * 41},
        },
    )

    checks, source_revision = MODULE.evaluate_evidence_manifest(manifest, files[:4])

    assert all(item["passed"] for item in checks)
    assert source_revision is None


def test_gate_rejects_absolute_manifest_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    retrieval = write_json(tmp_path / "retrieval.json", retrieval_report())
    experiment = write_json(tmp_path / "experiment.json", experiment_report())
    agent = write_json(tmp_path / "agent.json", agent_report())
    system = write_json(tmp_path / "system.json", system_evidence_report())
    extras = [write_json(tmp_path / f"extra-{index}.json", {"index": index}) for index in range(6)]
    manifest = write_json(
        tmp_path / "manifest.json",
        {
            "format_version": 2,
            "files": [
                {"path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
                for path in [retrieval, experiment, agent, system, *extras]
            ],
        },
    )

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=retrieval,
            experiment_report=experiment,
            agent_report=agent,
            system_evidence_report=system,
            evidence_manifest=manifest,
        )
    )

    assert "maturity evidence manifest verified" in {item["name"] for item in report["failures"]}


def test_gate_requires_manifest_to_cover_gate_inputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    unrelated_files = [
        write_json(tmp_path / f"unrelated-{index}.json", {"index": index})
        for index in range(10)
    ]
    manifest = write_json(tmp_path / "manifest.json", build_manifest(unrelated_files, tmp_path))

    report = MODULE.build_report(
        SimpleNamespace(
            retrieval_report=write_json(tmp_path / "retrieval.json", retrieval_report()),
            experiment_report=write_json(tmp_path / "experiment.json", experiment_report()),
            agent_report=write_json(tmp_path / "agent.json", agent_report()),
            system_evidence_report=write_json(tmp_path / "system.json", system_evidence_report()),
            evidence_manifest=manifest,
        )
    )

    coverage_failure = next(
        item for item in report["failures"] if item["name"] == "maturity evidence manifest covers gate inputs"
    )
    assert coverage_failure["actual"] == ["agent.json", "experiment.json", "retrieval.json", "system.json"]
