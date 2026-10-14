from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from copy import deepcopy
import json,re,hashlib

ROOT=Path('/Users/yusong/Downloads/new/full-system/docs/thesis-revision-T134-2026-10-09')
SOURCE=ROOT/'source-1005-修改.docx'
OUT=ROOT/'1005-导师批注修订版-2026-10-09.docx'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W='{'+NS['w']+'}';XML='{http://www.w3.org/XML/1998/namespace}'
with ZipFile(SOURCE) as z:
    parts={n:z.read(n) for n in z.namelist()}; infos=z.infolist()
d=etree.fromstring(parts['word/document.xml'])
ps=d.findall('.//w:p',NS)
originals=[''.join(p.xpath('.//w:t/text()',namespaces=NS)) for p in ps]
revision_counts={name:len(d.findall('.//w:'+name,NS)) for name in ['ins','del','rPrChange','pPrChange','tblPrChange','trPrChange','tcPrChange','tblGridChange','tblPrExChange','sectPrChange']}
for x in d.xpath('.//w:del|.//w:rPrChange|.//w:pPrChange|.//w:tblPrChange|.//w:trPrChange|.//w:tblGridChange|.//w:tblPrExChange|.//w:tcPrChange|.//w:sectPrChange',namespaces=NS):
    if etree.QName(x).localname=='del':
        parent=x.getparent();pos=parent.index(x)
        for marker in x.xpath('.//w:commentRangeStart|.//w:commentRangeEnd|.//w:commentReference',namespaces=NS):
            marker=deepcopy(marker)
            if etree.QName(marker).localname=='commentReference':
                r=etree.Element(W+'r');r.append(marker);marker=r
            parent.insert(pos,marker);pos+=1
    x.getparent().remove(x)
for x in d.xpath('.//w:ins',namespaces=NS):
    parent=x.getparent();pos=parent.index(x)
    for child in list(x):parent.insert(pos,child);pos+=1
    parent.remove(x)

changes=[]
def settext(p,text):
    # Retain bookmarks, comment ranges and references, and paragraph properties.
    pp=p.find('w:pPr',NS)
    rp=p.find('.//w:rPr',NS)
    rp=deepcopy(rp) if rp is not None else None
    markers=[deepcopy(x) for x in p.xpath('.//w:commentRangeStart|.//w:commentRangeEnd|.//w:commentReference|.//w:bookmarkStart|.//w:bookmarkEnd',namespaces=NS)]
    for x in list(p):
        if x is not pp:p.remove(x)
    starts=[x for x in markers if etree.QName(x).localname.endswith('Start')]
    ends=[x for x in markers if etree.QName(x).localname.endswith('End')]
    refs=[x for x in markers if etree.QName(x).localname=='commentReference']
    for x in starts:p.append(x)
    rr=etree.SubElement(p,W+'r')
    if rp is not None:
        for x in rp.xpath('.//w:highlight|.//w:rPrChange',namespaces=NS):x.getparent().remove(x)
        rr.append(rp)
    for j,seg in enumerate(text.split('\t')):
        if j:etree.SubElement(rr,W+'tab')
        t=etree.SubElement(rr,W+'t');t.text=seg;t.set(XML+'space','preserve')
    for x in ends:p.append(x)
    for x in refs:
        r=etree.SubElement(p,W+'r');r.append(x)

def replace(i,text,reason):
    settext(ps[i],text)
    changes.append({'p':i,'old':originals[i],'new':text,'reason':reason})

language=json.loads(Path('/tmp/thesis-product-manager-language.json').read_text())
for op in language['paragraph_replacements']:
    replace(op['p'],op['new'],'导师批注 '+','.join(op['comments']))
replace(187,'针对上述研究问题，本文的总体研究目标是：设计并实现一个面向科研实验记录的智能电子实验笔记系统，实现实验记录的统一管理与受控智能辅助，使实验知识可组织、可检索、可追溯。具体研究内容如下：','研究内容引导句改为具体研究内容如下，后续已按导师删除线保留四项')
ps[192].getparent().remove(ps[192])
changes.append({'removed_p':192,'old':originals[192],'reason':'落实导师2026-10-09T22:44:17Z整段删除线，研究内容保留前四项'})
replace(52,'Members edit and version notes, upload materials, and correct scanned records; reviewers approve records; project leaders manage membership and permissions; administrators maintain accounts and global access. Features include document archiving, graph and source browsing, project question answering and evaluation, fixed-task generation, plan-coverage checks, on-demand alerts, and audit queries.','同步中文用户与功能摘要')
replace(54,'Next.js and Rust/Axum provide interfaces and APIs; PostgreSQL/pgvector stores records and embeddings; DeepSeek supports generation. Approval triggers relation extraction and graph updates. Planned knowledge remains separate for comparison. Approved documents support project-scoped hybrid retrieval, and task templates organize evidence. Session tools require project authorization and high-risk calls require confirmation. Matching users, tools, idempotency keys, and parameters reuse write results. Sources and calls are logged.','同步中文实现路径摘要')
replace(55,'Archived tests passed eight browser scenarios and eight confirmation and idempotency tests. Corrected extraction on four synthetic notes achieved 100.00% precision, recall, and F1 against 52 internal reference relations, indicating fixed-set agreement. Ordinary and graph-enhanced prototype retrieval completed 4/20 and 14/20 questions; citation checks passed 17/20 and 15/20. Four current Rust configurations produced 144 answers. One-hop relations achieved 74.44% fact coverage versus 46.67% for document retrieval; question-level p=0.0938 exceeded 0.05, indicating no statistically significant difference. Semantic evaluations and role-based API checks assessed evidence support and workflow constraints.','同步结果适用边界与统计解释')

