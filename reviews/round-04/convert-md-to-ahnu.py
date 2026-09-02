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
def guard(s: str) -> str:
    s = re.sub(r"^```latex$", "```{=latex}", s, flags=re.M)
    s = re.sub(r"\\includegraphics\[[^\]]*\]\{[^}]*\}",
               r"\\fbox{\\parbox[c][6cm][c]{0.85\\textwidth}{\\centering (位图占位:由学校模板插入原图)}}", s, flags=re.M)
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
    frag.write_text(guard(fragment), encoding="utf-8")
    r = subprocess.run(["pandoc", str(frag), "-f", "markdown+smart", "-t", "latex",
                        "--top-level-division=chapter", "--shift-heading-level-by=-1",
                        "-o", str(frag.with_suffix(".tex"))], capture_output=True, text=True)
    if r.returncode:
        print("pandoc fail", name, r.stderr[:400]); sys.exit(1)
    return frag.with_suffix(".tex").read_text(encoding="utf-8")

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
en_body = re.sub(r"Key words:[^\n]*", "", en_body)
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
