# -*- coding: utf-8 -*-
"""论文 PDF 视觉核验驱动(双套核验标准第二层的自动化,见 reviews/round-04/视觉核验管线.md)。

三段式判定之 OCR 坐标扫描自动化:
1. pdftoppm 按页渲染 PNG;
2. ocr_tool(Swift+Vision,scripts/audit/vcheck/)输出 x y w h conf text TSV(像素坐标);
3. 共基线碰撞判定:两段文本 y 区间重叠 ≥ 60% 较小盒高度(即同一行)且 x 区间交叠超过
   tol(默认 25px@300dpi,约半个正文字宽)→ 重叠;OCR 框天然外扩,相邻表格列间的
   小幅框交叠(实测 15-16px 级)属跨列噪声不判重叠,真实挤压(历史表 6-2)交叠远超此值;
   上下堆叠行(tikz 节点 \\\\ 换行、双行表头)是合法排版,不判重叠;
   OCR 文本出现 latex/verbatim/needspace 等裸串 → 转换器 fence bug;
   低置信(conf<40)条目 → 登记待用户目验清单,不判 pass 也不判 fail。

用法:
    python scripts/audit/thesis_visual_check.py --pdf main.pdf --pages 3,15,18-20 [--dpi 300] [--json OUT]

退出码:0=抽查页全部通过;1=存在重叠/裸串;2=渲染或 OCR 工具错误。
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_OCR_TOOL = "/tmp/vcheck/ocr_tool"
ENSURE_SCRIPT = Path(__file__).resolve().parent / "vcheck" / "ensure_ocr_tool.sh"

RESIDUE_RE = re.compile(
    r"(?i)(?<![A-Za-z])(latex|needspace|verbatim|includegraphics|usepackage|tikzpicture)(?![A-Za-z])")


def parse_pages(spec: str) -> list[int]:
    """'3,15,18-20' -> [3, 15, 18, 19, 20](1-based,去重升序)。"""
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            lo_i, hi_i = int(lo), int(hi)
            if lo_i < 1 or hi_i < lo_i:
                raise ValueError(f"非法页码区间: {part}")
            pages.update(range(lo_i, hi_i + 1))
        else:
            page = int(part)
            if page < 1:
                raise ValueError(f"非法页码: {part}")
            pages.add(page)
    if not pages:
        raise ValueError("页码为空")
    return sorted(pages)


def parse_ocr_tsv(stdout: str) -> list[dict]:
    """解析 ocr_tool stdout TSV: x y w h conf text。"""
    boxes = []
    for ln in stdout.split("\n"):
        ln = ln.rstrip("\n")
        if not ln or ln.startswith("IMAGE\t"):
            continue
        cols = ln.split("\t")
        if len(cols) < 6:
            continue
        x, y, w, h, conf = (int(c) for c in cols[:5])
        boxes.append({"x": x, "y": y, "w": w, "h": h, "conf": conf,
                      "text": "\t".join(cols[5:])})
    return boxes


def find_overlaps(boxes: list[dict], tol: int, v_frac: float = 0.6) -> list[dict]:
    """共基线碰撞判定:x 区间交叠(> tol px)且 y 区间重叠 ≥ v_frac*较小盒高度。

    y 区间几乎不重叠的上下堆叠文字(tikz 节点 \\\\ 换行、双行表头)是合法排版,不判重叠;
    严格共基线(同一行内挤压)才判。完全同文同位的重复观测不算。O(n^2) 对单页规模足够。
    """
    overlaps = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            same_obs = (a["text"] == b["text"]
                        and abs(a["x"] - b["x"]) <= 3 and abs(a["y"] - b["y"]) <= 3)
            if same_obs:
                continue
            v_inter = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if v_inter < v_frac * min(a["h"], b["h"]):
                continue
            x_inter = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            if x_inter > tol:
                overlaps.append({
                    "overlap_px": x_inter,
                    "a": {"text": a["text"], "x": a["x"], "y": a["y"]},
                    "b": {"text": b["text"], "x": b["x"], "y": b["y"]},
                })
    return overlaps


def scan_residue(boxes: list[dict]) -> list[dict]:
    hits = []
    for box in boxes:
        for m in RESIDUE_RE.finditer(box["text"]):
            hits.append({"token": m.group(1), "text": box["text"][:120],
                         "x": box["x"], "y": box["y"]})
    return hits


def ensure_ocr_tool(path: str | None, build: bool = True) -> str:
    tool = path or DEFAULT_OCR_TOOL
    if Path(tool).exists():
        return tool
    if not build:
        raise FileNotFoundError(f"OCR 工具不存在: {tool}(可运行 {ENSURE_SCRIPT} 重建)")
    subprocess.run(["sh", str(ENSURE_SCRIPT)], check=True, capture_output=True, text=True)
    if not Path(tool).exists():
        raise FileNotFoundError(f"OCR 工具重建后仍不存在: {tool}")
    return tool


def run_ocr(tool: str, png: Path) -> list[dict]:
    proc = subprocess.run([tool, str(png)], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"ocr_tool 失败(rc={proc.returncode}): {proc.stderr[:200]}")
    return parse_ocr_tsv(proc.stdout)


def render_page(pdf: Path, page: int, dpi: int, workdir: Path) -> Path:
    prefix = workdir / f"pg{page}"
    subprocess.run(
        ["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-png",
         str(pdf), str(prefix)],
        check=True, capture_output=True, timeout=300)
    matches = sorted(glob.glob(f"{prefix}-*.png")) or sorted(glob.glob(f"{prefix}.png"))
    if not matches:
        raise FileNotFoundError(f"pdftoppm 未产出 {prefix}*.png")
    return Path(matches[0])


def check_page(pdf: Path, page: int, dpi: int, workdir: Path, tool: str) -> dict:
    png = render_page(pdf, page, dpi, workdir)
    boxes = run_ocr(tool, png)
    overlaps = find_overlaps(boxes, tol=round(25 * dpi / 300))
    residue = scan_residue(boxes)
    low_conf = [b for b in boxes if b["conf"] < 40]
    return {
        "page": page,
        "png": str(png),
        "boxes": len(boxes),
        "pass": not overlaps and not residue,
        "overlaps": overlaps,
        "residue": residue,
        "low_conf_count": len(low_conf),
        "low_conf_samples": [b["text"] for b in low_conf[:5]],
    }


def format_report(pages: list[dict]) -> str:
    lines = []
    for p in pages:
        mark = "PASS" if p["pass"] else "FAIL"
        lines.append(f"[{mark}] p{p['page']}  boxes={p['boxes']}  "
                     f"overlaps={len(p['overlaps'])}  residue={len(p['residue'])}  "
                     f"low_conf={p['low_conf_count']}")
        for ov in p["overlaps"][:5]:
            lines.append(f"       重叠 {ov['overlap_px']}px: {ov['a']['text']!r} <-> {ov['b']['text']!r}")
        for rz in p["residue"][:5]:
            lines.append(f"       裸串 {rz['token']!r}: {rz['text'][:60]!r}")
        if p["low_conf_count"]:
            lines.append(f"       待用户目验(低置信 {p['low_conf_count']} 条): "
                         f"{p['low_conf_samples']}")
    verdict = all(p["pass"] for p in pages) if pages else False
    lines.append("VERDICT: " + ("PASS 视觉抽查通过" if verdict else "FAIL 存在重叠/裸串页"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="论文 PDF 视觉核验(OCR 坐标扫描)")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", required=True, help="如 3,15,18-20")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--workdir", default=None, help="渲染产物目录,默认 /tmp/vcheck/auto-<ts>")
    ap.add_argument("--ocr-tool", default=None, help="默认 /tmp/vcheck/ocr_tool,缺失时自动重建")
    ap.add_argument("--no-build", action="store_true", help="OCR 工具缺失时不自动重建")
    ap.add_argument("--json", dest="json_out", help="可选,结果 JSON 输出路径")
    args = ap.parse_args(argv)

    try:
        pages_spec = parse_pages(args.pages)
    except ValueError as exc:
        print(f"页码解析失败: {exc}", file=sys.stderr)
        return 2
    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"PDF 不存在: {pdf}", file=sys.stderr)
        return 2
    workdir = Path(args.workdir) if args.workdir else Path("/tmp/vcheck") / "auto"
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        tool = ensure_ocr_tool(args.ocr_tool, build=not args.no_build)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        print(f"OCR 工具不可用: {exc}", file=sys.stderr)
        return 2

    results = []
    for page in pages_spec:
        try:
            results.append(check_page(pdf, page, args.dpi, workdir, tool))
        except (subprocess.SubprocessError, RuntimeError, FileNotFoundError) as exc:
            print(f"p{page} 处理失败: {exc}", file=sys.stderr)
            return 2
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(format_report(results))
    return 0 if all(p["pass"] for p in results) else 1


if __name__ == "__main__":
    sys.exit(main())
