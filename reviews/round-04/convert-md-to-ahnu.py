# -*- coding: utf-8 -*-
"""最新重构稿 md → bensz-thesis/thesis-ahnu-master 项目章节 tex"""
import io, re, subprocess, sys, shutil
from pathlib import Path

MD = Path("/Users/yusong/Downloads/new/full-system/docs/毕业论文重构稿.md")
PROJ = Path("/tmp/crlt/projects/thesis-ahnu-master")
CN_NUM = "一二三四五六七八九十"

text = MD.read_text(encoding="utf-8")
lines0 = text.split("\n")
if lines0 and lines0[0].strip().startswith("面向科研实验记录"):
    lines0 = lines0[1:]
    while lines0 and not lines0[0].strip():
        lines0 = lines0[1:]
    text = "\n".join(lines0)

# ---------- 切分 ## 段 ----------
segs = []  # (title, body)
cur_title, cur = None, []
for ln in text.split("\n"):
    m = re.match(r"^## (.+)$", ln)
    if m:
        if cur_title is not None:
            segs.append((cur_title, "\n".join(cur)))
        cur_title, cur = m.group(1).strip(), []
    else:
        cur.append(ln)
if cur_title is not None:
    segs.append((cur_title, "\n".join(cur)))
segs = dict(segs)
print("segments:", list(segs.keys()))

# ---------- 片段清洗 ----------
TABLE_NAMES = {
    "7-2": "交付系统复现批次结果",
    "7-3": "功能闭环与安全边界测试项",
    "7-4": "性能测试指标与判定方式",
    "7-5": "实验数据处理阶段与产出",
    "7-6": "实验记录样例的结构化结果",
    "7-7": "三项目语料规模统计",
    "7-8": "关系核验原始与修复后批次",
    "7-9": "20 题成对实验总体结果",
    "7-10": "分题型任务完成率",
    "7-11": "图谱最低得分阈值敏感性",
    "7-12": "四臂扩展消融结果",
    "7-13": "实验 5 单项目五方法描述性结果",
    "7-14": "固定任务生成验证明细",
    "A-1": "RAG 对照实验问题清单",
    "B-1": "核心数据表域映射",
    "B-2": "主要数据表字段与主外键",
    "B-3": "运行时扩展域数据表",
    "C-1": "MCP 工具完整安全规格",
    "C-2": "固定任务模板注册表",
    "D-1": "GSE111619 数据文件完整性清单",    "1-1": "代表性路线五维比较",
    "3-1": "用户角色与需求定位",
    "3-2": "关键痛点与需求约束对应",
    "3-3": "业务场景与AI处理目标映射",
    "4-1": "用户类型与能力矩阵",
    "4-2": "核心功能模块输入输出",
    "4-3": "功能链路与验证材料对应",
    "5-1": "实体类型定义",
    "5-2": "关系类型定义",
    "5-3": "抽取运行批次与计数",
    "5-4": "固定任务模板与安全属性",
    "5-5": "MCP受控工具安全规格",
    "5-6": "预警四维指标与缺省阈值",
    "5-7": "预警操作权限与审计事件",
    "6-1": "核心已审核笔记结构化样例",
    "6-2": "知识图谱抽取关系样例",
    "6-3": "创新点运行界面素材索引",
    "6-4": "系统界面截图素材索引",
}

CAPTION_OVERRIDES = {
    "| 工具 | 风险 | 需确认 | 强制幂等键 | 权限范围 | 审计动作 |": "C-1",
}

def add_table_captions(s: str) -> str:
    """给每张 markdown 管道表注入题注行(供 merge-captions.py 并入 longtable)。
    编号取表前 6 行内最近一次出现的"表 X-Y"或"表 X-Y";6 行内没有编号的表按
    CAPTION_OVERRIDES 的行号内容键补录(附录表等前文远离表体的情形)。"""
    lines = s.split("\n")
    out = []
    pending_caption = None
    for i, ln in enumerate(lines):
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?$", lines[i + 1]):
            # 找近前文编号
            cap = None
            for back in range(1, 7):
                seg = "\n".join(lines[max(0, i - back):i])
                m = re.findall(r"表 ([A-Z]-\d+|\d+-\d+)[^\dA-Z]", seg + " ")
                if m:
                    cap = m[-1]
                    break
            if ln in CAPTION_OVERRIDES:
                cap = CAPTION_OVERRIDES[ln]
            elif cap is None and pending_caption:
                cap = pending_caption
                pending_caption = None
            if cap:
                # 题注文本:用编号 + 通用名(从表首格内容生成简短名)
                cap_name = TABLE_NAMES.get(cap)
                if cap_name is None:
                    first_cell = ln.strip("|").split("|")[0].strip()
                    cap_name = first_cell
                cap_line = "\\textbf{表 %s  %s}" % (cap, cap_name)
                out.append("")
                out.append("\\needspace{6\\baselineskip}")
                out.append(cap_line)
                out.append("")
        elif pending_caption is None:
            pass
        out.append(ln)
    return "\n".join(out)

