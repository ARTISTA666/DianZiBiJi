#!/usr/bin/env python3
"""Validate and extract a storage backup without following archive links."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import sys
import tarfile


class UnsafeStorageArchive(ValueError):
    """Raised when an archive member could escape or redirect extraction."""


def validate_member(member: tarfile.TarInfo) -> None:
    name = member.name
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise UnsafeStorageArchive(f"unsafe member path: {name!r}")
    if member.issym():
        raise UnsafeStorageArchive(f"symbolic links are not allowed: {name!r}")
    if member.islnk():
        raise UnsafeStorageArchive(f"hard links are not allowed: {name!r}")
    if not (member.isdir() or member.isfile()):
        raise UnsafeStorageArchive(f"special members are not allowed: {name!r}")


def safe_extract(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            validate_member(member)
        archive.extractall(destination, members=members, filter="data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        safe_extract(args.archive, args.destination)
    except (OSError, tarfile.TarError, UnsafeStorageArchive) as error:
        print(f"[FAIL] unsafe storage archive: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
