#!/bin/bash
# AHNU 版式复刻构建:pandoc → .tex → xelatex ×2
set -e
ROOT=/Users/yusong/Downloads/new/full-system
BUILD=/tmp/thesis-ahnu
SRC="$ROOT/docs/毕业论文重构稿.md"
OUT="$ROOT/docs/毕业论文重构稿-AHNU版式-2026-08-29.pdf"
rm -rf "$BUILD" && mkdir -p "$BUILD" && cd "$BUILD"

# ---------- 1. 预处理 ----------
python3 - <<'PYEOF'
import io, re
t = io.open("/Users/yusong/Downloads/new/full-system/docs/毕业论文重构稿.md", encoding="utf-8").read()

# latex 围栏转原生 latex
t = re.sub(r"^```latex$", "```{=latex}", t, flags=re.M)

# 图片占位(仓库内无位图)
t = re.sub(r"\\includegraphics\[[^\]]*\]\{[^}]*\}",
           r"\\fbox{\\parbox[c][6cm][c]{0.85\\textwidth}{\\centering (位图占位:正式排版由学校模板插入原图)}}", t)

# tikz 节点内 \\[S]/\\[G] 转义保护
t = t.replace("\\\\[S]", "\\\\{}[S]").replace("\\\\[G]", "\\\\{}[G]")

# 公式文本行的下划线转义(防 pandoc/latex 误解析)
lines = t.split("\n")
for i, ln in enumerate(lines):
    if re.match(r"^(Read\(u, p\)|Write\(u, p\)|Review\(u, p\)|Manage\(u, p\)|conf\(r\) =|P = TP|F1 = 2PR|C = \(1/N\)|Src_avg|T_avg)", ln):
        lines[i] = ln.replace("_", "\\_")
t = "\n".join(lines)

# 摘要标题留空 + 封面 + 罗马页码
cover = r"""\begin{titlepage}
\thispagestyle{empty}
\begin{center}
{\zihao{-4}\raggedright 分类号：待填}\par
\vspace{2.0cm}
{\zihao{0}\kaishu 安徽师范大学}\par
\vspace{1.4cm}
{\zihao{2}\heiti 硕　士　学　位　论　文}\par
\vspace{1.6cm}
{\zihao{4}\heiti 题　　目：}\\[2mm]
{\zihao{4}\songti 面向科研实验记录的智能电子实验笔记系统设计与实现}\par
\vspace{0.4cm}
{\zihao{4}\heiti Title:}\\[2mm]
{\zihao{-4}Design and Implementation of an Intelligent Electronic Laboratory Notebook System for Scientific Experiment Records}\par
\vspace{1.6cm}
{\zihao{4}\heiti 学科、专业：}\underline{\makebox[6.8cm][c]{电　子　信　息}}\par
\vspace{2mm}
{\zihao{4}\heiti 研究方向：}\underline{\makebox[6.8cm][c]{待\qquad 填}}\par
\vspace{2mm}
{\zihao{4}\heiti 作者姓名：}\underline{\makebox[6.8cm][c]{待\qquad 填}}\par
\vspace{2mm}
{\zihao{4}\heiti 导师及职称：}\underline{\makebox[6.8cm][c]{待\qquad 填}}\par
\vspace{2mm}
{\zihao{4}\heiti 论文提交日：}\underline{\makebox[6.8cm][c]{2026 年\quad 月\quad 日}}\par
\vspace{2mm}
{\zihao{4}\heiti 授予学位单位：}\underline{\makebox[6.2cm][c]{2026 年\quad 月}}\par
\end{center}
\end{titlepage}
\pagenumbering{roman}
"""
t = t.replace("## 摘要", cover + "## 摘  要", 1)

# 目录插入 + 正文起阿拉伯页码
t = t.replace("## 第一章 绪论",
  "\\clearpage\n\\tableofcontents\n\\clearpage\n\\pagenumbering{arabic}\\setcounter{page}{1}\n## 第一章 绪论", 1)

io.open("pre.md", "w", encoding="utf-8").write(t)
print("preprocess ok")
PYEOF

# ---------- 2. 版式头 ----------
cat > header.tex <<'HT'
\setcounter{secnumdepth}{-2}
\setcounter{tocdepth}{2}
\ctexset{
  section={format={\centering\heiti\zihao{3}},beforeskip=1.2em,afterskip=1em},
  subsection={format={\heiti\zihao{4}},beforeskip=0.9em,afterskip=0.6em},
  subsubsection={format={\heiti\zihao{-4}},beforeskip=0.8em,afterskip=0.5em}
}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{}
\renewcommand{\headrulewidth}{0.6pt}
\fancyfoot[C]{\zihao{5}\thepage}
\renewcommand{\contentsname}{目\hspace{1em}录}
HT

# ---------- 3. pandoc → tex(不启用标题移位,防首页被吞) ----------
pandoc pre.md -s -t latex -o thesis.tex \
  -V documentclass=ctexart \
  -V classoption="zihao=-4,fontset=mac" \
  -V geometry:"left=3cm,right=2.5cm,top=3cm,bottom=2.5cm" \
  -V linestretch=1.5 \
  -H header.tex

# 剥离模板自动生成的标题块(封面由预处理提供)
sed -i '' '/\\maketitle/d; /^\\title{/d; /^\\author{/d; /^\\date{/d' thesis.tex

# ---------- 4. xelatex 两遍(目录/页码收敛) ----------
xelatex -interaction=nonstopmode thesis.tex >/dev/null 2>&1 || true
xelatex -interaction=nonstopmode thesis.tex 2>&1 | tail -3 || true
[ -f thesis.pdf ] && cp thesis.pdf "$OUT" && echo "BUILT: $OUT ($(du -k "$OUT" | cut -f1) KB)"
