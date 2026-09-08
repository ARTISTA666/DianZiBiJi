from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize_system_reviews.py"
SPEC = importlib.util.spec_from_file_location("summarize_system_reviews", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def rating(evaluator_id: int, accurate: bool, traceable: bool, score: int) -> dict:
    return {
        "evaluator_user_id": evaluator_id,
        "is_accurate": accurate,
        "is_traceable": traceable,
        "score": score,
        "comment": "错误或证据不足" if not accurate or not traceable else "",
        "review_protocol": "method_masked",
    }


def write_export(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "question_index",
                "question",
                "mode",
                "status",
                "query_log_id",
                "evaluations_json",
            ],
        )
        writer.writeheader()
        for row in rows:
            row.setdefault("question", f"Question {row['question_index']}")
        writer.writerows(rows)


class SummarizeSystemReviewsTests(unittest.TestCase):
    def test_summarizes_complete_export_and_paired_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            rows = [
                {
                    "question_index": 1,
                    "mode": "project_rag",
                    "status": "completed",
                    "query_log_id": 11,
                    "evaluations_json": json.dumps([
                        rating(2, False, False, 2),
                        rating(3, False, True, 3),
                    ]),
                },
                {
                    "question_index": 1,
                    "mode": "kg_enhanced_rag",
                    "status": "completed",
                    "query_log_id": 12,
                    "evaluations_json": json.dumps([
                        rating(2, True, True, 4),
                        rating(3, False, True, 3),
                    ]),
                },
                {
                    "question_index": 2,
                    "mode": "project_rag",
                    "status": "completed",
                    "query_log_id": 13,
                    "evaluations_json": json.dumps([
                        rating(2, True, True, 4),
                        rating(3, True, True, 4),
                    ]),
                },
                {
                    "question_index": 2,
                    "mode": "kg_enhanced_rag",
                    "status": "completed",
                    "query_log_id": 14,
                    "evaluations_json": json.dumps([
                        rating(2, True, True, 5),
                        rating(3, True, True, 4),
                    ]),
                },
            ]
            write_export(path, rows)

            result = MODULE.summarize(path)

        self.assertEqual(result["by_mode"]["project_rag"]["accuracy_rate"], 0.5)
        self.assertEqual(result["by_mode"]["kg_enhanced_rag"]["accuracy_rate"], 0.75)
        self.assertEqual(
            result["paired_mode_comparison"]["accuracy"],
            {
                "paired_ratings": 4,
                "improved": 1,
                "worsened": 0,
                "unchanged": 3,
                "net_change_rate": 0.25,
            },
        )
        self.assertEqual(result["reviewer_ids"], [2, 3])
        self.assertEqual(len(result["source_export_sha256"]), 64)

    def test_rejects_missing_second_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            write_export(
                path,
                [{
                    "question_index": 1,
                    "mode": "project_rag",
                    "status": "completed",
                    "query_log_id": 11,
                    "evaluations_json": json.dumps([rating(2, True, True, 4)]),
                }],
            )

            with self.assertRaisesRegex(ValueError, "expected 2"):
                MODULE.summarize(path)

    def test_rejects_negative_judgment_without_comment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            invalid = rating(2, False, True, 2)
            invalid["comment"] = ""
            write_export(
                path,
                [{
                    "question_index": 1,
                    "mode": "project_rag",
                    "status": "completed",
                    "query_log_id": 11,
                    "evaluations_json": json.dumps([invalid, rating(3, True, True, 4)]),
                }],
            )

            with self.assertRaisesRegex(ValueError, "requires a comment"):
                MODULE.summarize(path)

    def test_rejects_unblinded_manager_rating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            unblinded = rating(2, True, True, 4)
            unblinded["review_protocol"] = "unblinded"
            write_export(
                path,
                [{
                    "question_index": 1,
                    "mode": "project_rag",
                    "status": "completed",
                    "query_log_id": 11,
                    "evaluations_json": json.dumps([unblinded, rating(3, True, True, 4)]),
                }],
            )

            with self.assertRaisesRegex(ValueError, "not submitted through method-masked review"):
                MODULE.summarize(path)

    def test_rejects_duplicate_question_mode_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            duplicate = {
                "question_index": 1,
                "mode": "project_rag",
                "status": "completed",
                "query_log_id": 11,
                "evaluations_json": json.dumps([rating(2, True, True, 4), rating(3, True, True, 4)]),
            }
            write_export(path, [duplicate, {**duplicate, "query_log_id": 12}])

            with self.assertRaisesRegex(ValueError, "duplicate item"):
                MODULE.summarize(path)

    def test_rejects_duplicate_query_log_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            write_export(
                path,
                [
                    {
                        "question_index": 1,
                        "mode": "project_rag",
                        "status": "completed",
                        "query_log_id": 11,
                        "evaluations_json": json.dumps([rating(2, True, True, 4), rating(3, True, True, 4)]),
                    },
                    {
                        "question_index": 1,
                        "mode": "kg_enhanced_rag",
                        "status": "completed",
                        "query_log_id": 11,
                        "evaluations_json": json.dumps([rating(2, True, True, 4), rating(3, True, True, 4)]),
                    },
                ],
            )

            with self.assertRaisesRegex(ValueError, "duplicate query_log_id"):
                MODULE.summarize(path)

    def test_rejects_invalid_query_log_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            write_export(
                path,
                [{
                    "question_index": 1,
                    "mode": "project_rag",
                    "status": "completed",
                    "query_log_id": "not-a-number",
                    "evaluations_json": json.dumps([rating(2, True, True, 4), rating(3, True, True, 4)]),
                }],
            )

            with self.assertRaisesRegex(ValueError, "invalid query_log_id"):
                MODULE.summarize(path)

    def test_rejects_non_positive_evaluator_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            write_export(
                path,
                [{
                    "question_index": 1,
                    "mode": "project_rag",
                    "status": "completed",
                    "query_log_id": 11,
                    "evaluations_json": json.dumps([rating(0, True, True, 4), rating(3, True, True, 4)]),
                }],
            )

            with self.assertRaisesRegex(ValueError, "invalid evaluator or score"):
                MODULE.summarize(path)

    def test_rejects_legacy_export_without_question_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["question_index", "mode", "status", "query_log_id", "evaluations_json"])
                writer.writeheader()
                writer.writerow(
                    {
                        "question_index": 1,
                        "mode": "project_rag",
                        "status": "completed",
                        "query_log_id": 11,
                        "evaluations_json": json.dumps([rating(2, True, True, 4), rating(3, True, True, 4)]),
                    }
                )

            with self.assertRaisesRegex(ValueError, "missing columns: question"):
                MODULE.summarize(path)


if __name__ == "__main__":
    unittest.main()
