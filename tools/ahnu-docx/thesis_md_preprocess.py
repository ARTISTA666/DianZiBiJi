#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增强版论文 md → AHNU 物电格式 docx 管线·阶段 1：md 预处理与资产清单。

职责（对应 2026-09-02 首版 docx 管线的同名职责，源稿换为创新点增强版 7 章稿）：
1. 解析 md：标题行与"版本说明"引用块不入正文；摘要/Abstract 抽出为前置部分。
2. 44 个 ```latex 围栏分拣为三类并替换为字母数字标记（pandoc 零解析风险）：
   - tikzpicture（18）→ QQTIKZ<n>QQ，代码另存供 standalone 渲染；
   - includegraphics（18 图，16 个围栏）→ QQIMG<n>QQ，trim 参数随图记录；
   - equation（10）→ $$aligned$$ 数学块 + QQEQ<tag>QQ 标记（\tag 剥离，& 剥离，\\ 保留）。
3. 题注推断：原样移植 convert-enhanced.add_table_captions 的"表前 6 行最近编号"
   逻辑，在**原始 md** 上推断（保证与 PDF 题注口径逐张一致），仅收集不改动。
4. 引号配对：全行直引号按行内交替配对转 “ ”（md 每行引号数为偶数已验证），
   行内反引号 code span 先摘除后还原；smart 关闭时 docx 引号方向由此步保证。
5. 4 行连续引用块拆为 4 个独立块（复现 09-03 审校轮修复项）。

产物（写入 --outdir）：body.md（供 pandoc）、inventory.json（图/式/题注/前置部分）。
"""

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

TABLE_NAMES = {
    "6-1": "两套运行时关键口径对照",
    "6-2": "交付系统复现批次结果",
    "6-3": "功能闭环与安全边界测试项",
    "6-4": "性能测试指标与判定方式",
    "6-5": "实验数据处理阶段与产出",
    "6-6": "实验记录样例的结构化结果",
    "6-7": "20 题成对实验总体结果",
    "A-1": "RAG 对照实验问题清单",
    "B-1": "核心数据表域映射",
    "B-2": "主要数据表字段与主外键",
    "B-3": "运行时扩展域数据表",
    "C-1": "MCP 工具完整安全规格",
    "C-2": "固定任务模板注册表",
    "D-1": "GSE111619 数据文件完整性清单",
    "1-1": "代表性路线五维比较",
    "3-1": "用户角色与需求定位",
    "3-2": "关键痛点与需求约束对应",
    "3-3": "业务场景与AI处理目标映射",
    "4-1": "用户类型与能力矩阵",
    "4-2": "核心功能模块输入输出",
    "4-3": "功能链路与验证材料对应",
    "4-4": "实体类型定义",
    "4-5": "关系类型定义",
    "4-6": "四类固定任务的设计约束",
    "4-7": "MCP受控工具安全规格",
    "4-8": "预警四维指标与缺省阈值",
    "4-9": "预警操作权限与审计事件",
    "5-1": "核心已审核笔记结构化样例",
    "5-2": "知识图谱抽取关系样例",
    "5-3": "三类 DeepSeek 调用接入方式",
}

# 与 reviews/round-04/convert-enhanced.py CAPTION_OVERRIDES 同源
CAPTION_OVERRIDES = {
    "| 工具 | 风险 | 需确认 | 强制幂等键 | 权限范围 | 审计动作 |": "C-1",
}

# 现役 PDF 关键词口径 = extraTex/meta.tex（转换器在 abstract tex 中覆写 md 关键词行，
# T-038 起口径以 meta.tex 为准；此处与 PDF 保持一致而非照抄 md）
KEYWORDS_ZH = "电子实验笔记；科研数据管理；知识图谱；检索增强生成；固定任务型智能辅助生成"
KEYWORDS_EN = ("Electronic Laboratory Notebook; Research Data Management; "
               "Knowledge Graph; Retrieval-Augmented Generation; Fixed-Task Intelligent Generation")

COVER = {
    "class_no": "TP391",
    "school_code": "10370",
    "title_zh": "面向科研实验记录的智能电子实验笔记系统设计与实现",
    "title_en": ("Design and Implementation of an Intelligent Electronic "
                 "Laboratory Notebook System for Scientific Experiment Records"),
    "major": "电子信息",
    "research_direction": "",
    "author": "",
    "supervisor": "",
    "submit_date": "2026 年 8 月 29 日",
    "degree_date": "2026 年 9 月",
}

FENCE_RE = re.compile(r"^```latex\s*$")
SEP_ROW_RE = re.compile(r"^\|[\s:|-]+\|?$")
CAPNUM_RE = re.compile(r"表 ([A-Z]-\d+|\d+-\d+)[^\dA-Z]")


