"""Strict repository-relative path handling for evidence manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def strict_repo_relative_path(root: Path, value: Any, *, base: Path | None = None) -> Path | None:
    """Accept only canonical POSIX spelling without symlink aliases."""
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    root = root.resolve()
    base = (base or root).resolve()
    if not base.is_relative_to(root):
        return None
    candidate = base.joinpath(*parts)
    current = base
    for part in parts:
        current /= part
        if current.is_symlink():
            return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root):
        return None
    expected = resolved.relative_to(base).as_posix()
    return resolved if value == expected else None
