from pathlib import Path
import hashlib,json,re
import pdfplumber

root=Path(__file__).resolve().parent
word=root/'1005-精简与角标校正版-2026-10-11.docx'
pdf=root/'native-wps/1005-精简与角标校正版-2026-10-11.pdf'
expected=json.loads((root/'changes.json').read_text())['citation_markers']
rx=re.compile(r'\[\d+(?:,\d+)*\]')
markers=[];book_labels=[]
with pdfplumber.open(pdf) as doc:
 for page_no,page in enumerate(doc.pages,1):
  chars=page.chars
  string=''.join(c['text'] for c in chars)
  for match in rx.finditer(string):
   a,b=match.span();citation=chars[a:b]
   if 74<=page_no<=77:
    if abs(citation[0]['x0']-79.44)<0.2:
     book_labels.append({'page':page_no,'text':match.group(),'sizes':[round(c['size'],3) for c in citation],'top':round(citation[0]['top'],3),'font':citation[0]['fontname']})
    continue
   # Compare with nearby regular text on the same line, allowing a citation at a line edge.
   nearby=chars[max(0,a-20):a]+chars[b:b+20]
   normal=[c for c in nearby if c['size']>9.5 and -1<=c['top']-citation[0]['top']<=7]
   rises=[round(c['bottom']-citation[0]['bottom'],3) for c in normal]
   markers.append({'page':page_no,'text':match.group(),'sizes':sorted(set(round(c['size'],3) for c in citation)),'fonts':sorted(set(c['fontname'] for c in citation)),'same_line_regular_bottom_rises':rises,'raised':bool(rises) and min(rises)>1,'full_marker_superscript':all(abs(c['size']-7.8)<0.001 and 'TimesNewRoman' in c['fontname'] for c in citation)})
assert [m['text'] for m in markers]==[m['text'] for m in expected],(len(markers),len(expected))
assert len(markers)==73 and all(m['full_marker_superscript'] and m['raised'] for m in markers)
assert [m['text'] for m in book_labels]==[f'[{i}]' for i in range(1,86)]
assert all(all(size>10 for size in m['sizes']) for m in book_labels)
report={'status':'PASS','word_sha256':hashlib.sha256(word.read_bytes()).hexdigest(),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'method':'Actual PDF glyph size, fonts and bottom-coordinate rise relative to nearby same-line regular text; full literal marker sequence compared with OOXML citation identity. Visual review is separate.','citation_group_count':73,'bibliography_label_count':85,'citations':markers,'bibliography_labels':book_labels}
(root/'pdf-citation-geometry-final.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print({k:report[k] for k in ['status','word_sha256','pdf_sha256','citation_group_count','bibliography_label_count']})
