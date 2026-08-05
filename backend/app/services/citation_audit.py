"""Unified citation audit utility.

Extracts citation markers from answer text via regex, validates them against
a set of allowed indices per marker prefix, and returns a structured result.

Used by both the agent summary/review pipeline (``[NFR]`` markers) and the
RAG Q&A evaluation pipeline (``[SG]`` markers).
"""

from __future__ import annotations

import re


def audit_citations(
    answer: str,
    allowed: dict[str, set[int]],
    *,
    pattern: str | None = None,
    flags: int = 0,
) -> dict:
    """Audit citation markers in *answer* against *allowed* index sets.

    Parameters
    ----------
    answer:
        The text to scan for citation markers.
    allowed:
        Mapping of single-character marker prefix (e.g. ``"N"``, ``"S"``)
        to the set of valid integer indices for that prefix.
    pattern:
        Optional regex pattern override.  Must contain two capture groups:
        ``(marker)(index)``.  The default also captures malformed marker
        bodies so they cannot bypass citation validation.
    flags:
        Regex flags forwarded to :func:`re.findall` (e.g. ``re.IGNORECASE``).

    Returns
    -------
    dict
        ``passed`` – bool indicating overall pass/fail.
        ``citation_count`` – total number of citation markers found.
        ``invalid_citations`` – list of malformed marker strings.
        ``has_evidence`` – bool indicating whether any evidence was provided.
        ``message`` – human-readable summary string (agent-style defaults;
        callers may override after the call).
    """
    prefixes = "".join(allowed.keys())
    if not prefixes:
        return {
            "passed": True,
            "citation_count": 0,
            "invalid_citations": [],
            "has_evidence": False,
            "message": "该回答没有可引用的项目证据。",
        }
    if pattern is None:
        pattern = rf"\[([{prefixes}])([^\]]*)\]"

    citations = []
    for kind, raw_index in re.findall(pattern, answer, flags):
        normalized_kind = kind.upper() if flags & re.IGNORECASE else kind
        try:
            index = int(raw_index) if raw_index.isdigit() else None
        except ValueError:
            index = None
        citations.append((normalized_kind, index, f"[{normalized_kind}{raw_index}]"))

    invalid = [
        marker
        for kind, item_id, marker in citations
        if item_id is None or item_id not in allowed.get(kind, set())
    ]

    has_evidence = any(bool(v) for v in allowed.values())
    passed = not invalid and (bool(citations) or not has_evidence)

    # Build human-readable message (agent-style defaults) ---------------
    if invalid:
        message = f"发现 {len(invalid)} 个无效引用：{'、'.join(invalid)}。"
    elif has_evidence and not citations:
        message = "草稿没有引用来源编号，需要人工检查。"
    elif citations:
        message = f"引用检查通过，共检查 {len(citations)} 个来源编号。"
    else:
        message = "该回答没有可引用的项目证据。"

    return {
        "passed": passed,
        "citation_count": len(citations),
        "invalid_citations": invalid,
        "has_evidence": has_evidence,
        "message": message,
    }
