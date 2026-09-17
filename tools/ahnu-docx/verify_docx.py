#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 5：docx 机器核验（零损失纪律）。

对照源 = agent-work/docx-build/body.md（预处理产物，fence 已替换为标记）。
比对口径与 scripts/audit/thesis_zero_loss_audit.py 的六类 token 思路一致，针对 docx 形态调整：
- 数字 token 多重集全等（Pandoc 中间稿 vs 正文区最终稿，保留段落边界）
- 引文 token [N]/[N-M] 多重集全等
- 正文/表格单元格/公式逐段全文多重集全等；前置中英文摘要另对 inventory 核验
- 标题三级逐条全等；结构计数（H1/H2/H3/表/图/公式表/文献条数）
- 残留清零：QQ 标记 / needspace / includegraphics / \\begin / 直引号 / ¿ / NBSP
排除项（两侧对称排除，不参与比对）：
- 图题注、表题注（docx 侧生成段；md 侧题注本在 fence 内已排除）
- 公式编号 （tag） 段（docx 侧专用；md 侧 \tag 已剥）
- 封面/声明/摘要/目录/页眉页脚（第一个 H1 之前的内容）
"""

import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from lxml import etree

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "agent-work/docx-build"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W, "m": M}

CAPTION_P = re.compile(r"^(表|图) [A-Z0-9]+-\d+　.+$")
EQNUM_P = re.compile(r"^（[A-Z0-9]+-\d+）$")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
CITE_RE = re.compile(r"\[\d+(?:\s*[-–,，]\s*\d+)*\]")


def md_stream_and_lines():
    """token 流在数学/文本边界插 \x00 防粘连（"3.0"+"1" 不得并成 "3.01"）；
    覆盖行剥内联数学、跳过 $$ 块内部行（docx 侧对应 OMML 文本，非逐字符对应）。"""
    text = (BUILD / "body.md").read_text(encoding="utf-8")
    atom_parts, cover_lines, in_block = [], [], False
    for ln in text.split("\n"):
        if re.match(r"^QQ(TIKZ|IMG|EQ)[\w-]+QQ$", ln.strip()):
            continue
        if ln.strip() == "$$":
            in_block = not in_block
            continue
        if in_block:
            atom_parts.append("\x00" + ln + "\x00")  # $$ 块整行独立成原子
            continue
        if re.match(r"^\|[-: |]+\|$", ln):
            continue
        ln = re.sub(r"^#{1,5}\s+", "", ln)
        for piece in re.split(r"(\$[^$\n]+\$)", ln):
            if piece:
                atom_parts.append(("\x00" + piece + "\x00") if piece.startswith("$") else piece)
        stripped = re.sub(r"\$[^$\n]+\$", "", ln)
        if normalize(stripped):
            cover_lines.append(stripped)
    return "".join(atom_parts), cover_lines


def normalize(s):
    """归一化但保留 \x00 原子边界。"""
    s = s.replace("**", "").replace("`", "").replace("*", "").replace("|", "")
    s = re.sub(r"\\([_\[\]*\\])", r"\1", s)
    return re.sub(r"[ \t\n]+", "", s)


def docx_stream_and_paras(docx_path):
    root = etree.fromstring(zipfile.ZipFile(docx_path).read("word/document.xml"))
    body = root.find(f"{{{W}}}body")
    started = False
    parts = []
    para_texts = []
    caption_texts = []
    raw_texts = []
    for ch in body:
        tag = etree.QName(ch).localname
        if tag == "sectPr":
            continue
        texts = [(t.text or "") for t in ch.iter() if t.tag in (f"{{{W}}}t", f"{{{M}}}t")]
        joined = "".join(texts)
        raw_texts.append(joined)
        if not started:
            # md 侧 body.md 不含摘要/Abstract（前置部分由总装直排），流比对从第一章起
            if tag == "p" and is_heading(ch, "1") and joined.startswith("第一章"):
                started = True
            else:
                continue
        if tag == "p":
            t = joined.strip()
            if not t:
                continue
            if CAPTION_P.match(t):
                caption_texts.append(t)
                continue
            if EQNUM_P.match(t):
                continue
            para_texts.append(t)
        parts.append(joined)
    return normalize("".join(parts)), para_texts, caption_texts, "".join(raw_texts), root


def is_heading(p_el, level):
    ps = p_el.find(f"{{{W}}}pPr/{{{W}}}pStyle")
    return ps is not None and ps.get(f"{{{W}}}val") == f"Heading{level}"


def main():
    docx_path = sys.argv[1] if len(sys.argv) > 1 else str(
        REPO / "docs/毕业论文重构稿-创新点增强版-AHNU物电格式-2026-09-17.docx")
    md_s, cover_lines = md_stream_and_lines()
    dx_s, para_texts, caption_texts, raw_all, root = docx_stream_and_paras(docx_path)
    inv = json.loads((BUILD / "inventory.json").read_text(encoding="utf-8"))

    fails = []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    # 1) 逐段比较 Pandoc 中间稿与最终稿，保留数学/文本边界。
    # 旧版把单元格数字拼接，并剥掉 md 数学但保留 docx 数学，导致误报。
    def content_paras(xml, final=False):
        started = not final
        result = []
        for p in xml.findall(".//w:body//w:p", NS):
            text = "".join(p.xpath(".//w:t/text()|.//m:t/text()", namespaces=NS)).replace("\xa0", " ")
            if is_heading(p, "1") and text.startswith("第一章"):
                started = True
            if started and text and not (CAPTION_P.match(text) or EQNUM_P.match(text)
                                          or re.match(r"^QQ(TIKZ|IMG|EQ)", text)):
                result.append(text)
        return result
    source_root = etree.fromstring(zipfile.ZipFile(BUILD / "body.docx").read("word/document.xml"))
    expected, actual = content_paras(source_root), content_paras(root, True)
    # 装订顺序调整允许章节搬动，不允许段落、表格单元格或公式丢失/增写。
    a, b = Counter(expected), Counter(actual)
    check("正文/单元格/公式逐段全等（Pandoc中间稿→最终稿）", a == b,
          f"缺失 {list((a-b).items())[:2]} 新增 {list((b-a).items())[:2]}")
    expected_s, actual_s = "\x00".join(expected), "\x00".join(actual)
    check("数字 token 全等（保留段落边界）",
          Counter(NUMBER_RE.findall(expected_s)) == Counter(NUMBER_RE.findall(actual_s)))
    check("引文 token 全等",
          Counter(CITE_RE.findall(expected_s)) == Counter(CITE_RE.findall(actual_s)))
    # 前置摘要不在中间稿中，单独对库存原文核验。
    raw_norm = normalize(raw_all)
    check("中英文摘要全部保留", all(normalize(t) in raw_norm
          for key in ("abstract_zh", "abstract_en") for t in inv[key]))

    # 3) 标题
    h1 = ["".join(t.text or "" for t in p.iter(f"{{{W}}}t")).strip()
          for p in root.iter(f"{{{W}}}p") if is_heading(p, "1")]
    check("H1 = 15(摘要/Abstract+13章级)", len(h1) == 15, f"实得 {len(h1)}: {h1}")
    h2n = sum(1 for p in root.iter(f"{{{W}}}p") if is_heading(p, "2"))
    h3n = sum(1 for p in root.iter(f"{{{W}}}p") if is_heading(p, "3"))
    check("H2=50 H3=30", h2n == 50 and h3n == 30, f"实得 H2={h2n} H3={h3n}")

    md_h2 = [normalize(re.sub(r"^##\s+", "", l)) for l in
             (BUILD / "body.md").read_text(encoding="utf-8").split("\n") if l.startswith("## ")]
    dx_h2 = [normalize("".join(t.text or "" for t in p.iter(f"{{{W}}}t")))
             for p in root.iter(f"{{{W}}}p") if is_heading(p, "2")]
    check("节标题逐条一致", md_h2 == dx_h2,
          f"差异 {[a for a, b in zip(md_h2, dx_h2) if a != b][:3]}")

    # 4) 结构计数
    tbls = root.findall(f".//{{{W}}}tbl")
    eq_tbls = [t for t in tbls if t.find(f".//{{{M}}}oMathPara") is not None]
    check("总表数 = 41(30正文+10公式+1封面)", len(tbls) == 41, f"实得 {len(tbls)}")
    check("公式表 = 10 且各带编号", len(eq_tbls) == 10 and all(
        EQNUM_P.match("".join(t.text or "" for t in tc.iter(f"{{{W}}}t")).strip())
        for t in eq_tbls
        for tc in t.findall(f"./{{{W}}}tr/{{{W}}}tc")[1:]), "")
    drawings = root.findall(f".//{{{W}}}drawing")
    check("插图 = 36(18tikz+18截图)", len(drawings) == 36, f"实得 {len(drawings)}")

    refs = [p for p in para_texts if re.match(r"^\[\d+\]", p)]
    check("文献条目 = 118", len(refs) == 118, f"实得 {len(refs)}")

    # 5) 题注与题注名
    caps = [t for t in caption_texts if t.startswith("表 ")]
    check("表题注 = 30 且顺序一致", len(caps) == 30 and all(
        caps[i].startswith(f"表 {c['num']}　") for i, c in enumerate(inv["table_captions"])),
        f"实得 {len(caps)}")
    fig_caps = [t for t in caption_texts if t.startswith("图 ")]
    check("图题注 = 36", len(fig_caps) == 36, f"实得 {len(fig_caps)}")

    # 6) 残留
    all_text = dx_s
    for pat, name in ((r"QQ(TIKZ|IMG|EQ)", "QQ标记"), (r"needspace", "needspace"),
                      (r"includegraphics", "includegraphics"), (r"\\begin", "latex环境"),
                      (r'"', "直引号"), (r"¿", "倒问号")):
        check(f"残留清零:{name}", not re.search(pat, all_text))
    check("残留清零:NBSP", "\xa0" not in raw_all)

    # 7) 公式编号与 tag 对应
    tags = sorted(re.findall(r"（([0-9]+-[0-9]+)）", dx_s.replace("，", "")))
    inv_tags = sorted(e["tag"] for e in inv["eqs"])
    check("公式编号集合一致", tags == inv_tags, f"{tags} vs {inv_tags}")

    print("\n" + ("ALL PASS ✅" if not fails else f"FAILED ({len(fails)}): {fails}"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
