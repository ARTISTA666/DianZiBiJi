"""Evaluate raw and human-corrected OCR text against frozen reference text."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_COLUMNS = {"sample_id", "reference_path", "raw_ocr_path"}
NUMBER_PATTERN = re.compile(r"[+-]?(?:\d+(?:[.,]\d+)?|\.\d+)(?:[eE][+-]?\d+)?%?")


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace without changing letter case or punctuation."""
    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", normalized).strip()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", normalize_text(text))


def levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def numeric_metrics(reference: str, prediction: str) -> dict:
    reference_tokens = NUMBER_PATTERN.findall(reference)
    prediction_tokens = NUMBER_PATTERN.findall(prediction)
    overlap = sum((Counter(reference_tokens) & Counter(prediction_tokens)).values())
    precision = overlap / len(prediction_tokens) if prediction_tokens else (1.0 if not reference_tokens else 0.0)
    recall = overlap / len(reference_tokens) if reference_tokens else (1.0 if not prediction_tokens else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "reference_count": len(reference_tokens),
        "prediction_count": len(prediction_tokens),
        "matched_count": overlap,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "exact_sequence_match": reference_tokens == prediction_tokens,
    }


def score_text(reference: str, prediction: str) -> dict:
    normalized_reference = normalize_text(reference)
    normalized_prediction = normalize_text(prediction)
    if not normalized_reference:
        raise ValueError("Reference text is empty after normalization.")

    distance = levenshtein_distance(normalized_reference, normalized_prediction)
    compact_reference = compact_text(reference)
    compact_prediction = compact_text(prediction)
    compact_distance = levenshtein_distance(compact_reference, compact_prediction)
    return {
        "reference_characters": len(normalized_reference),
        "prediction_characters": len(normalized_prediction),
        "edit_distance": distance,
        "character_error_rate": round(distance / len(normalized_reference), 6),
        "compact_reference_characters": len(compact_reference),
        "compact_edit_distance": compact_distance,
        "compact_character_error_rate": round(compact_distance / len(compact_reference), 6),
        "numeric_tokens": numeric_metrics(normalized_reference, normalized_prediction),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_input(manifest_path: Path, value: str, field: str, sample_id: str) -> Path:
    if not value.strip():
        raise ValueError(f"Sample {sample_id} is missing {field}.")
    path = Path(value.strip())
    if not path.is_absolute():
        path = manifest_path.parent / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"Sample {sample_id} file does not exist: {path}")
    return path


def evaluate_manifest(manifest_path: Path) -> dict:
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        if not REQUIRED_COLUMNS.issubset(columns):
            missing = ", ".join(sorted(REQUIRED_COLUMNS - columns))
            raise ValueError(f"Manifest is missing columns: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError("Manifest has no samples.")

    samples: list[dict] = []
    seen_ids: set[str] = set()
    for row in rows:
        sample_id = row["sample_id"].strip()
        if not sample_id:
            raise ValueError("Manifest contains an empty sample_id.")
        if sample_id in seen_ids:
            raise ValueError(f"Duplicate sample_id: {sample_id}")
        seen_ids.add(sample_id)

        reference_path = resolve_input(manifest_path, row["reference_path"], "reference_path", sample_id)
        raw_path = resolve_input(manifest_path, row["raw_ocr_path"], "raw_ocr_path", sample_id)
        reference = reference_path.read_text(encoding="utf-8-sig")
        raw_text = raw_path.read_text(encoding="utf-8-sig")
        sample = {
            "sample_id": sample_id,
            "source_url": row.get("source_url", "").strip(),
            "reference": {"path": str(reference_path), "sha256": sha256(reference_path)},
            "raw_ocr": {"path": str(raw_path), "sha256": sha256(raw_path), **score_text(reference, raw_text)},
            "corrected_ocr": None,
        }
        corrected_value = row.get("corrected_ocr_path", "").strip()
        if corrected_value:
            corrected_path = resolve_input(manifest_path, corrected_value, "corrected_ocr_path", sample_id)
            corrected_text = corrected_path.read_text(encoding="utf-8-sig")
            sample["corrected_ocr"] = {
                "path": str(corrected_path),
                "sha256": sha256(corrected_path),
                **score_text(reference, corrected_text),
            }
        samples.append(sample)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path.resolve()),
        "metric_definition": {
            "character_error_rate": "Levenshtein edit distance divided by reference character count; lower is better.",
            "compact_character_error_rate": "The same formula after removing whitespace; lower is better.",
            "numeric_f1": "Exact numeric-token overlap F1; higher is better.",
            "normalization": "Unicode NFKC and collapsed whitespace; case and punctuation are preserved.",
        },
        "sample_count": len(samples),
        "summary": summarize(samples),
        "samples": samples,
    }


