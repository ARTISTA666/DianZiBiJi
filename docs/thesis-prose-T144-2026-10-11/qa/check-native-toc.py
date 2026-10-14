"""Read-only verification of all Word PAGEREF caches against the delivered native PDF."""
import argparse, datetime, hashlib, io, json, re, zipfile
from pathlib import Path
from lxml import etree as E
from pypdf import PdfReader

qa = Path(__file__).resolve().parent
task = qa.parent
parser = argparse.ArgumentParser()
parser.add_argument('--word', required=True)
parser.add_argument('--word-sha256', required=True)
parser.add_argument('--pdf', required=True)
parser.add_argument('--pdf-sha256', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
word, pdf = Path(args.word).resolve(), Path(args.pdf).resolve()
sha = lambda b: hashlib.sha256(b).hexdigest()
wb, pb = word.read_bytes(), pdf.read_bytes()
assert sha(wb) == args.word_sha256
assert sha(pb) == args.pdf_sha256
n = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
w = '{' + n['w'] + '}'
d = E.fromstring(zipfile.ZipFile(io.BytesIO(wb)).read('word/document.xml'))
norm = lambda s: re.sub(r'\s+', '', s)
text = lambda p: norm(''.join(p.xpath('.//w:t/text()', namespaces=n)))
lines = [[norm(s) for s in p.extract_text().splitlines()] for p in PdfReader(io.BytesIO(pb)).pages]
assert len(lines) <= 100
first = next(i + 1 for i, v in enumerate(lines) if '第一章绪论' in v)
heads = {}
for b in d.xpath('.//w:bookmarkStart', namespaces=n):
    p = b
    while p.tag != w + 'p': p = p.getparent()
    heads[b.get(w + 'name')] = text(p)
entries = []
for p in d.xpath('.//w:p', namespaces=n):
    ins = p.xpath('.//w:instrText[contains(text(),"PAGEREF")]', namespaces=n)
    if not ins: continue
    assert len(ins) == 1
    bookmark = re.search(r'PAGEREF\s+(\S+)', ins[0].text)[1]
    title = heads[bookmark]
    separated = False
    run = ins[0].getparent().getnext()
    cached = []
    while run is not None:
        fields = run.findall('.//w:fldChar', n)
        if any(f.get(w + 'fldCharType') == 'separate' for f in fields): separated = True
        elif any(f.get(w + 'fldCharType') == 'end' for f in fields): break
        elif separated: cached.extend(run.findall('.//w:t', n))
        run = run.getnext()
    assert len(cached) == 1
    cache = cached[0].text
    found = [i + 1 for i, v in enumerate(lines) if i + 1 >= first and title in v]
    if title in ['摘要', 'Abstract']:
        found = [i + 1 for i, v in enumerate(lines[:first-1]) if title in v]
        assert len(found) == 1
        expected = 'I' if title == '摘要' else 'II'
        heading_visible = title in lines[found[0] - 1]
    else:
        expected = str(found[0] - first + 1) if len(found) == 1 else None
        heading_visible = len(found) == 1
    toc_lines = [{'physical_page': i + 1, 'line': s} for i, v in enumerate(lines[:first - 1]) for s in v if s.startswith(title + '...')]
    visible = len(toc_lines) == 1 and toc_lines[0]['line'].endswith('...' + cache)
    entries.append({'bookmark': bookmark, 'title': title, 'word_cached_printed_page': cache,
                    'actual_heading_physical_pages': found, 'expected_printed_page': expected,
                    'native_PDF_TOC_lines': toc_lines, 'actual_heading_visible': heading_visible,
                    'word_cache_equal_actual_heading': cache == expected,
                    'native_PDF_TOC_equal_Word_cache': visible,
                    'pass': heading_visible and cache == expected and visible})
checks = {'physical_page_cap_100': len(lines) <= 100, '100_TOC_entries': len(entries) == 100,
          'all_heading_locations_and_Word_caches_match': all(e['word_cache_equal_actual_heading'] and e['actual_heading_visible'] for e in entries),
          'all_native_PDF_TOC_lines_match_Word_caches': all(e['native_PDF_TOC_equal_Word_cache'] for e in entries)}
result = {'task': 'T144 independent delivered native PDF <=100-page / 100-entry TOC verification',
          'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'input': {'word': str(word), 'word_sha256': sha(wb), 'pdf': str(pdf), 'pdf_sha256': sha(pb)},
          'body_first_physical_page': first, 'pdf_page_count': len(lines), 'entry_count': len(entries),
          'checks': checks, 'entries': entries, 'findings': [e for e in entries if not e['pass']],
          'result': 'PASS' if all(checks.values()) else 'FAIL',
          'scope': 'Independent read of actual Word field caches and final PDF text. Visual TOC/page appearance is verified separately.'}
out = qa / args.output
assert out.parent == qa
assert not out.exists()
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'result': result['result'], 'checks': checks, 'findings': result['findings'], 'output_sha256': sha(out.read_bytes())}, ensure_ascii=False))
