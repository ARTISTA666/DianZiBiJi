#!/usr/bin/env python3
"""AHNU physics master's thesis: isolated Markdown → XeLaTeX PDF build."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    with (cwd / 'build.log').open('a') as f:
        f.write('\n' + repr(command) + '\n' + result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed; see {cwd / "build.log"}')
    return result.stdout


def validate_source(text):
    titles = re.findall(r'^## (.+)$', text, re.M)
    if len(titles) != len(set(titles)):
        raise ValueError('Duplicate top-level headings would discard content')
    for title in ('摘要', 'Abstract', '致谢', '参考文献'):
        if title not in titles:
            raise ValueError(f'Missing section: {title}')
    chapters = [t for t in titles if re.match(r'^第[一二三四五六七八九十]+章 ', t)]
    expected = ['第' + n + '章 ' for n in '一二三四五六七八九十'[:len(chapters)]]
    if not chapters or any(not t.startswith(n) for t, n in zip(chapters, expected)):
        raise ValueError('Chapters must be consecutive and ordered, starting at one')
    known = set(chapters + [t for t in titles if t.startswith('附录')] + ['摘要', 'Abstract', '致谢', '参考文献'])
    if set(titles) - known:
        raise ValueError(f'Unmapped sections: {set(titles) - known}')
    return chapters


def main_tex(chapter_count):
    chapters = '\n'.join(r'\input{extraTex/body/chapter-%02d.tex}' % n for n in range(1, chapter_count + 1))
    return r'''\documentclass[UTF8,12pt,a4paper,oneside,openany,fontset=none,AutoFakeBold]{ctexbook}
\usepackage{bensz-thesis}
\BenszThesisSetup{template=thesis-ahnu-master}
\usepackage{ahnu-reference}
\input{extraTex/meta.tex}
\begin{document}
\pagenumbering{Roman}
\ahnuMakeCover\clearpage
\ahnuMakeTitlePage\clearpage
\pagestyle{ahnu-front}
\input{extraTex/front/abstract_zh.tex}\clearpage
\input{extraTex/front/abstract_en.tex}\clearpage
\tableofcontents\clearpage
\pagenumbering{arabic}\pagestyle{ahnu-main}
''' + chapters + r'''
\clearpage\chapter*{致谢}\addcontentsline{toc}{chapter}{致谢}
\input{extraTex/back/thanks.tex}
\ahnuReferencesHeading
\input{extraTex/back/references.tex}
\clearpage\input{extraTex/body/appendix.tex}
\end{document}
'''


def tex_escape(value):
    return ''.join({'\\':r'\textbackslash{}','{':r'\{','}':r'\}','%':r'\%','&':r'\&','#':r'\#','_':r'\_','$':r'\$','^':r'\textasciicircum{}','~':r'\textasciitilde{}'}.get(c,c) for c in value)


def format_references(tex):
    """Style entries without replacing the author's bibliography metadata."""
    pattern = r'^\{\[\}(\d+)\{\]\}\s+'
    labels = [int(n) for n in re.findall(pattern, tex, re.M)]
    if not labels or labels != list(range(1, len(labels) + 1)):
        raise ValueError('Bibliography labels must be consecutive, unique and ordered')
    body = re.sub(pattern, lambda m: r'\item[{[' + m[1] + ']}] ', tex, flags=re.M)
    return '\\begin{ahnuReferences}\n' + body.strip() + '\n\\end{ahnuReferences}\n', len(labels)


def superscript_citations(tex, reference_count):
    # Only Pandoc's literal bracket form; math and raw TeX use other forms.
    # A zero or out-of-range ID denotes an interval/data value, never a citation.
    pattern = r'\{\[\}(\d+(?:\s*[,，\-–]\s*\d+)*)\{\]\}'
    def replace(match):
        ids = [int(n) for n in re.findall(r'\d+', match[1])]
        if all(1 <= n <= reference_count for n in ids):
            return r'\textsuperscript{[' + match[1] + ']}'
        return match[0]
    return re.sub(pattern, replace, tex)


