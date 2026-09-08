"""Measure a Tesseract upper bound using human-provided text-line boxes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ocr_image import PREPROCESS_MODES, preprocess_pil_image


TEXT_TYPES = {"handwritten", "printed", "annotation"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(path: Path, parent: Path) -> str:
    return Path(os.path.relpath(path.resolve(), parent.resolve())).as_posix()


def load_jsonl(path: Path) -> dict[str, dict]:
    records = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            records[record["file_name"]] = record
    return records


def sorted_text_regions(record: dict) -> list[dict]:
    return sorted(
        (region for region in record.get("regions") or [] if region.get("type") in TEXT_TYPES),
        key=lambda region: (region["bbox"][1], region["bbox"][0]),
    )


def padded_bbox(bbox: list[int], size: tuple[int, int], padding: int = 8) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width, height = size
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def run_upper_bound(
    selection_path: Path,
    metadata_path: Path,
    base_manifest_path: Path,
    output_dir: Path,
    language: str = "ukr",
    page_segmentation_mode: int = 7,
    preprocessing_mode: str = "grayscale_autocontrast",
    timeout: int = 15,
) -> dict:
    if preprocessing_mode not in PREPROCESS_MODES - {"none"}:
        raise ValueError(f"Unsupported OCR preprocessing mode: {preprocessing_mode}")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    metadata = load_jsonl(metadata_path)
    with base_manifest_path.open(encoding="utf-8-sig", newline="") as source:
        manifest_rows = {row["sample_id"]: row for row in csv.DictReader(source)}

    output_dir.mkdir(parents=True, exist_ok=False)
    report_samples = []
    evaluation_rows = []
    for selected in selection["samples"]:
        sample_id = selected["sample_id"]
        record = metadata[selected["file_name"]]
        base_row = manifest_rows[sample_id]
        image_path = (base_manifest_path.parent / base_row["image_path"]).resolve()
        reference_path = (base_manifest_path.parent / base_row["reference_path"]).resolve()
        raw_path = output_dir / "raw" / f"{sample_id}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        line_records = []
        page_started = time.perf_counter()
        with Image.open(image_path) as page:
            for index, region in enumerate(sorted_text_regions(record), start=1):
                bbox = padded_bbox(region["bbox"], page.size)
                crop = page.crop(bbox)
                processed, preprocessing = preprocess_pil_image(crop, preprocessing_mode)
                crop_path = output_dir / "crops" / sample_id / f"{index:03d}.png"
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                processed.save(crop_path, format="PNG", dpi=(300, 300), optimize=True)
                command = [
                    "tesseract",
                    str(crop_path),
                    "stdout",
                    "-l",
                    language,
                    "--psm",
                    str(page_segmentation_mode),
                ]
                started = time.perf_counter()
                try:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(
                        f"Line OCR timed out for {sample_id} region {index} after {timeout} seconds"
                    ) from exc
                if result.returncode != 0:
                    raise RuntimeError(
                        f"Line OCR failed for {sample_id} region {index}: {result.stderr.strip()}"
                    )
                text = result.stdout.strip()
                lines.append(text)
                line_records.append(
                    {
                        "index": index,
                        "bbox": list(bbox),
                        "crop_sha256": sha256(crop_path),
                        "raw_text": text,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        "preprocessing": preprocessing,
                    }
                )
        raw_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report_samples.append(
            {
                "sample_id": sample_id,
                "image_sha256": sha256(image_path),
                "region_count": len(line_records),
                "elapsed_ms": round((time.perf_counter() - page_started) * 1000, 3),
                "raw_ocr_sha256": sha256(raw_path),
                "lines": line_records,
            }
        )
        evaluation_rows.append(
            {
                "sample_id": sample_id,
                "image_path": relative_path(image_path, output_dir),
                "reference_path": relative_path(reference_path, output_dir),
                "raw_ocr_path": relative_path(raw_path, output_dir),
                "corrected_ocr_path": "",
                "source_url": base_row.get("source_url", ""),
            }
        )

    evaluation_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        evaluation_buffer,
        fieldnames=[
            "sample_id",
            "image_path",
            "reference_path",
            "raw_ocr_path",
            "corrected_ocr_path",
            "source_url",
        ],
    )
    writer.writeheader()
    writer.writerows(evaluation_rows)
    (output_dir / "evaluation_manifest.csv").write_text(
        evaluation_buffer.getvalue(), encoding="utf-8"
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "diagnostic upper bound using human-provided line boxes; not deployable system output",
        "language": language,
        "page_segmentation_mode": page_segmentation_mode,
        "preprocessing_mode": preprocessing_mode,
        "selection_sha256": sha256(selection_path),
        "metadata_sha256": sha256(metadata_path),
        "sample_count": len(report_samples),
        "region_count": sum(sample["region_count"] for sample in report_samples),
        "samples": report_samples,
    }
    (output_dir / "run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--language", default="ukr")
    parser.add_argument("--psm", type=int, default=7)
    parser.add_argument("--preprocess", choices=sorted(PREPROCESS_MODES - {"none"}), default="grayscale_autocontrast")
    parser.add_argument("--timeout", type=int, default=15)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_upper_bound(
        args.selection,
        args.metadata,
        args.manifest,
        args.output_dir,
        language=args.language,
        page_segmentation_mode=args.psm,
        preprocessing_mode=args.preprocess,
        timeout=args.timeout,
    )
    print(f"wrote {args.output_dir} for {report['sample_count']} pages and {report['region_count']} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
