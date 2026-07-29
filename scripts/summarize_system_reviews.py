"""Validate and summarize human ratings from a system experiment CSV export."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_COLUMNS = {
    "question_index",
    "question",
    "mode",
    "status",
    "query_log_id",
    "evaluations_json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def agreement(pairs: list[tuple[bool, bool]]) -> dict:
    if not pairs:
        return {"paired_items": 0, "agreement_rate": None, "cohens_kappa": None}
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_true = sum(left for left, _ in pairs) / len(pairs)
    right_true = sum(right for _, right in pairs) / len(pairs)
    expected = left_true * right_true + (1 - left_true) * (1 - right_true)
    kappa = 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1 - expected)
    return {
        "paired_items": len(pairs),
        "agreement_rate": round(observed, 6),
        "cohens_kappa": round(kappa, 6),
    }


def parse_rating(item: dict, item_id: str) -> dict:
    try:
        evaluator_id = int(item["evaluator_user_id"])
        score = int(item["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{item_id} contains an invalid evaluator or score.") from exc
    if evaluator_id <= 0:
        raise ValueError(f"{item_id} contains an invalid evaluator or score.")
    accurate = item.get("is_accurate")
    traceable = item.get("is_traceable")
    if not isinstance(accurate, bool) or not isinstance(traceable, bool):
        raise ValueError(f"{item_id} contains an invalid binary judgment.")
    if not 1 <= score <= 5:
        raise ValueError(f"{item_id} score must be between 1 and 5.")
    comment = str(item.get("comment") or "").strip()
    if (not accurate or not traceable) and not comment:
        raise ValueError(f"{item_id} requires a comment for a negative judgment.")
    review_protocol = str(item.get("review_protocol") or "").strip()
    if review_protocol != "method_masked":
        raise ValueError(
            f"{item_id} contains a rating that was not submitted through method-masked review."
        )
    return {
        "evaluator_id": evaluator_id,
        "score": score,
        "accurate": accurate,
        "traceable": traceable,
        "comment": comment,
        "review_protocol": review_protocol,
    }


def read_export(path: Path, expected_reviewers: int = 2, allow_incomplete: bool = False) -> tuple[list[dict], dict]:
    if expected_reviewers < 1:
        raise ValueError("expected_reviewers must be at least 1.")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        if not REQUIRED_COLUMNS.issubset(columns):
            missing = ", ".join(sorted(REQUIRED_COLUMNS - columns))
            raise ValueError(f"Experiment export is missing columns: {missing}")
        export_rows = list(reader)
    if not export_rows:
        raise ValueError("Experiment export is empty.")

    ratings: list[dict] = []
    issues: list[str] = []
    reviewer_sets: list[set[int]] = []
    modes_by_question: dict[int, set[str]] = defaultdict(set)
    question_text_by_index: dict[int, str] = {}
    all_modes: set[str] = set()
    seen_items: set[tuple[int, str]] = set()
    seen_query_log_ids: set[str] = set()
    for row in export_rows:
        try:
            question_index = int(row["question_index"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Experiment export contains an invalid question_index.") from exc
        mode = row["mode"].strip()
        question = row["question"].strip()
        item_id = f"question#{question_index}:{mode or 'missing-mode'}"
        if not question:
            issues.append(f"question#{question_index} has no question text")
            continue
        existing_question = question_text_by_index.setdefault(question_index, question)
        if question != existing_question:
            raise ValueError(f"Experiment export contains inconsistent question text for question#{question_index}.")
        if not mode:
            issues.append(f"{item_id} has no mode")
            continue
        item_key = (question_index, mode)
        if item_key in seen_items:
            raise ValueError(f"Experiment export contains duplicate item: {item_id}")
        seen_items.add(item_key)
        all_modes.add(mode)
        modes_by_question[question_index].add(mode)
        query_log_id = row["query_log_id"].strip()
        if row["status"].strip().lower() != "completed" or not query_log_id:
            issues.append(f"{item_id} did not complete")
            continue
        try:
            if int(query_log_id) <= 0:
                raise ValueError
        except ValueError as exc:
            raise ValueError(f"{item_id} contains an invalid query_log_id.") from exc
        if query_log_id in seen_query_log_ids:
            raise ValueError(f"Experiment export contains duplicate query_log_id: {query_log_id}")
        seen_query_log_ids.add(query_log_id)
        try:
            evaluations = json.loads(row["evaluations_json"] or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{item_id} has invalid evaluations_json.") from exc
        if not isinstance(evaluations, list):
            raise ValueError(f"{item_id} evaluations_json must be a list.")

        item_ratings = [parse_rating(item, item_id) for item in evaluations]
        reviewer_ids = [item["evaluator_id"] for item in item_ratings]
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError(f"{item_id} contains duplicate evaluator ratings.")
        if len(item_ratings) != expected_reviewers:
            issues.append(
                f"{item_id} has {len(item_ratings)} ratings; expected {expected_reviewers}"
            )
            if not allow_incomplete:
                continue
        else:
            reviewer_sets.append(set(reviewer_ids))
        for rating in item_ratings:
            ratings.append(
                {
                    **rating,
                    "item_id": item_id,
                    "question_index": question_index,
                    "mode": mode,
                    "query_log_id": query_log_id,
                }
            )

    for question_index, modes in sorted(modes_by_question.items()):
        if modes != all_modes:
            issues.append(
                f"question#{question_index} has modes {sorted(modes)}; expected {sorted(all_modes)}"
            )
    if reviewer_sets and any(reviewer_set != reviewer_sets[0] for reviewer_set in reviewer_sets[1:]):
        issues.append("completed items do not use one consistent reviewer set")
    if issues and not allow_incomplete:
        raise ValueError("Incomplete human review: " + "; ".join(issues))
    if not ratings:
        raise ValueError("No valid human ratings were found.")
    return ratings, {
        "export_item_count": len(export_rows),
        "expected_reviewers_per_item": expected_reviewers,
        "question_indices": sorted(modes_by_question),
        "question_text_by_index": {str(key): value for key, value in sorted(question_text_by_index.items())},
        "issues": issues,
    }


def rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def group_summary(items: list[dict]) -> dict:
    return {
        "item_count": len({item["item_id"] for item in items}),
        "rating_count": len(items),
        "accuracy_rate": rate(sum(item["accurate"] for item in items), len(items)),
        "traceability_rate": rate(sum(item["traceable"] for item in items), len(items)),
        "mean_score": round(statistics.fmean(item["score"] for item in items), 6),
    }


def paired_binary_change(
    ratings: list[dict],
    attribute: str,
    baseline_mode: str,
    comparison_mode: str,
) -> dict | None:
    values = {
        (item["question_index"], item["evaluator_id"], item["mode"]): item[attribute]
        for item in ratings
    }
    pairs = []
    for question_index, evaluator_id in sorted(
        {(item["question_index"], item["evaluator_id"]) for item in ratings}
    ):
        baseline_key = (question_index, evaluator_id, baseline_mode)
        comparison_key = (question_index, evaluator_id, comparison_mode)
        if baseline_key in values and comparison_key in values:
            pairs.append((values[baseline_key], values[comparison_key]))
    if not pairs:
        return None
    improved = sum(not baseline and comparison for baseline, comparison in pairs)
    worsened = sum(baseline and not comparison for baseline, comparison in pairs)
    return {
        "paired_ratings": len(pairs),
        "improved": improved,
        "worsened": worsened,
        "unchanged": len(pairs) - improved - worsened,
        "net_change_rate": round((improved - worsened) / len(pairs), 6),
    }


def paired_score_change(ratings: list[dict], baseline_mode: str, comparison_mode: str) -> dict | None:
    scores = {
        (item["question_index"], item["evaluator_id"], item["mode"]): item["score"]
        for item in ratings
    }
    deltas = []
    for question_index, evaluator_id in sorted(
        {(item["question_index"], item["evaluator_id"]) for item in ratings}
    ):
        baseline_key = (question_index, evaluator_id, baseline_mode)
        comparison_key = (question_index, evaluator_id, comparison_mode)
        if baseline_key in scores and comparison_key in scores:
            deltas.append(scores[comparison_key] - scores[baseline_key])
    if not deltas:
        return None
    return {
        "paired_ratings": len(deltas),
        "mean_score_change": round(statistics.fmean(deltas), 6),
        "positive": sum(delta > 0 for delta in deltas),
        "negative": sum(delta < 0 for delta in deltas),
        "unchanged": sum(delta == 0 for delta in deltas),
    }


def summarize(
    path: Path,
    expected_reviewers: int = 2,
    allow_incomplete: bool = False,
    baseline_mode: str = "project_rag",
    comparison_mode: str = "kg_enhanced_rag",
) -> dict:
    ratings, completion = read_export(path, expected_reviewers, allow_incomplete)
    by_mode: dict[str, list[dict]] = defaultdict(list)
    by_reviewer: dict[int, list[dict]] = defaultdict(list)
    by_item: dict[str, list[dict]] = defaultdict(list)
    for rating in ratings:
        by_mode[rating["mode"]].append(rating)
        by_reviewer[rating["evaluator_id"]].append(rating)
        by_item[rating["item_id"]].append(rating)

    accuracy_pairs = []
    traceability_pairs = []
    for items in by_item.values():
        ordered = sorted(items, key=lambda item: item["evaluator_id"])
        for left, right in itertools.combinations(ordered, 2):
            accuracy_pairs.append((left["accurate"], right["accurate"]))
            traceability_pairs.append((left["traceable"], right["traceable"]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_export": str(path.resolve()),
        "source_export_sha256": sha256(path),
        "completion": completion,
        "reviewer_ids": sorted(by_reviewer),
        "by_mode": {
            mode: group_summary(items)
            for mode, items in sorted(by_mode.items())
        },
        "by_reviewer": {
            str(reviewer_id): group_summary(items)
            for reviewer_id, items in sorted(by_reviewer.items())
        },
        "agreement": {
            "accuracy": agreement(accuracy_pairs),
            "traceability": agreement(traceability_pairs),
        },
        "paired_mode_comparison": {
            "baseline_mode": baseline_mode,
            "comparison_mode": comparison_mode,
            "accuracy": paired_binary_change(
                ratings, "accurate", baseline_mode, comparison_mode
            ),
            "traceability": paired_binary_change(
                ratings, "traceable", baseline_mode, comparison_mode
            ),
            "score": paired_score_change(ratings, baseline_mode, comparison_mode),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True, help="CSV exported by the experiment API.")
    parser.add_argument("--expected-reviewers", type=int, default=2)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--baseline-mode", default="project_rag")
    parser.add_argument("--comparison-mode", default="kg_enhanced_rag")
    parser.add_argument("-o", "--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = summarize(
        args.export,
        expected_reviewers=args.expected_reviewers,
        allow_incomplete=args.allow_incomplete,
        baseline_mode=args.baseline_mode,
        comparison_mode=args.comparison_mode,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
