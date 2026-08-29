from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).with_name("export_runtime_evidence.py")
SPEC = importlib.util.spec_from_file_location("export_runtime_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def image_fixture() -> dict:
    return {
        "Id": "sha256:" + "a" * 64,
        "RepoDigests": ["eln-backend@sha256:" + "b" * 64],
        "Architecture": "arm64",
        "Os": "linux",
        "RootFS": {"Layers": ["sha256:" + "c" * 64]},
        "Config": {
            "Entrypoint": ["/usr/local/bin/eln-backend"],
            "Cmd": [],
            "WorkingDir": "/app",
            "User": "eln",
            "Env": ["POSTGRES_PASSWORD=must-not-enter-projection"],
            "Labels": {"org.opencontainers.image.revision": "d" * 40, "other": "ignored"},
        },
        "Created": "dynamic",
    }


def container_fixture() -> dict:
    return {
        "Id": "container-id-a",
        "Name": "/eln-backend-1",
        "Image": "sha256:" + "a" * 64,
        "Path": "/usr/local/bin/eln-backend",
        "Args": [],
        "Config": {
            "Entrypoint": ["/usr/local/bin/eln-backend"],
            "Cmd": [],
            "Env": ["SECRET_KEY=must-not-enter-projection"],
            "Labels": {"com.docker.compose.project": "eln", "com.docker.compose.service": "backend"},
        },
        "State": {"StartedAt": "dynamic", "Health": {"Log": ["dynamic"]}},
    }


def compose_fixture(revision: str, secret: str = "first-secret", env_value: str = "first-env") -> dict:
    return {
        "name": "full-system",
        "services": {
            "backend": {
                "build": {
                    "context": str(MODULE.ROOT / "backend"),
                    "dockerfile": "Dockerfile",
                    "args": {"BUILD_REVISION": revision, "SECRET_KEY": secret},
                },
                "environment": {"SECRET_KEY": secret, "PUBLIC_SETTING": env_value},
                "ports": [{"mode": "ingress", "target": 8000, "published": 8001, "protocol": "tcp"}],
                "healthcheck": {"test": ["CMD", "curl", "--fail", "http://127.0.0.1:8000/ready"], "interval": "10s", "retries": 12},
            },
            "db": {
                "image": "pgvector/pgvector:pg16",
                "environment": {"POSTGRES_PASSWORD": secret},
                "healthcheck": {"test": ["CMD-SHELL", "pg_isready"], "interval": "10s", "retries": 5},
            },
        },
    }


def test_resolved_compose_projection_drops_env_and_secrets() -> None:
    first = MODULE.resolved_compose_projection(compose_fixture("a" * 40, "one", "alpha"), "a" * 40)
    second = MODULE.resolved_compose_projection(compose_fixture("a" * 40, "two", "beta"), "a" * 40)

    assert first == second
    serialized = json.dumps(first, ensure_ascii=False)
    assert "SECRET_KEY" not in serialized
    assert "POSTGRES_PASSWORD" not in serialized
    assert "first-env" not in serialized


def test_resolved_compose_projection_changes_with_build_revision() -> None:
    first = MODULE.resolved_compose_projection(compose_fixture("a" * 40), "a" * 40)
    second = MODULE.resolved_compose_projection(compose_fixture("b" * 40), "b" * 40)

    assert first != second
    assert MODULE.projection_hash(first) != MODULE.projection_hash(second)


def test_projection_ignores_dynamic_and_secret_image_fields() -> None:
    image = image_fixture()
    baseline = MODULE.projection_hash(MODULE.image_projection(image))
    image["Created"] = "changed"
    image["Config"]["Env"] = ["POSTGRES_PASSWORD=changed"]
    assert MODULE.projection_hash(MODULE.image_projection(image)) == baseline


def test_projection_ignores_dynamic_and_secret_container_fields() -> None:
    container = container_fixture()
    baseline = MODULE.projection_hash(MODULE.container_projection(container))
    container["Id"] = "changed-id"
    container["Name"] = "/changed"
    container["State"]["StartedAt"] = "changed"
    container["Config"]["Env"] = ["SECRET_KEY=changed"]
    assert MODULE.projection_hash(MODULE.container_projection(container)) == baseline


def test_projection_changes_for_image_identity_or_oci_revision() -> None:
    image = image_fixture()
    baseline = MODULE.projection_hash(MODULE.image_projection(image))
    image["Id"] = "sha256:" + "e" * 64
    assert MODULE.projection_hash(MODULE.image_projection(image)) != baseline
    image = image_fixture()
    image["Config"]["Labels"]["org.opencontainers.image.revision"] = "f" * 40
    assert MODULE.projection_hash(MODULE.image_projection(image)) != baseline


def test_projection_is_canonical_under_key_reordering() -> None:
    image = image_fixture()
    reordered = {key: image[key] for key in reversed(list(image))}
    assert MODULE.projection_hash(MODULE.image_projection(image)) == MODULE.projection_hash(MODULE.image_projection(reordered))


def test_immutable_digest_prefers_repo_digest_but_requires_sha256() -> None:
    digest, image_id, repo_digests = MODULE.immutable_image_digest(image_fixture())
    assert digest == "sha256:" + "b" * 64
    assert image_id == "sha256:" + "a" * 64
    assert repo_digests == ["eln-backend@sha256:" + "b" * 64]


def test_local_repo_digest_is_not_registry_provenance() -> None:
    assert MODULE.registry_repo_digest(["eln-backend@sha256:" + "b" * 64]) is None
    assert MODULE.registry_repo_digest(["registry.example/eln-backend@sha256:" + "b" * 64]) == (
        "registry.example/eln-backend@sha256:" + "b" * 64
    )


def test_export_drops_existing_unknown_and_secret_fields(tmp_path: Path, monkeypatch) -> None:
    head = "a" * 40
    image = image_fixture()
    image["Config"]["Labels"]["org.opencontainers.image.revision"] = head
    container = container_fixture()
    output_dir = tmp_path / "system-evidence"
    output_dir.mkdir()
    (output_dir / "runtime-config-latest.json").write_text(
        json.dumps(
            {
                "SECRET_KEY": "do-not-copy",
                "source": {"SECRET_TOKEN": "do-not-copy"},
                "unknown": {"nested": True},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(MODULE, "checkout_revision", lambda: head)
    monkeypatch.setattr(
        MODULE,
        "compose_config",
        lambda _head: json.dumps(compose_fixture(head)).encode("utf-8"),
    )
    monkeypatch.setattr(
        MODULE,
        "fetch_json",
        lambda url: (
            {"status": "ready", "revision": head, "checks": {"database": "ok", "SECRET_TOKEN": "do-not-copy"}}
            if url.endswith("/ready")
            else {"status": "ok", "revision": head, "runtime": {"api_runtime": "rust-axum", "SECRET_KEY": "do-not-copy"}}
        ),
    )
    monkeypatch.setattr(
        MODULE,
        "docker_json",
        lambda args: image if args[:2] == ["image", "inspect"] else container,
    )

    MODULE.export(
        image_name="eln-backend:latest",
        container_name="eln-backend-1",
        backend_url="http://backend",
        output_dir=output_dir,
    )

    payload = json.loads((output_dir / "runtime-config-latest.json").read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "SECRET_KEY" not in serialized
    assert "SECRET_TOKEN" not in serialized
    assert "unknown" not in payload
    assert payload["source"] == {"dockerfile_sha256": MODULE.sha256_bytes((MODULE.ROOT / "backend" / "Dockerfile").read_bytes())}
    assert payload["endpoint_observation"]["ready"]["checks"] == {"database": "ok"}
    assert payload["endpoint_observation"]["metrics"]["runtime"] == {"api_runtime": "rust-axum"}


def test_export_embeds_recomputable_resolved_compose_projection(tmp_path: Path, monkeypatch) -> None:
    head = "a" * 40
    image = image_fixture()
    image["Config"]["Labels"]["org.opencontainers.image.revision"] = head
    output_dir = tmp_path / "system-evidence"
    output_dir.mkdir()
    compose = compose_fixture(head)

    monkeypatch.setattr(MODULE, "checkout_revision", lambda: head)
    monkeypatch.setattr(MODULE, "compose_config", lambda _head: json.dumps(compose).encode("utf-8"))
    monkeypatch.setattr(
        MODULE,
        "fetch_json",
        lambda url: {"status": "ready", "revision": head}
        if url.endswith("/ready")
        else {"status": "ok", "revision": head, "runtime": {"api_runtime": "rust-axum"}},
    )
    monkeypatch.setattr(
        MODULE,
        "docker_json",
        lambda args: image if args[:2] == ["image", "inspect"] else container_fixture(),
    )

    MODULE.export(
        image_name="eln-backend:latest",
        container_name="eln-backend-1",
        backend_url="http://backend",
        output_dir=output_dir,
    )

    payload = json.loads((output_dir / "runtime-config-latest.json").read_text(encoding="utf-8"))
    resolved = payload["config_sources"]["resolved_compose"]
    projection = resolved["projection"]
    canonical = MODULE.canonical_json(projection)
    assert resolved["canonical_bytes"] == len(canonical)
    assert resolved["canonical_sha256"] == MODULE.sha256_bytes(canonical)
    assert resolved["projection_schema"] == MODULE.COMPOSE_PROJECTION_SCHEMA
    assert "sha256" not in resolved
    assert "raw_path" not in resolved
    assert "retained" not in resolved
