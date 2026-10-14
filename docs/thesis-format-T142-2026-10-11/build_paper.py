from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from difflib import SequenceMatcher
from bisect import bisect_right
import copy,json,re,hashlib
R=Path(__file__).resolve().parent
SRC=Path('/Users/yusong/Desktop/1005-深审整改版-2026-10-11.docx')
OUT=R/'1005-精简与角标校正版-2026-10-11.docx'
N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W='{'+N['w']+'}';ID='{http://schemas.microsoft.com/office/word/2010/wordml}paraId';SPACE='{http://www.w3.org/XML/1998/namespace}space'
rx=re.compile(r'\[\d+(?:\s*[-–—,，、]\s*\d+)*\]')
num=lambda t:re.findall(r'\d+(?:\.\d+)?',t)
txt=lambda p:''.join(p.xpath('.//w:t/text()',namespaces=N))
with ZipFile(SRC) as z:parts={n:z.read(n) for n in z.namelist()};infos=z.infolist()
d=E.fromstring(parts['word/document.xml']);ps=d.xpath('//w:p',namespaces=N)
oldparas=[txt(p) for p in ps]
assert hashlib.sha256(SRC.read_bytes()).hexdigest()=='501184b1d12d5611709606f24feed69437e6d862ff12d27a292a2f91fe1df948'
proposals=json.loads((R/'accepted-shortening.json').read_text());changes=[]
for row in proposals:
 p=ps[row['index']];old=txt(p);new=row['after'];assert old==row['before'] and p.get(ID)==row['id'];assert not p.xpath('ancestor::w:tbl|.//m:oMath',namespaces=N)
 assert num(old)==num(new),(row['index'],'numeric change');assert rx.findall(old)==rx.findall(new),(row['index'],'citation change')
 assert len(new)<len(old),(row['index'],'not shortening')
 nodes=p.xpath('.//w:t',namespaces=N); starts=[];ends=[];pos=0
 for n in nodes:starts.append(pos);pos+=len(n.text or '');ends.append(pos)
 strings=['']*len(nodes)
 for op,a,b,c,e in SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
  if op=='equal':
   for j,(start,end) in enumerate(zip(starts,ends)):
    lo,hi=max(a,start),min(b,end)
    if lo<hi:strings[j]+=old[lo:hi]
  elif op in ['insert','replace']:strings[min(bisect_right(ends,a),len(nodes)-1)]+=new[c:e]
 for n,value in zip(nodes,strings):
  n.text=value
  if value[:1].isspace() or value[-1:].isspace():n.set(SPACE,'preserve')
 assert txt(p)==new
 changes.append(row)
ref_start=next(i for i,p in enumerate(ps) if txt(p)=='参考文献')
ref_end=next(i for i,p in enumerate(ps) if i>ref_start and txt(p).startswith('附录'))
citations=[]
for i,p in enumerate(ps):
 if ref_start<=i<ref_end:continue
 text=txt(p);matches=list(rx.finditer(text))
 if not matches:continue
 intervals=[]
 for match in matches:
  numbers=[int(x) for x in re.findall(r'\d+',match.group())]
  assert all(1<=x<=85 for x in numbers),(i,match.group(),'not a reference')
  intervals.append((match.start(),match.end()))
  citations.append({'index':i,'id':p.get(ID),'text':match.group(),'start':match.start(),'end':match.end()})
 runs=p.xpath('.//w:r[not(ancestor::m:oMath)]',namespaces=N);pos=0
 for r in runs:
  value=''.join(r.xpath('./w:t/text()',namespaces=N));end=pos+len(value)
  cuts={0,len(value)};inside=[]
  for a,b in intervals:
   if pos<b and end>a:
    lo,hi=max(a,pos)-pos,min(b,end)-pos;cuts.update([lo,hi]);inside.append((lo,hi))
  if inside:
   assert all(c.tag in [W+'rPr',W+'t'] for c in r),(i,'mixed run cannot be safely split')
   parent=r.getparent();at=parent.index(r)
   cut=sorted(cuts)
   for lo,hi in zip(cut,cut[1:]):
    if lo==hi:continue
    newr=copy.deepcopy(r)
    for c in list(newr):
     if c.tag!=W+'rPr':newr.remove(c)
    t=E.SubElement(newr,W+'t');t.text=value[lo:hi]
    if t.text[:1].isspace() or t.text[-1:].isspace():t.set(SPACE,'preserve')
    if any(a<=lo and hi<=b for a,b in inside):
     pr=newr.find('w:rPr',N)
     if pr is None:pr=E.Element(W+'rPr');newr.insert(0,pr)
     for name in ['position','vertAlign','sz','szCs']:
      for c in pr.findall('w:'+name,N):pr.remove(c)
     font=pr.find('w:rFonts',N)
     if font is None:font=E.SubElement(pr,W+'rFonts')
     for attr in ['ascii','hAnsi','eastAsia','cs']:font.set(W+attr,'Times New Roman')
     E.SubElement(pr,W+'sz').set(W+'val','24');E.SubElement(pr,W+'szCs').set(W+'val','24');E.SubElement(pr,W+'vertAlign').set(W+'val','superscript')
    parent.insert(at,newr);at+=1
   parent.remove(r)
  pos=end
 assert txt(p)==text,(i,'superscript changed text')
line_changes=[]
for index in [193,194,195,229,230,234,239,354,1012,1020,1039,1047]:
 p=ps[index];sp=p.find('w:pPr/w:spacing',N)
 assert sp is not None and sp.get(W+'line')=='380' and sp.get(W+'lineRule')=='exact', index
 before=dict(sp.attrib);sp.set(W+'line','400')
 line_changes.append({'index':index,'id':p.get(ID),'before':before,'after':dict(sp.attrib)})
table_indent_changes=[]
for index in [11,37,38,39,*range(57,102),107]:
 t=d.findall('.//w:tbl',N)[index];pr=t.find('w:tblPr',N)
 ind=pr.find('w:tblInd',N);mar=pr.find('w:tblCellMar/w:left',N)
 assert ind is not None and ind.get(W+'w')=='0' and pr.find('w:jc',N) is None,index
 value=mar.get(W+'w');assert value in ['60','70'],(index,value)
 before=dict(ind.attrib);ind.set(W+'w',value)
 q=t.getprevious();caption=txt(q)
 table_indent_changes.append({'table_index':index,'caption':caption,'before':before,'after':dict(ind.attrib),'reason':'仅以单元格左边距抵消左对齐表格横线越出版心，不改宽度网格内容字号边框'})
parts['word/document.xml']=E.tostring(d,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(OUT,'w') as z:
 for info in infos:z.writestr(info,parts[info.filename])
report={'task':'T142','source':str(SRC),'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'output':str(OUT),'output_sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'revisions':changes,'saved_chars':sum(len(c['before'])-len(c['after']) for c in changes),'citation_markers':citations,'superscript_marker_count':len(citations),'bibliography_paragraph_bounds':[ref_start,ref_end],'line_spacing_changes':line_changes,'table_indent_changes':table_indent_changes,'body_font_and_line_spacing':'12 plain paragraphs exact19pt to exact20pt; all other paragraph properties unchanged','global_font_shrink':False}
(R/'changes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['output','output_sha256','saved_chars','superscript_marker_count']},ensure_ascii=False))
