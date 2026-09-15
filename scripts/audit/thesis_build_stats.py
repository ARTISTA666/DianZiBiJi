# -*- coding: utf-8 -*-
"""论文 PDF 构建统计与第一层脚本核验(视觉核验管线.md 双套标准之第一层的自动化)。

解析 latexmk/xelatex 产物:
- main.log  页数、LaTeX 错误(! 行)、Missing character 缺字、undefined reference/citation、rerun 提示
- main.blg  biber ERROR/WARN
- missfont.log 行数
- --residue-scan:pdftotext 扫描源码裸串(latex/verbatim/needspace 等,命中列为人工复核项)

用法:
    python scripts/audit/thesis_build_stats.py --build-dir /tmp/crlt/projects/thesis-ahnu-master [--json OUT] [--residue-scan]

退出码:0=全部硬指标通过;1=存在错误/缺字/undefined;2=构建产物缺失。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

PAGES_RE = re.compile(r"Output written on \S+ \((\d+) pages?(?:, \d+ bytes)?\)")
ERROR_LINE_RE = re.compile(r"^! (.+)$", re.M)
MISSING_CHAR_RE = re.compile(r"Missing character: There is no (.) in font (.+?)!")
UNDEF_REF_RE = re.compile(r"LaTeX Warning: Reference `([^']+)' on page (\d+) undefined")
UNDEF_CIT_RE = re.compile(r"LaTeX Warning: Citation `([^']+)' on page \d+ undefined")
RERUN_RE = re.compile(r"LaTeX Warning: Label\(s\) may have changed\. Rerun")

RESIDUE_TOKEN_RE = re.compile(
    r"(?i)(?<![A-Za-z])(latex|needspace|verbatim|includegraphics|usepackage|tikzpicture)(?![A-Za-z])")


def parse_main_log(text: str) -> dict:
    missing = Counter()
    for ch, font in MISSING_CHAR_RE.findall(text):
        missing[f"{ch!r}@{font}"] += 1
    return {
        "pages": int(m.group(1)) if (m := PAGES_RE.search(text)) else None,
        "latex_errors": [ln.strip() for ln in ERROR_LINE_RE.findall(text)],
        "missing_characters": {"total": sum(missing.values()), "by_char_font": dict(missing)},
        "undefined_references": sorted(set(UNDEF_REF_RE.findall(text))),
        "undefined_citations": sorted(set(UNDEF_CIT_RE.findall(text))),
        "rerun_warnings": len(RERUN_RE.findall(text)),
    }


BIBER_LEVEL_RE = re.compile(r"^(?:\[[^\]]*\]\s*)?\S*>\s*(ERROR|WARN) - (.+)$", re.M)


def parse_biber_log(text: str) -> dict:
    errors, warns = [], []
    for level, msg in BIBER_LEVEL_RE.findall(text):
        (errors if level == "ERROR" else warns).append(msg.strip())
    return {"biber_errors": errors, "biber_warnings": warns}


def scan_residue(pdf_path: Path) -> list[dict]:
    """pdftotext 文本层扫描转换器 fence bug 的源码裸串。命中为人工复核项,不计入硬失败。"""
    try:
        out = subprocess.run(
            ["pdftotext", "-q", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return [{"error": f"pdftotext 不可用或失败: {exc}"}]
    hits = []
    for lineno, ln in enumerate(out.split("\n"), 1):
        for m in RESIDUE_TOKEN_RE.finditer(ln):
            hits.append({"line": lineno, "token": m.group(1), "context": ln.strip()[:120]})
    return hits


def collect(build_dir: Path, residue: bool = False) -> dict:
    report: dict = {"build_dir": str(build_dir)}
    hard_fail: list[str] = []
    manual_review: list[str] = []

    log_path = build_dir / "main.log"
    pdf_path = build_dir / "main.pdf"
    for label, path in (("main.log", log_path), ("main.pdf", pdf_path)):
        if not path.exists():
            report[label] = "MISSING"
            hard_fail.append(f"{label} 不存在: {path}")
    if hard_fail:
        report["pass"] = False
        report["hard_fail"] = hard_fail
        return report

    report.update(parse_main_log(log_path.read_text(encoding="utf-8", errors="replace")))

    blg_path = build_dir / "main.blg"
    if blg_path.exists():
        report.update(parse_biber_log(blg_path.read_text(encoding="utf-8", errors="replace")))
    else:
        report["biber_errors"] = ["main.blg 不存在(未跑 biber?)"]
    missfont = build_dir / "missfont.log"
    report["missfont_log_lines"] = (
        len(missfont.read_text(encoding="utf-8", errors="replace").splitlines())
        if missfont.exists() else 0)

    if residue:
        hits = scan_residue(pdf_path)
        report["residue_hits"] = hits
        for h in hits:
            if "error" in h:
                manual_review.append(h["error"])
            else:
                manual_review.append(f"p? L{h['line']}: {h['token']} … {h['context'][:60]}")

    n_err = len(report["latex_errors"])
    n_miss = report["missing_characters"]["total"]
    n_uref = len(report["undefined_references"])
    n_ucit = len(report["undefined_citations"])
    n_biber = len(report["biber_errors"])
    if n_err:
        hard_fail.append(f"LaTeX 错误 {n_err}: {report['latex_errors'][:3]}")
    if n_miss:
        hard_fail.append(f"Missing character {n_miss}: {report['missing_characters']['by_char_font']}")
    if n_uref:
        hard_fail.append(f"undefined reference {n_uref}: {report['undefined_references'][:5]}")
    if n_ucit:
        hard_fail.append(f"undefined citation {n_ucit}: {report['undefined_citations'][:5]}")
    if n_biber:
        hard_fail.append(f"biber ERROR {n_biber}: {report['biber_errors'][:3]}")
    if report.get("rerun_warnings"):
        manual_review.append(f"存在 {report['rerun_warnings']} 处 rerun 提示(可能需再编译一轮)")
    if report.get("missfont_log_lines"):
        manual_review.append(f"missfont.log 有 {report['missfont_log_lines']} 行(字体回退记录)")

    report["pass"] = not hard_fail
    report["hard_fail"] = hard_fail
    report["manual_review"] = manual_review
    return report


def format_report(report: dict) -> str:
    lines = [f"构建目录: {report['build_dir']}"]
    if report.get("pages") is not None:
        lines.append(f"页数: {report['pages']}")
    for key in ("latex_errors", "undefined_references", "undefined_citations", "biber_errors"):
        lines.append(f"{key}: {len(report.get(key, []))}")
    lines.append(f"missing_characters: {report.get('missing_characters', {}).get('total', '?')}")
    if report.get("residue_hits") is not None:
        lines.append(f"residue_hits(人工复核): {len(report['residue_hits'])}")
    for item in report.get("hard_fail", []):
        lines.append(f"[FAIL] {item}")
    for item in report.get("manual_review", []):
        lines.append(f"[REVIEW] {item}")
    lines.append("VERDICT: " + ("PASS 第一层核验通过" if report.get("pass") else "FAIL"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="论文 PDF 构建统计与第一层核验")
    ap.add_argument("--build-dir", default="/tmp/crlt/projects/thesis-ahnu-master")
    ap.add_argument("--json", dest="json_out", help="可选,结果 JSON 输出路径")
    ap.add_argument("--residue-scan", action="store_true", help="pdftotext 扫描源码裸串")
    args = ap.parse_args(argv)

    report = collect(Path(args.build_dir), residue=args.residue_scan)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(format_report(report))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
