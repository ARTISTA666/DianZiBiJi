from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_htrflow_batch.py"
SPEC = importlib.util.spec_from_file_location("run_htrflow_batch", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RunHtrflowBatchTests(unittest.TestCase):
    def test_writes_outputs_and_reproducibility_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.jpg").write_bytes(b"image")
            (root / "reference.txt").write_text("Experiment 42", encoding="utf-8")
            manifest = root / "manifest.csv"
            manifest.write_text(
                "sample_id,image_path,reference_path,source_url\n"
                "A,page.jpg,reference.txt,https://example.test/A\n",
                encoding="utf-8",
            )

            def fake_runner(command, check):
                self.assertFalse(check)
                pipeline = json.loads(Path(command[2]).read_text(encoding="utf-8"))
                exports = {
                    step["settings"]["format"]: Path(step["settings"]["dest"])
                    for step in pipeline["steps"]
                    if step["step"] == "Export"
                }
                (exports["txt"] / "images").mkdir()
                (exports["json"] / "images").mkdir()
                (exports["txt"] / "images" / "page.txt").write_text(
                    "Experiment 42\n", encoding="utf-8"
                )
                (exports["json"] / "images" / "page.json").write_text(
                    '{"page": "A"}\n', encoding="utf-8"
                )
                return type("Result", (), {"returncode": 0})()

            output_dir = root / "run"
            report = MODULE.run_batch(
                manifest_path=manifest,
                output_dir=output_dir,
                htrflow_executable="fake-htrflow",
                command_runner=fake_runner,
            )

            self.assertEqual(report["sample_count"], 1)
            self.assertEqual(report["models"]["recognition"]["id"], MODULE.RECOGNITION_MODEL)
            self.assertEqual(report["models"]["recognition"]["batch_size"], 8)
            self.assertEqual(len(report["samples"][0]["image_sha256"]), 64)
            with (output_dir / "evaluation.csv").open(encoding="utf-8", newline="") as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row["raw_ocr_path"], "raw/images/page.txt")
            self.assertEqual(row["reference_path"], "../reference.txt")

    def test_nested_layout_adds_region_segmentation(self) -> None:
        pipeline = MODULE.build_pipeline(Path("raw"), Path("metadata"), "cpu", "nested")
        self.assertEqual(pipeline["steps"][0]["settings"]["model_settings"]["model"], MODULE.REGION_MODEL)
        self.assertEqual(pipeline["steps"][3]["step"], "ReadingOrderMarginalia")

    def test_spread_layout_splits_and_combines_left_before_right(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (8, 4), "white").save(root / "spread.jpg")
            (root / "reference.txt").write_text("left\nright", encoding="utf-8")
            manifest = root / "manifest.csv"
            manifest.write_text(
                "sample_id,image_path,reference_path,source_url\n"
                "A,spread.jpg,reference.txt,https://example.test/A\n",
                encoding="utf-8",
            )

            def fake_runner(command, check):
                pipeline = json.loads(Path(command[2]).read_text(encoding="utf-8"))
                exports = {
                    step["settings"]["format"]: Path(step["settings"]["dest"])
                    for step in pipeline["steps"]
                    if step["step"] == "Export"
                }
                for label in ("left", "right"):
                    (exports["txt"] / f"A__{label}.txt").write_text(label, encoding="utf-8")
                    (exports["json"] / f"A__{label}.json").write_text("{}", encoding="utf-8")
                return type("Result", (), {"returncode": 0})()

            output_dir = root / "run"
            report = MODULE.run_batch(
                manifest,
                output_dir,
                layout="spread",
                command_runner=fake_runner,
            )

            combined = output_dir / "combined" / "A.txt"
            self.assertEqual(combined.read_text(encoding="utf-8"), "left\nright\n")
            self.assertEqual(report["samples"][0]["preprocessing"]["split_x"], 4)

    def test_rejects_existing_report_without_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "run"
            output.mkdir()
            (output / "run.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                MODULE.run_batch(root / "missing.csv", output)


if __name__ == "__main__":
    unittest.main()
