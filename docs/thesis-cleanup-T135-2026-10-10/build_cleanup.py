from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from difflib import SequenceMatcher
from bisect import bisect_right
import json, hashlib, copy

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'source-T134.docx'
OUT=ROOT/'1005-防御性说明清理版-2026-10-10.docx'
N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
W='{'+N['w']+'}'
with ZipFile(SOURCE) as z:
    parts={x:z.read(x) for x in z.namelist()};infos=z.infolist()
doc=etree.fromstring(parts['word/document.xml'])
ps=doc.xpath('//w:body//w:p',namespaces=N)
text=lambda p:''.join(p.xpath('.//w:t/text()',namespaces=N))
def replace_text(p,new):
    nodes=p.xpath('.//w:t',namespaces=N);old=text(p)
    lengths=[len(n.text or '') for n in nodes];starts=[];ends=[];pos=0
    for length in lengths:starts.append(pos);pos+=length;ends.append(pos)
    strings=['']*len(nodes)
    def owner(offset):return min(bisect_right(ends,offset),len(nodes)-1)
    for op,a,b,c,d in SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
        if op=='equal':
            for j,(start,end) in enumerate(zip(starts,ends)):
                lo,hi=max(a,start),min(b,end)
                if lo<hi:strings[j]+=old[lo:hi]
        elif op in ['insert','replace']:
            strings[owner(a)]+=new[c:d]
    for n,s in zip(nodes,strings):
        n.text=s
        if s[:1].isspace() or s[-1:].isspace():n.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    assert text(p)==new

rows=json.loads((ROOT/'approved-replacements.json').read_text())
changed=[];deleted=set()
for row in rows:
    p=ps[row['p']];assert text(p)==row['old'],row['p']
    action=row.get('action','replace')
    if action=='delete_row':
        tr=p
        while tr.tag!=W+'tr':tr=tr.getparent()
        for q in tr.xpath('.//w:p',namespaces=N):deleted.add(ps.index(q))
        assert not tr.xpath('.//w:bookmarkStart|.//w:commentRangeStart|.//w:drawing|.//*[local-name()="oMath"]',namespaces=N)
        tr.getparent().remove(tr)
    elif action=='delete':
        assert not p.xpath('.//w:bookmarkStart|.//w:commentRangeStart|.//w:drawing|.//*[local-name()="oMath"]',namespaces=N),row['p']
        deleted.add(row['p']);p.getparent().remove(p)
    else:replace_text(p,row['new'])
    changed.append(row)

figs=json.loads((ROOT/'figure-changes.json').read_text())['figures']
media_changes=[]
rel=etree.fromstring(parts['word/_rels/document.xml.rels'])
rmap={e.get('Id'):'word/'+e.get('Target') for e in rel}
for f in figs:
    media=f['media'];parts[media]=(ROOT/'figures'/f['png']).read_bytes()
    for p in ps:
        for b in p.xpath('.//a:blip',namespaces=N):
            if rmap.get(b.get('{'+N['r']+'}embed'))!=media:continue
            drawing=b
            while drawing.tag!=W+'drawing':drawing=drawing.getparent()
            extent=drawing.find('.//wp:extent',N);oldcy=int(extent.get('cy'))
            newcy=round(int(extent.get('cx'))*f['height']/f['width'])
            extent.set('cy',str(newcy))
            for e in drawing.findall('.//a:xfrm/a:ext',N):e.set('cy',str(newcy))
            media_changes.append({'p':ps.index(p),'media':media,'old_cy':oldcy,'new_cy':newcy})
parts['word/document.xml']=etree.tostring(doc,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(OUT,'w') as z:
    for info in infos:z.writestr(info,parts[info.filename])
changes={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'paragraph_changes':changed,'deleted_source_paragraphs':sorted(deleted),'image_extent_changes':media_changes}
(ROOT/'changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2))
print(json.dumps({'output':str(OUT),'text_changes':len(changed),'deleted_paragraphs':len(deleted),'rebuilt_figures':len(media_changes)},ensure_ascii=False))