def guard(s: str) -> str:
    s = re.sub(r"^```latex$", "```{=latex}", s, flags=re.M)
    def _img(m):
        path = m.group(0)
        return path if ("assets/screenshots/" in path or "assets/innovation-screenshots/" in path) else (
            r"\\fbox{\\parbox[c][6cm][c]{0.85\\textwidth}{\\centering (位图占位:由学校模板插入原图)}}")
    s = re.sub(r"\\includegraphics\[[^\]]*\]\{[^}]*\}", _img, s)
    s = s.replace("\\\\[S]", "\\\\{}[S]").replace("\\\\[G]", "\\\\{}[G]")
    s = s.replace("℃", "°C").replace("‐", "-")
    out = []
    for ln in s.split("\n"):
        if re.match(r"^(Read\(u, p\)|Write\(u, p\)|Review\(u, p\)|Manage\(u, p\)|conf\(r\) =|P = TP|F1 = 2PR|C = \(1/N\)|Src_avg|T_avg)", ln):
            ln = ln.replace("_", "\\_")
        out.append(ln)
    return "\n".join(out)

def to_tex(fragment: str, name: str) -> str:
    frag = Path(f"/tmp/crlt/frag_{name}.md")
    frag.write_text(guard(add_table_captions(fragment)), encoding="utf-8")
    r = subprocess.run(["pandoc", str(frag), "-f", "markdown+smart", "-t", "latex",
                        "--top-level-division=chapter", "--shift-heading-level-by=-1",
                        "-o", str(frag.with_suffix(".tex"))], capture_output=True, text=True)
    if r.returncode:
        print("pandoc fail", name, r.stderr[:400]); sys.exit(1)
    return fix_bare_param_strings(fix_table_code_breaks(frag.with_suffix(".tex").read_text(encoding="utf-8")))

def fix_table_code_breaks(tex: str) -> str:
    """texttt 代码串断行修复:列表逗号后、以及长 texttt 内部的下划线转义点后插 allowbreak。"""
    # 1) 列表分隔: \texttt{a},\texttt{b} / a、b
    pat1 = re.compile(r'(\\texttt\{[^}]*\})(,|、)(?=\\texttt\{)')
    tex = pat1.sub(r'\1\2\\allowbreak ', tex)
    # 2) \texttt{...} 内部: 下划线转义(\_)与逗号后允许断行(仅长度>16 的串)
    def _inner(m):
        body = m.group(1)
        if len(body) <= 16:
            return m.group(0)
        body2 = body.replace("\\_", "\\_\\allowbreak{}")
        body2 = body2.replace(",", ",\\allowbreak{}")
        body2 = body2.replace("/", "/\\allowbreak{}")
        body2 = body2.replace("-", "-\\allowbreak{}")
        body2 = body2.replace("=", "=\\allowbreak{}")
        return "\\texttt{" + body2 + "}"
    tex = re.sub(r'\\texttt\{([^}]*)\}', _inner, tex)
    return tex

def to_tex(fragment: str, name: str) -> str:
    frag = Path(f"/tmp/crlt/frag_{name}.md")
    frag.write_text(guard(add_table_captions(fragment)), encoding="utf-8")
    r = subprocess.run(["pandoc", str(frag), "-f", "markdown+smart", "-t", "latex",
                        "--top-level-division=chapter", "--shift-heading-level-by=-1",
                        "-o", str(frag.with_suffix(".tex"))], capture_output=True, text=True)
    if r.returncode:
        print("pandoc fail", name, r.stderr[:400]); sys.exit(1)
    return fix_bare_param_strings(fix_table_code_breaks(frag.with_suffix(".tex").read_text(encoding="utf-8")))

def fix_bare_param_strings(tex: str) -> str:
    """裸参数串(非 texttt)temperature=...,max_tokens=... 逗号/等号后插断点。"""
    tex = tex.replace("temperature=0.1,max\\_tokens=2200,stream=false",
                      "temperature=0.1,\\allowbreak{}max\\_tokens=2200,\\allowbreak{}stream=false")
    tex = tex.replace("temperature=0.1,max\\_tokens=1800,stream=false",
                      "temperature=0.1,\\allowbreak{}max\\_tokens=1800,\\allowbreak{}stream=false")
    return tex


def strip_numbers(tex: str) -> str:
    tex = re.sub(r"(\\chapter\{)第[一二三四五六七八九十]+章\s*", r"\1", tex)
    tex = re.sub(r"(\\section\{)\d+\.\d+\s*", r"\1", tex)
    tex = re.sub(r"(\\subsection\{)\d+\.\d+\.\d+\s*", r"\1", tex)
    return tex

# ---------- 摘要 / Abstract ----------
zh_body = to_tex(segs["摘要"], "abszh")
zh_body = re.sub(r"\\section\*?\{摘\s*要\}\n?", "", zh_body)
zh_body = re.sub(r"关键词：[^\n]*", "", zh_body)
(PROJ/"extraTex/front/abstract_zh.tex").write_text(
    "\\ahnuFrontHeading{摘\\quad 要}\n\n" + zh_body.strip() +
    "\n\n\\vspace{1.2cm}\n\\noindent\\textbf{关键词：}\\ahnuKeywordsZh\n", encoding="utf-8")

