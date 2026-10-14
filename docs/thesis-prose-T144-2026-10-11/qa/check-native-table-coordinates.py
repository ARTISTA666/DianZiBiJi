"""Read-only final native-PDF horizontal rule boundary audit using actual vector coordinates."""
import argparse, json, hashlib, datetime, zipfile, re, unicodedata
from pathlib import Path
from lxml import etree as E
import pdfplumber
from pypdf import PdfReader
Q=Path(__file__).resolve().parent;NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'};W='{'+NS['w']+'}'
h=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
norm=lambda t:re.sub(r'\s+','',unicodedata.normalize('NFKC',t))
def main():
 ap=argparse.ArgumentParser()
 for k in ['word','word-sha256','pdf','pdf-sha256','output']:ap.add_argument('--'+k,required=True)
 a=ap.parse_args();wp,pp=Path(a.word).resolve(),Path(a.pdf).resolve();assert h(wp)==a.word_sha256 and h(pp)==a.pdf_sha256
 d=E.fromstring(zipfile.ZipFile(wp).read('word/document.xml'));s=d.xpath('.//w:sectPr',namespaces=NS)[-1];mar=s.find('w:pgMar',NS);sz=s.find('w:pgSz',NS)
 left=int(mar.get(W+'left'))/20;right=(int(sz.get(W+'w'))-int(mar.get(W+'right')))/20
 baseline=json.loads((Q/'source-protection-inventory-35e9.json').read_text());strict=[t for t in baseline['tables'] if t['strict_data_table']];assert len(strict)==98 and min(sum(map(int,t['grid_twips']))/20 for t in strict)>300
 all_lines=[];bad=[];pages=[];texts=[]
 with pdfplumber.open(pp) as pdf:
  for i,p in enumerate(pdf.pages,1):
   texts.append([norm(x) for x in p.extract_text().splitlines()]);pl=[]
   for e in p.edges:
    if e.get('orientation')!='h' or e['x1']-e['x0']<300:continue
    v={k:e[k] for k in ['x0','x1','top','bottom']};v.update(physical_page=i,printed_page=i-7,inside_body=e['x0']>=left-.05 and e['x1']<=right+.05)
    all_lines.append(v);pl.append(v)
    if not v['inside_body']:bad.append(v)
   pages.append({'physical_page':i,'page_size_pt':[p.width,p.height],'wide_rules':len(pl),'left_min':min([v['x0'] for v in pl],default=None),'right_max':max([v['x1'] for v in pl],default=None)})
  assert len(pdf.pages)==100
 mappings=[]
 for idx,t in enumerate(d.xpath('.//w:tbl',namespaces=NS)):
  prev=t.getprevious();cap=''
  while prev is not None:
   if prev.tag==W+'p':
    txt=''.join(prev.xpath('.//w:t/text()',namespaces=NS))
    if re.match(r'^表\s*[A-D\d]+-\d+(?:[a-z]|\([a-z]\))?[\s　]',txt):cap=txt;break
   prev=prev.getprevious()
  cp=norm(cap);phys=[j+1 for j,l in enumerate(texts) if cp and (cp in l or any(cp==''.join(l[k:k+2]) for k in range(len(l)-1)))]
  pr=t.find('w:tblPr',NS)
  def read(name):
   n=pr.find('w:'+name,NS);return None if n is None else {k.split('}')[-1]:v for k,v in n.attrib.items()}
  mar=pr.find('w:tblCellMar/w:left',NS)
  mappings.append({'table_index':idx,'caption':cap,'physical_pages':phys,'strict_three_rule_table':baseline['tables'][idx]['strict_data_table'],'jc':read('jc'),'tblW':read('tblW'),'tblInd':read('tblInd'),'left_cell_margin':None if mar is None else {k.split('}')[-1]:v for k,v in mar.attrib.items()},'grid_width_twips':sum(int(x.get(W+'w')) for x in t.findall('w:tblGrid/w:gridCol',NS))})
 ann=[]
 for i,p in enumerate(PdfReader(pp).pages,1):
  for ref in p.get('/Annots',[]):ann.append({'physical_page':i,'subtype':str(ref.get_object().get('/Subtype'))})
 obj={'task':'T144 independent final actual-PDF vector table rule boundary audit','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs':{'word':str(wp),'word_sha256':h(wp),'pdf':str(pp),'pdf_sha256':h(pp)},'physical_pages':100,'body_interval_pt':[left,right],'tolerance_pt':.05,'strict_table_count':98,'minimum_table_grid_width_pt':min(sum(map(int,t['grid_twips']))/20 for t in strict),'scope':'All 100 pages and all horizontal vector edges at least 300pt long. All 98 strict tables have full grid width at least416pt, so their continuous outer rules are included. This verifies actual rule endpoints, beyond coarse pixel inspection; same-page appearance is checked separately. No source or document changes.','wide_horizontal_rules_scanned':len(all_lines),'violation_count':len(bad),'affected_physical_pages':sorted({v['physical_page'] for v in bad}),'violations':bad,'all_lines':all_lines,'pages':pages,'tables':mappings,'annotation_count':len(ann),'annotation_subtypes':sorted({v['subtype'] for v in ann}),'only_Link_annotations':bool(ann) and all(v['subtype']=='/Link' for v in ann),'result':'PASS_WIDE_TABLE_RULE_COORDINATES' if not bad else 'BLOCKED_TABLE_RULE_OVERFLOW'}
 out=Q/a.output;assert out.parent==Q and not out.exists();out.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'path':str(out),'sha256':h(out),'result':obj['result'],'wide_rules':len(all_lines),'violation_count':len(bad),'annotations':len(ann),'subtypes':obj['annotation_subtypes']},ensure_ascii=False))
if __name__=='__main__':main()
