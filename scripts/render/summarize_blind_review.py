"""Validate and summarize a randomized blind-review sheet."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


REQUIRED_SHEET_COLUMNS = {
    "blind_id",
    "is_accurate",
    "is_traceable",
    "score_1_to_5",
    "reviewer_signature",
}
REQUIRED_KEY_COLUMNS = {"blind_id", "mode"}
TRUE_VALUES = {"1", "true", "yes", "y", "是", "准确", "可追溯"}
FALSE_VALUES = {"0", "false", "no", "n", "否", "不准确", "不可追溯"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return None


def agreement(values: list[tuple[bool, bool]]) -> dict:
    if not values:
        return {"n": 0, "agreement_rate": None, "cohens_kappa": None}
    agree = sum(left == right for left, right in values)
    observed = agree / len(values)
    left_true = sum(left for left, _ in values) / len(values)
    right_true = sum(right for _, right in values) / len(values)
    expected = left_true * right_true + (1 - left_true) * (1 - right_true)
    kappa = 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1 - expected)
    return {"n": len(values), "agreement_rate": round(observed, 4), "cohens_kappa": round(kappa, 4)}


def summarize(sheet_path: Path, key_path: Path, allow_incomplete: bool = False) -> dict:
    sheet = read_csv(sheet_path)
    key = read_csv(key_path)
    if not sheet:
        raise ValueError("Blind-review sheet is empty.")
    if not REQUIRED_SHEET_COLUMNS.issubset(sheet[0]):
        missing = sorted(REQUIRED_SHEET_COLUMNS - set(sheet[0]))
        raise ValueError("Missing sheet columns: " + ", ".join(missing))
    if not key or not REQUIRED_KEY_COLUMNS.issubset(key[0]):
        missing = sorted(REQUIRED_KEY_COLUMNS - (set(key[0]) if key else set()))
        raise ValueError("Missing key columns: " + ", ".join(missing))

    mode_by_blind_id = {row["blind_id"]: row["mode"] for row in key}
    missing_reviews: list[str] = []
    rows: list[dict] = []
    for row in sheet:
        blind_id = row["blind_id"]
        accurate = parse_bool(row["is_accurate"])
        traceable = parse_bool(row["is_traceable"])
        try:
            score = int(row["score_1_to_5"])
        except ValueError:
            score = 0
        complete = (
            blind_id in mode_by_blind_id
            and accurate is not None
            and traceable is not None
            and 1 <= score <= 5
            and bool(row["reviewer_signature"].strip())
        )
        if not complete:
            missing_reviews.append(blind_id)
        else:
            rows.append(
                {
                    "blind_id": blind_id,
                    "mode": mode_by_blind_id[blind_id],
                    "accurate": accurate,
                    "traceable": traceable,
                    "score": score,
                    "reviewer_signature": row["reviewer_signature"].strip(),
                }
            )

    if missing_reviews and not allow_incomplete:
        raise ValueError("Incomplete blind-review rows: " + ", ".join(missing_reviews))

    by_mode: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)

    by_blind_id: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_blind_id[row["blind_id"]].append(row)
    reviewer_pairs = [
        items for items in by_blind_id.values() if len(items) == 2 and len({item["reviewer_signature"] for item in items}) == 2
    ]

    return {
        "total_rows": len(sheet),
        "completed_rows": len(rows),
        "incomplete_rows": missing_reviews,
        "by_mode": {
            mode: {
                "n": len(items),
                "accuracy_rate": round(sum(item["accurate"] for item in items) / len(items), 4),
                "traceability_rate": round(sum(item["traceable"] for item in items) / len(items), 4),
                "mean_score": round(statistics.fmean(item["score"] for item in items), 4),
            }
            for mode, items in sorted(by_mode.items())
            if items
        },
        "mode_counts": dict(Counter(row["mode"] for row in rows)),
        "two_reviewer_agreement": {
            "accuracy": agreement([(items[0]["accurate"], items[1]["accurate"]) for items in reviewer_pairs]),
            "traceability": agreement([(items[0]["traceable"], items[1]["traceable"]) for items in reviewer_pairs]),
        },
    }


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        sheet = Path(tmp) / "sheet.csv"
        key = Path(tmp) / "key.csv"
        sheet.write_text(
            "blind_id,is_accurate,is_traceable,score_1_to_5,reviewer_signature\n"
            "B01,yes,no,4,R1\n"
            "B01,yes,yes,5,R2\n",
            encoding="utf-8",
        )
        key.write_text("blind_id,mode\nB01,kg_enhanced_rag\n", encoding="utf-8")
        result = summarize(sheet, key)
        assert result["completed_rows"] == 2
        assert result["by_mode"]["kg_enhanced_rag"]["accuracy_rate"] == 1.0
        assert result["by_mode"]["kg_enhanced_rag"]["traceability_rate"] == 0.5
        assert result["two_reviewer_agreement"]["accuracy"]["cohens_kappa"] == 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=Path, help="Randomized blind-review sheet CSV.")
    parser.add_argument("--key", type=Path, help="Blind-review decode key CSV.")
    parser.add_argument("-o", "--output", type=Path, help="JSON summary path.")
    parser.add_argument("--allow-incomplete", action="store_true", help="Summarize completed rows without failing.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in checks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return 0
    if not args.sheet or not args.key:
        raise SystemExit("Provide --sheet and --key, or use --self-test.")
    result = summarize(args.sheet, args.key, args.allow_incomplete)
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
