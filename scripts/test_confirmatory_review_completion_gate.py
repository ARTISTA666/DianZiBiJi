from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from freeze_preregistration import build_manifest  # noqa: E402

SCRIPT = ROOT / "scripts" / "confirmatory_review_completion_gate.py"
SPEC = importlib.util.spec_from_file_location("confirmatory_review_completion_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


COMMIT = "a" * 40


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def final_gate_report(passed: bool = True) -> dict:
    checks = [
        {"name": name, "passed": passed, "detail": {}}
        for name in sorted(MODULE.REQUIRED_FINAL_MATURITY_CHECKS)
    ]
    return {
        "generated_at": "2026-07-18T00:00:00+00:00",
        "source_revision": COMMIT,
        "passed": passed,
        "scope": "final maturity gate for confirmatory human review",
        "checks": checks,
        "failures": [] if passed else [checks[0]],
    }


def rating(evaluator_id: int) -> dict:
    return {
        "evaluator_user_id": evaluator_id,
        "is_accurate": True,
        "is_traceable": True,
        "score": 4,
        "comment": "",
        "review_protocol": "method_masked",
    }


def write_export(
    path: Path,
    question_count: int,
    modes: list[str],
    reviewer_ids: tuple[int, int] = (2, 3),
    *,
    include_protocol: bool = True,
    final_gate: Path | None = None,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        fieldnames = ["question_index", "question", "mode", "status", "query_log_id", "evaluations_json"]
        if include_protocol:
            fieldnames += ["review_batch_id", "export_protocol", "final_maturity_gate_sha256"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        query_log_id = 1
        for question_index in range(question_count):
            for mode in modes:
                row = {
                    "question_index": question_index,
                    "question": f"Frozen question {question_index}?",
                    "mode": mode,
                    "status": "completed",
                    "query_log_id": query_log_id,
                    "evaluations_json": json.dumps([rating(reviewer_ids[0]), rating(reviewer_ids[1])]),
                }
                if include_protocol:
                    row.update(
                        {
                            "review_batch_id": "RABCDEF123456",
                            "export_protocol": MODULE.FORMAL_EXPORT_PROTOCOL,
                            "final_maturity_gate_sha256": sha256(final_gate) if final_gate else "missing-final-gate-hash",
                        }
                    )
                writer.writerow(row)
                query_log_id += 1


def write_freeze(path: Path, root: Path, question_count: int = 60) -> Path:
    corpus = root / "corpus.json"
    corpus.write_text('{"frozen": true}\n', encoding="utf-8")
    freeze = {
        "methods": ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"],
        "model": "deepseek-v4-flash",
        "prompt_version": "confirmatory-review-v1",
        "random_seed": 20260716,
        "projects": [{"project_id": f"P{i}"} for i in range(3)],
        "questions": [
            {
                "question_id": f"Q{i}",
                "question_index": i,
                "question": f"Frozen question {i}?",
                "project_id": f"P{i % 3}",
                "gold_facts": ["fact"],
            }
            for i in range(question_count)
        ],
        "reviewers": [
            {"reviewer_id": "R1", "user_id": 2, "involved_in_development": False, "can_read": False, "can_evaluate": True, "can_write": False, "can_review": False, "can_manage": False},
            {"reviewer_id": "R2", "user_id": 3, "involved_in_development": False, "can_read": False, "can_evaluate": True, "can_write": False, "can_review": False, "can_manage": False},
        ],
        "files": [{"path": "corpus.json", "sha256": sha256(corpus)}],
    }
    path.write_text(json.dumps(freeze), encoding="utf-8")
    return path


def args(tmp_path: Path, modes: list[str]) -> argparse.Namespace:
    final_gate = write_json(tmp_path / "final-gate.json", final_gate_report())
    freeze = write_freeze(tmp_path / "freeze.json", tmp_path)
    export = tmp_path / "export.csv"
    write_export(export, 60, modes, final_gate=final_gate)
    evidence_manifest = tmp_path / "review-manifest.json"
    evidence_manifest.write_text(json.dumps(build_manifest([final_gate, freeze, export], tmp_path)), encoding="utf-8")
    return argparse.Namespace(final_gate=final_gate, freeze=freeze, export=export, evidence_manifest=evidence_manifest, root=tmp_path)


def test_completion_gate_passes_complete_five_mode_review(tmp_path: Path) -> None:
    report = MODULE.build_report(args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"]))

    assert report["passed"] is True
    assert isinstance(report["generated_at"], str)
    assert report["source_revision"] == COMMIT
    final_check = next(
        item for item in report["checks"] if item["name"] == "final maturity gate passed before reporting review"
    )
    assert final_check["detail"]["source_revision"] == COMMIT


def test_completion_gate_rejects_missing_export(tmp_path: Path) -> None:
    final_gate = write_json(tmp_path / "final-gate.json", final_gate_report())
    freeze = write_freeze(tmp_path / "freeze.json", tmp_path)
    evidence_manifest = tmp_path / "review-manifest.json"
    evidence_manifest.write_text(json.dumps(build_manifest([final_gate, freeze], tmp_path)), encoding="utf-8")
    report = MODULE.build_report(argparse.Namespace(final_gate=final_gate, freeze=freeze, export=tmp_path / "missing.csv", evidence_manifest=evidence_manifest, root=tmp_path))

    assert "human review export exists" in {item["name"] for item in report["failures"]}


def test_completion_gate_requires_final_maturity_gate_passed(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    gate_args.final_gate = write_json(tmp_path / "final-gate.json", final_gate_report(False))
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "final maturity gate passed before reporting review" in {item["name"] for item in report["failures"]}
    assert report["source_revision"] is None


def test_completion_gate_rejects_final_gate_without_source_revision(tmp_path: Path) -> None:
    payload = final_gate_report()
    payload.pop("source_revision")
    final_gate = write_json(tmp_path / "final-gate.json", payload)

    result = MODULE.final_maturity_gate_check(final_gate)

    assert result["passed"] is False
    assert result["detail"]["source_revision"] is None
    assert result["detail"]["source_revision_valid"] is False


def test_completion_gate_rejects_malformed_final_gate_source_revision(tmp_path: Path) -> None:
    payload = final_gate_report()
    payload["source_revision"] = "a" * 41
    final_gate = write_json(tmp_path / "final-gate.json", payload)

    result = MODULE.final_maturity_gate_check(final_gate)

    assert result["passed"] is False
    assert result["detail"]["source_revision_valid"] is False


def test_completion_gate_rejects_minimal_final_gate_pass(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    gate_args.final_gate = write_json(tmp_path / "final-gate.json", {"passed": True})
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "final maturity gate passed before reporting review" in {item["name"] for item in report["failures"]}


def test_completion_gate_rejects_less_than_five_modes(tmp_path: Path) -> None:
    report = MODULE.build_report(args(tmp_path, ["project_rag", "kg_enhanced_rag"]))

    assert "human review methods match frozen methods" in {item["name"] for item in report["failures"]}


def test_completion_gate_rejects_legacy_export_without_protocol_columns(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    write_export(gate_args.export, 60, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"], include_protocol=False)
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    protocol_check = next(item for item in report["failures"] if item["name"] == "human review export uses confirmatory protocol")
    assert protocol_check["detail"]["missing_columns"] == ["export_protocol", "final_maturity_gate_sha256", "review_batch_id"]


def test_completion_gate_rejects_wrong_export_protocol(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    rows = list(csv.DictReader(gate_args.export.open("r", encoding="utf-8")))
    for row in rows:
        row["export_protocol"] = "legacy"
    with gate_args.export.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "human review export uses confirmatory protocol" in {item["name"] for item in report["failures"]}


def test_completion_gate_rejects_inconsistent_review_batch_id(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    rows = list(csv.DictReader(gate_args.export.open("r", encoding="utf-8")))
    rows[0]["review_batch_id"] = "R000000000000"
    with gate_args.export.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "human review export uses confirmatory protocol" in {item["name"] for item in report["failures"]}


def test_completion_gate_rejects_bad_review_batch_id_format(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    rows = list(csv.DictReader(gate_args.export.open("r", encoding="utf-8")))
    for row in rows:
        row["review_batch_id"] = "not-a-batch-id"
    with gate_args.export.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    protocol_check = next(item for item in report["failures"] if item["name"] == "human review export uses confirmatory protocol")
    assert protocol_check["detail"]["valid_batch_ids"] is False


def test_completion_gate_rejects_mismatched_final_gate_hash(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    rows = list(csv.DictReader(gate_args.export.open("r", encoding="utf-8")))
    for row in rows:
        row["final_maturity_gate_sha256"] = "0" * 64
    with gate_args.export.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "human review export uses confirmatory protocol" in {item["name"] for item in report["failures"]}


def test_completion_gate_rejects_bad_final_gate_hash_format(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    rows = list(csv.DictReader(gate_args.export.open("r", encoding="utf-8")))
    for row in rows:
        row["final_maturity_gate_sha256"] = "not-a-sha"
    with gate_args.export.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    protocol_check = next(item for item in report["failures"] if item["name"] == "human review export uses confirmatory protocol")
    assert protocol_check["detail"]["valid_final_maturity_gate_sha256"] is False


def test_completion_gate_rejects_wrong_reviewer_ids(tmp_path: Path) -> None:
    freeze = write_freeze(tmp_path / "freeze.json", tmp_path)
    export = tmp_path / "export.csv"
    evidence_manifest = tmp_path / "review-manifest.json"
    final_gate = write_json(tmp_path / "final-gate.json", final_gate_report())
    write_export(export, 60, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"], reviewer_ids=(2, 4), final_gate=final_gate)
    evidence_manifest.write_text(json.dumps(build_manifest([final_gate, freeze, export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(argparse.Namespace(final_gate=final_gate, freeze=freeze, export=export, evidence_manifest=evidence_manifest, root=tmp_path))

    assert "human review reviewers match frozen reviewers" in {item["name"] for item in report["failures"]}


def test_completion_gate_rejects_wrong_question_indices(tmp_path: Path) -> None:
    freeze = write_freeze(tmp_path / "freeze.json", tmp_path)
    export = tmp_path / "export.csv"
    final_gate = write_json(tmp_path / "final-gate.json", final_gate_report())
    write_export(export, 60, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"], final_gate=final_gate)
    rows = list(csv.DictReader(export.open("r", encoding="utf-8")))
    for row in rows:
        if row["question_index"] == "0":
            row["question_index"] = "999"
    with export.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    evidence_manifest = tmp_path / "review-manifest.json"
    evidence_manifest.write_text(json.dumps(build_manifest([final_gate, freeze, export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(argparse.Namespace(final_gate=final_gate, freeze=freeze, export=export, evidence_manifest=evidence_manifest, root=tmp_path))

    assert "human review questions match frozen questions" in {item["name"] for item in report["failures"]}


def test_completion_gate_rejects_wrong_question_text(tmp_path: Path) -> None:
    freeze = write_freeze(tmp_path / "freeze.json", tmp_path)
    export = tmp_path / "export.csv"
    final_gate = write_json(tmp_path / "final-gate.json", final_gate_report())
    write_export(export, 60, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"], final_gate=final_gate)
    rows = list(csv.DictReader(export.open("r", encoding="utf-8")))
    for row in rows:
        if row["question_index"] == "0":
            row["question"] = "Different question text?"
    with export.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    evidence_manifest = tmp_path / "review-manifest.json"
    evidence_manifest.write_text(json.dumps(build_manifest([final_gate, freeze, export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(argparse.Namespace(final_gate=final_gate, freeze=freeze, export=export, evidence_manifest=evidence_manifest, root=tmp_path))

    question_check = next(item for item in report["failures"] if item["name"] == "human review questions match frozen questions")
    assert question_check["detail"]["question_texts_match"] is False


def test_completion_gate_requires_review_evidence_manifest(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    gate_args.evidence_manifest = tmp_path / "missing-manifest.json"

    report = MODULE.build_report(gate_args)

    assert "confirmatory review evidence manifest verified" in {item["name"] for item in report["failures"]}


def test_completion_gate_requires_manifest_to_cover_freeze_and_export(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("unrelated", encoding="utf-8")
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([unrelated], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    manifest_check = next(item for item in report["failures"] if item["name"] == "confirmatory review evidence manifest verified")
    assert "final-gate.json" in manifest_check["detail"]["missing_required_paths"]
    assert "freeze.json" in manifest_check["detail"]["missing_required_paths"]
    assert "export.csv" in manifest_check["detail"]["missing_required_paths"]


def test_completion_gate_rejects_changed_review_export_after_freeze(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    gate_args.export.write_text(gate_args.export.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "confirmatory review evidence manifest verified" in {item["name"] for item in report["failures"]}


def test_completion_gate_reports_corrupt_final_gate_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    gate_args.final_gate.write_text("{not json", encoding="utf-8")
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "final maturity gate passed before reporting review" in {item["name"] for item in report["failures"]}


def test_completion_gate_reports_corrupt_freeze_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    gate_args.freeze.write_text("{not json", encoding="utf-8")
    gate_args.evidence_manifest.write_text(json.dumps(build_manifest([gate_args.final_gate, gate_args.freeze, gate_args.export], tmp_path)), encoding="utf-8")

    report = MODULE.build_report(gate_args)

    assert "confirmatory freeze exists and validates" in {item["name"] for item in report["failures"]}


def test_completion_gate_reports_corrupt_manifest_without_crashing(tmp_path: Path) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    gate_args.evidence_manifest.write_text("{not json", encoding="utf-8")

    report = MODULE.build_report(gate_args)

    manifest_failure = next(item for item in report["failures"] if item["name"] == "confirmatory review evidence manifest verified")
    assert manifest_failure["detail"]["file_count"] == 0


def test_completion_gate_reports_freeze_validator_exception_without_crashing(tmp_path: Path, monkeypatch) -> None:
    gate_args = args(tmp_path, ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"])
    monkeypatch.setattr(MODULE, "validate_human_freeze", lambda freeze, root: (_ for _ in ()).throw(ValueError("bad freeze shape")))

    report = MODULE.build_report(gate_args)

    failure = next(item for item in report["failures"] if item["name"] == "confirmatory freeze exists and validates")
    assert failure["detail"]["error"] == "bad freeze shape"
