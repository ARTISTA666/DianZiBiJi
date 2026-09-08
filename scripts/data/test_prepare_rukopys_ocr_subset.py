from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_rukopys_ocr_subset.py"
SPEC = importlib.util.spec_from_file_location("prepare_rukopys_ocr_subset", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def record(index: int, *, source: str = "university", region_type: str = "handwritten") -> dict:
    return {
        "file_name": f"images/{index:02d}.jpg",
        "image_width": 100,
        "image_height": 200,
        "source": source,
        "annotation_source": "annotator",
        "regions": [
            {
                "bbox": [0, 10, 80, 20],
                "type": region_type,
                "language": "uk",
                "legibility": "legible",
                "text": "текст " * 60,
            }
        ],
    }


class PrepareRukopysSubsetTests(unittest.TestCase):
    def test_filters_and_selects_evenly_before_images_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata.jsonl"
            records = [record(index) for index in range(11)]
            records.extend([record(20, source="school"), record(21, region_type="formula")])
            metadata.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
                encoding="utf-8",
            )

            result = MODULE.prepare(metadata, root / "output", sample_count=10)

            self.assertEqual(result["candidate_count"], 11)
            self.assertEqual(result["sample_count"], 10)
            self.assertEqual(result["samples"][0]["sample_id"], "00")
            self.assertEqual(result["samples"][-1]["sample_id"], "10")
            self.assertNotIn("05", [item["sample_id"] for item in result["samples"]])
            self.assertTrue((root / "output" / "ocr_manifest.csv").is_file())

    def test_refuses_to_change_a_frozen_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata.jsonl"
            metadata.write_text(json.dumps(record(0), ensure_ascii=False) + "\n", encoding="utf-8")
            MODULE.prepare(metadata, root / "output", sample_count=1)
            (root / "output" / "references" / "00.txt").write_text("changed", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Frozen file differs"):
                MODULE.prepare(metadata, root / "output", sample_count=1)

    def test_rejects_too_few_eligible_pages(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only 1 eligible records"):
            MODULE.evenly_spaced([record(0)], 2)

    def test_holdout_allows_empty_structural_regions_and_excludes_development_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "train" / "metadata.jsonl"
            metadata.parent.mkdir()
            development = record(0)
            holdout = record(1)
            holdout["regions"].append(
                {
                    "bbox": [0, 30, 80, 80],
                    "type": "image",
                    "language": "other",
                    "legibility": "illegible",
                    "text": "",
                }
            )
            metadata.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in (development, holdout)),
                encoding="utf-8",
            )
            excluded = root / "development.json"
            excluded.write_text(
                json.dumps({"samples": [{"file_name": development["file_name"]}]}),
                encoding="utf-8",
            )

            result = MODULE.prepare(
                metadata,
                root / "holdout",
                sample_count=1,
                allow_structural_regions=True,
                exclude_selection_path=excluded,
            )

            self.assertEqual([item["sample_id"] for item in result["samples"]], ["01"])
            self.assertEqual(result["excluded_selection"]["excluded_file_count"], 1)
            manifest = (root / "holdout" / "ocr_manifest.csv").read_text(encoding="utf-8")
            self.assertIn("../train/images/01.jpg", manifest)


if __name__ == "__main__":
    unittest.main()
