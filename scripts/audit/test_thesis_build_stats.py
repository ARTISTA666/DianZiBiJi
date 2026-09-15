from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit" / "thesis_build_stats.py"
SPEC = importlib.util.spec_from_file_location("thesis_build_stats", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


CLEAN_LOG = """This is XeTeX, Version 3.141592653
(./main.tex
Output written on main.pdf (130 pages).
"""

DIRTY_LOG = """This is XeTeX
! Undefined control sequence.
l.123 \\badmacro
Missing character: There is no 一 in font FandolSong-Regular!
Missing character: There is no 一 in font FandolSong-Regular!
Missing character: There is no ⧗ in font [lmroman10-regular]!
LaTeX Warning: Reference `fig:6-4' on page 88 undefined
LaTeX Warning: Citation `chen2024' on page 12 undefined
LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.
Output written on main.pdf (131 pages).
"""

BIBER_LOG = """[0] Config.pm:329> INFO - This is Biber 2.22
[50] biber:342> INFO - === Wed Sep 16, 2026
[123] biber:456> ERROR - Bib file not found
[124] Util.pm:12> WARN - Something minor
"""


def test_parse_main_log_clean():
    stats = MODULE.parse_main_log(CLEAN_LOG)
    assert stats["pages"] == 130
    assert stats["latex_errors"] == []
    assert stats["missing_characters"]["total"] == 0


def test_parse_main_log_dirty():
    stats = MODULE.parse_main_log(DIRTY_LOG)
    assert stats["pages"] == 131
    assert stats["latex_errors"] == ["Undefined control sequence."]
    assert stats["missing_characters"]["total"] == 3
    assert stats["undefined_references"] == [("fig:6-4", "88")]
    assert stats["undefined_citations"] == ["chen2024"]
    assert stats["rerun_warnings"] == 1


def test_parse_biber_log():
    stats = MODULE.parse_biber_log(BIBER_LOG)
    assert stats["biber_errors"] == ["Bib file not found"]
    assert stats["biber_warnings"] == ["Something minor"]


BIBER_CLEAN_LOG = """[0] Config.pm:329> INFO - This is Biber 2.22
[50] biber:342> INFO - === Wed Sep 16, 2026
[2465] bbl.pm:779> INFO - Output to main.bbl
"""


def _make_build_dir(tmp_path, log_text):
    d = tmp_path / "proj"
    d.mkdir(parents=True, exist_ok=True)
    (d / "main.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "main.log").write_text(log_text, encoding="utf-8")
    (d / "main.blg").write_text(BIBER_CLEAN_LOG, encoding="utf-8")
    return d


def test_collect_pass_and_fail(tmp_path):
    clean = MODULE.collect(_make_build_dir(tmp_path, CLEAN_LOG))
    assert clean["pass"] is True
    assert clean["pages"] == 130

    dirty = MODULE.collect(_make_build_dir(tmp_path, DIRTY_LOG))
    assert dirty["pass"] is False
    assert any("LaTeX 错误" in f for f in dirty["hard_fail"])
    assert any("Missing character" in f for f in dirty["hard_fail"])
    assert any("undefined reference" in f for f in dirty["hard_fail"])


def test_collect_missing_build_dir(tmp_path):
    report = MODULE.collect(tmp_path / "nonexistent")
    assert report["pass"] is False
    assert any("不存在" in f for f in report["hard_fail"])


def test_main_exit_codes(tmp_path):
    d = _make_build_dir(tmp_path, CLEAN_LOG)
    assert MODULE.main(["--build-dir", str(d)]) == 0
    d2 = _make_build_dir(tmp_path / "b2", DIRTY_LOG)
    assert MODULE.main(["--build-dir", str(d2)]) == 1


def test_residue_scan_reports_pdftotext_failure(tmp_path):
    pdf = tmp_path / "nofile.pdf"
    hits = MODULE.scan_residue(pdf)
    assert hits and "error" in hits[0]
