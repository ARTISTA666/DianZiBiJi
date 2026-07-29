#!/usr/bin/env python3
"""Restore a backup into an isolated PostgreSQL container and temp storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def validate_backup(backup: Path) -> dict:
    required = {name: backup / name for name in ("manifest.txt", "database.dump", "storage.tar.gz")}
    missing = [name for name, path in required.items() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError("Missing backup files: " + ", ".join(missing))
    manifest = parse_manifest(required["manifest.txt"])
    if manifest.get("manifest_version") != "1":
        raise ValueError("Unsupported backup manifest version")
    checks = {
        "database.dump": sha256(required["database.dump"]) == manifest.get("database_sha256"),
        "storage.tar.gz": sha256(required["storage.tar.gz"]) == manifest.get("storage_sha256"),
    }
    if not all(checks.values()):
        raise ValueError("Backup checksum mismatch")
    return {"manifest": manifest, "checks": checks}


def run(command: list[str], *, input_bytes: bytes | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=ROOT,
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def wait_for_database(container: str, user: str, database: str, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = run(["docker", "exec", container, "pg_isready", "-U", user, "-d", database], timeout=10)
        if result.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError(f"Isolated database did not become ready: {container}")


def restore_database(backup: Path, container: str, user: str, database: str) -> dict:
    dump = (backup / "database.dump").read_bytes()
    listed = run(["docker", "exec", "-i", container, "pg_restore", "--list"], input_bytes=dump)
    if listed.returncode != 0:
        raise RuntimeError(listed.stderr.decode("utf-8", errors="replace"))
    restored = run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "pg_restore",
            "-U",
            user,
            "-d",
            database,
            "--no-owner",
            "--no-acl",
            "--exit-on-error",
        ],
        input_bytes=dump,
        timeout=300,
    )
    if restored.returncode != 0:
        raise RuntimeError(restored.stderr.decode("utf-8", errors="replace"))
    table_count = run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-Atc",
            "select count(*) from information_schema.tables where table_schema='public';",
        ]
    )
    if table_count.returncode != 0:
        raise RuntimeError(table_count.stderr.decode("utf-8", errors="replace"))
    return {
        "dump_list_readable": True,
        "restored": True,
        "public_table_count": int(table_count.stdout.decode("utf-8").strip() or "0"),
    }


def restore_storage(backup: Path, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(backup / "storage.tar.gz", "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError(f"Unsafe storage archive path: {member.name}")
        archive.extractall(destination, filter="data")
    files = [path for path in destination.rglob("*") if path.is_file()]
    return {"restored": True, "file_count": len(files), "bytes": sum(path.stat().st_size for path in files)}


def drill(backup: Path, *, output: Path | None = None, keep: bool = False) -> dict:
    backup = backup.resolve()
    validation = validate_backup(backup)
    suffix = f"{int(time.time())}"
    container = f"eln-restore-drill-{suffix}"
    database = "eln_restore_drill"
    user = "eln_restore_drill"
    password = "eln_restore_drill"
    temp_root = Path(tempfile.mkdtemp(prefix="eln-restore-drill-"))
    started = False
    try:
        created = run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container,
                "-e",
                f"POSTGRES_DB={database}",
                "-e",
                f"POSTGRES_USER={user}",
                "-e",
                f"POSTGRES_PASSWORD={password}",
                "pgvector/pgvector:pg16",
            ],
            timeout=120,
        )
        if created.returncode != 0:
            raise RuntimeError(created.stderr.decode("utf-8", errors="replace"))
        started = True
        wait_for_database(container, user, database)
        database_result = restore_database(backup, container, user, database)
        storage_result = restore_storage(backup, temp_root / "storage")
        report = {
            "ok": database_result["restored"] and storage_result["restored"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "backup": str(backup),
            "manifest": validation["manifest"],
            "checks": validation["checks"],
            "database": database_result,
            "storage": storage_result,
        }
    finally:
        if started and not keep:
            run(["docker", "rm", "-f", container], timeout=60)
        if not keep:
            shutil.rmtree(temp_root, ignore_errors=True)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "system-evidence" / "restore-drill-latest.json")
    parser.add_argument("--keep", action="store_true", help="Keep temp container and storage for debugging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = drill(args.backup, output=args.output, keep=args.keep)
    print(json.dumps({"ok": report["ok"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
