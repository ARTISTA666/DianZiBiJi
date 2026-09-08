from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_ocr.py"
SPEC = importlib.util.spec_from_file_location("evaluate_ocr", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class EvaluateOcrTests(unittest.TestCase):
    def test_levenshtein_distance_and_normalization(self) -> None:
        self.assertEqual(MODULE.levenshtein_distance("kitten", "sitting"), 3)
        self.assertEqual(MODULE.levenshtein_distance("", "abc"), 3)
        self.assertEqual(MODULE.normalize_text("Ａ\r\n  B"), "A B")

    def test_scores_text_and_numbers_without_calling_cer_accuracy(self) -> None:
        result = MODULE.score_text("实验 58 C，时间 20 min", "实验 59 C，时间 20 min")

        self.assertEqual(result["edit_distance"], 1)
        self.assertAlmostEqual(
            result["character_error_rate"],
            1 / result["reference_characters"],
            places=6,
        )
        self.assertEqual(result["numeric_tokens"]["reference_count"], 2)
        self.assertEqual(result["numeric_tokens"]["matched_count"], 1)
        self.assertNotIn("accuracy", result)

    def test_rejects_empty_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "Reference text is empty"):
            MODULE.score_text(" \n", "some OCR")

    def test_manifest_report_is_recomputable_and_uses_paired_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            reference_a = tmp_path / "reference-a.txt"
            raw_a = tmp_path / "raw-a.txt"
            corrected_a = tmp_path / "corrected-a.txt"
            reference_b = tmp_path / "reference-b.txt"
            raw_b = tmp_path / "raw-b.txt"
            reference_a.write_text("ABCDE", encoding="utf-8")
            raw_a.write_text("AXCYE", encoding="utf-8")
            corrected_a.write_text("ABCYE", encoding="utf-8")
            reference_b.write_text("12345", encoding="utf-8")
            raw_b.write_text("12345", encoding="utf-8")

            manifest = tmp_path / "manifest.csv"
            with manifest.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=[
                        "sample_id",
                        "reference_path",
                        "raw_ocr_path",
                        "corrected_ocr_path",
                        "source_url",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "sample_id": "A",
                        "reference_path": reference_a.name,
                        "raw_ocr_path": raw_a.name,
                        "corrected_ocr_path": corrected_a.name,
                        "source_url": "https://example.test/a",
                    }
                )
                writer.writerow(
                    {
                        "sample_id": "B",
                        "reference_path": reference_b.name,
                        "raw_ocr_path": raw_b.name,
                        "corrected_ocr_path": "",
                        "source_url": "https://example.test/b",
                    }
                )

            report = MODULE.evaluate_manifest(manifest)

        self.assertEqual(report["sample_count"], 2)
        self.assertEqual(report["summary"]["raw"]["micro_character_error_rate"], 0.2)
        self.assertEqual(
            report["summary"]["paired_change"],
            {
                "sample_count": 1,
                "raw_micro_character_error_rate": 0.4,
                "corrected_micro_character_error_rate": 0.2,
                "error_rate_reduction_percentage_points": 20.0,
                "raw_micro_compact_character_error_rate": 0.4,
                "corrected_micro_compact_character_error_rate": 0.2,
            },
        )
        self.assertEqual(report["summary"]["raw"]["micro_compact_character_error_rate"], 0.2)
        self.assertEqual(
            report["summary"]["raw"]["numeric_tokens"],
            {
                "reference_count": 1,
                "prediction_count": 1,
                "matched_count": 1,
                "precision": 1.0,
                "recall": 1.0,
                "f1": 1.0,
                "exact_sequence_sample_count": 2,
            },
        )
        self.assertEqual(len(report["samples"][0]["reference"]["sha256"]), 64)

    def test_manifest_rejects_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            text = tmp_path / "text.txt"
            text.write_text("abc", encoding="utf-8")
            manifest = tmp_path / "manifest.csv"
            manifest.write_text(
                "sample_id,reference_path,raw_ocr_path\n"
                "A,text.txt,text.txt\n"
                "A,text.txt,text.txt\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Duplicate sample_id"):
                MODULE.evaluate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
