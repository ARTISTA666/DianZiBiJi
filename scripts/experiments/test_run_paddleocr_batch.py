from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_paddleocr_batch.py"
SPEC = importlib.util.spec_from_file_location("run_paddleocr_batch", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakePipeline:
    def predict(self, **kwargs):
        assert kwargs["use_doc_orientation_classify"] is False
        assert kwargs["use_doc_unwarping"] is False
        assert kwargs["use_textline_orientation"] is False
        return [{"rec_texts": ["Result 42", "second line"], "rec_scores": [0.8, 0.6]}]


class RunPaddleOcrBatchTests(unittest.TestCase):
    def test_writes_outputs_and_reproducibility_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.jpg").write_bytes(b"image")
            (root / "reference.txt").write_text("Result 42", encoding="utf-8")
            manifest = root / "manifest.csv"
            manifest.write_text(
                "sample_id,image_path,reference_path,raw_ocr_path,source_url\n"
                "A,page.jpg,reference.txt,unused.txt,https://example.test/A\n",
                encoding="utf-8",
            )
            model_root = root / "models"
            (model_root / MODULE.DEFAULT_DETECTOR).mkdir(parents=True)
            (model_root / MODULE.DEFAULT_DETECTOR / "weights.bin").write_bytes(b"detector")

            report = MODULE.run_batch(
                manifest_path=manifest,
                output_path=root / "variant" / "run.json",
                raw_output_dir=root / "variant" / "raw",
                evaluation_manifest_output=root / "variant" / "evaluation.csv",
                pipeline_factory=lambda detector, recognizer: FakePipeline(),
                installed_versions={"paddlepaddle": "3.2.1", "paddleocr": "3.7.0", "paddlex": "3.7.2"},
                model_root=model_root,
            )

            self.assertEqual(report["sample_count"], 1)
            self.assertEqual(report["detector"], MODULE.DEFAULT_DETECTOR)
            self.assertEqual(report["samples"][0]["detected_line_count"], 2)
            self.assertEqual(report["samples"][0]["mean_model_score"], 0.7)
            self.assertEqual(len(report["samples"][0]["image_sha256"]), 64)
            self.assertEqual(
                (root / "variant" / "raw" / "A.txt").read_text(encoding="utf-8"),
                "Result 42\nsecond line\n",
            )
            with (root / "variant" / "evaluation.csv").open(encoding="utf-8", newline="") as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row["raw_ocr_path"], "raw/A.txt")
            self.assertEqual(row["reference_path"], "../reference.txt")
            artifact = report["model_artifacts"][MODULE.DEFAULT_DETECTOR]
            self.assertEqual(artifact["file_count"], 1)
            self.assertEqual(len(artifact["tree_sha256"]), 64)

    def test_rejects_existing_report_without_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "run.json"
            report.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                MODULE.run_batch(
                    manifest_path=root / "missing.csv",
                    output_path=report,
                    raw_output_dir=root / "raw",
                    pipeline_factory=lambda detector, recognizer: FakePipeline(),
                    installed_versions={},
                    model_root=root,
                )


if __name__ == "__main__":
    unittest.main()
