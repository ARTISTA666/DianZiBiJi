from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_paper_material_freshness.py")
SPEC = importlib.util.spec_from_file_location("check_paper_material_freshness", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_material(tmp_path: Path, digest: str = "a" * 64) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    material = tmp_path / "material.md"
    material.write_text(
        """# Material

## 输入材料指纹

| 材料 | 路径 | SHA-256 |
| --- | --- | --- |
| raw_csv | `input.csv` | `DIGEST` |
""".replace("DIGEST", digest),
        encoding="utf-8",
    )
    (tmp_path / "input.csv").write_text("input\n", encoding="utf-8")
    return material


def test_matching_fingerprint_passes(tmp_path: Path) -> None:
    material = write_material(tmp_path)
    expected = MODULE.sha256_file(tmp_path / "input.csv")
    material.write_text(material.read_text(encoding="utf-8").replace("a" * 64, expected), encoding="utf-8")

    result = MODULE.check_material(material, tmp_path)

    assert result["passed"] is True
    assert result["checked"] == 1
    assert result["mismatches"] == []


def test_changed_input_fails_closed_with_expected_and_actual_digest(tmp_path: Path) -> None:
    material = write_material(tmp_path)

    result = MODULE.check_material(material, tmp_path)

    assert result["passed"] is False
    assert result["checked"] == 1
    assert result["mismatches"][0]["name"] == "raw_csv"
    assert result["mismatches"][0]["expected_sha256"] == "a" * 64
    assert len(result["mismatches"][0]["actual_sha256"]) == 64


def test_missing_input_and_malformed_digest_are_reported(tmp_path: Path) -> None:
    material = tmp_path / "material.md"
    material.write_text(
        """## 输入材料指纹

| 材料 | 路径 | SHA-256 |
| --- | --- | --- |
| missing | `missing.json` | `not-a-digest` |
""",
        encoding="utf-8",
    )

    result = MODULE.check_material(material, tmp_path)

    assert result["passed"] is False
    assert {item["reason"] for item in result["mismatches"]} == {"malformed_digest", "missing_input"}


def test_cli_writes_machine_readable_result(tmp_path: Path) -> None:
    material = write_material(tmp_path)
    output = tmp_path / "freshness.json"
    exit_code = MODULE.run_cli([str(material), "--root", str(tmp_path), "--output", str(output)])

    assert exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["material"] == "material.md"
    assert payload["root"] == "."


def test_missing_fingerprint_section_is_reported(tmp_path: Path) -> None:
    material = tmp_path / "material.md"
    material.write_text("# Material\n\nNo input fingerprint table.\n", encoding="utf-8")

    result = MODULE.check_material(material, tmp_path)

    assert result["passed"] is False
    assert result["fingerprints"] == 0
    assert result["mismatches"] == [{"reason": "missing_fingerprint_section"}]


def test_malformed_fingerprint_row_is_reported_with_line_number(tmp_path: Path) -> None:
    material = tmp_path / "material.md"
    material.write_text(
        """## 输入材料指纹

| 材料 | 路径 | SHA-256 |
| --- | --- | --- |
| raw_csv | input.csv | not-a-digest |
""",
        encoding="utf-8",
    )

    result = MODULE.check_material(material, tmp_path)

    assert result["passed"] is False
    assert result["fingerprints"] == 0
    assert result["mismatches"] == [
        {"reason": "malformed_fingerprint_row", "line": 5}
    ]


def test_material_path_is_portable_posix_relative(tmp_path: Path) -> None:
    material = write_material(tmp_path / "nested")

    result = MODULE.check_material(material, tmp_path)

    assert result["material"] == "nested/material.md"
    assert "\\" not in result["material"]


def test_material_outside_root_fails_closed_with_portable_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    material = write_material(outside)

    result = MODULE.check_material(material, root)

    assert result["passed"] is False
    assert result["material"] == "../outside/material.md"
    assert "\\" not in result["material"]
    assert {item["reason"] for item in result["mismatches"]} >= {"material_outside_root"}
