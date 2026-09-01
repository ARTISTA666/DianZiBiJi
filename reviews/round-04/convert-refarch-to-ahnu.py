# -*- coding: utf-8 -*-
"""参考架构版重构稿 md → bensz-thesis/thesis-ahnu-master 项目章节 tex（第三版）
结构与 convert-md-to-ahnu.py 相同，但内容源为 docs/毕业论文重构稿-参考架构版.md，
六章正文 + 缩略词表启用 + 摘要/关键词/meta 同步参考架构版。
"""
import io, re, subprocess, sys
from pathlib import Path

MD = Path("/Users/yusong/Downloads/new/full-system/docs/毕业论文重构稿-参考架构版.md")
PROJ = Path("/tmp/crlt/projects/thesis-ahnu-master")

text = MD.read_text(encoding="utf-8")
lines0 = text.split("\n")
# 跳过 H1 标题与稿首说明引注块
if lines0 and lines0[0].strip().startswith("# "):
    lines0 = lines0[1:]
while lines0 and (not lines0[0].strip() or lines0[0].strip().startswith(">")):
    lines0 = lines0[1:]
text = "\n".join(lines0)

# ---------- 切分 ## 段 ----------
segs = {}
cur_title, cur = None, []
for ln in text.split("\n"):
    m = re.match(r"^## (.+)$", ln)
    if m:
        if cur_title is not None:
            segs[cur_title] = "\n".join(cur)
        cur_title, cur = m.group(1).strip(), []
    else:
        cur.append(ln)
if cur_title is not None:
    segs[cur_title] = "\n".join(cur)
print("segments:", list(segs.keys()))

# ---------- 片段清洗 ----------
def guard(s: str) -> str:
    s = re.sub(r"^```latex$", "```{=latex}", s, flags=re.M)
    # 参考架构版允许真实插图:assets/screenshots 下的 png 直接放行,其余 includegraphics 仍替换为占位框
    def _img(m):
        path = m.group(0)
        return path if "assets/screenshots/" in path else (
            r"\\fbox{\\parbox[c][6cm][c]{0.85\\textwidth}{\\centering (位图占位:由学校模板插入原图)}}")
    s = re.sub(r"\\includegraphics\[[^\]]*\]\{[^}]*\}", _img, s)
    s = s.replace("\\\\[S]", "\\\\{}[S]").replace("\\\\[G]", "\\\\{}[G]")
    s = s.replace("℃", "°C").replace("‐", "-")
    out = []
    for ln in s.split("\n"):
        if re.match(r"^(Read\(u,p\)|Read\(u, p\)|Write\(u, p\)|Review\(u, p\)|Manage\(u, p\))", ln):
            ln = ln.replace("_", "\\_")
        out.append(ln)
    return "\n".join(out)

def to_tex(fragment: str, name: str) -> str:
    frag = Path(f"/tmp/crlt/frag_rv_{name}.md")
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

# ---------- 摘要 / Abstract（参考架构版为编号工作项体例，保留原样转换） ----------
zh_body = to_tex(segs["摘 要"], "abszh")
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

# ---------- 缩略词表（参考架构版含缩略词表段，启用） ----------
abbrev_body = to_tex(segs["缩略词对照表"], "abbrev")
abbrev_body = re.sub(r"\\section\*?\{[^}]*\}\n?", "", abbrev_body)
(PROJ/"extraTex/front/abbreviations.tex").write_text(
    "\\ahnuFrontHeading{缩略词对照表}\n\n" + abbrev_body.strip() + "\n", encoding="utf-8")
print("abbreviations enabled")

# ---------- 六章正文 ----------
cn2ord = {c: i+1 for i, c in enumerate("一二三四五六七八九十")}
ch_count = 0
for title, body in segs.items():
    m = re.match(r"^第([一二三四五六七八九十]+)章 (.+)$", title)
    if not m:
        continue
    n = cn2ord[m.group(1)]
    tex = strip_numbers(to_tex("## " + title + "\n\n" + body, f"ch{n}"))
    (PROJ/f"extraTex/body/chapter-{n:02d}.tex").write_text(tex, encoding="utf-8")
    ch_count += 1
    print(f"chapter-{n:02d} <- {title}")
assert ch_count == 6, f"expect 6 chapters, got {ch_count}"

# ---------- 清空附录（参考架构版无附录） ----------
(PROJ/"extraTex/body/appendix.tex").write_text("% 参考架构版不含附录\n", encoding="utf-8")

# ---------- 参考文献 / 致谢 ----------
ref_body = to_tex(segs["参考文献"], "refs")
ref_body = ref_body.replace("_", "\\_")
(PROJ/"extraTex/back/references.tex").write_text(ref_body.strip() + "\n", encoding="utf-8")
thanks_body = to_tex(segs["致谢"], "thanks")
(PROJ/"extraTex/back/thanks.tex").write_text(thanks_body.strip() + "\n", encoding="utf-8")

# ---------- main.tex：只保留 chapter-01..06 的输入（清理 07/08 与附录输入行） ----------
mp = PROJ/"main.tex"
mt = mp.read_text(encoding="utf-8")
mt = re.sub(r"\\input\{extraTex/body/chapter-0[78]\.tex\}\n", "", mt)
mt = mt.replace("\\input{extraTex/body/appendix.tex}\n", "")
mp.write_text(mt, encoding="utf-8")
print("main.tex updated to 6 chapters")

# ---------- meta.tex：参考架构版元数据（提交日期按今日） ----------
(PROJ/"extraTex/meta.tex").write_text("""\\def\\ahnuClassNo{TP391}
\\def\\ahnuTitleZh{面向科研实验记录的智能电子实验笔记系统设计与实现}
\\def\\ahnuTitleEn{Design and Implementation of an Intelligent Electronic\\\\Laboratory Notebook System for Scientific Experiment Records}
\\def\\ahnuMajor{电子信息}
\\def\\ahnuResearchDirection{待填}
\\def\\ahnuAuthor{待填}
\\def\\ahnuSupervisor{待填}
\\def\\ahnuSubmitDate{2026 年 9 月 1 日}
\\def\\ahnuDegreeDate{2026 年 9 月}
\\def\\ahnuBottomLine{安徽师范大学硕士学位论文}
\\def\\ahnuBottomDate{（二〇二六年九月）}
\\def\\ahnuKeywordsZh{电子实验笔记；知识图谱；检索增强生成；项目权限隔离；固定任务型智能体}
\\def\\ahnuKeywordsEn{Electronic Laboratory Notebook; Knowledge Graph; Retrieval-Augmented Generation; Project Permission Isolation; Fixed-Task Intelligent Generation}
""", encoding="utf-8")
print("meta written")
import subprocess
subprocess.run(["python3", "reviews/round-04/merge-captions.py"], cwd="/Users/yusong/Downloads/new/full-system", check=True)
print("MIGRATION DONE (reference-architecture edition)")