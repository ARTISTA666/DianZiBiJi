"""Prepare a frozen OCR benchmark from Joseph Henry's real experiment notebook."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import random
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


ASSET_NUMBERS = range(6592, 6787)
ASSET_PREFIX = "SIA-SIA2012-"
COLLECTION_URL = "https://siarchives.si.edu/collections/siris_sic_13447"
TRANSCRIPTION_PROJECT_ID = 6778
DEFAULT_SEED = 20260713
DEFAULT_DEVELOPMENT_COUNT = 5
DEFAULT_HOLDOUT_COUNT = 10
DEFAULT_MIN_REFERENCE_CHARS = 500
DEFAULT_IMAGE_MAX_PIXELS = 1800
EDITORIAL_TAG_PATTERN = re.compile(r"\[\[.*?\]\]", re.DOTALL)
BREAK_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
SPACE_PATTERN = re.compile(r"[ \t\f\v]+")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def relative_path(path: Path, parent: Path) -> str:
    return Path(path.resolve()).relative_to(parent.resolve()).as_posix()


def candidate_ids(seed: int) -> list[str]:
    numbers = list(ASSET_NUMBERS)
    random.Random(seed).shuffle(numbers)
    return [f"{ASSET_PREFIX}{number}" for number in numbers]


def clean_reference_text(chars: str) -> str:
    """Remove editorial markup while preserving the transcribed visible words."""
    text = BREAK_PATTERN.sub("\n", html.unescape(chars))
    text = EDITORIAL_TAG_PATTERN.sub("", text)
    lines = [SPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def annotation_url(asset_id: str) -> str:
    return f"https://ids.si.edu/ids/annotation/{asset_id}"


def image_url(asset_id: str, max_pixels: int) -> str:
    return (
        f"https://ids.si.edu/ids/iiif/{asset_id}/"
        f"full/{max_pixels},/0/default.jpg"
    )


def source_page_url(asset_id: str) -> str:
    return (
        "https://transcription.si.edu/view/"
        f"{TRANSCRIPTION_PROJECT_ID}/{asset_id}"
    )


def fetch_bytes(url: str, *, timeout: int = 180, attempts: int = 4) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ELN-OCR-Evaluation/1.0 (educational research)"},
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(url) from exc
            if attempt == attempts - 1:
                raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == attempts - 1:
                raise
        time.sleep(2**attempt)
    raise RuntimeError(f"Unable to download {url}")


def annotation_record(asset_id: str) -> tuple[bytes, str]:
    raw = fetch_bytes(annotation_url(asset_id))
    payload = json.loads(raw)
    resources = payload.get("resources") or []
    if not resources:
        return raw, ""
    chars = resources[0].get("resource", {}).get("chars", "")
    return raw, clean_reference_text(str(chars))


def select_samples(
    *,
    seed: int,
    count: int,
    min_reference_chars: int,
) -> tuple[list[dict], list[dict]]:
    selected: list[dict] = []
    audit: list[dict] = []
    for asset_id in candidate_ids(seed):
        try:
            annotation, reference = annotation_record(asset_id)
        except FileNotFoundError:
            audit.append(
                {
                    "asset_id": asset_id,
                    "eligible": False,
                    "reason": "annotation_not_found",
                }
            )
            continue
        reference_characters = len(reference)
        eligible = reference_characters >= min_reference_chars
        reason = "eligible" if eligible else "reference_too_short"
        if eligible:
            try:
                preview = fetch_bytes(image_url(asset_id, 150))
                if len(preview) < 1_000 or not preview.startswith(b"\xff\xd8"):
                    eligible = False
                    reason = "invalid_image_preview"
            except FileNotFoundError:
                eligible = False
                reason = "image_not_available"
        audit.append(
            {
                "asset_id": asset_id,
                "eligible": eligible,
                "reason": reason,
                "reference_characters": reference_characters,
                "annotation_sha256": sha256_bytes(annotation),
            }
        )
        if eligible:
            selected.append(
                {
                    "asset_id": asset_id,
                    "annotation": annotation,
                    "reference": reference,
                }
            )
        if len(selected) == count:
            return selected, audit
    raise RuntimeError(f"Only {len(selected)} eligible pages found; required {count}")


def write_bytes(path: Path, content: bytes, *, replace: bool) -> None:
    if path.exists() and not replace:
        if path.read_bytes() != content:
            raise ValueError(f"Existing file differs; use --replace: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(content)
    temporary.replace(path)


def download_sample(
    sample: dict,
    *,
    output_dir: Path,
    image_max_pixels: int,
    replace: bool,
) -> dict:
    asset_id = sample["asset_id"]
    image_path = output_dir / "images" / f"{asset_id}.jpg"
    annotation_path = output_dir / "annotations" / f"{asset_id}.json"
    reference_path = output_dir / "references" / f"{asset_id}.txt"
    image_content = (
        fetch_bytes(image_url(asset_id, image_max_pixels))
        if replace or not image_path.exists()
        else image_path.read_bytes()
    )
    if len(image_content) < 10_000 or not image_content.startswith(b"\xff\xd8"):
        raise ValueError(f"Downloaded image is not a valid JPEG: {asset_id}")
    reference_content = (sample["reference"].strip() + "\n").encode("utf-8")
    write_bytes(image_path, image_content, replace=replace)
    write_bytes(annotation_path, sample["annotation"], replace=replace)
    write_bytes(reference_path, reference_content, replace=replace)
    return {
        "asset_id": asset_id,
        "image_path": image_path,
        "annotation_path": annotation_path,
        "reference_path": reference_path,
        "image_sha256": sha256_bytes(image_content),
        "annotation_sha256": sha256_bytes(sample["annotation"]),
        "reference_sha256": sha256_bytes(reference_content),
        "reference_characters": len(sample["reference"]),
    }


def prepare_dataset(
    output_dir: Path,
    *,
    seed: int = DEFAULT_SEED,
    development_count: int = DEFAULT_DEVELOPMENT_COUNT,
    holdout_count: int = DEFAULT_HOLDOUT_COUNT,
    min_reference_chars: int = DEFAULT_MIN_REFERENCE_CHARS,
    image_max_pixels: int = DEFAULT_IMAGE_MAX_PIXELS,
    workers: int = 4,
    replace: bool = False,
) -> dict:
    output_dir = output_dir.resolve()
    total = development_count + holdout_count
    selected, audit = select_samples(
        seed=seed,
        count=total,
        min_reference_chars=min_reference_chars,
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        records = list(
            executor.map(
                lambda sample: download_sample(
                    sample,
                    output_dir=output_dir,
                    image_max_pixels=image_max_pixels,
                    replace=replace,
                ),
                selected,
            )
        )

    fieldnames = [
        "sample_id",
        "split",
        "image_path",
        "reference_path",
        "raw_ocr_path",
        "source_url",
        "image_url",
        "annotation_url",
        "image_sha256",
        "reference_sha256",
        "annotation_sha256",
        "reference_characters",
    ]
    rows = []
    for index, record in enumerate(records):
        split = "development" if index < development_count else "holdout"
        raw_path = output_dir / "runs" / "tesseract" / "raw" / f"{record['asset_id']}.txt"
        rows.append(
            {
                "sample_id": record["asset_id"],
                "split": split,
                "image_path": relative_path(record["image_path"], output_dir),
                "reference_path": relative_path(record["reference_path"], output_dir),
                "raw_ocr_path": relative_path(raw_path, output_dir),
                "source_url": source_page_url(record["asset_id"]),
                "image_url": image_url(record["asset_id"], image_max_pixels),
                "annotation_url": annotation_url(record["asset_id"]),
                "image_sha256": record["image_sha256"],
                "reference_sha256": record["reference_sha256"],
                "annotation_sha256": record["annotation_sha256"],
                "reference_characters": record["reference_characters"],
            }
        )
    manifest_paths = {
        "all": output_dir / "manifest.csv",
        "development": output_dir / "development-manifest.csv",
        "holdout": output_dir / "holdout-manifest.csv",
    }
    for split, manifest_path in manifest_paths.items():
        manifest_rows = rows if split == "all" else [row for row in rows if row["split"] == split]
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(manifest_rows)

    selection = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "Joseph Henry's Record of Experiments, Book 3",
        "collection_url": COLLECTION_URL,
        "transcription_project_id": TRANSCRIPTION_PROJECT_ID,
        "source_asset_range": [f"{ASSET_PREFIX}6592", f"{ASSET_PREFIX}6786"],
        "source_page_count": len(ASSET_NUMBERS),
        "rights": (
            "Smithsonian Institution Archives permits personal and educational use; "
            "the collection record states no restrictions."
        ),
        "selection": {
            "method": "Python random.Random(seed).shuffle over the complete numeric asset range",
            "seed": seed,
            "minimum_reference_characters": min_reference_chars,
            "development_count": development_count,
            "holdout_count": holdout_count,
            "selected_in_order": [record["asset_id"] for record in records],
            "assessed_before_target_reached": audit,
        },
        "image_max_pixels": image_max_pixels,
        "manifests": {
            split: {
                "path": str(path),
                "sha256": sha256_bytes(path.read_bytes()),
            }
            for split, path in manifest_paths.items()
        },
    }
    selection_path = output_dir / "selection.json"
    selection_path.write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return selection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/real/smithsonian_joseph_henry"),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--development-count", type=int, default=DEFAULT_DEVELOPMENT_COUNT)
    parser.add_argument("--holdout-count", type=int, default=DEFAULT_HOLDOUT_COUNT)
    parser.add_argument("--min-reference-chars", type=int, default=DEFAULT_MIN_REFERENCE_CHARS)
    parser.add_argument("--image-max-pixels", type=int, default=DEFAULT_IMAGE_MAX_PIXELS)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = prepare_dataset(
        args.output_dir,
        seed=args.seed,
        development_count=args.development_count,
        holdout_count=args.holdout_count,
        min_reference_chars=args.min_reference_chars,
        image_max_pixels=args.image_max_pixels,
        workers=args.workers,
        replace=args.replace,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
