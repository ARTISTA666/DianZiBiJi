from __future__ import annotations

import importlib.util
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "restore_drill.py"
SPEC = importlib.util.spec_from_file_location("restore_drill", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_backup(root: Path, database: bytes = b"db", storage: bytes = b"storage") -> Path:
    backup = root / "backup"
    backup.mkdir()
    (backup / "database.dump").write_bytes(database)
    (backup / "storage.tar.gz").write_bytes(storage)
    (backup / "manifest.txt").write_text(
        "\n".join(
            (
                "manifest_version=1",
                f"database_sha256={MODULE.sha256(backup / 'database.dump')}",
                f"storage_sha256={MODULE.sha256(backup / 'storage.tar.gz')}",
            )
        ),
        encoding="utf-8",
    )
    return backup


def test_validate_backup_accepts_matching_hashes(tmp_path: Path) -> None:
    backup = write_backup(tmp_path)

    result = MODULE.validate_backup(backup)

    assert result["checks"] == {"database.dump": True, "storage.tar.gz": True}


def test_validate_backup_rejects_tampered_archive(tmp_path: Path) -> None:
    backup = write_backup(tmp_path)
    (backup / "storage.tar.gz").write_bytes(b"tampered")

    try:
        MODULE.validate_backup(backup)
    except ValueError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("expected checksum failure")


def test_restore_storage_rejects_path_traversal(tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()
    with tarfile.open(backup / "storage.tar.gz", "w:gz") as archive:
        bad = tmp_path / "bad.txt"
        bad.write_text("bad", encoding="utf-8")
        archive.add(bad, arcname="../bad.txt")

    try:
        MODULE.restore_storage(backup, tmp_path / "restore")
    except ValueError as exc:
        assert "Unsafe storage archive path" in str(exc)
    else:
        raise AssertionError("expected unsafe archive failure")
