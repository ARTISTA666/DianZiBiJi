#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 3：构造 pandoc reference docx（物电学院格式样式集）。

版面（SPECIFICATION.md §2）：A4，上/下 2.54cm，左 3.0cm（含装订线），右 2.5cm。
样式（§3.2 表）：
- Normal/正文：宋体+Times New Roman 小四 12pt，两端对齐，首行缩进 2 字符，固定行距 20 磅
  （行距取研究生院 202003 规定口径，与现役 PDF 一致；物电 spec 允许 1.25~1.5 倍）
- Heading1 章标题：黑体 三号 16pt 加粗 居中，每章另起页
- Heading2 节标题：黑体 四号 14pt 加粗 左对齐
- Heading3 条标题：黑体 小四 12pt 加粗 左对齐
- Block Text 引用块：楷体 12pt，左缩进 2 字符
- 表内/题注/文献按五号 10.5pt 在总装阶段处理（pandoc 不经这些样式）
"""

import docx
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "agent-work/docx-build/ahnu_ref.docx"


def set_fonts(style, west, east, size_pt, bold=False):
    f = style.font
    f.name = west
    f.size = Pt(size_pt)
    f.bold = bold
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), west)
    rfonts.set(qn("w:hAnsi"), west)
    rfonts.set(qn("w:eastAsia"), east)


def first_line_chars(style, chars=200):
    """按“字符”单位设首行缩进（2 字符=200×1%），随字号自适应。"""
    ppr = style.element.get_or_add_pPr()
    ind = ppr.find(qn("w:ind"))
    if ind is None:
        ind = ppr.makeelement(qn("w:ind"), {})
        ppr.append(ind)
    ind.set(qn("w:firstLineChars"), str(chars))
    ind.set(qn("w:firstLine"), "480")


def fixed_spacing(style, pt=None, line=20, before=0, after=0):
    pf = style.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if pt == "exact":
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(line)
    else:
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = 1.35


def get_or_add_para_style(st, name):
    try:
        return st[name]
    except KeyError:
        return st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def build():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(2.54)
    sec.left_margin, sec.right_margin = Cm(3.0), Cm(2.5)
    sec.header_distance = sec.footer_distance = Cm(1.5)

    st = doc.styles
    normal = st["Normal"]
    set_fonts(normal, "Times New Roman", "宋体", 12)
    fixed_spacing(normal)

    body = get_or_add_para_style(st, "Body Text")
    set_fonts(body, "Times New Roman", "宋体", 12)
    fixed_spacing(body)
    body.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    first_line_chars(body)

    fp = get_or_add_para_style(st, "First Paragraph")
    set_fonts(fp, "Times New Roman", "宋体", 12)
    fixed_spacing(fp)
    fp.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    first_line_chars(fp)

    h1 = st["Heading 1"]
    set_fonts(h1, "Times New Roman", "黑体", 16, bold=True)
    h1.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h1.paragraph_format.page_break_before = True
    fixed_spacing(h1, before=0, after=18)
    # 黑体西文也用黑体/Times：题注式章标题内含英文较少，西文用 Times
    h1.element.get_or_add_pPr()

    h2 = st["Heading 2"]
    set_fonts(h2, "Times New Roman", "黑体", 14, bold=True)
    h2.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    fixed_spacing(h2, before=13, after=6)
    h2.paragraph_format.keep_with_next = True

    h3 = st["Heading 3"]
    set_fonts(h3, "Times New Roman", "黑体", 12, bold=True)
    h3.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    fixed_spacing(h3, before=6, after=6)
    h3.paragraph_format.keep_with_next = True

    # 引用块（pandoc Block Text 样式）
    bt = get_or_add_para_style(st, "Block Text")
    set_fonts(bt, "Times New Roman", "楷体", 12)
    fixed_spacing(bt)
    bt.paragraph_format.left_indent = Cm(0.99)

    # 行内代码字符样式（pandoc "Verbatim Char"）
    try:
        vc = st["Verbatim Char"]
        set_fonts(vc, "Menlo", "宋体", 10.5)
    except KeyError:
        pass

    # 紧凑列表样式
    try:
        cp = st["Compact"]
        set_fonts(cp, "Times New Roman", "宋体", 12)
        fixed_spacing(cp)
    except KeyError:
        pass

    # 表格基础样式：pandoc 用 "Table"；默认清边框，三线由总装逐表设置
    try:
        tbl = st.add_style("Thesis Table", WD_STYLE_TYPE.TABLE)
    except Exception:
        pass

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    print(f"reference docx -> {OUT}")


if __name__ == "__main__":
    build()
