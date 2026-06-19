"""Remove uncited thesis references and renumber citations deterministically."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
THESIS = ROOT / "docs" / "毕业论文初稿.md"
REFERENCE_HEADING = "## 参考文献"
CITATION_RE = re.compile(r"\[([0-9,\-–—\s]+)\]")
REFERENCE_RE = re.compile(r"(?ms)^\[(\d+)\]\s+(.*?)(?=^\[\d+\]\s+|\Z)")


def expand_numbers(value: str) -> list[int]:
    numbers: list[int] = []
    for token in re.split(r"[,，]\s*", value.strip()):
        token = token.strip()
        match = re.fullmatch(r"(\d+)\s*[-–—]\s*(\d+)", token)
        if match:
            start, end = map(int, match.groups())
            numbers.extend(range(start, end + 1))
        elif token.isdigit():
            numbers.append(int(token))
    return numbers


def compress_numbers(numbers: list[int]) -> str:
    ordered = sorted(dict.fromkeys(numbers))
    groups: list[str] = []
    start = previous = ordered[0]
    for number in ordered[1:]:
        if number == previous + 1:
            previous = number
            continue
        groups.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = number
    groups.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(groups)


def main() -> None:
    text = THESIS.read_text(encoding="utf-8")
    body, references_text = text.split(REFERENCE_HEADING, 1)

    cited = sorted(
        {
            number
            for match in CITATION_RE.finditer(body)
            for number in expand_numbers(match.group(1))
        }
    )
    references = {int(number): entry.strip() for number, entry in REFERENCE_RE.findall(references_text)}
    missing = sorted(set(cited) - references.keys())
    if missing:
        raise SystemExit(f"Dangling citations: {missing}")

    mapping = {old: new for new, old in enumerate(cited, start=1)}

    def replace_citation(match: re.Match[str]) -> str:
        old_numbers = expand_numbers(match.group(1))
        return f"[{compress_numbers([mapping[number] for number in old_numbers])}]"

    rewritten_body = CITATION_RE.sub(replace_citation, body).rstrip()
    rewritten_references = "\n\n".join(
        f"[{mapping[old]}] {references[old]}" for old in cited
    )
    THESIS.write_text(
        f"{rewritten_body}\n\n{REFERENCE_HEADING}\n\n{rewritten_references}\n",
        encoding="utf-8",
    )
    removed = sorted(references.keys() - set(cited))
    print(f"Kept {len(cited)} cited references; removed {len(removed)} orphan references.")
    print(f"Removed old reference numbers: {removed}")


if __name__ == "__main__":
    main()
