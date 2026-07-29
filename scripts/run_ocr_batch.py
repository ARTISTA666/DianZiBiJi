"""Run a frozen OCR manifest with Tesseract and record reproducibility evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ocr_image import PREPROCESS_MODES, preprocess_image


REQUIRED_COLUMNS = {"sample_id", "image_path", "raw_ocr_path"}
TESSERACT_CONFIG_PATTERN = re.compile(r"^[A-Za-z0-9_]+=[^\r\n]+$")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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


def available_languages(executable: str, timeout: int) -> set[str]:
    result = subprocess.run(
        [executable, "--list-langs"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to list Tesseract languages")
    return {line.strip() for line in result.stdout.splitlines()[1:] if line.strip()}


def tesseract_version(executable: str, timeout: int) -> str:
    result = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to read Tesseract version")
    return result.stdout.splitlines()[0].strip()


def validate_tesseract_configs(configs: list[str] | None) -> list[str]:
    normalized = [item.strip() for item in (configs or []) if item.strip()]
    invalid = [item for item in normalized if not TESSERACT_CONFIG_PATTERN.fullmatch(item)]
    if invalid:
        raise ValueError(f"Invalid Tesseract config: {invalid[0]}")
    return normalized


def relative_path(path: Path, parent: Path) -> str:
    return Path(os.path.relpath(path.resolve(), parent.resolve())).as_posix()


def run_batch(
    manifest_path: Path,
    output_path: Path,
    executable: str = "tesseract",
    language: str = "chi_sim+eng",
    page_segmentation_mode: int = 3,
    dpi: int | None = None,
    tesseract_configs: list[str] | None = None,
    preprocessing_mode: str = "none",
    raw_output_dir: Path | None = None,
    processed_output_dir: Path | None = None,
    evaluation_manifest_output: Path | None = None,
    timeout: int = 120,
    replace: bool = False,
) -> dict:
    if not 0 <= page_segmentation_mode <= 13:
        raise ValueError("page_segmentation_mode must be between 0 and 13")
    if dpi is not None and dpi < 1:
        raise ValueError("dpi must be positive")
    if preprocessing_mode not in PREPROCESS_MODES:
        raise ValueError(f"Unsupported OCR preprocessing mode: {preprocessing_mode}")
    configs = validate_tesseract_configs(tesseract_configs)
    if output_path.exists() and not replace:
        raise ValueError(f"Run report already exists; use --replace: {output_path}")
    if evaluation_manifest_output is not None and evaluation_manifest_output.exists() and not replace:
        raise ValueError(
            f"Evaluation manifest already exists; use --replace: {evaluation_manifest_output}"
        )
    rows = read_manifest(manifest_path)
    requested_languages = [item.strip() for item in language.replace(",", "+").split("+") if item.strip()]
    if not requested_languages:
        raise ValueError("language must not be empty")
    missing = sorted(set(requested_languages) - available_languages(executable, timeout))
    if missing:
        raise ValueError(f"Tesseract language data is missing: {', '.join(missing)}")

    pending_outputs: list[tuple[Path, bytes]] = []
    samples = []
    evaluation_rows = []
    seen_ids: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="ocr-preprocessed-") as temp_directory:
        for row in rows:
            sample_id = row["sample_id"].strip()
            if not sample_id or sample_id in seen_ids:
                raise ValueError(f"Invalid or duplicate sample_id: {sample_id!r}")
            seen_ids.add(sample_id)
            image_path = resolve_path(manifest_path, row["image_path"], "image_path", sample_id)
            raw_path = (
                raw_output_dir.resolve() / f"{sample_id}.txt"
                if raw_output_dir is not None
                else resolve_path(manifest_path, row["raw_ocr_path"], "raw_ocr_path", sample_id)
            )
            if not image_path.is_file():
                raise ValueError(f"Sample {sample_id} image does not exist: {image_path}")
            if raw_path.exists() and not replace:
                raise ValueError(f"Raw OCR output already exists; use --replace: {raw_path}")

            ocr_image_path = image_path
            preprocessing = None
            if preprocessing_mode != "none":
                ocr_image_path = (
                    processed_output_dir.resolve() / f"{sample_id}.png"
                    if processed_output_dir is not None
                    else Path(temp_directory) / f"{sample_id}.png"
                )
                preprocessing = preprocess_image(image_path, ocr_image_path, preprocessing_mode)

            command = [
                executable,
                str(ocr_image_path),
                "stdout",
                "-l",
                "+".join(requested_languages),
                "--psm",
                str(page_segmentation_mode),
            ]
            if dpi is not None:
                command.extend(["--dpi", str(dpi)])
            for config in configs:
                command.extend(["-c", config])
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
                raise RuntimeError(f"OCR timed out for {sample_id} after {timeout} seconds") from exc
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            if result.returncode != 0:
                message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
                raise RuntimeError(f"OCR failed for {sample_id}: {message}")
            raw_bytes = result.stdout.strip().encode("utf-8") + b"\n"
            pending_outputs.append((raw_path, raw_bytes))
            samples.append(
                {
                    "sample_id": sample_id,
                    "image_path": str(image_path),
                    "image_sha256": sha256_file(image_path),
                    "processed_image_path": str(ocr_image_path) if preprocessing is not None else None,
                    "processed_image_sha256": sha256_file(ocr_image_path) if preprocessing is not None else None,
                    "preprocessing": preprocessing,
                    "raw_ocr_path": str(raw_path),
                    "raw_ocr_sha256": sha256_bytes(raw_bytes),
                    "raw_characters": len(result.stdout.strip()),
                    "elapsed_ms": elapsed_ms,
                    "stderr": result.stderr.strip(),
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

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": tesseract_version(executable, timeout),
        "language": "+".join(requested_languages),
        "page_segmentation_mode": page_segmentation_mode,
        "dpi": dpi,
        "tesseract_configs": configs,
        "preprocessing_mode": preprocessing_mode,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "sample_count": len(samples),
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tesseract", default="tesseract")
    parser.add_argument("--language", default="chi_sim+eng")
    parser.add_argument("--psm", type=int, default=3)
    parser.add_argument("--dpi", type=int)
    parser.add_argument("--config", action="append", default=[])
    parser.add_argument("--preprocess", choices=sorted(PREPROCESS_MODES), default="none")
    parser.add_argument("--raw-output-dir", type=Path)
    parser.add_argument("--processed-output-dir", type=Path)
    parser.add_argument("--evaluation-manifest-output", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_batch(
        args.manifest,
        args.output,
        executable=args.tesseract,
        language=args.language,
        page_segmentation_mode=args.psm,
        dpi=args.dpi,
        tesseract_configs=args.config,
        preprocessing_mode=args.preprocess,
        raw_output_dir=args.raw_output_dir,
        processed_output_dir=args.processed_output_dir,
        evaluation_manifest_output=args.evaluation_manifest_output,
        timeout=args.timeout,
        replace=args.replace,
    )
    print(f"wrote {args.output} for {report['sample_count']} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
