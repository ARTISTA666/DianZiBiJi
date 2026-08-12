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
    document: dict[str, Any], metrics: dict[str, Any], backend_url: str
) -> dict[str, Any]:
    openapi_text = render_json(document)
    rows = build_api_rows(document)
    runtime = metrics.get("runtime") if isinstance(metrics.get("runtime"), dict) else {}
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
        "revision": metrics.get("revision"),
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


def _update_manifest(output_dir: Path, evidence: dict[str, Any]) -> None:
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
    existing = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    preserved = [entry for entry in existing if isinstance(entry, dict) and entry.get("name") not in CONTRACT_FILES]
    manifest["files"] = sorted(
        preserved + [_file_entry(output_dir / name) for name in CONTRACT_FILES],
        key=lambda entry: str(entry.get("name", "")),
    )
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["contract"] = {
        "generator": "export_rust_contract_evidence.py",
        "schema": evidence["schema"],
        "runtime": evidence["runtime"],
        "openapi_sha256": evidence["api"]["openapi_sha256"],
    }
    _write_atomic(manifest_path, render_json(manifest))


def write_evidence(
    output_dir: Path, document: dict[str, Any], metrics: dict[str, Any], backend_url: str
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    openapi_text = render_json(document)
    api_csv = render_api_csv(document)
    evidence = build_contract_evidence(document, metrics, backend_url)
    _write_atomic(output_dir / "openapi.json", openapi_text)
    _write_atomic(output_dir / "api-list.csv", api_csv)
    _write_atomic(output_dir / "rust-runtime-contract-latest.json", render_json(evidence))
    _update_manifest(output_dir, evidence)
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
        document = fetch_json(backend_endpoint(backend_url, "/openapi.json"))
        metrics = fetch_json(backend_endpoint(backend_url, "/metrics"))
        result = write_evidence(args.output_dir, document, metrics, backend_url)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Rust contract evidence export failed: {exc}", file=sys.stderr)
        return 1
    print(render_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