def format_test_table(tex):
    """The reference uses a grid for functional tests and three rules for data."""
    def replace(match):
        table = match[0]
        if '表 6-3 功能闭环与安全边界测试项' not in table:
            return table
        split = table.index(r'\multicolumn')
        spec, rest = table[:split], table[split:]
        columns = spec.count(r'\arraybackslash')
        if not columns:
            raise ValueError('Unsupported functional-test table preamble')
        spec = spec.replace('@{}', '|').replace('\n  >', '|\n  >')
        # First column needs only the existing left rule, not a duplicate.
        spec = spec.replace('||\n', '|\n', 1)
        spec = spec.replace(r'\raggedright', r'\centering')
        spec = re.sub(r'\\linewidth - \d+\\tabcolsep',
                      lambda _: rf'\linewidth - {2*columns}\tabcolsep - {columns+1}\arrayrulewidth', spec)
        rest = rest.replace(r'\raggedright', r'\centering')
        rest = rest.replace(r'\toprule\noalign{}', r'\hline').replace(r'\midrule\noalign{}', r'\hline')
        rest = rest.replace(r'\bottomrule\noalign{}', '')
        header, rows = rest.split(r'\endlastfoot', 1)
        rows = rows.replace('\\\\\n', '\\\\\\hline\n')
        return '{\\bfseries\n' + spec + header + r'\endlastfoot' + rows + '\n}'
    return re.sub(r'\\begin\{longtable\}[\s\S]*?\\end\{longtable\}', replace, tex)


