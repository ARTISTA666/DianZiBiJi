"""Read-only cell-text pagination screening; does not substitute for original-size visual QA."""
import argparse, datetime, hashlib, io, json, re, unicodedata, zipfile
from pathlib import Path
from lxml import etree as E
from pypdf import PdfReader

QA = Path(__file__).resolve().parent
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W, M = ('{'+NS[k]+'}' for k in ['w','m'])
sha = lambda b: hashlib.sha256(b).hexdigest()
norm = lambda t: re.sub(r'[\s\u200b\ufeff]+', '', unicodedata.normalize('NFKC',t))

def main():
    ap=argparse.ArgumentParser()
    for name in ['word','word-sha256','pdf','pdf-sha256','output']:ap.add_argument('--'+name,required=True)
    a=ap.parse_args();wp,pp=Path(a.word).resolve(),Path(a.pdf).resolve();wb,pb=wp.read_bytes(),pp.read_bytes()
    assert sha(wb)==a.word_sha256 and sha(pb)==a.pdf_sha256
    d=E.fromstring(zipfile.ZipFile(io.BytesIO(wb)).read('word/document.xml'))
    pdf=PdfReader(io.BytesIO(pb));pages=[norm(p.extract_text()) for p in pdf.pages]
    lines=[[norm(x) for x in p.extract_text().splitlines()] for p in pdf.pages]
    baseline=json.loads((QA/'source-protection-inventory-35e9.json').read_text());tables=d.xpath('.//w:tbl',namespaces=NS)
    assert len(tables)==len(baseline['tables'])
    results=[]
    for i,t in enumerate(tables):
        if not baseline['tables'][i]['strict_data_table']:continue
        prev=t.getprevious();caption=''
        while prev is not None:
            if prev.tag==W+'p':
                txt=''.join(prev.xpath('.//w:t/text()',namespaces=NS))
                if re.match(r'^表\s*[A-D\d]+-\d+(?:[a-z]|\([a-z]\))?[\s　]',txt):caption=txt;break
            prev=prev.getprevious()
        cp=norm(caption)
        found=[j+1 for j,l in enumerate(lines) if cp in l or any(cp==''.join(l[k:k+2]) for k in range(len(l)-1))]
        chunks=[]
        for para in t.xpath('.//w:p',namespaces=NS):
            chunk=''
            for child in para:
                if child.tag in [M+'oMath',M+'oMathPara']:
                    if norm(chunk):chunks.append(norm(chunk));chunk=''
                else:chunk+=''.join(child.xpath('.//w:t/text()',namespaces=NS))
            if norm(chunk):chunks.append(norm(chunk))
        missing=[] if len(found)!=1 else [s for s in chunks if s not in pages[found[0]-1]]
        results.append({'table_index':i,'caption':caption,'caption_physical_pages':found,
                        'cell_text_fragment_count':len(chunks),'missing_cell_text_fragments':missing,
                        'all_plain_cell_text_on_caption_page':len(found)==1 and not missing,
                        'status':'PASS_TEXT_SCREEN' if len(found)==1 and not missing else 'EXTRACTION_AMBIGUITY_REQUIRES_VISUAL'})
    assert len(results)==98
    obj={'task':'T144 independent native-PDF same-page cell-text screening',
         'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'inputs':{'word':str(wp),'word_sha256':sha(wb),'pdf':str(pp),'pdf_sha256':sha(pb)},
         'table_count':len(results),'text_screen_pass_count':sum(v['all_plain_cell_text_on_caption_page'] for v in results),
         'requiring_visual':[v for v in results if not v['all_plain_cell_text_on_caption_page']],
         'tables':results,
         'scope':'Matching captions uses complete normalized lines (or one wrapped line), not prefix matches. Inline OMML separates plain-text fragments and is protected independently in Word. Missing PDF text, including subscript extraction, is not a pagination failure without visual confirmation. Positive cell-text screening supports same-page placement; original-size review verifies appearance, formula glyphs and complete rules.'}
    out=QA/a.output;assert out.parent==QA and not out.exists();out.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'path':str(out),'sha256':sha(out.read_bytes()),'tables':len(results),'screen_pass':obj['text_screen_pass_count'],'visual_pending':len(obj['requiring_visual'])}))

if __name__=='__main__':main()
