"""T144 read-only actual-PDF citation glyph geometry; adapted from the T142/T143 check."""
import argparse, datetime, hashlib, json, re
from pathlib import Path
import pdfplumber
from pypdf import PdfReader

Q=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--word',required=True);ap.add_argument('--word-sha256',required=True)
ap.add_argument('--pdf',required=True);ap.add_argument('--pdf-sha256',required=True);ap.add_argument('--output',required=True)
a=ap.parse_args();word=Path(a.word).resolve();pdf=Path(a.pdf).resolve()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(word)==a.word_sha256 and sha(pdf)==a.pdf_sha256
baseline=json.loads((Q/'source-protection-inventory-35e9.json').read_text())
expected=baseline['citations'];rx=re.compile(r'\[\d+(?:,\d+)*\]');norm=lambda s:re.sub(r'\s+','',s)
ps=baseline['paragraphs'];start=next(i for i,p in enumerate(ps) if p['text']=='参考文献')
next_heading=next(p['text'] for p in ps[start+1:] if norm(p['text']).startswith('附录A'))
lines=[[norm(s) for s in p.extract_text().splitlines()] for p in PdfReader(pdf).pages]
bib_start=[i+1 for i,ls in enumerate(lines) if '参考文献' in ls]
bib_end=[i+1 for i,ls in enumerate(lines) if norm(next_heading) in ls]
assert len(bib_start)==len(bib_end)==1,(bib_start,bib_end,next_heading)
bibliography_pages=list(range(bib_start[0],bib_end[0]));assert bibliography_pages
left=int(baseline['sections'][-1]['pgMar']['{http://schemas.openxmlformats.org/wordprocessingml/2006/main}left'])/20
markers=[];book_labels=[]
with pdfplumber.open(pdf) as doc:
 for page_no,page in enumerate(doc.pages,1):
  chars=page.chars
  assert all(len(c['text'])==1 for c in chars),'PDF glyph-to-character indexing assumes one character per glyph'
  string=''.join(c['text'] for c in chars)
  for match in rx.finditer(string):
   i,j=match.span();citation=chars[i:j]
   if page_no in bibliography_pages:
    if abs(citation[0]['x0']-left)<.2:
     book_labels.append({'page':page_no,'text':match.group(),'sizes':[round(c['size'],3) for c in citation],'top':round(citation[0]['top'],3),'font':citation[0]['fontname']})
    continue
   nearby=chars[max(0,i-20):i]+chars[j:j+20]
   normal=[c for c in nearby if c['size']>9.5 and -1<=c['top']-citation[0]['top']<=7]
   rises=[round(c['bottom']-citation[0]['bottom'],3) for c in normal]
   markers.append({'page':page_no,'text':match.group(),'sizes':sorted(set(round(c['size'],3) for c in citation)),
    'fonts':sorted(set(c['fontname'] for c in citation)),'same_line_regular_bottom_rises':rises,
    'raised':bool(rises) and min(rises)>1,
    'full_marker_superscript':all(abs(c['size']-7.8)<.001 and 'TimesNewRoman' in c['fontname'] for c in citation)})
checks={'dynamic_bibliography_heading_locations':bool(bibliography_pages),
 'exact_73_citation_literals_and_sequence':[m['text'] for m in markers]==[m['literal'] for m in expected] and len(markers)==73,
 'whole_marker_brackets_numbers_7_8pt_TimesNewRoman':all(m['full_marker_superscript'] for m in markers),
 'all_citations_actually_raised':all(m['raised'] for m in markers),
 '85_normal_bibliography_labels_order_1_85':[m['text'] for m in book_labels]==[f'[{i}]' for i in range(1,86)],
 'bibliography_labels_remain_normal_size_not_superscript':all(all(s>10 for s in m['sizes']) for m in book_labels)}
src=Q.parents[1]/'t143-2026-10-11/check_pdf_citations.py'
report={'task':'T144 independent native-PDF citation and bibliography glyph geometry','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'inputs':{'word':str(word),'word_sha256':sha(word),'pdf':str(pdf),'pdf_sha256':sha(pdf),'source_inventory_sha256':sha(Q/'source-protection-inventory-35e9.json')},
 'script_provenance':{'T143_script':str(src),'T143_script_sha256':sha(src),'adaptations':['CLI explicit input/hash/output identity','73 current-author-source citation inventory','bibliography page range derived from actual PDF heading text, without old 74–77 hard coding','full bracket+number glyph size/font/vertical rise retained']},
 'bibliography_physical_pages':bibliography_pages,'bibliography_end_next_heading':next_heading,'checks':checks,
 'method':'Actual PDF glyph size, fonts and bottom-coordinate rise relative to nearby same-line regular text. Full literal sequence compared with current source OOXML identity. Native-page visual review is separate.',
 'citation_group_count':len(markers),'bibliography_label_count':len(book_labels),'citations':markers,'bibliography_labels':book_labels,
 'findings':[{'check':k} for k,v in checks.items() if not v],'status':'PASS' if all(checks.values()) else 'FAIL'}
out=Q/a.output;assert out.parent==Q and not out.exists();out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':report['status'],'checks':checks,'bibliography_physical_pages':bibliography_pages,'sha256':sha(out)},ensure_ascii=False))
