"""Restore the 80-entry reference catalog and original citation numbering."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from prune_references import CITATION_RE, REFERENCE_HEADING, compress_numbers, expand_numbers


ROOT = Path(__file__).resolve().parent.parent
THESIS = ROOT / "docs" / "毕业论文初稿.md"
REPO_PATH = "docs/毕业论文初稿.md"
REMOVED_OLD_NUMBERS = {
    31, 34, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47,
    53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 66, 67, 68,
    69, 70, 71, 72, 73, 75, 79, 80,
}


def main() -> None:
    current = THESIS.read_text(encoding="utf-8")
    body, _ = current.split(REFERENCE_HEADING, 1)

    old_cited = [number for number in range(1, 81) if number not in REMOVED_OLD_NUMBERS]
    new_to_old = {new: old for new, old in enumerate(old_cited, start=1)}

    def restore_citation(match: re.Match[str]) -> str:
        new_numbers = expand_numbers(match.group(1))
        return f"[{compress_numbers([new_to_old[number] for number in new_numbers])}]"

    restored_body = CITATION_RE.sub(restore_citation, body).rstrip()
    committed = subprocess.run(
        ["git", "show", f"HEAD:{REPO_PATH}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    _, committed_references = committed.split(REFERENCE_HEADING, 1)
    THESIS.write_text(
        f"{restored_body}\n\n{REFERENCE_HEADING}{committed_references}",
        encoding="utf-8",
    )
    print("Restored the 80-entry reference catalog and original citation numbering.")


if __name__ == "__main__":
    main()
