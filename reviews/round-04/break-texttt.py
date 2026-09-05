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
    inner = inner.replace("-", "-" + AB)
    # 长 hex/哈希串(≥16 位连续字母数字)每 8 字符插断点,否则无法断行
    def _hexrun(mm):
        run = mm.group(0)
        if len(run) >= 16:
            return AB.join(run[i:i+8] for i in range(0, len(run), 8))
        return run
    inner = re.sub(r"[0-9a-f]{16,}", _hexrun, inner)
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

def fix_refs(path: Path) -> int:
    """参考文献条目:DOI/arXiv 长串断行(允许小数点后断,仅限该文件)。"""
    t = path.read_text(encoding="utf-8")
    out = []
    for ln in t.split("\n"):
        res = []
        for i, ch in enumerate(ln):
            nxt = ln[i+1] if i+1 < len(ln) else ""
            res.append(ch)
            if ch in "/-." and nxt.isascii() and (nxt.isalnum() or nxt in "({"):
                if ch == "." and (ln[i-1] if i else "").isdigit() and nxt.isdigit():
                    pass  # 10.1371 的小数点也允许断(仅参考文献文件)
                res.append(AB)
        out.append("".join(res))
    nt = "\n".join(out)
    if nt != t:
        path.write_text(nt, encoding="utf-8")
        return 1
    return 0

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
changed += fix_refs(PROJ / "extraTex/back/references.tex")

SKIP_ENVS = ("longtable", "tikzpicture", "equation", "aligned", "cases",
             "tabular", "lstlisting", "verbatim", "alignedat")
def fix_body(path: Path) -> int:
    """正文段落(环境外、非命令行)插断点:修复正文长 ASCII 串溢出。"""
    t = path.read_text(encoding="utf-8")
    lines = t.split("\n")
    out, env = [], 0
    n = 0
    for ln in lines:
        stripped = ln.lstrip()
        for ev in SKIP_ENVS:
            if "begin{" + ev + "}" in ln:
                env += 1
        if env == 0 and not stripped.startswith(BS) and stripped:
            res = []
            for i, ch in enumerate(stripped):
                nxt = stripped[i+1] if i+1 < len(stripped) else ""
                res.append(ch)
                if ch in "/-=._" and not (nxt.isascii() and nxt.isdigit() and ch in ".="):
                    res.append(AB)
            ln = " " * (len(ln) - len(stripped)) + "".join(res)
            n += 1
        for ev in SKIP_ENVS:
            if "end{" + ev + "}" in ln:
                env = max(0, env - 1)
        out.append(ln)
    nt = "\n".join(out)
    if nt != t:
        path.write_text(nt, encoding="utf-8")
    return n

# fix_body 暂停:其断点会破坏 hyperref 目录/封面(根因待查);遗留溢出改由 md 侧定向修复
if False:
    for bf in sorted(PROJ.glob("extraTex/body/chapter-0*.tex")) + \
              sorted(PROJ.glob("extraTex/back/*.tex")) + \
              [PROJ / "extraTex/back/references.tex"]:
        if bf.exists():
            fix_body(bf)
print("files rewritten:", changed)
