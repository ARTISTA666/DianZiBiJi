"""Run a frozen OCR manifest with HTRflow and preserve reproducibility evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


SEGMENTATION_MODEL = "Riksarkivet/yolov9-lines-within-regions-1"
REGION_MODEL = "Riksarkivet/yolov9-regions-1"
RECOGNITION_MODEL = "microsoft/trocr-base-handwritten"
REQUIRED_COLUMNS = {"sample_id", "image_path", "reference_path"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(manifest_path: Path, value: str, field: str, sample_id: str) -> Path:
    if not value.strip():
        raise ValueError(f"Sample {sample_id} is missing {field}")
    path = Path(value.strip())
    if not path.is_absolute():
        path = manifest_path.parent / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"Sample {sample_id} {field} does not exist: {path}")
    return path


def relative_path(path: Path, parent: Path) -> str:
    return Path(os.path.relpath(path.resolve(), parent.resolve())).as_posix()


def read_manifest(manifest_path: Path) -> list[dict]:
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        if not REQUIRED_COLUMNS.issubset(columns):
            missing = ", ".join(sorted(REQUIRED_COLUMNS - columns))
            raise ValueError(f"Manifest is missing columns: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError("Manifest has no samples")
    return rows


def package_versions() -> dict[str, str | None]:
    result = {}
    for package in ("htrflow", "transformers", "torch", "ultralytics"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def cached_model_revision(model_id: str) -> str | None:
    cache_root = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    model_directory = "models--" + model_id.replace("/", "--")
    ref_path = cache_root / model_directory / "refs" / "main"
    return ref_path.read_text(encoding="utf-8").strip() if ref_path.is_file() else None


def segmentation_step(model: str, device: str) -> dict:
    return {
        "step": "Segmentation",
        "settings": {
            "model": "YOLO",
            "model_settings": {"model": model, "device": device},
            "generation_settings": {"batch_size": 1},
        },
    }


def build_pipeline(
    raw_dir: Path,
    metadata_dir: Path,
    device: str,
    layout: str,
    recognition_model: str = RECOGNITION_MODEL,
    recognition_batch_size: int = 8,
) -> dict:
    steps = []
    if layout == "nested":
        steps.append(segmentation_step(REGION_MODEL, device))
    steps.extend(
        [
            segmentation_step(SEGMENTATION_MODEL, device),
            {
                "step": "TextRecognition",
                "settings": {
                    "model": "TrOCR",
                    "model_settings": {"model": recognition_model, "device": device},
                    "generation_settings": {
                        "batch_size": recognition_batch_size,
                        "num_beams": 1,
                    },
                },
            },
            {"step": "ReadingOrderMarginalia" if layout == "nested" else "OrderLines"},
            {"step": "Export", "settings": {"format": "txt", "dest": str(raw_dir)}},
            {"step": "Export", "settings": {"format": "json", "dest": str(metadata_dir)}},
        ]
    )
    return {"steps": steps}


def unique_output(directory: Path, sample_id: str, suffix: str) -> Path:
    matches = list(directory.rglob(f"{sample_id}{suffix}"))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one HTRflow {suffix} output for {sample_id}, found {len(matches)}"
        )
    return matches[0]


def split_spread(image_path: Path, output_dir: Path, sample_id: str) -> tuple[list[Path], dict]:
    from PIL import Image

    with Image.open(image_path) as image:
        if image.width <= image.height:
            raise ValueError(f"Spread layout requires a landscape image: {image_path}")
        source_size = [image.width, image.height]
        split_x = image.width // 2
        parts = [
            ("left", image.crop((0, 0, split_x, image.height))),
            ("right", image.crop((split_x, 0, image.width, image.height))),
        ]
        paths = []
        for label, part in parts:
            path = output_dir / f"{sample_id}__{label}.png"
            part.save(path, format="PNG", optimize=True)
            paths.append(path)
    return paths, {
        "method": "vertical_center_split",
        "source_size": source_size,
        "split_x": split_x,
        "parts": [
            {"path": str(path), "sha256": sha256_file(path)}
            for path in paths
        ],
    }


def run_batch(
    manifest_path: Path,
    output_dir: Path,
    htrflow_executable: str = "htrflow",
    device: str = "cpu",
    layout: str = "simple",
    recognition_model: str = RECOGNITION_MODEL,
    recognition_batch_size: int = 8,
    replace: bool = False,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict:
    if layout not in {"simple", "nested", "spread"}:
        raise ValueError(f"Unsupported layout: {layout}")
    if recognition_batch_size < 1:
        raise ValueError("recognition_batch_size must be positive")
    manifest_path = manifest_path.resolve()
    output_dir = output_dir.resolve()
    report_path = output_dir / "run.json"
    evaluation_manifest_path = output_dir / "evaluation.csv"
    if report_path.exists() and not replace:
        raise ValueError(f"Run report already exists; use --replace: {report_path}")

    rows = read_manifest(manifest_path)
    samples = []
    seen_ids: set[str] = set()
    for row in rows:
        sample_id = row["sample_id"].strip()
        if not sample_id or sample_id in seen_ids:
            raise ValueError(f"Invalid or duplicate sample_id: {sample_id!r}")
        seen_ids.add(sample_id)
        image_path = resolve_path(manifest_path, row["image_path"], "image_path", sample_id)
        reference_path = resolve_path(manifest_path, row["reference_path"], "reference_path", sample_id)
        samples.append((row, sample_id, image_path, reference_path))

    raw_dir = output_dir / "raw"
    metadata_dir = output_dir / "metadata"
    combined_dir = output_dir / "combined"
    split_input_dir = output_dir / "split-inputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    combined_dir.mkdir(parents=True, exist_ok=True)
    split_input_dir.mkdir(parents=True, exist_ok=True)
    existing = [
        path
        for _, sample_id, _, _ in samples
        for directory, suffix in (
            (raw_dir, ".txt"),
            (metadata_dir, ".json"),
            (combined_dir, ".txt"),
            (split_input_dir, ".png"),
        )
        for path in directory.rglob(f"{sample_id}*{suffix}")
    ]
    if existing and not replace:
        raise ValueError(f"HTRflow output already exists; use --replace: {existing[0]}")
    if replace:
        for path in existing:
            path.unlink()

    input_groups: dict[str, list[Path]] = {}
    preprocessing: dict[str, dict | None] = {}
    for _, sample_id, image_path, _ in samples:
        if layout == "spread":
            input_groups[sample_id], preprocessing[sample_id] = split_spread(
                image_path, split_input_dir, sample_id
            )
        else:
            input_groups[sample_id] = [image_path]
            preprocessing[sample_id] = None
    input_paths = [path for _, sample_id, _, _ in samples for path in input_groups[sample_id]]

    pipeline_path = output_dir / "pipeline.json"
    inputs_path = output_dir / "inputs.txt"
    log_path = output_dir / "htrflow.log"
    pipeline_path.write_text(
        json.dumps(
            build_pipeline(
                raw_dir,
                metadata_dir,
                device,
                layout,
                recognition_model,
                recognition_batch_size,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    inputs_path.write_text("".join(f"{image_path}\n" for image_path in input_paths), encoding="utf-8")
    command = [
        htrflow_executable,
        "pipeline",
        str(pipeline_path),
        "--inputs-file",
        str(inputs_path),
        "--label",
        f"htrflow-{manifest_path.stem}",
        "--logfile",
        str(log_path),
        "--loglevel",
        "info",
        "--batch-output",
        str(min(len(input_paths), 10)),
    ]
    started = time.perf_counter()
    completed = command_runner(command, check=False)
    elapsed_seconds = round(time.perf_counter() - started, 3)
    if completed.returncode != 0:
        raise RuntimeError(f"HTRflow failed with exit code {completed.returncode}; see {log_path}")

    evaluation_rows = []
    sample_reports = []
    for row, sample_id, image_path, reference_path in samples:
        part_ids = [path.stem for path in input_groups[sample_id]]
        raw_parts = [unique_output(raw_dir, part_id, ".txt") for part_id in part_ids]
        metadata_paths = [
            unique_output(metadata_dir, part_id, ".json") for part_id in part_ids
        ]
        if layout == "spread":
            raw_path = combined_dir / f"{sample_id}.txt"
            raw_path.write_text(
                "\n".join(
                    path.read_text(encoding="utf-8-sig").strip() for path in raw_parts
                ).strip()
                + "\n",
                encoding="utf-8",
            )
        else:
            raw_path = raw_parts[0]
        sample_reports.append(
            {
                "sample_id": sample_id,
                "image_path": str(image_path),
                "image_sha256": sha256_file(image_path),
                "reference_path": str(reference_path),
                "reference_sha256": sha256_file(reference_path),
                "raw_ocr_path": str(raw_path),
                "raw_ocr_sha256": sha256_file(raw_path),
                "metadata": [
                    {"path": str(path), "sha256": sha256_file(path)}
                    for path in metadata_paths
                ],
                "preprocessing": preprocessing[sample_id],
                "raw_characters": len(raw_path.read_text(encoding="utf-8-sig").strip()),
            }
        )
        evaluation_rows.append(
            {
                "sample_id": sample_id,
                "image_path": relative_path(image_path, output_dir),
                "reference_path": relative_path(reference_path, output_dir),
                "raw_ocr_path": relative_path(raw_path, output_dir),
                "corrected_ocr_path": "",
                "source_url": row.get("source_url", "").strip(),
            }
        )

    manifest_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(manifest_buffer, fieldnames=list(evaluation_rows[0]))
    writer.writeheader()
    writer.writerows(evaluation_rows)
    evaluation_manifest_path.write_text(manifest_buffer.getvalue(), encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "HTRflow",
        "package_versions": package_versions(),
        "device": device,
        "layout": layout,
        "models": {
            "region": (
                {"id": REGION_MODEL, "revision": cached_model_revision(REGION_MODEL)}
                if layout == "nested"
                else None
            ),
            "segmentation": {
                "id": SEGMENTATION_MODEL,
                "revision": cached_model_revision(SEGMENTATION_MODEL),
            },
            "recognition": {
                "id": recognition_model,
                "revision": cached_model_revision(recognition_model),
                "batch_size": recognition_batch_size,
            },
        },
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "pipeline_path": str(pipeline_path),
        "pipeline_sha256": sha256_file(pipeline_path),
        "command": command,
        "elapsed_seconds": elapsed_seconds,
        "sample_count": len(sample_reports),
        "samples": sample_reports,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--htrflow", default="htrflow")
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="cpu")
    parser.add_argument("--layout", choices=("simple", "nested", "spread"), default="simple")
    parser.add_argument("--recognition-model", default=RECOGNITION_MODEL)
    parser.add_argument("--recognition-batch-size", type=int, default=8)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_batch(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        htrflow_executable=args.htrflow,
        device=args.device,
        layout=args.layout,
        recognition_model=args.recognition_model,
        recognition_batch_size=args.recognition_batch_size,
        replace=args.replace,
    )
    print(f"wrote {args.output_dir / 'run.json'} for {report['sample_count']} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