def wrap_identifiers(tex):
    """Allow breaks within code identifiers; preserve every displayed character."""
    start = 0
    while True:
        a = tex.find(r'\texttt{', start)
        if a < 0:
            break
        b, depth = a + len(r'\texttt{'), 1
        content_start = b
        while b < len(tex) and depth:
            if tex[b] == '{' and tex[b-1] != '\\':
                depth += 1
            elif tex[b] == '}' and tex[b-1] != '\\':
                depth -= 1
            b += 1
        if depth:
            raise ValueError('Unbalanced texttt in converted document')
        body = tex[content_start:b-1]
        # Do not split TeX command names; split only literal alphabetic runs.
        body = re.sub(r'\\[A-Za-z]+|[A-Za-z0-9]{5,}',
                      lambda m: m[0] if m[0].startswith('\\') else r'\allowbreak{}'.join(m[0][i:i+4] for i in range(0,len(m[0]),4)),body)
        tex = tex[:content_start] + body + tex[b-1:]
        start = content_start + len(body) + 1
    return tex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'docs/毕业论文重构稿-创新点增强版.md')
    parser.add_argument('--output', type=Path, default=ROOT/'output/ahnu-thesis')
    parser.add_argument('--metadata', type=Path, default=HERE/'metadata.json')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--strict', action='store_true', help='Fail on font fallback, missing author metadata, missing glyphs or overflow')
    args = parser.parse_args()
    source = args.source.resolve()
    raw = source.read_bytes()
    text = raw.decode('utf-8')
    chapters = validate_source(text)
    meta = json.loads(args.metadata.read_text())
    for binary in ['pandoc'] + ([] if args.prepare_only else ['xelatex','latexmk','pdftotext','pdfinfo']):
        if not shutil.which(binary):
            raise ValueError(f'Missing dependency: {binary}')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out = args.output.resolve() / stamp
    out.mkdir(parents=True)
    for directory in ('front', 'body', 'back'):
        (out/'extraTex'/directory).mkdir(parents=True)
    snapshot = out/'source.md'
    snapshot.write_bytes(raw)
    shutil.copytree(HERE/'template',out,dirs_exist_ok=True)
    asset_hashes = {}
    for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', text):
        if name.startswith('assets/screenshots/'):
            asset = ROOT/'docs/user-guide-assets'/Path(name).name
        elif name.startswith('assets/innovation-screenshots/'):
            asset = ROOT/'docs/innovation/screenshots'/Path(name).name
        else:
            asset = source.parent/name
        if not asset.is_file():
            raise ValueError(f'Missing image (no placeholders allowed): {asset}')
        target = (out/name).resolve()
        if not target.is_relative_to(out):
            raise ValueError(f'Image escapes build directory: {name}')
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(asset,target)
        asset_hashes[name] = sha(target)
    run([sys.executable,str(HERE/'convert.py'),str(snapshot),str(out)],out)
    run([sys.executable,str(HERE/'merge_captions.py'),str(out)],out)
    (out/'main.tex').write_text(main_tex(len(chapters)))
    if any(not re.fullmatch(r'ahnu[A-Za-z]+', key) or not isinstance(value, str) for key,value in meta.items()):
        raise ValueError('Metadata requires ahnu-prefixed command names and plain text values')
    (out/'extraTex/meta.tex').write_text('\n'.join(r'\def\%s{%s}'%(key,r'\\'.join(tex_escape(line) for line in value.split('\n'))) for key,value in meta.items()))
    refs = out/'extraTex/back/references.tex'
    ref_tex, reference_count = format_references(refs.read_text())
    refs.write_text(ref_tex)
    # Keep screenshot and caption on one page; do not alter TikZ drawings.
    paths = list((out/'extraTex/body').glob('*.tex')) + list((out/'extraTex/front').glob('abstract_*.tex')) + list((out/'extraTex/back').glob('*.tex'))
    for path in paths:
        tex = wrap_identifiers(path.read_text())
        tex = tex.replace('AgentGenerationService', r'Agent\allowbreak{}Generation\allowbreak{}Service')
        tex = tex.replace(r'\needspace{6\baselineskip}', '')
        # Reserve enough room for a short chapter summary, avoiding a final
        # line stranded on an otherwise empty page before the next chapter.
        tex = tex.replace(r'\section{本章小结}',
                          r'\Needspace{280bp}\section{本章小结}')
        tex = format_test_table(tex)
        if path.name == 'references.tex':
            tex = tex.replace('//', r'//\allowbreak{}')
        else:
            tex = superscript_citations(tex, reference_count)
        tex = re.sub(r'\\begin\{center\}\s*(\\includegraphics[\s\S]*?\\captionof\*?\{figure\}[^\n]*?)\s*\\end\{center\}',r'\\begin{center}\\begin{minipage}{\\linewidth}\\centering\n\1\n\\end{minipage}\\end{center}',tex)
        # Constrain drawings without distorting them; no raster placeholders.
        tex = tex.replace(r'\begin{tikzpicture}',r'\begin{adjustbox}{max width=\linewidth}\begin{tikzpicture}')
        tex = tex.replace(r'\end{tikzpicture}',r'\end{tikzpicture}\end{adjustbox}')
        # Break long literal slash-separated lists, excluding command paths.
        tex = re.sub(r'(?<![A-Za-z\\/{])(?:[A-Za-z0-9-]+/){2,}[A-Za-z0-9-]+',
                     lambda m: m[0].replace('/',r'/\allowbreak{}'),tex)
        path.write_text(tex)
    report = {'version':'ahnu-reference-v2','source':str(source),'source_sha256':sha(snapshot),'chapters':chapters,'images':asset_hashes,'references':reference_count,'status':'prepared','reference_profile':json.loads((HERE/'reference-profile.json').read_text()),'warnings':['版式以作者提供的2024范文实测为准；非学院认证模板','罗马页码连续计数，未复刻范文缺失背页导致的I/III/V跳号','参考文献保留源稿文字和编号，未自动改写文献元数据'],'metadata_missing':[k for k in ('ahnuAuthor','ahnuSupervisor','ahnuResearchDirection','ahnuSubmitDate','ahnuBottomDate') if not meta.get(k)]}
    abstract = text.split('## 摘要',1)[1].split('## Abstract',1)[0].split('关键词',1)[0]
    report['abstract_han_characters'] = len(re.findall(r'[\u4e00-\u9fff]',abstract))
    if report['abstract_han_characters'] > 1000:
        report['warnings'].append('中文摘要汉字计数超过1000；需作者压缩内容')
    report['implementation_sha256'] = {str(p.relative_to(HERE)): sha(p) for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.py','.sty','.tex','.def','.json','.png')}
    report['metadata_sha256'] = sha(args.metadata)
    report['tool_versions'] = {tool:run([tool,'--version'],out).splitlines()[0] for tool in ['pandoc']+([] if args.prepare_only else ['xelatex','latexmk'])}
    if not args.prepare_only:
        run(['latexmk','-xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error','main.tex'],out)
        log=(out/'main.log').read_text(errors='replace')
        report['missing_glyphs']=re.findall(r'Missing character:[^\n]+',log)
        report['overfull_boxes']=re.findall(r'Overfull \\[hv]box[^\n]+',log)
        report['font_fallbacks']=re.findall(r'AHNU-FONT-FALLBACK:[^\n]+',log)
        report['pdf_info']=run(['pdfinfo','main.pdf'],out)
        run(['pdftotext','-layout','main.pdf','main.txt'],out)
        if report['missing_glyphs'] or report['overfull_boxes']:
            report['status']='failed-layout'
        else:
            report['status']='preview-built'
        report['pdf_sha256']=sha(out/'main.pdf')
    report['source_unchanged_since_snapshot']=sha(source)==sha(snapshot)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(out)
    if report['status'].startswith('failed') or (args.strict and (args.prepare_only or report.get('font_fallbacks') or report['metadata_missing'])):
        raise RuntimeError(f'Validation failed; see {out / "report.json"}')


if __name__=='__main__':
    main()
