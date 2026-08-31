# -*- coding: utf-8 -*-
"""v4: \texttt/单元格断行点 + pandoc 列宽表达式 → 原生 dimexpr(消除 calc/\real 依赖)"""
import io, re
from pathlib import Path

PROJ = Path("/tmp/crlt/projects/thesis-ahnu-master")
BS = chr(92)
AB = BS + "allowbreak{}"

tt = re.compile(re.escape(BS + "texttt{") + r"([^{}]*)" + re.escape("}"))

def fix_tt(m):
    inner = m.group(1)
    inner = inner.replace(BS + "_", BS + "_" + AB)
    inner = inner.replace("/", "/" + AB)
    inner = inner.replace(".", "." + AB)
    inner = inner.replace("=", "=" + AB)
    return BS + "texttt{" + inner + "}"

def fix_line(ln: str) -> str:
    if ("\real{" in ln) or ("tabcolsep" in ln) or ("p{" in ln) \
       or ln.lstrip().startswith(">") or ("\\linewidth" in ln):
        return ln
    out = []
    for i, ch in enumerate(ln):
        prev = ln[i-1] if i > 0 else ""
        nxt = ln[i+1] if i+1 < len(ln) else ""
        if ch in "/-._=":
            if prev.isdigit() and nxt.isdigit():
                out.append(ch); continue
            if ch == "." and prev.isdigit():
                out.append(ch); continue
            out.append(ch)
            if ch in "/-=.":
                out.append(AB)
        else:
            out.append(ch)
    return "".join(out)

def fix_plain(seg: str) -> str:
    spans = []
    def stash(m):
        spans.append(m.group(0))
        return chr(0) + str(len(spans) - 1) + chr(0)
    seg = tt.sub(stash, seg)
    seg = seg.replace(BS + "_", BS + "_" + AB)
    seg = "\n".join(fix_line(l) for l in seg.split("\n"))
    def unstash(m):
        return spans[int(m.group(1))]
    return re.sub(chr(0) + r"(\d+)" + chr(0), unstash, seg)

lt = re.compile(re.escape(BS + "begin{longtable}") + r"[\s\S]*?" + re.escape(BS + "end{longtable}"))

# pandoc 列宽: p{(\linewidth - N\tabcolsep) * \real{W}} → p{\dimexpr(...)*NUM/10000\relax}
width_pat = re.compile(
    re.escape("p{(" + BS + "linewidth - ") + r"(\d+)" + re.escape(BS + "tabcolsep) * "
              + BS + "real{") + r"([0-9.]+)" + re.escape("}}"))

def fix_width(m):
    ncol = m.group(1)
    num = int(round(float(m.group(2)) * 10000))
    return ("p{" + BS + "dimexpr(" + BS + "linewidth - " + ncol + BS + "tabcolsep)*"
            + str(num) + "/10000" + BS + "relax}")

changed = 0
for f in PROJ.glob("extraTex/**/*.tex"):
    t = f.read_text(encoding="utf-8")
    t = t.replace(BS + "allowbreak", "")   # 清除旧断点(含粘连坏词)
    t = tt.sub(fix_tt, t)
    t = lt.sub(lambda m: fix_plain(m.group(0)), t)
    t = width_pat.sub(fix_width, t)
    t = t.replace("@{}}", "}")   # 去掉 longtable 可选参数尾部的 @{}(规避 no counter 冲突)
    f.write_text(t, encoding="utf-8")
    changed += 1
print("files rewritten:", changed)
