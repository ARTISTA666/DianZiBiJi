"""Check thesis citation coverage and minimum Chinese character count."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
THESIS = ROOT / "docs" / "毕业论文初稿.md"
REFERENCE_HEADING = "## 参考文献"
REFERENCE_RE = re.compile(r"(?m)^\[(\d+)\]\s+")
CITATION_RE = re.compile(r"\[((?:\d+(?:-\d+)?)(?:,\d+(?:-\d+)?)*)\]")


def main() -> None:
    text = THESIS.read_text(encoding="utf-8")
    body, references = text.split(REFERENCE_HEADING, 1)
    reference_numbers = {int(value) for value in REFERENCE_RE.findall(references)}

    cited_numbers: set[int] = set()
    for match in CITATION_RE.finditer(body):
        for item in match.group(1).split(","):
            bounds = item.split("-", 1)
            first = int(bounds[0])
            last = int(bounds[1]) if len(bounds) == 2 else first
            cited_numbers.update(range(first, last + 1))

    missing_entries = sorted(cited_numbers - reference_numbers)
    uncited_entries = sorted(reference_numbers - cited_numbers)
    expected = set(range(1, len(reference_numbers) + 1))
    numbering_gaps = sorted(expected - reference_numbers)

    clean = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", clean))

    print(f"REFERENCE_COUNT: {len(reference_numbers)}")
    print(f"CITED_REFERENCE_COUNT: {len(cited_numbers)}")
    print(f"MISSING_REFERENCE_ENTRIES: {missing_entries}")
    print(f"UNCITED_REFERENCE_ENTRIES: {uncited_entries}")
    print(f"NUMBERING_GAPS: {numbering_gaps}")
    print(f"CHINESE_CHARS: {chinese_count}")
    print(f"CHINESE_CHAR_SHORTFALL: {max(0, 30000 - chinese_count)}")

    if missing_entries or uncited_entries or numbering_gaps or chinese_count < 30000:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
