#!/usr/bin/env python3
"""Export the live Rust API contract into the checked-in system evidence bundle.

The repository contains a historical FastAPI exporter, but the Rust/Axum image is
the production API owner.  This small exporter deliberately reads the running
Rust endpoints so that OpenAPI and API-list evidence cannot silently drift from
the deployed contract.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "system-evidence"
HTTP_METHODS = ("delete", "get", "head", "options", "patch", "post", "put", "trace")
CONTRACT_FILES = ("api-list.csv", "openapi.json", "rust-runtime-contract-latest.json")
RUNTIME_FILES = ("runtime-config-latest.json", "container-image-latest.json")
REQUIRED_MANIFEST_FILES = CONTRACT_FILES + RUNTIME_FILES
REVISION_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def sha256_bytes(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def render_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def backend_endpoint(backend_url: str, path: str) -> str:
    return urljoin(backend_url.rstrip("/") + "/", path.lstrip("/"))


def fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} did not return a JSON object")
    return payload


def checkout_revision() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD^{commit}"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip().lower()
    if result.returncode or not REVISION_PATTERN.fullmatch(revision):
        raise RuntimeError("checkout HEAD is not a full hexadecimal revision")
    return revision


def verify_clean_compose_checkout() -> None:
    runner = ROOT / "scripts" / "docker-compose-with-revision.sh"
    result = subprocess.run(
        [str(runner), "config", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("revision-bound Compose wrapper rejected the evidence checkout")


def build_api_rows(document: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    paths = document.get("paths") or {}
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI paths must be an object")
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            tags = operation.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            rows.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "tags": ",".join(str(tag) for tag in tags),
                    "summary": str(operation.get("summary") or operation.get("description") or ""),
                    "operation_id": str(operation.get("operationId") or ""),
                }
            )
    return sorted(rows, key=lambda row: (row["path"], row["method"]))


def render_api_csv(document: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=("method", "path", "tags", "summary", "operation_id"),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(build_api_rows(document))
    return output.getvalue()


def build_contract_evidence(
    document: dict[str, Any],
    metrics: dict[str, Any],
    backend_url: str,
    ready: dict[str, Any] | None = None,
    expected_revision: str | None = None,
    expected_tooling_revision: str | None = None,
) -> dict[str, Any]:
    openapi_text = render_json(document)
    rows = build_api_rows(document)
    runtime = metrics.get("runtime") if isinstance(metrics.get("runtime"), dict) else {}
    ready = {"status": "ready", "revision": metrics.get("revision")} if ready is None else ready
    ready_revision = ready.get("revision")
    metrics_revision = metrics.get("revision")
    if not isinstance(ready_revision, str) or ready_revision != metrics_revision:
        raise ValueError("/ready and /metrics revisions must match")
    if ready.get("status") != "ready" or metrics.get("status") != "ok":
        raise ValueError("/ready and /metrics must report healthy statuses")
    # The endpoint revision identifies R (the deployed runtime source).  T is
    # the revision of the exporter/tooling checkout and must never be written
    # into endpoint/app/runtime revision fields.
    if expected_tooling_revision is not None and (not isinstance(expected_tooling_revision, str) or not REVISION_PATTERN.fullmatch(expected_tooling_revision)):
        raise ValueError("experiment tooling revision is invalid")
    if expected_revision is not None and (not isinstance(expected_revision, str) or not REVISION_PATTERN.fullmatch(expected_revision)):
        raise ValueError("runtime source revision is invalid")
    if expected_revision is not None and ready_revision.lower() != expected_revision.lower():
        raise ValueError("runtime source revision does not match expected R")
    return {
        "schema": "full-system.rust-runtime-contract-evidence",
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "backend_url": backend_url,
            "openapi_url": backend_endpoint(backend_url, "/openapi.json"),
            "metrics_url": backend_endpoint(backend_url, "/metrics"),
        },
        "runtime": runtime,
        "revision": metrics_revision,
        "endpoint_revision": ready_revision,
        "runtime_source_revision": ready_revision,
        "build_revision": ready_revision,
        "app_revision": ready_revision,
        "runtime_revision": ready_revision,
        "experiment_tooling_revision": expected_tooling_revision,
        "status": metrics.get("status"),
        "api": {
            "openapi_version": document.get("openapi"),
            "operation_count": len(rows),
            "path_count": len(document.get("paths") or {}),
            "openapi_sha256": sha256_bytes(openapi_text),
        },
    }


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8-sig" if path.name == "api-list.csv" else "utf-8")
    temporary.replace(path)


def _file_entry(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {"name": path.name, "bytes": len(payload), "sha256": sha256_bytes(payload)}


def _verify_runtime_evidence(
    output_dir: Path,
    revision: str,
    tooling_revision: str | None = None,
    *,
    require_all: bool = False,
) -> None:
    strict_binding = require_all or tooling_revision is not None
    if strict_binding and (not isinstance(revision, str) or not REVISION_PATTERN.fullmatch(revision)):
        raise ValueError("runtime source revision is missing or invalid")
    required_runtime_fields = {
        "runtime-config-latest.json": ("runtime_source_revision", "build_revision", "app_revision", "runtime_revision"),
        "container-image-latest.json": ("runtime_source_revision", "build_revision", "app_revision", "runtime_revision", "oci_revision", "endpoint_revision"),
    }
    for name in RUNTIME_FILES:
        path = output_dir / name
        if not path.is_file():
            raise ValueError(f"required runtime evidence is missing: {name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"required runtime evidence is invalid: {name}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"runtime evidence revision drift: {name}")
        if strict_binding:
            fields = required_runtime_fields[name]
            if any(
                not isinstance(payload.get(field), str)
                or not REVISION_PATTERN.fullmatch(payload[field])
                or payload[field] != revision
                for field in fields
            ):
                raise ValueError(f"runtime evidence revision drift: {name}")
        elif any(
            payload.get(field) not in (None, revision)
            for field in ("runtime_source_revision", "build_revision", "app_revision", "runtime_revision")
        ):
            raise ValueError(f"runtime evidence revision drift: {name}")
        if tooling_revision is not None and (
            not isinstance(payload.get("experiment_tooling_revision"), str)
            or not REVISION_PATTERN.fullmatch(payload["experiment_tooling_revision"])
            or payload["experiment_tooling_revision"] != tooling_revision
        ):
            raise ValueError(f"runtime evidence tooling revision drift: {name}")
        if not strict_binding and name == "container-image-latest.json" and any(
            payload.get(field) not in (None, revision) for field in ("oci_revision", "endpoint_revision")
        ):
            raise ValueError(f"container image revision drift: {name}")


def _manifest_file_entries(output_dir: Path, existing: list[Any]) -> list[dict[str, Any]]:
    """Recompute every declared file hash; never carry stale integrity data forward."""
    entries: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw_entry in existing:
        if not isinstance(raw_entry, dict) or not isinstance(raw_entry.get("name"), str):
            raise ValueError("manifest files must contain named file objects")
        name = raw_entry["name"]
        if not name or Path(name).name != name or name == "manifest.json":
            raise ValueError(f"manifest file name is unsafe: {name!r}")
        if name in names:
            raise ValueError(f"manifest contains duplicate file: {name}")
        names.add(name)
        path = output_dir / name
        if not path.is_file():
            raise ValueError(f"manifest file is missing: {name}")
        entry = _file_entry(path)
        if name in RUNTIME_FILES and raw_entry.get("sha256") != entry["sha256"]:
            raise ValueError(f"runtime evidence hash drift: {name}")
        entries.append(entry)
    for name in REQUIRED_MANIFEST_FILES:
        if name not in names:
            path = output_dir / name
            if not path.is_file():
                raise ValueError(f"required manifest file is missing: {name}")
            entries.append(_file_entry(path))
    return sorted(entries, key=lambda entry: entry["name"])


def _update_manifest(output_dir: Path, evidence: dict[str, Any], *, require_all: bool = False) -> None:
    manifest_path = output_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    counts["api_operations"] = evidence["api"]["operation_count"]
    manifest["counts"] = counts
    _verify_runtime_evidence(
        output_dir,
        evidence["runtime_source_revision"],
        evidence["experiment_tooling_revision"],
        require_all=require_all,
    )
    existing = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    manifest["files"] = _manifest_file_entries(output_dir, existing)
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["app_revision"] = evidence["app_revision"]
    manifest["runtime_source_revision"] = evidence["runtime_source_revision"]
    manifest["experiment_tooling_revision"] = evidence["experiment_tooling_revision"]
    manifest["contract"] = {
        "generator": "export_rust_contract_evidence.py",
        "schema": evidence["schema"],
        "runtime": evidence["runtime"],
        "openapi_sha256": evidence["api"]["openapi_sha256"],
    }
    _write_atomic(manifest_path, render_json(manifest))


def write_evidence(
    output_dir: Path,
    document: dict[str, Any],
    metrics: dict[str, Any],
    backend_url: str,
    ready: dict[str, Any] | None = None,
    expected_revision: str | None = None,
    expected_tooling_revision: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    openapi_text = render_json(document)
    api_csv = render_api_csv(document)
    evidence = build_contract_evidence(document, metrics, backend_url, ready, expected_revision, expected_tooling_revision)
    _write_atomic(output_dir / "openapi.json", openapi_text)
    _write_atomic(output_dir / "api-list.csv", api_csv)
    _write_atomic(output_dir / "rust-runtime-contract-latest.json", render_json(evidence))
    _update_manifest(
        output_dir,
        evidence,
        require_all=expected_revision is not None or expected_tooling_revision is not None,
    )
    return {
        "output_dir": str(output_dir),
        "api_operations": evidence["api"]["operation_count"],
        "api_paths": evidence["api"]["path_count"],
        "openapi_sha256": evidence["api"]["openapi_sha256"],
        "runtime": evidence["runtime"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    backend_url = args.backend_url.rstrip("/")
    try:
        expected_revision = checkout_revision()
        verify_clean_compose_checkout()
        document = fetch_json(backend_endpoint(backend_url, "/openapi.json"))
        metrics = fetch_json(backend_endpoint(backend_url, "/metrics"))
        ready = fetch_json(backend_endpoint(backend_url, "/ready"))
        result = write_evidence(
            args.output_dir,
            document,
            metrics,
            backend_url,
            ready,
            expected_tooling_revision=expected_revision,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Rust contract evidence export failed: {exc}", file=sys.stderr)
        return 1
    print(render_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
