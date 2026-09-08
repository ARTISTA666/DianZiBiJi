from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_ocr_region_upper_bound.py"
SPEC = importlib.util.spec_from_file_location("run_ocr_region_upper_bound", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RegionUpperBoundTests(unittest.TestCase):
    def test_uses_sorted_text_regions_and_writes_page_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "page.jpg"
            image = Image.new("RGB", (200, 120), "white")
            draw = ImageDraw.Draw(image)
            draw.line((20, 30, 180, 30), fill="black", width=3)
            draw.line((20, 80, 180, 80), fill="black", width=3)
            image.save(image_path)
            (root / "reference.txt").write_text("first\nsecond\n", encoding="utf-8")
            selection = root / "selection.json"
            selection.write_text(
                json.dumps(
                    {
                        "samples": [
                            {"sample_id": "A", "file_name": "images/page.jpg"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            metadata = root / "metadata.jsonl"
            metadata.write_text(
                json.dumps(
                    {
                        "file_name": "images/page.jpg",
                        "regions": [
                            {"bbox": [20, 70, 180, 90], "type": "handwritten", "text": "second"},
                            {"bbox": [20, 20, 180, 40], "type": "handwritten", "text": "first"},
                            {"bbox": [0, 0, 10, 10], "type": "image", "text": ""},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            manifest = root / "manifest.csv"
            manifest.write_text(
                "sample_id,image_path,reference_path,raw_ocr_path,source_url\n"
                "A,page.jpg,reference.txt,unused.txt,https://example.test/A\n",
                encoding="utf-8",
            )

            def fake_run(command, **_kwargs):
                text = "first" if command[1].endswith("001.png") else "second"
                return subprocess.CompletedProcess(command, 0, stdout=text + "\n", stderr="")

            output = root / "output"
            with patch.object(MODULE.subprocess, "run", side_effect=fake_run):
                report = MODULE.run_upper_bound(selection, metadata, manifest, output)

            self.assertEqual(report["region_count"], 2)
            self.assertEqual((output / "raw" / "A.txt").read_text(encoding="utf-8"), "first\nsecond\n")
            self.assertTrue((output / "evaluation_manifest.csv").is_file())


if __name__ == "__main__":
    unittest.main()
