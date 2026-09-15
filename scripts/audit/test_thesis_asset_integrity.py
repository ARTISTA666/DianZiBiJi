from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit" / "thesis_asset_integrity.py"
SPEC = importlib.util.spec_from_file_location("thesis_asset_integrity", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_project(root: Path, main_tex: str, chapter_tex: str | None = None) -> Path:
    proj = root / "thesis-ahnu-master"
    (proj / "extraTex" / "body").mkdir(parents=True)
    (proj / "assets" / "screenshots").mkdir(parents=True)
    (proj / "extraTex" / "back").mkdir(parents=True)
    (proj / "assets" / "screenshots" / "fig.png").write_bytes(b"png")
    (proj / "extraTex" / "back" / "references-gb.bib").write_text("@misc{x}", encoding="utf-8")
    (proj / "main.tex").write_text(main_tex, encoding="utf-8")
    (proj / "extraTex" / "body" / "chapter-01.tex").write_text(
        chapter_tex
        if chapter_tex is not None
        else "\\includegraphics[width=0.8\\textwidth]{assets/screenshots/fig.png}\n"
             "\\includegraphics{assets/screenshots/gone}\n",
        encoding="utf-8")
    return proj


MAIN_TEX = "\\addbibresource{extraTex/back/references-gb.bib}\n\\includegraphics{cover.png}\n"


def test_check_project(tmp_path):
    proj = make_project(tmp_path, MAIN_TEX)
    (proj / "cover.png").write_bytes(b"png")
    report = MODULE.check_project(proj)
    assert report["graphics_refs"] == 3
    assert report["graphics_resolved"] == 2
    assert len(report["graphics_missing"]) == 1
    assert report["graphics_missing"][0]["ref"] == "assets/screenshots/gone"
    assert report["pass"] is False


def test_extensionless_resolution(tmp_path):
    proj = make_project(
        tmp_path,
        "\\includegraphics{assets/screenshots/fig}\n",
        chapter_tex="\\includegraphics[width=0.8\\textwidth]{assets/screenshots/fig.png}\n")
    report = MODULE.check_project(proj)
    assert report["graphics_resolved"] == 2  # 无扩展名命中 .png
    assert report["pass"] is True


def test_bib_missing(tmp_path):
    proj = make_project(tmp_path, "\\addbibresource{extraTex/back/lost.bib}\n")
    report = MODULE.check_project(proj)
    assert report["bib_missing"] == ["extraTex/back/lost.bib"]
    assert report["pass"] is False


def test_main_exit_codes(tmp_path):
    proj = make_project(tmp_path, MAIN_TEX)
    assert MODULE.main(["--project", str(proj)]) == 1
    assert MODULE.main(["--project", str(tmp_path / "none")]) == 2