literature=json.loads(Path('/tmp/thesis-literature-replacements.json').read_text())
for op in literature['replacements']:
    chunks=op['new'].split('\n')
    replace(int(op['p']),chunks[0],'研究现状按作者、方法、问题及效果重写或文献元数据核正')
    last=ps[int(op['p'])]
    for chunk in chunks[1:]:
        new=deepcopy(last);new.attrib.clear()
        for x in new.xpath('.//w:commentRangeStart|.//w:commentRangeEnd|.//w:commentReference|.//w:bookmarkStart|.//w:bookmarkEnd',namespaces=NS):x.getparent().remove(x)
        settext(new,chunk);last.addnext(new);last=new
        changes.append({'after_p':op['p'],'new':chunk,'reason':'文献综述扩写分段'})
stats=json.loads(Path('/tmp/thesis-stats-replacements.json').read_text())
for op in stats['replacements']:
    chunks=op['new'].split('\n')
    replace(int(op['p']),chunks[0],'统计计算与来源解释')
    last=ps[int(op['p'])]
    for chunk in chunks[1:]:
        new=deepcopy(last)
        for k in list(new.attrib):del new.attrib[k]
        for x in new.xpath('.//w:commentRangeStart|.//w:commentRangeEnd|.//w:commentReference|.//w:bookmarkStart|.//w:bookmarkEnd',namespaces=NS):x.getparent().remove(x)
        settext(new,chunk);last.addnext(new);last=new
        changes.append({'after_p':op['p'],'new':chunk,'reason':'统计计算与来源补充段'})
for ref in stats['references']:
    p=deepcopy(ps[1760]);settext(p,ref['text'])
    for k in list(p.attrib):del p.attrib[k]
    ps[1760].addnext(p)
    # Preserve append order after the previous added entry.
    ps[1760]=p
    changes.append({'new':ref['text'],'reason':'新增统计方法参考文献'})

# Reliable tab-stop indentation after a fixed-width line-number area.
depths={599:0,600:0,601:0,602:0,603:0,604:0,605:1,606:1,607:0,608:0,609:1,610:2,611:1,612:0,613:0,614:0,615:0,616:0,617:1,618:1,619:1,620:0,621:0,622:0}
for i,depth in depths.items():
    line,body=originals[i].split(':',1)
    if i==599:body='if rebuild then'
    replace(i,str(int(line)+(2 if i>599 else 0))+':\t'+'\t'*depth+body.strip(),'for/if块缩进')
    pp=ps[i].find('w:pPr',NS)
    if pp is None:pp=etree.SubElement(ps[i],W+'pPr')
    for x in pp.findall('w:tabs',NS):pp.remove(x)
    tabs=etree.SubElement(pp,W+'tabs')
    for pos in [480,780,1080]:
        x=etree.SubElement(tabs,W+'tab');x.set(W+'val','left');x.set(W+'pos',str(pos))
last=ps[599]
for text in ['2:\t\tClearNoteGraph(n.id)','3:\tend if']:
    p=deepcopy(ps[599]);p.attrib.clear();settext(p,text);last.addnext(p);last=p
    changes.append({'after_p':599,'new':text,'reason':'展开首个if块并缩进，后续行号顺延'})

def rightnumber(p,text):
    settext(p,text)
    pp=p.find('w:pPr',NS)
    if pp is None:pp=etree.SubElement(p,W+'pPr')
    jc=pp.find('w:jc',NS)
    if jc is None:jc=etree.SubElement(pp,W+'jc')
    jc.set(W+'val','right')
    spacing=pp.find('w:spacing',NS)
    if spacing is not None:spacing.set(W+'lineRule','atLeast');spacing.set(W+'line','240')

for i,num in [(1272,1),(1277,2),(1282,3),(1287,4),(1292,5),(1302,7)]:
    rightnumber(ps[i],f'（6-{num}）');changes.append({'p':i,'old':originals[i],'new':f'（6-{num}）','reason':'公式编号右对齐/顺延'})
