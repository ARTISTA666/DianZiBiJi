from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = load_module(
    "check_rag_experiment_evidence_for_paper_material",
    ROOT / "scripts/check_rag_experiment_evidence.py",
)
FIXTURES = load_module(
    "check_rag_experiment_evidence_fixtures_for_paper_material",
    ROOT / "scripts/test_check_rag_experiment_evidence.py",
)
MODULE = load_module(
    "render_rag_evidence_paper_material",
    ROOT / "scripts/render_rag_evidence_paper_material.py",
)
FRESHNESS = load_module(
    "check_paper_material_freshness_for_rag_evidence_material",
    ROOT / "scripts/check_paper_material_freshness.py",
)


def checked_package() -> tuple[dict, dict]:
    package = FIXTURES.package()
    failures = CHECKER.validate(package)
    result = {
        "passed": not failures,
        "package": "evidence.json",
        "schema_version": package["schema_version"],
        "case_count": package["case_count"],
        "failures": failures,
        "statistics": CHECKER.derive_statistics(package),
    }
    return package, result


REQUIRED_INPUTS = (
    "scripts/check_rag_experiment_evidence.py",
    "scripts/render_rag_evidence_paper_material.py",
    "docs/experiments/rag-evidence-package-protocol-v1.md",
    "docs/experiments/rag-paper-evidence-index-v1.md",
)


def prepared_workspace(tmp_path: Path) -> tuple[dict, dict, Path, Path]:
    package, check_result = checked_package()
    for relative in REQUIRED_INPUTS:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    package_path = tmp_path / "docs/experiments/evidence.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    return package, check_result, package_path, tmp_path


def test_renders_citable_descriptive_material_from_checked_package(tmp_path: Path) -> None:
    package, check_result, package_path, root = prepared_workspace(tmp_path)

    material = MODULE.render(package, check_result, package_path, root)

    assert "RAG 证据包描述性统计材料 v1" in material
    assert "rag-evidence-package-v1" in material
    assert "rag-evidence-statistics-v1" in material
    assert "completed_with_errors" in material
    assert "project_rag" in material
    assert "kg_enhanced_rag" in material
    assert "中位数" in material and "P95" in material
    assert "paper_ready=false" in material
    assert "输入材料指纹" in material
    assert "SHA-256" in material
    assert "check_rag_experiment_evidence.py" in material
    assert "render_rag_evidence_paper_material.py" in material
    assert "人工准确率、引用正确性、显著性检验或方法优越性" in material
    assert "失败案例逐项清单" in material
    assert "`query_error`" in material
    assert "timeout" in material
    assert "来源/图谱证据" in material
    assert "docs/experiments/evidence.json" in material
    assert str(root) not in material


def test_failure_case_rows_are_sorted_and_retain_machine_readable_fields() -> None:
    package, _ = checked_package()
    rows = MODULE.failure_case_rows(package)

    assert [row["execution_order"] for row in rows] == [2]
    assert rows[0]["failure_scope"] == "case"
    assert rows[0]["failure_code"] == "query_error"
    assert rows[0]["query_log_id"] is None
    assert rows[0]["source_count"] == 0
    assert rows[0]["graph_hit_count"] == 0


def test_failure_case_table_escapes_untrusted_error_text(tmp_path: Path) -> None:
    package, check_result, package_path, root = prepared_workspace(tmp_path)
    package["cases"][1]["error"] = "timeout | retry\nraw"

    material = MODULE.render(package, check_result, package_path, root)

    assert "timeout \\| retry raw" in material
    assert "timeout | retry\nraw" not in material


def test_renderer_rejects_failed_checker_result(tmp_path: Path) -> None:
    package, check_result, package_path, root = prepared_workspace(tmp_path)
    check_result["passed"] = False
    check_result["failures"] = ["tampered"]

    with pytest.raises(ValueError, match="passed checker result"):
        MODULE.render(package, check_result, package_path, root)


def test_renderer_rejects_statistics_drift(tmp_path: Path) -> None:
    package, check_result, package_path, root = prepared_workspace(tmp_path)
    check_result["statistics"] = deepcopy(check_result["statistics"])
    check_result["statistics"]["observed_case_count"] = 999

    with pytest.raises(ValueError, match="statistics do not match"):
        MODULE.render(package, check_result, package_path, root)


def test_renderer_rejects_non_v1_package(tmp_path: Path) -> None:
    package, check_result, package_path, root = prepared_workspace(tmp_path)
    package["schema_version"] = "legacy"

    with pytest.raises(ValueError, match="unsupported evidence package schema"):
        MODULE.render(package, check_result, package_path, root)


def test_cli_writes_material_without_absolute_workspace_path(tmp_path: Path) -> None:
    package, check_result, package_path, root = prepared_workspace(tmp_path)
    check_path = tmp_path / "check.json"
    output_path = tmp_path / "appendix.md"
    check_path.write_text(json.dumps(check_result, ensure_ascii=False), encoding="utf-8")

    exit_code = MODULE.run_cli(
        [
            "--package",
            str(package_path),
            "--check-result",
            str(check_path),
            "--output",
            str(output_path),
            "--root",
            str(root),
        ]
    )

    assert exit_code == 0
    material = output_path.read_text(encoding="utf-8")
    assert "evidence.json" in material
    assert str(tmp_path) not in material
    freshness = FRESHNESS.check_material(output_path, root)
    assert freshness["passed"] is True
    assert freshness["fingerprints"] == 5
    assert freshness["checked"] == 5
    assert freshness["mismatches"] == []


def test_fingerprints_are_stable_and_use_relative_paths() -> None:
    fingerprints = MODULE.input_fingerprints(
        ROOT / "scripts/test_check_rag_experiment_evidence.py", ROOT
    )

    names = [item["name"] for item in fingerprints]
    assert names == [
        "evidence_package",
        "evidence_checker",
        "paper_material_renderer",
        "evidence_protocol",
        "paper_evidence_index",
    ]
    assert all(len(item["sha256"]) == 64 for item in fingerprints)
    assert all("/Users/" not in item["path"] for item in fingerprints)
