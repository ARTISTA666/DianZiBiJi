"""Deterministic image preprocessing for OCR input."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageOps


PREPROCESS_MODES = {
    "none",
    "grayscale_autocontrast",
    "grayscale_otsu",
    "crop_autocontrast",
    "crop_otsu",
}


def _content_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    denoised = image.filter(ImageFilter.MedianFilter(size=3))
    ink_mask = denoised.point(lambda value: 255 if value < 245 else 0)
    return ink_mask.getbbox()


def _expand_bbox(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    margin: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width, height = image_size
    return (
        max(0, left - margin),
        max(0, top - margin),
        min(width, right + margin),
        min(height, bottom + margin),
    )


def preprocess_pil_image(source: Image.Image, mode: str) -> tuple[Image.Image, dict]:
    if mode not in PREPROCESS_MODES - {"none"}:
        raise ValueError(f"Unsupported OCR preprocessing mode: {mode}")
    grayscale = ImageOps.grayscale(source)
    original_size = grayscale.size
    crop_bbox = None
    if mode.startswith("crop_"):
        detected = _content_bbox(grayscale)
        if detected is not None:
            margin = max(20, round(max(grayscale.size) * 0.005))
            crop_bbox = _expand_bbox(detected, grayscale.size, margin)
            grayscale = grayscale.crop(crop_bbox)
    processed = ImageOps.autocontrast(grayscale, cutoff=1)
    threshold = None
    if mode.endswith("_otsu"):
        threshold_value, binary = cv2.threshold(
            np.asarray(processed),
            0,
            255,
            cv2.THRESH_BINARY | cv2.THRESH_OTSU,
        )
        threshold = int(threshold_value)
        processed = Image.fromarray(binary)
    processed = ImageOps.expand(processed, border=20, fill=255)
    return processed, {
        "mode": mode,
        "original_size": list(original_size),
        "processed_size": list(processed.size),
        "crop_bbox": list(crop_bbox) if crop_bbox is not None else None,
        "otsu_threshold": threshold,
    }


def preprocess_image(source_path: Path, output_path: Path, mode: str) -> dict:
    with Image.open(source_path) as source:
        processed, metadata = preprocess_pil_image(source, mode)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        processed.save(output_path, format="PNG", dpi=(300, 300), optimize=True)
    return metadata
