"""Run a frozen OCR manifest with PaddleOCR and record reproducibility evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


REQUIRED_COLUMNS = {"sample_id", "image_path", "raw_ocr_path"}
DEFAULT_DETECTOR = "PP-OCRv5_mobile_det"
DEFAULT_RECOGNIZER = "eslav_PP-OCRv5_mobile_rec"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative_path(path: Path, parent: Path) -> str:
    return Path(os.path.relpath(path.resolve(), parent.resolve())).as_posix()


def resolve_path(manifest_path: Path, value: str, field: str, sample_id: str) -> Path:
    if not value.strip():
        raise ValueError(f"Sample {sample_id} is missing {field}")
    path = Path(value.strip())
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


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


def package_versions() -> dict[str, str]:
    return {
        name: importlib.metadata.version(name)
        for name in ("paddlepaddle", "paddleocr", "paddlex")
    }


def model_artifact_record(model_dir: Path) -> dict | None:
    if not model_dir.is_dir():
        return None
    files = sorted(path for path in model_dir.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    total_bytes = 0
    for path in files:
        relative = path.relative_to(model_dir).as_posix()
        file_hash = sha256_file(path)
        total_bytes += path.stat().st_size
        digest.update(f"{relative}\0{file_hash}\n".encode("utf-8"))
    return {
        "path": str(model_dir.resolve()),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def create_pipeline(detector: str, recognizer: str):
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "PaddleOCR is not installed. Run this script in the isolated PaddleOCR environment."
        ) from exc
    return PaddleOCR(
        text_detection_model_name=detector,
        text_recognition_model_name=recognizer,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def run_batch(
    manifest_path: Path,
    output_path: Path,
    raw_output_dir: Path,
    evaluation_manifest_output: Path | None = None,
    detector: str = DEFAULT_DETECTOR,
    recognizer: str = DEFAULT_RECOGNIZER,
    replace: bool = False,
    pipeline_factory: Callable[[str, str], object] = create_pipeline,
    installed_versions: dict[str, str] | None = None,
    model_root: Path | None = None,
) -> dict:
    if output_path.exists() and not replace:
        raise ValueError(f"Run report already exists; use --replace: {output_path}")
    if evaluation_manifest_output is not None and evaluation_manifest_output.exists() and not replace:
        raise ValueError(
            f"Evaluation manifest already exists; use --replace: {evaluation_manifest_output}"
        )
    rows = read_manifest(manifest_path)
    pending_outputs: list[tuple[Path, bytes]] = []
    samples: list[dict] = []
    evaluation_rows: list[dict] = []
    seen_ids: set[str] = set()

    init_started = time.perf_counter()
    pipeline = pipeline_factory(detector, recognizer)
    initialization_ms = round((time.perf_counter() - init_started) * 1000, 3)

    for row in rows:
        sample_id = row["sample_id"].strip()
        if not sample_id or sample_id in seen_ids:
            raise ValueError(f"Invalid or duplicate sample_id: {sample_id!r}")
        seen_ids.add(sample_id)
        image_path = resolve_path(manifest_path, row["image_path"], "image_path", sample_id)
        raw_path = raw_output_dir.resolve() / f"{sample_id}.txt"
        if not image_path.is_file():
            raise ValueError(f"Sample {sample_id} image does not exist: {image_path}")
        if raw_path.exists() and not replace:
            raise ValueError(f"Raw OCR output already exists; use --replace: {raw_path}")

        started = time.perf_counter()
        results = pipeline.predict(
            input=str(image_path),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        if len(results) != 1:
            raise RuntimeError(f"OCR returned {len(results)} results for image {sample_id}")
        result = results[0]
        lines = [str(value).strip() for value in result.get("rec_texts", []) if str(value).strip()]
        raw_bytes = ("\n".join(lines).strip() + "\n").encode("utf-8")
        scores = [float(value) for value in result.get("rec_scores", [])]
        pending_outputs.append((raw_path, raw_bytes))
        samples.append(
            {
                "sample_id": sample_id,
                "image_path": str(image_path),
                "image_sha256": sha256_file(image_path),
                "raw_ocr_path": str(raw_path),
                "raw_ocr_sha256": sha256_bytes(raw_bytes),
                "raw_characters": len(raw_bytes.decode("utf-8").strip()),
                "detected_line_count": len(lines),
                "mean_model_score": round(statistics.fmean(scores), 6) if scores else None,
                "elapsed_ms": elapsed_ms,
            }
        )
        if evaluation_manifest_output is not None:
            reference_path = resolve_path(
                manifest_path,
                row.get("reference_path", ""),
                "reference_path",
                sample_id,
            )
            evaluation_rows.append(
                {
                    "sample_id": sample_id,
                    "image_path": relative_path(image_path, evaluation_manifest_output.parent),
                    "reference_path": relative_path(reference_path, evaluation_manifest_output.parent),
                    "raw_ocr_path": relative_path(raw_path, evaluation_manifest_output.parent),
                    "corrected_ocr_path": "",
                    "source_url": row.get("source_url", "").strip(),
                }
            )

    for raw_path, content in pending_outputs:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(content)

    root = (model_root or Path.home() / ".paddlex" / "official_models").resolve()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "PaddleOCR",
        "package_versions": installed_versions or package_versions(),
        "detector": detector,
        "recognizer": recognizer,
        "initialization_ms": initialization_ms,
        "model_artifacts": {
            detector: model_artifact_record(root / detector),
            recognizer: model_artifact_record(root / recognizer),
        },
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "sample_count": len(samples),
        "total_prediction_ms": round(sum(item["elapsed_ms"] for item in samples), 3),
        "samples": samples,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if evaluation_manifest_output is not None:
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
        writer.writerows(evaluation_rows)
        evaluation_manifest_output.parent.mkdir(parents=True, exist_ok=True)
        evaluation_manifest_output.write_text(manifest_buffer.getvalue(), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output-dir", type=Path, required=True)
    parser.add_argument("--evaluation-manifest-output", type=Path)
    parser.add_argument("--detector", default=DEFAULT_DETECTOR)
    parser.add_argument("--recognizer", default=DEFAULT_RECOGNIZER)
    parser.add_argument("--replace", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_batch(
        manifest_path=args.manifest,
        output_path=args.output,
        raw_output_dir=args.raw_output_dir,
        evaluation_manifest_output=args.evaluation_manifest_output,
        detector=args.detector,
        recognizer=args.recognizer,
        replace=args.replace,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
