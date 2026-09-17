#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 2：tikz 围栏 → standalone xelatex → 300dpi PNG。

沿用 09-02 首版管线口径：xelatex standalone + ctex fandol 字体（不依赖系统宋体，
与本机 Songti SC 回退序无关）。每个围栏一次独立编译；编译失败逐张报错并保留日志。
输出 agent-work/docx-build/tikz/figNN.png（300dpi，白底裁边）。
"""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PREAMBLE = r"""\documentclass[border=6pt]{standalone}
\usepackage{ctex}
\usepackage{tikz}
\usetikzlibrary{shapes.geometric,shapes.misc,shapes.arrows,arrows.meta,positioning,fit,calc,backgrounds,decorations.pathmorphing,decorations.pathreplacing,matrix}
\begin{document}"""

EPILOG = r"\end{document}"


def render_one(tex_path: Path, outdir: Path) -> str:
    name = tex_path.stem
    work = outdir / name
    work.mkdir(exist_ok=True)
    doc = work / f"{name}.tex"
    # 与 convert-enhanced.guard() 同源修复：节点内 \\[S]/\\[G] 会被解析为换行可选间距，
    # 插入空组阻断（docx 文本层的 [S]/[G] 不受影响，此为渲染层问题）
    src = tex_path.read_text(encoding="utf-8").replace("\\\\[S]", "\\\\{}[S]").replace("\\\\[G]", "\\\\{}[G]")
    doc.write_text(PREAMBLE + "\n" + src + "\n" + EPILOG, encoding="utf-8")
    r = subprocess.run(
        ["xelatex", "-interaction=nonstopmode", "-halt-on-error", f"{name}.tex"],
        cwd=work, capture_output=True, text=True, timeout=180)
    pdf = work / f"{name}.pdf"
    if not pdf.exists():
        log = (work / f"{name}.log")
        tail = log.read_text(errors="ignore")[-1500:] if log.exists() else r.stdout[-1500:]
        return f"FAIL {name}: {tail}"
    subprocess.run(["pdftoppm", "-png", "-r", "300", "-singlefile",
                    str(pdf), str(outdir / name)], check=True, timeout=120)
    return f"OK {name} -> {outdir / (name + '.png')}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parents[2] / "agent-work/docx-build/tikz"))
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    tdir = Path(args.dir)
    texs = sorted(tdir.glob("fig*.tex"))
    if not texs:
        sys.exit("no fig*.tex found")
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for res in ex.map(lambda p: render_one(p, tdir), texs):
            print(res)
            results.append(res)
    fails = [r for r in results if r.startswith("FAIL")]
    print(f"\n{len(results) - len(fails)}/{len(results)} rendered")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
