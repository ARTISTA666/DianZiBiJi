"""
将论文初稿 Markdown 转换为 Word (.docx)
用法：python scripts/md_to_docx.py
"""
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

MD_PATH = Path(__file__).resolve().parent.parent / "docs/毕业论文初稿.md"
DOCX_PATH = Path(__file__).resolve().parent.parent / "docs/毕业论文初稿_v2.docx"


def parse_markdown(md_text: str):
    """Simple markdown to docx converter focused on thesis structure"""
    doc = Document()

    # Page setup
    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(3.17)

    # Style: Normal
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)
    style.paragraph_format.line_spacing = 1.5
    style.paragraph_format.space_after = Pt(0)

    lines = md_text.split("\n")
    i = 0
    tables_buffer = []

    while i < len(lines):
        line = lines[i]

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # Collect table lines
        if line.startswith("|") and "---" not in line:
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                if "---" not in lines[i]:
                    table_lines.append(lines[i])
                i += 1
            if table_lines:
                add_table(doc, table_lines)
            continue

        # Headings
        if line.startswith("## ") or line.startswith("### ") or line.startswith("#### "):
            level = len(line.split()[0]) - 1
            text = line.lstrip("# ").strip()
            heading = doc.add_heading(text, level=min(level, 3))
            # Remove the default bold for level 3
            if level >= 3:
                for run in heading.runs:
                    run.font.size = Pt(12)
            i += 1
            continue

        # Bold text
        if line.startswith("**") and line.endswith("**"):
            p = doc.add_paragraph()
            run = p.add_run(line.strip("* "))
            run.bold = True
            run.font.size = Pt(12)
            # Check if it's actually a sub-heading
            if any(word in line for word in ["创新点", "不足", "展望", "问题"]):
                p.paragraph_format.space_before = Pt(6)
            i += 1
            continue

        # Regular paragraph
        text = line.strip()
        if text:
            p = doc.add_paragraph()
            # Handle inline bold
            parts = re.split(r"(\*\*.*?\*\*)", text)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    run = p.add_run(part.strip("*"))
                    run.bold = True
                    run.font.size = Pt(12)
                else:
                    run = p.add_run(part)
                    run.font.size = Pt(12)

        i += 1

    return doc


def add_table(doc, lines):
    """Add a markdown table to the document"""
    rows = []
    for line in lines:
        line = line.strip().strip("|")
        cells = [c.strip() for c in line.split("|")]
        rows.append(cells)

    if len(rows) < 2:
        return

    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    for j, cell_text in enumerate(rows[0]):
        cell = table.rows[0].cells[j]
        cell.text = cell_text
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(10)

    # Data rows
    for i in range(1, len(rows)):
        for j, cell_text in enumerate(rows[i]):
            cell = table.rows[i].cells[j]
            cell.text = cell_text
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.size = Pt(10)

    # Add spacing after table
    doc.add_paragraph()


def main():
    md_text = MD_PATH.read_text(encoding="utf-8")
    doc = parse_markdown(md_text)
    doc.save(str(DOCX_PATH))
    print(f"Word document saved: {DOCX_PATH}")
    print(f"Size: {DOCX_PATH.stat().st_size} bytes")


if __name__ == "__main__":
    main()
