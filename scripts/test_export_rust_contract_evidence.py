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
    ready = {"status": "ready", "revision": "abc"}

    evidence = MODULE.build_contract_evidence(document, metrics, "http://backend", ready)

    assert evidence["runtime"] == metrics["runtime"]
    assert evidence["app_revision"] == evidence["runtime_revision"] == "abc"
    assert evidence["api"]["operation_count"] == 1
    assert evidence["api"]["openapi_sha256"] == MODULE.sha256_bytes(MODULE.render_json(document))
    assert evidence["source"]["openapi_url"] == "http://backend/openapi.json"


def test_write_evidence_updates_contract_files_and_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "system-evidence"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")
    for name, extra in (
        ("runtime-config-latest.json", {}),
        ("container-image-latest.json", {"oci_revision": "abc", "endpoint_revision": "abc"}),
    ):
        (output_dir / name).write_text(
            json.dumps({"build_revision": "abc", "app_revision": "abc", "runtime_revision": "abc", **extra}),
            encoding="utf-8",
        )
    (output_dir / "manifest.json").write_text(
        json.dumps({"counts": {"database_tables": 26}, "files": [{"name": "old.txt"}]}),
        encoding="utf-8",
    )
    document = {"openapi": "3.0.3", "paths": {"/health": {"get": {"summary": "Health"}}}}
    metrics = {"status": "ok", "revision": "abc", "runtime": {"api_runtime": "rust-axum"}}
    ready = {"status": "ready", "revision": "abc"}

    result = MODULE.write_evidence(output_dir, document, metrics, "http://backend", ready)

    assert result["api_operations"] == 1
    assert json.loads((output_dir / "openapi.json").read_text(encoding="utf-8")) == document
    assert (output_dir / "api-list.csv").read_text(encoding="utf-8-sig").splitlines()[1].startswith("GET,/health")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["app_revision"] == "abc"
    assert manifest["counts"]["api_operations"] == 1
    assert {entry["name"] for entry in manifest["files"]} >= {
        "api-list.csv",
        "container-image-latest.json",
        "openapi.json",
        "rust-runtime-contract-latest.json",
        "runtime-config-latest.json",
    }
    old_entry = next(entry for entry in manifest["files"] if entry["name"] == "old.txt")
    assert old_entry["bytes"] == 3
    assert old_entry["sha256"] == MODULE.sha256_bytes(b"old")


def test_write_evidence_rejects_missing_declared_manifest_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "system-evidence"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(
        json.dumps({"files": [{"name": "missing.json", "sha256": "stale"}]}),
        encoding="utf-8",
    )
    document = {"openapi": "3.0.3", "paths": {}}
    metrics = {"status": "ok", "revision": "abc", "runtime": {"api_runtime": "rust-axum"}}
    ready = {"status": "ready", "revision": "abc"}
    (output_dir / "runtime-config-latest.json").write_text(
        json.dumps({"build_revision": "abc", "app_revision": "abc", "runtime_revision": "abc"}),
        encoding="utf-8",
    )
    (output_dir / "container-image-latest.json").write_text(
        json.dumps({"build_revision": "abc", "app_revision": "abc", "runtime_revision": "abc", "oci_revision": "abc", "endpoint_revision": "abc"}),
        encoding="utf-8",
    )

    try:
        MODULE.write_evidence(output_dir, document, metrics, "http://backend", ready)
    except ValueError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("stale manifest entries must not survive export")


