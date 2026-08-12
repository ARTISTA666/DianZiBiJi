from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_rust_contract_evidence.py"
SPEC = importlib.util.spec_from_file_location("export_rust_contract_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_api_rows_is_sorted_and_preserves_tags() -> None:
    document = {
        "paths": {
            "/z": {"post": {"summary": "Z", "operationId": "z", "tags": ["late"]}},
            "/a": {"get": {"summary": "A", "operationId": "a", "tags": ["early", "read"]}},
        }
    }

    assert MODULE.build_api_rows(document) == [
        {
            "method": "GET",
            "path": "/a",
            "tags": "early,read",
            "summary": "A",
            "operation_id": "a",
        },
        {
            "method": "POST",
            "path": "/z",
            "tags": "late",
            "summary": "Z",
            "operation_id": "z",
        },
    ]


def test_build_contract_evidence_binds_runtime_and_openapi() -> None:
    document = {"openapi": "3.0.3", "paths": {"/health": {"get": {}}}}
    metrics = {
        "status": "ok",
        "revision": "abc",
        "runtime": {
            "api_runtime": "rust-axum",
            "embedding_backend": "hash",
            "embedding_model": "rust-hash-512-v1",
            "embedding_dimension": 512,
        },
    }

    evidence = MODULE.build_contract_evidence(document, metrics, "http://backend")

    assert evidence["runtime"] == metrics["runtime"]
    assert evidence["api"]["operation_count"] == 1
    assert evidence["api"]["openapi_sha256"] == MODULE.sha256_bytes(MODULE.render_json(document))
    assert evidence["source"]["openapi_url"] == "http://backend/openapi.json"


def test_write_evidence_updates_contract_files_and_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "system-evidence"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(
        json.dumps({"counts": {"database_tables": 26}, "files": [{"name": "old.txt"}]}),
        encoding="utf-8",
    )
    document = {"openapi": "3.0.3", "paths": {"/health": {"get": {"summary": "Health"}}}}
    metrics = {"status": "ok", "revision": "abc", "runtime": {"api_runtime": "rust-axum"}}

    result = MODULE.write_evidence(output_dir, document, metrics, "http://backend")

    assert result["api_operations"] == 1
    assert json.loads((output_dir / "openapi.json").read_text(encoding="utf-8")) == document
    assert (output_dir / "api-list.csv").read_text(encoding="utf-8-sig").splitlines()[1].startswith("GET,/health")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["api_operations"] == 1
    assert {entry["name"] for entry in manifest["files"]} >= {
        "api-list.csv",
        "openapi.json",
        "rust-runtime-contract-latest.json",
    }
