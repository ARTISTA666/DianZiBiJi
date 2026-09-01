# -*- coding: utf-8 -*-
"""表题注合并:把独立的 textbf 表题注段并入其后最近的 longtable 首行,
以 multicolumn 居中形式消除题注/表体跨页分离与列宽崩塌(caption 误入列 preamble 会导致 array Error)。
由 convert-refarch-to-ahnu.py 在写完章节 tex 后调用;幂等,可重复执行。

正则用 re.escape 构造字面前缀,规避反斜杠转义歧义。
"""
import re
from pathlib import Path

PROJ = Path("/tmp/crlt/projects/thesis-ahnu-master")
B = chr(92)  # 单个反斜杠(LaTeX 命令前缀)

# 题注行字面形如:B + "textbf{表 3-1 系统角色分析表}"
prefix = re.escape(B + "textbf{表 ")
rest = r"(\d+)-(\d+)\s([^}]*)\}$"
line_re = re.compile(prefix + rest)

total = 0
for f in sorted(PROJ.glob("extraTex/body/chapter-0*.tex")):
    lines = f.read_text().split("\n")
    out, i, merged = [], 0, 0
    while i < len(lines):
        ln = lines[i]
        m = line_re.match(ln.strip())
        if not m:
            out.append(ln)
            i += 1
            continue
        j = i + 1
        while j < len(lines) and j <= i + 6 and "begin{longtable}" not in lines[j]:
            j += 1
        if j >= len(lines) or "begin{longtable}" not in lines[j]:
            out.append(ln)
            i += 1
            continue
        title = "表 %s-%s %s" % (m.group(1), m.group(2), m.group(3))
        out.extend(lines[i + 1:j + 1])  # 保留 LTcaptype 行与 begin{longtable} 行
        # 列数:begin 行 @{} 之后的列定义(lrr 简表)或后续 >{ 列定义行(dimexpr 表)
        _spec = lines[j].split("@{}", 1)[-1]        # "@{}lrr@{}}" -> "lrr@{}}"
        _spec = _spec.split("@{")[0]                # -> "lrr"
        cols = len(re.findall(r"[lrc]", _spec))
        j += 1
        while j < len(lines) and lines[j].lstrip().startswith(">{"):
            cols += 1
            out.append(lines[j])
            j += 1
        # LaTeX 文本: \multicolumn{cols}{c}{\textbf{title}}\\
        out.append(B + "multicolumn{%d}{c}{" % cols
                   + B + "textbf{%s}}" % title + B*2)
        merged += 1
        i = j
    if merged:
        f.write_text("\n".join(out))
        print(f.name, "merged", merged)
        total += merged
print("total merged:", total)