def parse_fences(lines):
    """按行扫 md，返回 (out_lines, tikz, imgs, eqs)。围栏整体替换为标记行。"""
    out, tikz, imgs, eqs = [], [], [], []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if FENCE_RE.match(ln):
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j])
                j += 1
            content = "\n".join(buf)
            if "\\begin{equation}" in content:
                tag_m = re.search(r"\\tag\{([^}]+)\}", content)
                tag = tag_m.group(1) if tag_m else f"EQ{len(eqs)+1}"
                body = re.sub(r"\\tag\{[^}]*\}", "", content)
                body = body.replace("\\begin{equation}", "").replace("\\end{equation}", "")
                body = body.replace("&", "")  # aligned 对齐符在 OMML 中残留 &amp;，全剥
                # \parbox{宽度}{内容} 不被 texmath 支持（pandoc 回退原文）；\text{内容} 能转
                # 且内嵌 $..$ 正常斜体（实测）。两处 \parbox 内容均无嵌套花括号。
                body = re.sub(r"\\parbox\{[^{}]*\}\{([^{}]*)\}", lambda m: "\\text{" + m.group(1) + "}", body)
                # 围栏内 \needspace 一并剥除；$$ 块内不得有空行（pandoc 段内数学不跨空行，
                # 违者整个公式静默消失——6-1 实测）
                body = re.sub(r"\\needspace\{[^}]*\}", "", body)
                body = re.sub(r"\n\s*\n", "\n", body).strip("\n")
                body = body.strip("\n")
                eqs.append({"tag": tag, "tex": body})
                out.append(f"$$\n{body}\n$$")
                out.append(f"QQEQ{tag}QQ")
            elif "\\begin{tikzpicture}" in content:
                cap_m = re.search(r"\\captionof\*\{figure\}\{(.+?)\}\s*$", content, re.M)
                caption = cap_m.group(1) if cap_m else ""
                tik_m = re.search(r"(\\begin\{tikzpicture\}.*\\end\{tikzpicture\})", content, re.S)
                tikz.append({"idx": len(tikz) + 1, "caption": caption, "tex": tik_m.group(1)})
                out.append(f"QQTIKZ{len(tikz)}QQ")
            elif "\\includegraphics" in content:
                for m in re.finditer(
                    r"\\includegraphics\[([^\]]*)\]\{([^}]*)\}\s*\n*\s*\\captionof\*\{figure\}\{(.+?)\}",
                    content,
                ):
                    opts, path, cap = m.group(1), m.group(2), m.group(3)
                    trim = None
                    t = re.search(r"trim=(\d+)bp (\d+)bp (\d+)bp (\d+)bp", opts)
                    if t:
                        # LaTeX trim 顺序 left bottom right top（big points）
                        trim = [int(t.group(1)), int(t.group(2)), int(t.group(3)), int(t.group(4))]
                    imgs.append({
                        "idx": len(imgs) + 1,
                        "path": path.strip(),
                        "caption": cap,
                        "trim_bp": trim,
                        "width_frac": 0.65 if "width=0.65" in opts else (0.86 if "width=0.86" in opts else 0.88),
                    })
                    # 标记之间必须空行分隔——连续标记行会被 pandoc 并成单段（图5-1/5-2 实测）
                    if out and out[-1].startswith("QQIMG"):
                        out.append("")
                    out.append(f"QQIMG{len(imgs)}QQ")
            else:
                raise SystemExit(f"未识别的 latex 围栏 @line{i+1}: {buf[:2]}")
            i = j + 1
            continue
        out.append(ln)
        i += 1
    return out, tikz, imgs, eqs


def infer_table_captions(text):
    """在原始 md 上逐表推断题注（与 convert-enhanced.add_table_captions 同逻辑，仅收集）。
    源函数中 pending_caption 恒为 None（从未赋值），故"6 行内无编号且无 override"的表
    推断不出题注——保持同口径，出现该情形即报错而不是静默沿用。"""
    lines = text.split("\n")
    caps = []
    for i, ln in enumerate(lines):
        if ln.startswith("|") and i + 1 < len(lines) and SEP_ROW_RE.match(lines[i + 1]):
            cap = None
            for back in range(1, 7):
                seg = "\n".join(lines[max(0, i - back):i])
                m = CAPNUM_RE.findall(seg + " ")
                if m:
                    cap = m[-1]
                    break
            if ln in CAPTION_OVERRIDES:
                cap = CAPTION_OVERRIDES[ln]
            caps.append({"num": cap, "name": TABLE_NAMES.get(cap, "") if cap else ""})
    return caps


CODESPAN_RE = re.compile(r"`[^`\n]+`")


def fix_quotes(text):
    """行内交替配对直引号→“ ”；code span 先摘除（内部引号属代码字面量，不动）。"""
    out_lines = []
    for ln in text.split("\n"):
        spans = []
        def _stash(m):
            spans.append(m.group(0))
            return f"\x00CODE{len(spans)-1}\x00"
        ln2 = CODESPAN_RE.sub(_stash, ln)
        if ln2.count('"') % 2 == 1:
            raise SystemExit(f"引号奇数行，中止（需人工核对）: {ln[:60]}")
        open_q = True
        buf = []
        for ch in ln2:
            if ch == '"':
                buf.append("“" if open_q else "”")
                open_q = not open_q
            else:
                buf.append(ch)
        ln2 = "".join(buf)
        for k, sp in enumerate(spans):
            ln2 = ln2.replace(f"\x00CODE{k}\x00", sp)
        out_lines.append(ln2)
    return "\n".join(out_lines)