en_body = to_tex(segs["Abstract"], "absen")
en_body = re.sub(r"\\section\*?\{Abstract\}\n?", "", en_body)
en_body = re.sub(r"Key words:.*?(?=\n\n|\Z)", "", en_body, flags=re.S)
(PROJ/"extraTex/front/abstract_en.tex").write_text(
    "\\ahnuFrontHeading{Abstract}\n\n" + en_body.strip() +
    "\n\n\\vspace{1.2cm}\n\\noindent\\textbf{Key words:}\\ \\ahnuKeywordsEn\n", encoding="utf-8")

# ---------- 八章正文 ----------
cn2ord = {c: i+1 for i, c in enumerate("一二三四五六七八九十")}
for title, body in segs.items():
    m = re.match(r"^第([一二三四五六七八九十]+)章 (.+)$", title)
    if not m:
        continue
    n = cn2ord[m.group(1)]
    tex = strip_numbers(to_tex("## " + title + "\n\n" + body, f"ch{n}"))
    (PROJ/f"extraTex/body/chapter-{n:02d}.tex").write_text(tex, encoding="utf-8")
    print(f"chapter-{n:02d} <- {title}")

# ---------- 附录 A-D(合并为无编号章 + 手工目录) ----------
appendix_titles = [t for t in segs if t.startswith("附录")]
parts = []
for t in appendix_titles:
    tex = to_tex("## " + t + "\n\n" + segs[t], f"apx{t[:3]}".replace(" ", ""))
    tex = re.sub(r"\\section\{", "\\\\section*{", tex)
    head = f"\\chapter*{{{t}}}\n\\addcontentsline{{toc}}{{chapter}}{{{t}}}\n"
    tex = re.sub(r"\\chapter\{[^}]*\}\n?", "", tex)
    # 节标题加目录行
    def addtoc(mo):
        inner = mo.group(1)
        return f"\\section*{{{inner}}}\n\\addcontentsline{{toc}}{{section}}{{{inner}}}\n"
    tex = re.sub(r"\\section\*\{([^}]*)\}\n?", addtoc, tex)
    parts.append(head + tex)
(PROJ/"extraTex/body/appendix.tex").write_text("\n\n".join(parts), encoding="utf-8")
print("appendix <-", appendix_titles)

# ---------- 参考文献 / 致谢 ----------
ref_body = to_tex(segs["参考文献"], "refs")
ref_body = ref_body.replace("_", "\\_")
(PROJ/"extraTex/back/references.tex").write_text(ref_body.strip() + "\n", encoding="utf-8")
thanks_body = to_tex(segs["致谢"], "thanks")
(PROJ/"extraTex/back/thanks.tex").write_text(thanks_body.strip() + "\n", encoding="utf-8")

# ---------- 缩略词表清空(当前正稿无此页) ----------
(PROJ/"extraTex/front/abbreviations.tex").write_text(
    "% 当前正稿未包含缩略词表;如需补充请在此填写\n", encoding="utf-8")

# ---------- main.tex:输入 8 章 + 附录 ----------
mp = PROJ/"main.tex"
mt = mp.read_text(encoding="utf-8")
mt = re.sub(r"(\\input\{extraTex/body/chapter-01\.tex\})([\s\S]*?)(\\clearpage\n\\chapter\*\{参考文献\})",
            lambda m: m.group(1) + "".join(f"\n\\input{{extraTex/body/chapter-{i:02d}.tex}}" for i in range(2, 9)) +
                      "\n\\input{extraTex/body/appendix.tex}\n" + m.group(3), mt)
mp.write_text(mt, encoding="utf-8")

# ---------- meta.tex:真实元数据 ----------
(PROJ/"extraTex/meta.tex").write_text("""\\def\\ahnuClassNo{TP391}
\\def\\ahnuTitleZh{面向科研实验记录的智能电子实验笔记系统设计与实现}
\\def\\ahnuTitleEn{Design and Implementation of an Intelligent Electronic\\\\Laboratory Notebook System for Scientific Experiment Records}
\\def\\ahnuMajor{电子信息}
\\def\\ahnuResearchDirection{}
\\def\\ahnuAuthor{}
\\def\\ahnuSupervisor{}
\\def\\ahnuSubmitDate{2026 年 8 月 29 日}
\\def\\ahnuDegreeDate{2026 年 9 月}
\\def\\ahnuBottomLine{安徽师范大学硕士学位论文}
\\def\\ahnuBottomDate{（二〇二六年九月）}
\\def\\ahnuKeywordsZh{电子实验笔记；科研数据管理；知识图谱；检索增强生成；固定任务型智能辅助生成}
\\def\\ahnuKeywordsEn{Electronic Laboratory Notebook; Research Data Management; Knowledge Graph; Retrieval-Augmented Generation; Fixed-Task Intelligent Generation}
""", encoding="utf-8")
print("meta written")
print("MIGRATION DONE")
