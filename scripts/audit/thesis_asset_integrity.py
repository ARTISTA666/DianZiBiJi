# -*- coding: utf-8 -*-
r"""论文构建工程图片引用完整性检查(/tmp 失血后重建前的必跑 preflight,台账 T-047 教训)。

扫描工程内 main.tex 与 extraTex/**/*.tex 的 \includegraphics 引用,
逐个解析相对工程根的文件是否存在(无扩展名时尝试 png/pdf/jpg/jpeg/eps);
顺带核查 \addbibresource/\bibliography 指向的 bib 文件。

用法:
    python scripts/audit/thesis_asset_integrity.py --project /tmp/crlt/projects/thesis-ahnu-master

退出码:0=全部引用可解析;1=存在缺失;2=工程不存在。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GRAPHICS_RE = re.compile(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}")
GRAPHICS_NOOPT_RE = re.compile(r"\\includegraphics\{([^}]+)\}")
BIB_RE = re.compile(r"\\(?:addbibresource|bibliography)\{([^}]+)\}")
EXT_CANDIDATES = ("", ".png", ".pdf", ".jpg", ".jpeg", ".eps")


def collect_tex_files(project: Path) -> list[Path]:
    tex = sorted(project.glob("*.tex")) + sorted(project.glob("extraTex/**/*.tex"))
    return [p for p in tex if p.is_file()]


def resolve_asset(project: Path, raw: str) -> Path | None:
    ref = raw.strip().strip("{}").strip()
    for ext in EXT_CANDIDATES:
        cand = project / (ref + ext)
        if cand.is_file():
            return cand
    return None


def check_project(project: Path) -> dict:
    refs: dict[str, list[str]] = {}
    bib_refs: list[str] = []
    for tex in collect_tex_files(project):
        text = tex.read_text(encoding="utf-8", errors="replace")
        for rx in (GRAPHICS_RE, GRAPHICS_NOOPT_RE):
            for raw in rx.findall(text):
                refs.setdefault(raw.strip(), []).append(str(tex.relative_to(project)))
        for raw in BIB_RE.findall(text):
            bib_refs.append(raw.strip())
    missing = []
    resolved = 0
    for raw in sorted(refs):
        if resolve_asset(project, raw) is None:
            missing.append({"ref": raw, "referenced_by": refs[raw]})
        else:
            resolved += 1
    bib_missing = []
    for raw in sorted(set(bib_refs)):
        cand = project / raw
        if not cand.is_file() and not (project / (raw + ".bib")).is_file():
            bib_missing.append(raw)
    return {
        "project": str(project),
        "tex_files": len(collect_tex_files(project)),
        "graphics_refs": len(refs),
        "graphics_resolved": resolved,
        "graphics_missing": missing,
        "bib_refs": sorted(set(bib_refs)),
        "bib_missing": bib_missing,
        "pass": not missing and not bib_missing,
    }


def format_report(report: dict) -> str:
    lines = [f"工程: {report['project']}  tex 文件 {report['tex_files']} 个,"
             f"图片引用 {report['graphics_refs']} 个(可解析 {report['graphics_resolved']})"]
    for m in report["graphics_missing"]:
        lines.append(f"[MISSING] {m['ref']}  <- {', '.join(m['referenced_by'])}")
    for b in report["bib_missing"]:
        lines.append(f"[MISSING] bib: {b}")
    lines.append("VERDICT: " + ("PASS 引用完整性通过" if report["pass"] else "FAIL 存在缺失引用"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="论文构建工程图片引用完整性检查")
    ap.add_argument("--project", default="/tmp/crlt/projects/thesis-ahnu-master")
    ap.add_argument("--json", dest="json_out", help="可选,结果 JSON 输出路径")
    args = ap.parse_args(argv)

    project = Path(args.project)
    if not project.is_dir():
        print(f"工程目录不存在: {project}", file=sys.stderr)
        return 2
    report = check_project(project)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(format_report(report))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
