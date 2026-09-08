from __future__ import annotations

import importlib.util
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_ocr_batch.py"
SPEC = importlib.util.spec_from_file_location("run_ocr_batch", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RunOcrBatchTests(unittest.TestCase):
    def test_runs_frozen_manifest_and_records_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "page.jpg"
            image.write_bytes(b"image")
            manifest = root / "manifest.csv"
            manifest.write_text(
                "sample_id,image_path,raw_ocr_path\nA,page.jpg,raw/A.txt\n",
                encoding="utf-8",
            )

            def fake_run(command, **_kwargs):
                if command[-1] == "--list-langs":
                    return subprocess.CompletedProcess(command, 0, stdout="List of available languages (1):\nukr\n", stderr="")
                if command[-1] == "--version":
                    return subprocess.CompletedProcess(command, 0, stdout="tesseract 5.3.0\n", stderr="")
                self.assertEqual(command[-4:], ["-l", "ukr", "--psm", "3"])
                return subprocess.CompletedProcess(command, 0, stdout="Результат 42\n", stderr="")

            with patch.object(MODULE.subprocess, "run", side_effect=fake_run):
                report = MODULE.run_batch(manifest, root / "run.json", language="ukr")

            self.assertEqual(report["sample_count"], 1)
            self.assertEqual(report["engine"], "tesseract 5.3.0")
            self.assertEqual(len(report["samples"][0]["image_sha256"]), 64)
            self.assertEqual((root / "raw" / "A.txt").read_text(encoding="utf-8"), "Результат 42\n")

    def test_rejects_missing_language_before_running_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.csv").write_text(
                "sample_id,image_path,raw_ocr_path\nA,missing.jpg,raw/A.txt\n",
                encoding="utf-8",
            )
            completed = subprocess.CompletedProcess(
                ["tesseract", "--list-langs"],
                0,
                stdout="List of available languages (1):\neng\n",
                stderr="",
            )
            with patch.object(MODULE.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(ValueError, "language data is missing: ukr"):
                    MODULE.run_batch(root / "manifest.csv", root / "run.json", language="ukr")

    def test_records_configs_and_writes_a_separate_evaluation_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.jpg").write_bytes(b"image")
            (root / "reference.txt").write_text("Результат 42", encoding="utf-8")
            manifest = root / "manifest.csv"
            manifest.write_text(
                "sample_id,image_path,reference_path,raw_ocr_path,source_url\n"
                "A,page.jpg,reference.txt,unused.txt,https://example.test/A\n",
                encoding="utf-8",
            )

            def fake_run(command, **_kwargs):
                if command[-1] == "--list-langs":
                    return subprocess.CompletedProcess(command, 0, stdout="Languages (1):\nukr\n", stderr="")
                if command[-1] == "--version":
                    return subprocess.CompletedProcess(command, 0, stdout="tesseract 5.5.0\n", stderr="")
                self.assertEqual(
                    command[-8:],
                    [
                        "-l",
                        "ukr",
                        "--psm",
                        "6",
                        "--dpi",
                        "300",
                        "-c",
                        "thresholding_method=2",
                    ],
                )
                return subprocess.CompletedProcess(command, 0, stdout="Результат 42\n", stderr="")

            evaluation_manifest = root / "variant" / "evaluation.csv"
            with patch.object(MODULE.subprocess, "run", side_effect=fake_run):
                report = MODULE.run_batch(
                    manifest,
                    root / "variant" / "run.json",
                    language="ukr",
                    page_segmentation_mode=6,
                    dpi=300,
                    tesseract_configs=["thresholding_method=2"],
                    raw_output_dir=root / "variant" / "raw",
                    evaluation_manifest_output=evaluation_manifest,
                )

            self.assertEqual(report["dpi"], 300)
            self.assertEqual(report["tesseract_configs"], ["thresholding_method=2"])
            with evaluation_manifest.open(encoding="utf-8", newline="") as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row["raw_ocr_path"], "raw/A.txt")
            self.assertEqual(row["reference_path"], "../reference.txt")

    def test_rejects_invalid_tesseract_config(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid Tesseract config"):
            MODULE.validate_tesseract_configs(["thresholding_method=2\nunsafe"])

    def test_preprocesses_an_image_and_records_its_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (100, 80), "white").save(root / "page.jpg")
            manifest = root / "manifest.csv"
            manifest.write_text(
                "sample_id,image_path,raw_ocr_path\nA,page.jpg,raw/A.txt\n",
                encoding="utf-8",
            )

            def fake_run(command, **_kwargs):
                if command[-1] == "--list-langs":
                    return subprocess.CompletedProcess(command, 0, stdout="Languages (1):\nukr\n", stderr="")
                if command[-1] == "--version":
                    return subprocess.CompletedProcess(command, 0, stdout="tesseract 5.5.0\n", stderr="")
                self.assertTrue(command[1].endswith("A.png"))
                return subprocess.CompletedProcess(command, 0, stdout="text\n", stderr="")

            with patch.object(MODULE.subprocess, "run", side_effect=fake_run):
                report = MODULE.run_batch(
                    manifest,
                    root / "run.json",
                    language="ukr",
                    preprocessing_mode="crop_otsu",
                    processed_output_dir=root / "processed",
                )

            sample = report["samples"][0]
            self.assertEqual(sample["preprocessing"]["mode"], "crop_otsu")
            self.assertEqual(len(sample["processed_image_sha256"]), 64)
            self.assertTrue((root / "processed" / "A.png").is_file())


if __name__ == "__main__":
    unittest.main()
