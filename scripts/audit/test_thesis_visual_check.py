from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit" / "thesis_visual_check.py"
SPEC = importlib.util.spec_from_file_location("thesis_visual_check", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


TSV_SAMPLE = "IMAGE\t1654\t2339\n120\t100\t200\t40\t92\t表 6-2 交付系统复现批次结果\n130\t100\t180\t40\t95\t交付系统复现\n500\t900\t300\t50\t97\t图 5-3 项目图谱全景\n"


def test_parse_pages():
    assert MODULE.parse_pages("3") == [3]
    assert MODULE.parse_pages("3,15,18-20") == [3, 15, 18, 19, 20]
    for bad in ("0", "5-3", "abc", ""):
        try:
            MODULE.parse_pages(bad)
        except ValueError:
            continue
        raise AssertionError(f"应拒绝非法页码: {bad}")


def test_parse_ocr_tsv():
    boxes = MODULE.parse_ocr_tsv(TSV_SAMPLE)
    assert len(boxes) == 3
    assert boxes[0] == {"x": 120, "y": 100, "w": 200, "h": 40, "conf": 92,
                        "text": "表 6-2 交付系统复现批次结果"}


def _box(x, y, w, h, text, conf=95):
    return {"x": x, "y": y, "w": w, "h": h, "conf": conf, "text": text}


def test_find_overlaps_detects_same_line_overlap():
    boxes = [
        _box(100, 200, 300, 40, "来源类型"),
        _box(300, 205, 120, 40, "置信度"),
        _box(450, 200, 200, 40, "金标准判定"),
    ]
    overlaps = MODULE.find_overlaps(boxes, tol=2)
    assert len(overlaps) == 1
    pair_texts = {overlaps[0]["a"]["text"], overlaps[0]["b"]["text"]}
    assert pair_texts == {"来源类型", "置信度"}


def test_find_overlaps_ignores_stacked_lines_duplicates_and_gaps():
    boxes = [
        # tikz 节点 \\ 换行的上下堆叠行:y 区间几乎不重叠,合法排版
        _box(100, 200, 300, 44, "第一章"),
        _box(100, 236, 300, 44, "绪论"),
        # 完全同文同位的重复观测
        _box(100, 200, 300, 44, "第一章"),
        # 同行但不交叠
        _box(100, 660, 150, 40, "左半"), _box(300, 660, 150, 40, "右半"),
        # 不同行
        _box(100, 900, 300, 40, "下行文本"),
    ]
    assert MODULE.find_overlaps(boxes, tol=2) == []


def test_scan_residue():
    boxes = [_box(0, 0, 100, 20, "needspace 裸串"), _box(0, 100, 100, 20, "正常中文")]
    hits = MODULE.scan_residue(boxes)
    assert len(hits) == 1 and hits[0]["token"] == "needspace"


def test_main_missing_tool_exit_2(tmp_path):
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    rc = MODULE.main(["--pdf", str(pdf), "--pages", "1", "--no-build",
                      "--ocr-tool", str(tmp_path / "no_tool")])
    assert rc == 2


def test_main_bad_pages_exit_2(tmp_path):
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    assert MODULE.main(["--pdf", str(pdf), "--pages", "0", "--no-build"]) == 2
    assert MODULE.main(["--pdf", str(tmp_path / "nofile.pdf"), "--pages", "1",
                        "--no-build"]) == 2