def split_quote_block(text):
    """连续多行 `>` 引用块按行拆为独立块（pandoc 会把相邻行并成单段，09-03 审校修复项）。"""
    lines = text.split("\n")
    out, run = [], []

    def flush():
        if not run:
            return
        out.append(run[0])
        for x in run[1:]:
            out.append("")
            out.append(x)
        run.clear()

    for ln in lines:
        if ln.startswith(">"):
            run.append(ln)
        else:
            flush()
            out.append(ln)
    flush()
    return "\n".join(out)


def shift_headings(md):
    """md 章为 ##（LaTeX 管线由转换器映射 \\chapter）；docx 走 pandoc 默认映射，
    需整体降一级：## → #（Heading1 章）、### → ##（节）、#### → ###（条）。"""
    return re.sub(r"^(#{1,5}) ", lambda m: "#" * (len(m.group(1)) - 1) + " ", md, flags=re.M)


def extract_front(body_text):
    """从 '## 摘要' … '## Abstract' … '## 第一章' 抽前置部分，返回 (摘要段列表, Abstract 段列表, 正文 md)。"""
    zh_m = re.search(r"^## 摘要\s*\n(.*?)^## Abstract\s*$", body_text, re.M | re.S)
    en_m = re.search(r"^## Abstract\s*\n(.*?)^## 第一章", body_text, re.M | re.S)
    if not (zh_m and en_m):
        raise SystemExit("摘要/Abstract 结构定位失败")
    zh = zh_m.group(1).strip()
    en = en_m.group(1).strip()
    zh = re.sub(r"^关键词：.*$", "", zh, flags=re.M).strip()
    en = re.sub(r"^Key words:.*$", "", en, flags=re.M).strip()
    zh_paras = [p.strip() for p in re.split(r"\n\s*\n", zh) if p.strip()]
    en_paras = [p.strip() for p in re.split(r"\n\s*\n", en) if p.strip()]
    main = body_text[en_m.end() - len("## 第一章"):]
    return zh_paras, en_paras, main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=str(REPO / "docs/毕业论文重构稿-创新点增强版.md"))
    ap.add_argument("--outdir", default=str(REPO / "agent-work/docx-build"))
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    src = Path(args.md).read_text(encoding="utf-8")
    lines = src.split("\n")

    # 标题行 + 版本说明引用块：首行非空文本行，随后第一个 `>` 连续块
    k = 0
    while not lines[k].strip():
        k += 1
    title = lines[k].strip()
    k += 1
    while k < len(lines) and not lines[k].strip():
        k += 1
    if k < len(lines) and lines[k].startswith(">"):
        while k < len(lines) and lines[k].startswith(">"):
            k += 1
    lines = lines[k:]

    body_lines, tikz, imgs, eqs = parse_fences(lines)
    body_text = "\n".join(body_lines)
    body_text = re.sub(r"^\\needspace\{[^}]*\}\s*$", "", body_text, flags=re.M)  # 围栏外残留（660 行图1-1 前）
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)

    zh_paras, en_paras, main_md = extract_front(body_text)

    captions = infer_table_captions(src)

    # 引用块拆行 + 引号配对（只作用于正文；摘要段亦处理）
    main_md = split_quote_block(main_md)
    main_md = fix_quotes(main_md)
    zh_paras = [fix_quotes(p) for p in zh_paras]
    en_paras = [fix_quotes(p) for p in en_paras]

    # 标题降级须在 extract_front 之后（其定位依赖 ## 摘要/## Abstract/## 第一章 原层级）
    main_md = shift_headings(main_md)

    # \?" + 中文 → ？”（T-038 入册的 pandoc smart 缺陷防御）
    main_md = re.sub(r'\?"(?=[\u4e00-\u9fff])', "？”", main_md)

    (outdir / "body.md").write_text(main_md, encoding="utf-8")
    inv = {
        "title": title,
        "cover": COVER,
        "keywords_zh": KEYWORDS_ZH,
        "keywords_en": KEYWORDS_EN,
        "abstract_zh": zh_paras,
        "abstract_en": en_paras,
        "tikz": tikz,
        "imgs": imgs,
        "eqs": eqs,
        "table_captions": captions,
    }
    (outdir / "inventory.json").write_text(
        json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8")

    # tikz 源另存
    tdir = outdir / "tikz"
    tdir.mkdir(exist_ok=True)
    for t in tikz:
        (tdir / f"fig{t['idx']:02d}.tex").write_text(t["tex"], encoding="utf-8")

    print(f"tikz={len(tikz)} imgs={len(imgs)} eqs={len(eqs)} tables={len(captions)} "
          f"abstract_zh={len(zh_paras)} abstract_en={len(en_paras)}")
    print("table captions:", [c["num"] for c in captions])
    missing = [c["num"] for c in captions if not c["name"]]
    print("captions without name:", missing or "none")


if __name__ == "__main__":
    main()
