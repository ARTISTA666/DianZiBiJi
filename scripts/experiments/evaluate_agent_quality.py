#!/usr/bin/env python3
"""Score Agent answers against a frozen claim/citation gold set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


CITATION_RE = re.compile(r"\[(?:N|F|R)\d+\]")


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def evidence_segments(answer: str) -> list[str]:
    segments = [item.strip() for item in re.split(r"(?:\n\s*\n|\n(?=\s*[-*#]))", answer)]
    return [item for item in segments if item]


def criterion_match(answer: str, criterion: dict[str, Any]) -> bool:
    haystack = normalized(answer)
    return all(normalized(term) in haystack for term in criterion["required_all"])


def criterion_is_cited(answer: str, criterion: dict[str, Any]) -> bool:
    return bool(criterion_citations(answer, criterion))


def criterion_citations(answer: str, criterion: dict[str, Any]) -> set[str]:
    anchors = [normalized(value) for value in criterion.get("anchor_any", [])]
    allowed = set(criterion["allowed_citations"])
    matched: set[str] = set()
    for segment in evidence_segments(answer):
        compact = normalized(segment)
        if anchors and not any(anchor in compact for anchor in anchors):
            continue
        matched.update(allowed.intersection(CITATION_RE.findall(segment)))
    return matched


def score_case(case: dict[str, Any], answer: str) -> dict[str, Any]:
    criteria = case["criteria"]
    checks = []
    semantically_supported: set[str] = set()
    for criterion in criteria:
        matched = criterion_match(answer, criterion)
        linked_citations = criterion_citations(answer, criterion) if matched else set()
        cited = matched and bool(linked_citations)
        semantically_supported.update(linked_citations)
        checks.append({"id": criterion["id"], "fact_matched": matched, "citation_matched": cited})

    citations = CITATION_RE.findall(answer)
    unique_citations = list(dict.fromkeys(citations))
    valid_citations = [value for value in unique_citations if value in semantically_supported]
    forbidden = [value for value in case.get("forbidden_claims", []) if normalized(value) in normalized(answer)]
    count = len(criteria)
    fact_count = sum(item["fact_matched"] for item in checks)
    cited_count = sum(item["citation_matched"] for item in checks)
    return {
        "id": case["id"],
        "task_type": case["task_type"],
        "fact_consistency": fact_count / count if count else 1.0,
        "citation_recall": cited_count / count if count else 1.0,
        "citation_precision": len(valid_citations) / len(unique_citations) if unique_citations else 0.0,
        "boundary_passed": not forbidden,
        "forbidden_claims_found": forbidden,
        "citation_count": len(unique_citations),
        "unsupported_citations": [value for value in unique_citations if value not in semantically_supported],
        "checks": checks,
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "answer_chars": len(answer),
    }


def score_run(gold: dict[str, Any], answers: dict[str, str]) -> dict[str, Any]:
    cases = [score_case(case, answers.get(case["id"], "")) for case in gold["cases"]]
    count = len(cases)
    mean = lambda key: sum(float(item[key]) for item in cases) / count if count else 0.0
    case_passed = [
        item["fact_consistency"] >= 0.9
        and item["citation_precision"] >= 0.9
        and item["citation_recall"] >= 0.9
        and item["boundary_passed"]
        for item in cases
    ]
    return {
        "schema": "full-system.agent-quality-report",
        "schema_version": 2,
        "gold_sha256": canonical_sha256(gold),
        "prompt_version": gold["prompt_version"],
        "case_count": count,
        "summary": {
            "fact_consistency": mean("fact_consistency"),
            "citation_precision": mean("citation_precision"),
            "citation_recall": mean("citation_recall"),
            "boundary_pass_rate": mean("boundary_passed"),
            "case_pass_rate": sum(case_passed) / count if count else 0.0,
            "minimum_case_fact_consistency": min((item["fact_consistency"] for item in cases), default=0.0),
            "minimum_case_citation_precision": min((item["citation_precision"] for item in cases), default=0.0),
            "minimum_case_citation_recall": min((item["citation_recall"] for item in cases), default=0.0),
            "human_review_status": "pending",
        },
        "cases": cases,
    }


def quality_gate_passed(report: dict[str, Any]) -> bool:
    """Require macro thresholds and every frozen case to pass.

    The macro thresholds prevent a single large/easy task from hiding a broken
    task type; the per-case gate is the local equivalent of a reliability gate.
    """
    summary = report["summary"]
    return (
        summary["fact_consistency"] >= 0.9
        and summary["citation_precision"] >= 0.9
        and summary["citation_recall"] >= 0.9
        and summary["boundary_pass_rate"] == 1.0
        and summary["case_pass_rate"] == 1.0
    )


def load_answers(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("answers", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("answers input must be a list or an object containing answers")
    result = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not isinstance(record.get("answer"), str):
            raise ValueError("each answer must contain string id and answer fields")
        result[record["id"]] = record["answer"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=Path("evaluation-lab/agent-quality/gold-v1.json"))
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    report = score_run(gold, load_answers(args.answers))
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    summary = report["summary"]
    return 0 if quality_gate_passed(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