def test_write_evidence_rejects_runtime_manifest_hash_drift(tmp_path: Path) -> None:
    output_dir = tmp_path / "system-evidence"
    output_dir.mkdir()
    for name, extra in (
        ("runtime-config-latest.json", {}),
        ("container-image-latest.json", {"oci_revision": "abc", "endpoint_revision": "abc"}),
    ):
        (output_dir / name).write_text(
            json.dumps({"build_revision": "abc", "app_revision": "abc", "runtime_revision": "abc", **extra}),
            encoding="utf-8",
        )
    (output_dir / "manifest.json").write_text(
        json.dumps({"files": [{"name": "runtime-config-latest.json", "sha256": "stale"}]}),
        encoding="utf-8",
    )
    document = {"openapi": "3.0.3", "paths": {}}
    metrics = {"status": "ok", "revision": "abc", "runtime": {"api_runtime": "rust-axum"}}
    ready = {"status": "ready", "revision": "abc"}

    try:
        MODULE.write_evidence(output_dir, document, metrics, "http://backend", ready)
    except ValueError as error:
        assert "hash drift" in str(error)
    else:
        raise AssertionError("runtime evidence hash drift must fail closed")


def test_write_evidence_rejects_runtime_manifest_hash_omission(tmp_path: Path) -> None:
    output_dir = tmp_path / "system-evidence"
    output_dir.mkdir()
    for name, extra in (
        ("runtime-config-latest.json", {}),
        ("container-image-latest.json", {"oci_revision": "abc", "endpoint_revision": "abc"}),
    ):
        (output_dir / name).write_text(
            json.dumps({"build_revision": "abc", "app_revision": "abc", "runtime_revision": "abc", **extra}),
            encoding="utf-8",
        )
    (output_dir / "manifest.json").write_text(
        json.dumps({"files": [{"name": "runtime-config-latest.json"}]}),
        encoding="utf-8",
    )
    document = {"openapi": "3.0.3", "paths": {}}
    metrics = {"status": "ok", "revision": "abc", "runtime": {"api_runtime": "rust-axum"}}
    ready = {"status": "ready", "revision": "abc"}

    try:
        MODULE.write_evidence(output_dir, document, metrics, "http://backend", ready)
    except ValueError as error:
        assert "hash drift" in str(error)
    else:
        raise AssertionError("runtime evidence without an integrity hash must fail closed")


def test_write_evidence_rejects_runtime_revision_drift(tmp_path: Path) -> None:
    output_dir = tmp_path / "system-evidence"
    output_dir.mkdir()
    (output_dir / "runtime-config-latest.json").write_text(
        json.dumps({"build_revision": "old", "app_revision": "old", "runtime_revision": "old"}),
        encoding="utf-8",
    )
    (output_dir / "container-image-latest.json").write_text(
        json.dumps({"build_revision": "abc", "app_revision": "abc", "runtime_revision": "abc", "oci_revision": "abc", "endpoint_revision": "abc"}),
        encoding="utf-8",
    )
    document = {"openapi": "3.0.3", "paths": {}}
    metrics = {"status": "ok", "revision": "abc", "runtime": {"api_runtime": "rust-axum"}}
    ready = {"status": "ready", "revision": "abc"}

    try:
        MODULE.write_evidence(output_dir, document, metrics, "http://backend", ready)
    except ValueError as error:
        assert "revision drift" in str(error)
    else:
        raise AssertionError("runtime evidence revision drift must fail closed")


def test_build_contract_evidence_rejects_revision_drift() -> None:
    document = {"openapi": "3.0.3", "paths": {}}
    metrics = {"status": "ok", "revision": "a" * 40, "runtime": {"api_runtime": "rust-axum"}}
    ready = {"status": "ready", "revision": "b" * 40}

    try:
        MODULE.build_contract_evidence(document, metrics, "http://backend", ready)
    except ValueError as error:
        assert "revisions" in str(error)
    else:
        raise AssertionError("revision drift must fail closed")


def test_build_contract_evidence_rejects_checkout_drift() -> None:
    document = {"openapi": "3.0.3", "paths": {}}
    metrics = {"status": "ok", "revision": "a" * 40, "runtime": {"api_runtime": "rust-axum"}}
    ready = {"status": "ready", "revision": "a" * 40}

    try:
        MODULE.build_contract_evidence(document, metrics, "http://backend", ready, "b" * 40)
    except ValueError as error:
        assert "checkout HEAD" in str(error)
    else:
        raise AssertionError("runtime evidence must match checkout HEAD")
