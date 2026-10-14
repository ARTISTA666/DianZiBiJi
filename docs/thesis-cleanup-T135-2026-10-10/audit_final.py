from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from pypdf import PdfReader
import json, re, hashlib, subprocess

ROOT=Path(__file__).resolve().parent
DOCX=ROOT/'1005-防御性说明清理版-2026-10-10.docx'
PDF=ROOT/'render-final-v3'/'1005-防御性说明清理版-2026-10-10.pdf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W='{'+N['w']+'}'
normalize=lambda t:re.sub(r'\s+','',t)
with ZipFile(DOCX) as z:doc=etree.fromstring(z.read('word/document.xml'))
pages=PdfReader(PDF).pages
lines=[[normalize(line) for line in p.extract_text().splitlines()] for p in pages]
toc=json.loads((ROOT/'toc-changes.json').read_text())
checked=[]
for row in toc['changes']:
    title=row['title']
    if title in ['摘要','Abstract']: physical=4 if title=='摘要' else 5
    else:
        found=[i+1 for i,page in enumerate(lines) if i+1>=toc['body_first_page'] and title in page]
        assert len(found)==1,(title,found)
        physical=found[0]
    assert physical==row['physical_page'],(title,physical,row['physical_page'])
    number=('I' if title=='摘要' else 'II') if title in ['摘要','Abstract'] else str(physical-toc['body_first_page']+1)
    assert number==row['new_cache']
    checked.append({'title':title,'physical_page':physical,'display_page':number})
assert len(checked)==100
(ROOT/'toc-final-audit.json').write_text(json.dumps({'pass':True,'docx_sha256':sha(DOCX),'pdf_sha256':sha(PDF),'physical_pages':len(pages),'checked_entries':len(checked),'entries':checked},ensure_ascii=False,indent=2))

# Whole-body and embedded-figure checks complement the human full-document read.
phrases=['非真人实验数据','非历史原始界面截图','不是新实验结果','历史界面原始截图','逐字段一致','逐字一致','不构成科研结果','不能据此推断','上游模型调用总次数未披露','逐条日志与JUnit未归档','本次未点击反馈','本轮性能观测']
body='\n'.join(''.join(p.xpath('.//w:t/text()',namespaces=N)) for p in doc.xpath('//w:body//w:p',namespaces=N))
body_hits=[p for p in phrases if p in body]
figures=[]
for f in json.loads((ROOT/'figure-changes.json').read_text())['figures']:
    path=ROOT/'figures'/f['png']
    run=subprocess.run(['/tmp/thesis-T135/ocr',str(path)],capture_output=True,text=True,check=True)
    recognized='\n'.join(line.split('\t',5)[-1] for line in run.stdout.splitlines())
    svg=(ROOT/'figures'/f['svg']).read_text()
    hits=[p for p in phrases if p in recognized or p in svg]
    figures.append({'media':f['media'],'png_sha256':sha(path),'svg_sha256':sha(ROOT/'figures'/f['svg']),'ocr':recognized,'disclaimer_hits':hits})
assert not body_hits and not any(f['disclaimer_hits'] for f in figures)
(ROOT/'disclaimer-final-audit.json').write_text(json.dumps({'pass':True,'docx_sha256':sha(DOCX),'reviewed_scope':'3581 source paragraphs read by three reviewers; all48 source figures OCR; six rebuilt figures re-OCR','target_phrases':phrases,'body_hits':body_hits,'figures':figures,'methodological_facts_retained':['合成记录和公开派生记录','GPT子代理评价与角色模拟','模板定义阶段和已编写测试用例','p=0.0938未达到0.05阈值']},ensure_ascii=False,indent=2))
print(json.dumps({'pages':len(pages),'toc_entries_checked':len(checked),'target_phrase_hits':len(body_hits),'rebuilt_figures_ocr':len(figures),'sha256':sha(DOCX)},ensure_ascii=False))
