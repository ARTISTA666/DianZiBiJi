# -*- coding: utf-8 -*-
"""v3: \texttt 与 longtable 单元格断行点;跳过列宽定义行与数字内部"""
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
    # 列宽定义/尺寸表达式行一律不动
    if ("\real{" in ln) or ("tabcolsep" in ln) or ("p{" in ln) \
       or ln.lstrip().startswith(">") or ("\\linewidth" in ln):
        return ln
    out = []
    for i, ch in enumerate(ln):
        prev = ln[i-1] if i > 0 else ""
        nxt = ln[i+1] if i+1 < len(ln) else ""
        if ch in "/-._=":
            # 数字内部(0.2000、2026-08)不插点;小数点前是数字不插点
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

changed = 0
for f in PROJ.glob("extraTex/**/*.tex"):
    t = f.read_text(encoding="utf-8")
    t = t.replace(BS + "allowbreak", "")   # 清除旧断点(含粘连坏词)
    t = tt.sub(fix_tt, t)
    t = lt.sub(lambda m: fix_plain(m.group(0)), t)
    f.write_text(t, encoding="utf-8")
    changed += 1
print("files rewritten:", changed)
