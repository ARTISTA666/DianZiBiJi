from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from pypdf import PdfReader
import re,json,hashlib,sys
root=Path('/Users/yusong/Downloads/new/full-system/docs/thesis-revision-T134-2026-10-09')
f=root/'1005-导师批注修订版-2026-10-09.docx'
pdf=Path(sys.argv[1])
N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'};W='{'+N['w']+'}'
with ZipFile(f) as z:parts={n:z.read(n) for n in z.namelist()};infos=z.infolist()
d=etree.fromstring(parts['word/document.xml']);ps=d.findall('.//w:p',N)
normalize=lambda t:re.sub(r'\s+','',t)
page_lines=[[normalize(line) for line in p.extract_text().splitlines()] for p in PdfReader(pdf).pages]
pages=[''.join(lines) for lines in page_lines]
prior_path=root/'toc-changes.json'
prior={r['title']:r['old_cache'] for r in json.loads(prior_path.read_text())['changes']} if prior_path.exists() else {}
heads={}
for b in d.findall('.//w:bookmarkStart',N):
 name=b.get(W+'name');p=b
 while p.tag!=W+'p':p=p.getparent()
 heads[name]=normalize(''.join(p.xpath('.//w:t/text()',namespaces=N)))
body_first=next(i+1 for i,t in enumerate(pages) if '第一章绪论' in t and '1.1研究背景及意义' in t and '科研实验记录是科研活动的原始凭证' in t)
rows=[];missing=[]
for p in ps:
 inst=p.xpath('.//w:instrText[contains(text(),"PAGEREF")]',namespaces=N)
 if not inst:continue
 assert len(inst)==1
 bookmark=re.search(r'PAGEREF\s+(\S+)',inst[0].text)[1]
 title=heads[bookmark]
 if title in ['摘要','Abstract']:
  num='I' if title=='摘要' else 'II'
  physical=4 if title=='摘要' else 5
 else:
  found=[i+1 for i,lines in enumerate(page_lines) if i+1>=body_first and title in lines]
  assert len(found)==1,(bookmark,title,found)
  if not found:missing.append((bookmark,title));continue
  physical=found[0];num=str(physical-body_first+1)
 result=[];separated=False
 run=inst[0].getparent().getnext()
 while run is not None:
  chars=run.findall('.//w:fldChar',N)
  if any(c.get(W+'fldCharType')=='separate' for c in chars):separated=True
  elif any(c.get(W+'fldCharType')=='end' for c in chars):break
  elif separated:result.extend(run.findall('.//w:t',N))
  run=run.getnext()
 assert len(result)==1,(title,len(result))
 rows.append({'paragraph_id':p.get('{http://schemas.microsoft.com/office/word/2010/wordml}paraId'),'title':title,'physical_page':physical,'old_cache':prior.get(title,result[0].text),'new_cache':num})
 result[0].text=num
print('body_first',body_first,'entries',len(rows),'missing',missing)
assert not missing
parts['word/document.xml']=etree.tostring(d,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(f,'w') as z:
 for info in infos:z.writestr(info,parts[info.filename])
(root/'toc-changes.json').write_text(json.dumps({'pdf':str(pdf),'body_first_page':body_first,'changes':rows,'output_sha256':hashlib.sha256(f.read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