for i,num in [(1296,6),(1306,8),(1307,9),(1309,10)]:
    p=deepcopy(ps[1272]);p.attrib.clear()
    for x in p.xpath('.//w:commentRangeStart|.//w:commentRangeEnd|.//w:commentReference|.//w:bookmarkStart|.//w:bookmarkEnd',namespaces=NS):x.getparent().remove(x)
    rightnumber(p,f'（6-{num}）');ps[i].addnext(p)
    changes.append({'after_p':i,'new':f'（6-{num}）','reason':'补缺失公式编号'})
# Put short formulas and their right-aligned numbers on the same line.
# Leave McNemar and context-precision expressions with their numbers on separate lines.
formula_numbers={1:(1271,1272),2:(1276,1277),3:(1281,1282),4:(1286,1287),5:(1291,1292),6:(1296,None),8:(1306,None),9:(1307,None)}
for num,(fi,ni) in formula_numbers.items():
    fp=ps[fi];lp=ps[ni] if ni is not None else fp.getnext()
    assert ''.join(lp.xpath('.//w:t/text()',namespaces=NS))==f'（6-{num}）'
    for wrapper in fp.findall('m:oMathPara',NS):
        at=fp.index(wrapper)
        for math in list(wrapper):
            if etree.QName(math).localname=='oMath':fp.insert(at,math);at+=1
        fp.remove(wrapper)
    pp=fp.find('w:pPr',NS)
    for old in pp.findall('w:tabs',NS):pp.remove(old)
    tabs=etree.SubElement(pp,W+'tabs')
    for val,position in [('center',1600),('right',3730)]:
        t=etree.SubElement(tabs,W+'tab');t.set(W+'val',val);t.set(W+'pos',str(position))
    if num<=7:
        r=etree.Element(W+'r');etree.SubElement(r,W+'tab');fp.insert(1,r)
    r=etree.SubElement(fp,W+'r');etree.SubElement(r,W+'tab')
    for x in list(lp):
        if etree.QName(x).localname!='pPr':fp.append(x)
    lp.getparent().remove(lp)
    changes.append({'formula_p':fi,'removed_number_p':ni,'number':f'（6-{num}）','reason':'公式及靠右编号同一行以保持指标表单页，原OMML不变'})
# Compact paragraph leading in the metric table so all rows stay on one page.
metric_table=ps[1271]
while metric_table.tag!=W+'tbl':metric_table=metric_table.getparent()
for paragraph in metric_table.findall('.//w:p',NS):
    pp=paragraph.find('w:pPr',NS)
    if pp is None:pp=etree.SubElement(paragraph,W+'pPr')
    spacing=pp.find('w:spacing',NS)
    if spacing is None:spacing=etree.SubElement(pp,W+'spacing')
    spacing.set(W+'line','260');spacing.set(W+'lineRule','atLeast' if paragraph.findall('.//m:oMath',NS) else 'exact')
    spacing.set(W+'before','0');spacing.set(W+'after','0')
changes.append({'table_contains_p':1271,'reason':'指标表段前段后为0，文字固定行距13磅，含数学段最小行距13磅，长公式编号独立靠右；不改表格行列与数学内容'})
replace(1312,'为评估系统在知识抽取、问答检索与任务生成上的表现，表6-4汇总各实验使用的指标、含义、计算方式与用途，并在相应指标行内给出式（6-1）至式（6-10）。其中，证据覆盖率、McNemar检验和三项RAGAS指标分别对应式（6-6）、式（6-7）及式（6-8）至式（6-10）。','编号范围与引用同步')
replace(1315,originals[1315].replace('式（6-6）','式（6-7）'),'McNemar式号同步')
replace(1349,originals[1349]+'修复后TP=52、FP=0、FN=0，因此按式（6-1）至式（6-3）计算，三个指标均为100.00%。该结果是同一固定合成样本与内部参考集的核验结果，不能据此推断对其他实验记录的抽取质量。','解释100%算式及固定样本边界')

for x in d.xpath('.//w:highlight[@w:val="red"]',namespaces=NS):x.getparent().remove(x)
parts['word/document.xml']=etree.tostring(d,encoding='UTF-8',xml_declaration=True,standalone=True)
settings=etree.fromstring(parts['word/settings.xml'])
for x in settings.findall('w:trackRevisions',NS):settings.remove(x)
parts['word/settings.xml']=etree.tostring(settings,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(OUT,'w') as z:
    for info in infos:z.writestr(info,parts[info.filename])
(ROOT/'changes.json').write_text(json.dumps({'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'accepted_revisions':revision_counts,'changes':changes},ensure_ascii=False,indent=2))
print(OUT,'changes',len(changes),'sha256',hashlib.sha256(OUT.read_bytes()).hexdigest())
