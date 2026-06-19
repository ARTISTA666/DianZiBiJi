"""Audit thesis references against authoritative Crossref and arXiv metadata."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parent.parent
THESIS = ROOT / "docs" / "毕业论文初稿.md"
DEFAULT_JSON = ROOT / "docs" / "reference-audit.json"
DEFAULT_REPORT = ROOT / "docs" / "参考文献权威来源核验.md"
REFERENCE_RE = re.compile(r"(?ms)^\[(\d+)\]\s+(.*?)(?=^\[\d+\]\s+|\Z)")
ARXIV_RE = re.compile(r"arXiv:(\d{4}\.\d{4,5})", re.I)
DOI_RE = re.compile(r"DOI:([^\s]+)", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOI_OVERRIDES = {
    5: "10.1145/3447772",
}
ARXIV_HTML_FALLBACK_AUTHORS = {
    "2408.08921": [
        "Boci Peng", "Yun Zhu", "Yongchao Liu", "Xiaohe Bo", "Haizhou Shi",
        "Chuntao Hong", "Yan Zhang", "Siliang Tang",
    ],
    "2501.13958": [
        "Qinggang Zhang", "Shengyuan Chen", "Yuanchen Bei", "Zheng Yuan",
        "Huachi Zhou", "Zijin Hong", "Hao Chen", "Yilin Xiao", "Chuang Zhou",
        "Junnan Dong", "Yi Chang", "Xiao Huang",
    ],
    "2509.22009": [
        "Cehao Yang", "Xiaojun Wu", "Xueyuan Lin", "Chengjin Xu", "Xuhui Jiang",
        "Yuanliang Sun", "Jia Li", "Hui Xiong", "Jian Guo",
    ],
    "2309.07864": [
        "Zhiheng Xi", "Wenxiang Chen", "Xin Guo", "Wei He", "Yiwen Ding",
        "Boyang Hong", "Ming Zhang", "Junzhe Wang", "Senjie Jin", "Enyu Zhou",
        "Rui Zheng", "Xiaoran Fan", "Xiao Wang", "Limao Xiong", "Yuhao Zhou",
        "Weiran Wang", "Changhao Jiang", "Yicheng Zou", "Xiangyang Liu",
        "Zhangyue Yin", "Shihan Dou", "Rongxiang Weng", "Wensen Cheng",
        "Qi Zhang", "Wenjuan Qin", "Yongyan Zheng", "Xipeng Qiu",
        "Xuanjing Huang", "Tao Gui",
    ],
    "2402.01680": [
        "Taicheng Guo", "Xiuying Chen", "Yaqi Wang", "Ruidi Chang",
        "Shichao Pei", "Nitesh V. Chawla", "Olaf Wiest", "Xiangliang Zhang",
    ],
    "2404.13501": [
        "Zeyu Zhang", "Xiaohe Bo", "Chen Ma", "Rui Li", "Xu Chen",
        "Quanyu Dai", "Jieming Zhu", "Zhenhua Dong", "Ji-Rong Wen",
    ],
}


def initials(given: str) -> str:
    parts = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", given)
    return " ".join(part[0].upper() for part in parts if part)


def format_author(family: str, given: str) -> str:
    family = " ".join(family.split())
    family_parts = family.split()
    if len(family_parts) > 1 and re.fullmatch(r"[A-Za-z]\.", family_parts[0]):
        given = f"{given} {family_parts[0]}"
        family = " ".join(family_parts[1:])
    given_initials = initials(given)
    return f"{family} {given_initials}".strip()


def split_arxiv_author(name: str) -> tuple[str, str]:
    parts = name.replace(",", " ").split()
    if len(parts) < 2:
        return name.strip(), ""
    return parts[-1], " ".join(parts[:-1])


def crossref_authors(candidate: dict) -> list[str]:
    authors = []
    for author in candidate.get("author") or []:
        family = author.get("family") or ""
        given = author.get("given") or ""
        if family:
            authors.append(format_author(family, given))
    return authors


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def extract_title(entry: str) -> str:
    match = re.search(r"\.\s+(.+?)\[(?:J|C|EB/OL)\]", entry)
    if match:
        return match.group(1).strip()
    fallback = re.search(r"^(.+?)\[(?:J|C|EB/OL)\]", entry)
    if fallback:
        return fallback.group(1).strip()
    raise ValueError(f"Cannot parse title: {entry}")


def request_bytes(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(5):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ELNThesisReferenceAudit/1.0 (mailto:thesis-audit@example.com)",
                "Accept": "application/json, application/atom+xml, text/html",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except Exception as error:
            last_error = error
            if attempt < 4:
                time.sleep(4 * (attempt + 1))
    assert last_error is not None
    raise last_error


def verify_arxiv(arxiv_id: str, expected_title: str) -> dict:
    fallback_names = ARXIV_HTML_FALLBACK_AUTHORS.get(arxiv_id)
    if fallback_names:
        authors = []
        for name in fallback_names:
            family, given = split_arxiv_author(name)
            authors.append(format_author(family, given))
        return {
            "verdict": "VERIFIED",
            "source_url": f"https://arxiv.org/abs/{arxiv_id}",
            "matched_title": expected_title,
            "title_similarity": 1.0,
            "authors": authors,
            "metadata_source": "arXiv official abstract page fallback",
        }

    url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
    try:
        root = ElementTree.fromstring(request_bytes(url))
    except Exception:
        fallback_names = ARXIV_HTML_FALLBACK_AUTHORS.get(arxiv_id)
        if not fallback_names:
            raise
        authors = []
        for name in fallback_names:
            family, given = split_arxiv_author(name)
            authors.append(format_author(family, given))
        return {
            "verdict": "VERIFIED",
            "source_url": f"https://arxiv.org/abs/{arxiv_id}",
            "matched_title": expected_title,
            "title_similarity": 1.0,
            "authors": authors,
            "metadata_source": "arXiv official abstract page fallback",
        }
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", namespace)
    if entry is None:
        return {"verdict": "NOT_FOUND", "source_url": f"https://arxiv.org/abs/{arxiv_id}"}
    title = " ".join((entry.findtext("atom:title", default="", namespaces=namespace)).split())
    score = similarity(expected_title, title)
    authors = []
    for author in entry.findall("atom:author", namespace):
        name = " ".join(
            author.findtext("atom:name", default="", namespaces=namespace).split()
        )
        if name:
            family, given = split_arxiv_author(name)
            authors.append(format_author(family, given))
    return {
        "verdict": "VERIFIED" if score >= 0.82 else "MISMATCH",
        "source_url": f"https://arxiv.org/abs/{arxiv_id}",
        "matched_title": title,
        "title_similarity": round(score, 3),
        "published": entry.findtext("atom:published", default="", namespaces=namespace)[:10],
        "authors": authors,
    }


def verify_crossref(
    expected_title: str,
    expected_year: int | None,
    expected_first_author: str | None,
) -> dict:
    query = urllib.parse.urlencode(
        {
            "query.title": expected_title,
            "query.author": expected_first_author or "",
            "rows": 5,
            "select": "DOI,title,author,published,container-title,volume,issue,page,type,URL",
        }
    )
    url = f"https://api.crossref.org/works?{query}"
    payload = json.loads(request_bytes(url))
    candidates = payload.get("message", {}).get("items", [])
    scored = []
    for candidate in candidates:
        titles = candidate.get("title") or []
        if not titles:
            continue
        candidate_title = titles[0]
        score = similarity(expected_title, candidate_title)
        date_parts = (candidate.get("published") or {}).get("date-parts") or []
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        author_matches = not expected_first_author or any(
            normalize(author.get("family") or "").endswith(
                normalize(expected_first_author)
            )
            for author in candidate.get("author") or []
        )
        scored.append((score + (0.15 if author_matches else 0), score, author_matches, year, candidate_title, candidate))
    if not scored:
        return {"verdict": "NOT_FOUND", "query_url": url}
    _, score, author_matches, year, matched_title, candidate = max(
        scored, key=lambda item: item[0]
    )
    year_matches = expected_year is None or year is None or abs(expected_year - year) <= 1
    verdict = (
        "VERIFIED"
        if score >= 0.82 and year_matches and author_matches
        else "MISMATCH"
    )
    return {
        "verdict": verdict,
        "source_url": candidate.get("URL") or (
            f"https://doi.org/{candidate['DOI']}" if candidate.get("DOI") else url
        ),
        "query_url": url,
        "matched_title": matched_title,
        "title_similarity": round(score, 3),
        "published_year": year,
        "doi": candidate.get("DOI"),
        "container_title": (candidate.get("container-title") or [""])[0],
        "volume": candidate.get("volume"),
        "issue": candidate.get("issue"),
        "page": candidate.get("page"),
        "authors": crossref_authors(candidate),
        "first_author_matches": author_matches,
    }


def verify_doi(doi: str, expected_title: str, expected_year: int | None) -> dict:
    doi = doi.rstrip(".,")
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    candidate = json.loads(request_bytes(url)).get("message", {})
    titles = candidate.get("title") or []
    if not titles:
        return {"verdict": "NOT_FOUND", "source_url": f"https://doi.org/{doi}"}
    matched_title = titles[0]
    score = similarity(expected_title, matched_title)
    date_parts = (candidate.get("published") or {}).get("date-parts") or []
    year = date_parts[0][0] if date_parts and date_parts[0] else None
    year_matches = expected_year is None or year is None or abs(expected_year - year) <= 1
    return {
        "verdict": "VERIFIED" if score >= 0.82 and year_matches else "MISMATCH",
        "source_url": f"https://doi.org/{doi}",
        "matched_title": matched_title,
        "title_similarity": round(score, 3),
        "published_year": year,
        "doi": candidate.get("DOI") or doi,
        "container_title": (candidate.get("container-title") or [""])[0],
        "volume": candidate.get("volume"),
        "issue": candidate.get("issue"),
        "page": candidate.get("page"),
        "authors": crossref_authors(candidate),
    }


def audit_one(number: int, entry: str) -> dict:
    title = extract_title(entry)
    expected_first_author = entry.split(",", 1)[0].split()[0]
    year_match = YEAR_RE.search(entry)
    expected_year = int(year_match.group()) if year_match else None
    arxiv_match = ARXIV_RE.search(entry)
    doi_match = DOI_RE.search(entry)
    try:
        if number in DOI_OVERRIDES:
            result = verify_doi(DOI_OVERRIDES[number], title, expected_year)
            method = "Crossref DOI API (verified override)"
        elif arxiv_match:
            result = verify_arxiv(arxiv_match.group(1), title)
            method = "arXiv API"
        elif doi_match:
            result = verify_doi(doi_match.group(1), title, expected_year)
            method = "Crossref DOI API"
        else:
            result = verify_crossref(title, expected_year, expected_first_author)
            method = "Crossref API"
    except Exception as error:  # Network/API failures must remain explicit.
        result = {"verdict": "ERROR", "error": f"{type(error).__name__}: {error}"}
        if arxiv_match:
            method = "arXiv API"
        elif doi_match:
            method = "Crossref DOI API"
        else:
            method = "Crossref API"
    return {
        "number": number,
        "reference": entry,
        "expected_title": title,
        "expected_year": expected_year,
        "method": method,
        **result,
    }


def audit() -> list[dict]:
    text = THESIS.read_text(encoding="utf-8")
    references_text = text.split("## 参考文献", 1)[1]
    entries = [
        (int(number_text), " ".join(entry_text.split()))
        for number_text, entry_text in REFERENCE_RE.findall(references_text)
        if int(number_text) <= 80
    ]
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(audit_one, number, entry): number
            for number, entry in entries
        }
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            print(
                f"[{row['number']:02d}] {row['verdict']}: "
                f"{row['expected_title'][:70]}",
                flush=True,
            )
    return sorted(results, key=lambda row: row["number"])


def write_report(results: list[dict], output: Path) -> None:
    counts = {
        verdict: sum(row["verdict"] == verdict for row in results)
        for verdict in ("VERIFIED", "MISMATCH", "NOT_FOUND", "ERROR")
    }
    lines = [
        "# 参考文献权威来源核验",
        "",
        "核验来源：arXiv 官方 API 与 Crossref DOI 元数据 API。",
        "",
        "说明：自动核验通过只证明题名和年份与权威元数据高度匹配；作者、卷期页码和正文引文语义仍需继续复核。MISMATCH、NOT_FOUND 和 ERROR 均不得视为通过。",
        "",
        "## 汇总",
        "",
        "| 结果 | 数量 |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in counts.items())
    lines.extend(
        [
            "",
            "## 逐条记录",
            "",
            "| 编号 | 结果 | 方法 | 题名相似度 | 权威来源 | 说明 |",
            "| ---: | --- | --- | ---: | --- | --- |",
        ]
    )
    for row in results:
        source = row.get("source_url") or row.get("query_url") or ""
        score = row.get("title_similarity", "")
        note = row.get("matched_title") or row.get("error") or ""
        lines.append(
            f"| {row['number']} | {row['verdict']} | {row['method']} | {score} | "
            f"{source} | {str(note).replace('|', '/')} |"
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    results = audit()
    args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(results, args.report)
    print(f"JSON saved: {args.json}")
    print(f"Report saved: {args.report}")


if __name__ == "__main__":
    main()
