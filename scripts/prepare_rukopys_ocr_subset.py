"""Freeze a deterministic RUKOPYS subset and its human reference text."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path


DATASET_URL = "https://huggingface.co/datasets/UkrainianCatholicUniversity/rukopys"
LICENSE = "CC BY-NC-SA 4.0"
TEXT_TYPES = {"handwritten", "printed", "annotation"}
STRUCTURAL_TYPES = {"image", "graph"}
EXCLUDED_MARKERS = ("~~", "[illegible]")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_records(metadata_path: Path) -> list[dict]:
    records = []
    with metadata_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on metadata line {line_number}") from exc
    return records


def reference_regions(record: dict) -> list[dict]:
    return sorted(
        (region for region in (record.get("regions") or []) if region.get("type") in TEXT_TYPES),
        key=lambda region: (
            region.get("bbox", [0, 0, 0, 0])[1],
            region.get("bbox", [0, 0, 0, 0])[0],
        ),
    )


def reference_text(record: dict) -> str:
    return "\n".join(region["text"].strip() for region in reference_regions(record)) + "\n"


def is_eligible(record: dict, minimum_characters: int, allowed_types: set[str] | None = None) -> bool:
    if record.get("source") != "university" or record.get("annotation_source") != "annotator":
        return False
    regions = record.get("regions") or []
    allowed = allowed_types or TEXT_TYPES
    if not regions or any(region.get("type") not in allowed for region in regions):
        return False
    text_regions = [region for region in regions if region.get("type") in TEXT_TYPES]
    if not text_regions or any(region.get("legibility") != "legible" for region in text_regions):
        return False
    texts = [str(region.get("text", "")).strip() for region in text_regions]
    if any(not text or any(marker in text for marker in EXCLUDED_MARKERS) for text in texts):
        return False
    return len(" ".join(texts)) >= minimum_characters


def evenly_spaced(records: list[dict], sample_count: int) -> list[dict]:
    if sample_count < 1:
        raise ValueError("sample_count must be positive")
    if len(records) < sample_count:
        raise ValueError(f"Only {len(records)} eligible records; {sample_count} requested")
    if sample_count == 1:
        return [records[0]]
    denominator = sample_count - 1
    last_index = len(records) - 1
    indexes = [
        (position * last_index + denominator // 2) // denominator
        for position in range(sample_count)
    ]
    return [records[index] for index in indexes]


def frozen_write(path: Path, content: bytes, replace: bool) -> None:
    if path.exists() and path.read_bytes() != content and not replace:
        raise ValueError(f"Frozen file differs; use --replace to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def prepare(
    metadata_path: Path,
    output_dir: Path,
    sample_count: int = 10,
    minimum_characters: int = 350,
    allow_structural_regions: bool = False,
    exclude_selection_path: Path | None = None,
    replace: bool = False,
) -> dict:
    records = load_records(metadata_path)
    allowed_types = TEXT_TYPES | STRUCTURAL_TYPES if allow_structural_regions else TEXT_TYPES
    excluded_file_names: set[str] = set()
    if exclude_selection_path is not None:
        excluded_selection = json.loads(exclude_selection_path.read_text(encoding="utf-8"))
        excluded_file_names = {sample["file_name"] for sample in excluded_selection.get("samples", [])}
    candidates = sorted(
        (
            record
            for record in records
            if record.get("file_name") not in excluded_file_names
            and is_eligible(record, minimum_characters, allowed_types)
        ),
        key=lambda record: record["file_name"],
    )
    selected = evenly_spaced(candidates, sample_count)
    dataset_root = metadata_path.resolve().parent.parent

    samples = []
    manifest_rows = []
    for record in selected:
        sample_id = Path(record["file_name"]).stem
        reference = reference_text(record).encode("utf-8")
        reference_path = output_dir / "references" / f"{sample_id}.txt"
        frozen_write(reference_path, reference, replace)
        source_url = f"{DATASET_URL}/blob/main/train/{record['file_name']}"
        samples.append(
            {
                "sample_id": sample_id,
                "file_name": record["file_name"],
                "image_width": record["image_width"],
                "image_height": record["image_height"],
                "reference_region_count": len(record["regions"]),
                "reference_characters": len(reference.decode("utf-8").strip()),
                "reference_sha256": sha256_bytes(reference),
                "source_url": source_url,
            }
        )
        manifest_rows.append(
            {
                "sample_id": sample_id,
                "image_path": Path(
                    os.path.relpath(dataset_root / "train" / record["file_name"], output_dir.resolve())
                ).as_posix(),
                "reference_path": f"references/{sample_id}.txt",
                "raw_ocr_path": f"raw_ocr/{sample_id}.txt",
                "corrected_ocr_path": "",
                "source_url": source_url,
            }
        )

    selection = {
        "dataset": "RUKOPYS",
        "dataset_url": DATASET_URL,
        "license": LICENSE,
        "metadata_path": str(metadata_path),
        "metadata_sha256": sha256_file(metadata_path),
        "selection_criteria": {
            "source": "university",
            "annotation_source": "annotator",
            "allowed_region_types": sorted(allowed_types),
            "all_regions_legible": True,
            "excluded_markers": list(EXCLUDED_MARKERS),
            "minimum_reference_characters": minimum_characters,
        },
        "selection_method": "Sort eligible file names, then take evenly spaced positions including both ends.",
        "candidate_count": len(candidates),
        "sample_count": len(samples),
        "samples": samples,
    }
    if exclude_selection_path is not None:
        selection["excluded_selection"] = {
            "path": str(exclude_selection_path),
            "sha256": sha256_file(exclude_selection_path),
            "excluded_file_count": len(excluded_file_names),
        }
    selection_bytes = (json.dumps(selection, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    frozen_write(output_dir / "selection.json", selection_bytes, replace)

    manifest_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        manifest_buffer,
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
    writer.writerows(manifest_rows)
    frozen_write(output_dir / "ocr_manifest.csv", manifest_buffer.getvalue().encode("utf-8"), replace)
    frozen_write(
        output_dir / "download_paths.txt",
        ("\n".join(f"train/{sample['file_name']}" for sample in samples) + "\n").encode("utf-8"),
        replace,
    )
    return selection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-count", type=int, default=10)
    parser.add_argument("--minimum-characters", type=int, default=350)
    parser.add_argument("--allow-structural-regions", action="store_true")
    parser.add_argument("--exclude-selection", type=Path)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selection = prepare(
        args.metadata,
        args.output_dir,
        sample_count=args.sample_count,
        minimum_characters=args.minimum_characters,
        allow_structural_regions=args.allow_structural_regions,
        exclude_selection_path=args.exclude_selection,
        replace=args.replace,
    )
    print(f"frozen {selection['sample_count']} of {selection['candidate_count']} eligible pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
