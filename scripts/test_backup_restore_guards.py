from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RESTORE = ROOT / "scripts" / "restore-system.sh"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_malicious_storage_archive(path: Path, member_kind: str) -> None:
    with tarfile.open(path, "w:gz") as archive:
        if member_kind == "path traversal":
            payload = b"outside"
            member = tarfile.TarInfo("../outside.txt")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
            return

        payload = b"safe"
        target = tarfile.TarInfo("safe.txt")
        target.size = len(payload)
        archive.addfile(target, io.BytesIO(payload))
        link = tarfile.TarInfo(f"{member_kind}.txt")
        link.type = tarfile.SYMTYPE if member_kind == "symlink" else tarfile.LNKTYPE
        link.linkname = "/etc/passwd" if member_kind == "symlink" else "safe.txt"
        archive.addfile(link)


def write_regular_storage_archive(path: Path) -> None:
    payload = b"restorable"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("uploads/example.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))


def run_restore_with_fake_docker(
    backup: Path, tools: Path
) -> subprocess.CompletedProcess[str]:
    tools.mkdir()
    docker = tools / "docker"
    docker.write_text(
        "#!/bin/sh\nprintf 'fake docker was called\\n' >&2\nexit 97\n",
        encoding="utf-8",
    )
    docker.chmod(0o700)
    environment = os.environ.copy()
    environment["PATH"] = f"{tools}{os.pathsep}{environment['PATH']}"
    return subprocess.run(
        ["sh", str(RESTORE), str(backup), "--confirm-replace"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_restore_requires_explicit_replacement_confirmation() -> None:
    result = subprocess.run(
        ["sh", str(RESTORE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--confirm-replace" in result.stderr


def test_restore_rejects_a_tampered_database_dump_before_docker_access() -> None:
    with tempfile.TemporaryDirectory() as directory:
        backup = Path(directory)
        (backup / "database.dump").write_bytes(b"tampered")
        (backup / "storage.tar.gz").write_bytes(b"archive")
        (backup / "manifest.txt").write_text(
            "\n".join(
                (
                    "manifest_version=1",
                    "database_sha256=not-the-real-hash",
                    "storage_sha256=also-not-the-real-hash",
                )
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            ["sh", str(RESTORE), str(backup), "--confirm-replace"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 1
    assert "database dump checksum" in result.stderr


@pytest.mark.parametrize("member_kind", ["path traversal", "symlink", "hardlink"])
def test_restore_rejects_unsafe_storage_members_before_docker_access(
    member_kind: str,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        backup = root / "backup"
        backup.mkdir()
        (backup / "database.dump").write_bytes(b"valid-enough-for-archive-guard")
        write_malicious_storage_archive(backup / "storage.tar.gz", member_kind)
        (backup / "manifest.txt").write_text(
            "\n".join(
                (
                    "manifest_version=1",
                    f"database_sha256={sha256(backup / 'database.dump')}",
                    f"storage_sha256={sha256(backup / 'storage.tar.gz')}",
                )
            ),
            encoding="utf-8",
        )

        result = run_restore_with_fake_docker(backup, root / "tools")

    assert result.returncode == 1
    assert "unsafe storage archive" in result.stderr.lower()
    assert "fake docker was called" not in result.stderr


def test_restore_accepts_regular_storage_members_before_database_checks() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        backup = root / "backup"
        backup.mkdir()
        (backup / "database.dump").write_bytes(b"valid-enough-for-archive-guard")
        write_regular_storage_archive(backup / "storage.tar.gz")
        (backup / "manifest.txt").write_text(
            "\n".join(
                (
                    "manifest_version=1",
                    f"database_sha256={sha256(backup / 'database.dump')}",
                    f"storage_sha256={sha256(backup / 'storage.tar.gz')}",
                )
            ),
            encoding="utf-8",
        )

        result = run_restore_with_fake_docker(backup, root / "tools")

    assert result.returncode == 1
    assert "unsafe storage archive" not in result.stderr.lower()
    assert "fake docker was called" in result.stderr
