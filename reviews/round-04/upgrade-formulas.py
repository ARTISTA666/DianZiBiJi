# -*- coding: utf-8 -*-
"""v2: 式(4-1)/(5-1)/(7-1)~(7-5) 纯文本公式 → 标准显示公式(完整块插入)"""
import io, re

MD = "/Users/yusong/Downloads/new/full-system/docs/毕业论文重构稿.md"
text = io.open(MD, encoding="utf-8").read()
lines = text.split("\n")

def find_line(prefix, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    raise SystemExit("NOT FOUND: " + prefix)

def block(tag, inner):
    b = "```latex\n\\begin{equation}\n" + inner + "\n\\tag{" + tag + "}\n\\end{equation}\n```"
    return b.split("\n")

# --- 式(4-1) ---
i1 = find_line("Read(u, p) = S(u)")
i4 = find_line("Manage(u, p) = S(u)")
assert i4 - i1 == 3
lines[i1:i4+1] = block("4-1",
 "\\begin{aligned}\n"
 "&\\mathrm{Read}(u,p) = S(u) \\lor O(u,p) \\lor M(u,p) \\lor \\mathrm{PI}(u,p) \\\\\n"
 "&\\mathrm{Write}(u,p) = S(u) \\lor W(u,p) \\\\\n"
 "&\\mathrm{Review}(u,p) = S(u) \\lor V(u,p) \\lor G(u,p) \\\\\n"
 "&\\mathrm{Manage}(u,p) = S(u) \\lor O(u,p) \\lor G(u,p)\n"
 "\\end{aligned}")

# --- 式(5-1) ---
i5 = find_line("conf(r) = 1.0,")
lines[i5:i5+2] = block("5-1",
 "conf(r) =\n"
 "\\begin{cases}\n"
 "1.0, & \\mbox{$r$ 来自项目、笔记、创建者、实验类型或附件等数据库元数据} \\\\\n"
 "0.7, & \\mbox{$r$ 来自笔记结构化字段或正文的规则抽取}\n"
 "\\end{cases}")

# --- 式(7-1) ---
i7 = find_line("P = TP / (TP + FP)")
lines[i7:i7+1] = block("7-1", "P = \\frac{TP}{TP+FP}, \\quad R = \\frac{TP}{TP+FN}")

# --- 式(7-2) ---
i8 = find_line("F1 = 2PR / (P + R)")
lines[i8:i8+1] = block("7-2", "F_{1} = \\frac{2PR}{P+R}")

# --- 式(7-3) ---
i9 = find_line("C = (1/N)")
lines[i9:i9+1] = block("7-3", "C = \\frac{1}{N}\\sum_{i=1}^{N} c_i")

# --- 式(7-4) ---
i10 = find_line("Src_avg = (1/N)")
lines[i10:i10+1] = block("7-4", "\\mathrm{Src}_{\\mathrm{avg}} = \\frac{1}{N}\\sum_{i=1}^{N} src_i")

# --- 式(7-5) ---
i11 = find_line("T_avg = (1/N)")
lines[i11:i11+1] = block("7-5", "\\mathrm{T}_{\\mathrm{avg}} = \\frac{1}{N}\\sum_{i=1}^{N} ms_i")

io.open(MD, "w", encoding="utf-8").write("\n".join(lines))
print("7 formulas upgraded (v2)")