def summarize(samples: list[dict]) -> dict:
    raw_reference_total = sum(item["raw_ocr"]["reference_characters"] for item in samples)
    raw_distance_total = sum(item["raw_ocr"]["edit_distance"] for item in samples)
    raw_compact_reference_total = sum(
        item["raw_ocr"]["compact_reference_characters"] for item in samples
    )
    raw_compact_distance_total = sum(item["raw_ocr"]["compact_edit_distance"] for item in samples)
    corrected_samples = [item for item in samples if item["corrected_ocr"] is not None]
    summary = {
        "raw": {
            "sample_count": len(samples),
            "micro_character_error_rate": round(raw_distance_total / raw_reference_total, 6),
            "macro_character_error_rate": round(
                statistics.fmean(item["raw_ocr"]["character_error_rate"] for item in samples), 6
            ),
            "micro_compact_character_error_rate": round(
                raw_compact_distance_total / raw_compact_reference_total, 6
            ),
            "macro_compact_character_error_rate": round(
                statistics.fmean(
                    item["raw_ocr"]["compact_character_error_rate"] for item in samples
                ),
                6,
            ),
            "numeric_tokens": aggregate_numeric_tokens(samples, "raw_ocr"),
        },
        "corrected": None,
        "paired_change": None,
    }
    if corrected_samples:
        corrected_reference_total = sum(item["corrected_ocr"]["reference_characters"] for item in corrected_samples)
        corrected_distance_total = sum(item["corrected_ocr"]["edit_distance"] for item in corrected_samples)
        corrected_compact_reference_total = sum(
            item["corrected_ocr"]["compact_reference_characters"] for item in corrected_samples
        )
        corrected_compact_distance_total = sum(
            item["corrected_ocr"]["compact_edit_distance"] for item in corrected_samples
        )
        paired_raw_distance = sum(item["raw_ocr"]["edit_distance"] for item in corrected_samples)
        paired_raw_reference = sum(item["raw_ocr"]["reference_characters"] for item in corrected_samples)
        paired_raw_compact_distance = sum(
            item["raw_ocr"]["compact_edit_distance"] for item in corrected_samples
        )
        paired_raw_compact_reference = sum(
            item["raw_ocr"]["compact_reference_characters"] for item in corrected_samples
        )
        paired_raw_cer = paired_raw_distance / paired_raw_reference
        paired_raw_compact_cer = paired_raw_compact_distance / paired_raw_compact_reference
        corrected_cer = corrected_distance_total / corrected_reference_total
        corrected_compact_cer = corrected_compact_distance_total / corrected_compact_reference_total
        summary["corrected"] = {
            "sample_count": len(corrected_samples),
            "micro_character_error_rate": round(corrected_cer, 6),
            "macro_character_error_rate": round(
                statistics.fmean(item["corrected_ocr"]["character_error_rate"] for item in corrected_samples), 6
            ),
            "micro_compact_character_error_rate": round(corrected_compact_cer, 6),
            "macro_compact_character_error_rate": round(
                statistics.fmean(
                    item["corrected_ocr"]["compact_character_error_rate"]
                    for item in corrected_samples
                ),
                6,
            ),
            "numeric_tokens": aggregate_numeric_tokens(corrected_samples, "corrected_ocr"),
        }
        summary["paired_change"] = {
            "sample_count": len(corrected_samples),
            "raw_micro_character_error_rate": round(paired_raw_cer, 6),
            "corrected_micro_character_error_rate": round(corrected_cer, 6),
            "error_rate_reduction_percentage_points": round((paired_raw_cer - corrected_cer) * 100, 4),
            "raw_micro_compact_character_error_rate": round(paired_raw_compact_cer, 6),
            "corrected_micro_compact_character_error_rate": round(corrected_compact_cer, 6),
        }
    return summary


def aggregate_numeric_tokens(samples: list[dict], field: str) -> dict:
    metrics = [item[field]["numeric_tokens"] for item in samples]
    reference_count = sum(item["reference_count"] for item in metrics)
    prediction_count = sum(item["prediction_count"] for item in metrics)
    matched_count = sum(item["matched_count"] for item in metrics)
    precision = matched_count / prediction_count if prediction_count else (1.0 if not reference_count else 0.0)
    recall = matched_count / reference_count if reference_count else (1.0 if not prediction_count else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "reference_count": reference_count,
        "prediction_count": prediction_count,
        "matched_count": matched_count,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "exact_sequence_sample_count": sum(item["exact_sequence_match"] for item in metrics),
    }


def self_test() -> None:
    assert levenshtein_distance("kitten", "sitting") == 3
    assert normalize_text("Ａ\r\n  B") == "A B"
    score = score_text("温度 58 C", "温度 59 C")
    assert score["edit_distance"] == 1
    assert score["numeric_tokens"]["matched_count"] == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="CSV manifest containing OCR text paths.")
    parser.add_argument("-o", "--output", type=Path, help="Write the JSON report to this path.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in checks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return 0
    if not args.manifest:
        raise SystemExit("Provide --manifest, or use --self-test.")
    report = evaluate_manifest(args.manifest)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
