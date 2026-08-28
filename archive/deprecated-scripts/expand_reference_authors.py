"""Expand abbreviated English reference author lists from audited official metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
THESIS = ROOT / "docs" / "毕业论文初稿.md"
AUDIT_JSON = ROOT / "docs" / "reference-audit.json"
REPORT = ROOT / "docs" / "参考文献作者展开核验.md"
REFERENCE_RE = re.compile(r"(?ms)^\[(\d+)\]\s+(.*?)(?=^\[\d+\]\s+|\Z)")


def replace_authors(entry: str, authors: list[str]) -> str:
    title_marker = re.search(r"\.\s+(.+?)\[(?:J|C|EB/OL|M|S|Z)\]", entry)
    if not title_marker:
        raise ValueError(f"Cannot locate title boundary: {entry}")
    remainder = entry[title_marker.start() :]
    return ", ".join(authors) + remainder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    text = THESIS.read_text(encoding="utf-8")
    prefix, references = text.split("## 参考文献", 1)
    audit = {
        row["number"]: row
        for row in json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    }

    replacements: dict[int, str] = {}
    rows = []
    for number_text, entry_text in REFERENCE_RE.findall(references):
        number = int(number_text)
        entry = " ".join(entry_text.split())
        if "et al." not in entry:
            continue
        row = audit.get(number)
        authors = (row or {}).get("authors") or []
        verdict = (row or {}).get("verdict")
        if verdict != "VERIFIED" or not authors:
            rows.append((number, "未展开", len(authors), (row or {}).get("source_url", "")))
            continue
        replacements[number] = replace_authors(entry, authors)
        rows.append((number, "已展开", len(authors), row.get("source_url", "")))

    if not args.check:
        def substitute(match: re.Match[str]) -> str:
            number = int(match.group(1))
            replacement = replacements.get(number)
            if replacement is None:
                return match.group(0)
            return f"[{number}] {replacement}\n\n"

        updated_references = REFERENCE_RE.sub(substitute, references)
        THESIS.write_text(prefix + "## 参考文献" + updated_references, encoding="utf-8")

    report_lines = [
        "# 参考文献作者展开核验",
        "",
        "作者来源：arXiv 官方 API 或 Crossref DOI 元数据 API。",
        "",
        "| 编号 | 状态 | 作者数 | 权威来源 |",
        "| ---: | --- | ---: | --- |",
    ]
    report_lines.extend(
        f"| {number} | {status} | {count} | {source} |"
        for number, status, count, source in rows
    )
    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    unresolved = [number for number, status, _, _ in rows if status != "已展开"]
    remaining = len(re.findall(r"\bet al\.", THESIS.read_text(encoding="utf-8")))
    print(f"Expanded: {len(replacements)}")
    print(f"Unresolved: {unresolved}")
    print(f"Remaining et al.: {remaining}")
    if unresolved or (not args.check and remaining):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
