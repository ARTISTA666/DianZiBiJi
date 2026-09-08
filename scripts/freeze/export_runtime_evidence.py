#!/usr/bin/env python3
"""Export secret-free, deterministic runtime and image identity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "system-evidence"
PROJECTION_SCHEMA = "full-system.rust-runtime-projection-v1"
COMPOSE_PROJECTION_SCHEMA = "full-system.rust-resolved-compose-projection-v1"
REVISION_FIELDS = ("org.opencontainers.image.revision", "org.opencontainers.image.source")
RUNTIME_FIELDS = ("api_runtime", "embedding_backend", "embedding_model", "embedding_dimension")
READY_CHECK_FIELDS = ("database", "storage")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} did not return a JSON object")
    return payload


def docker_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"docker command failed: {' '.join(args)}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"docker command returned invalid JSON: {' '.join(args)}") from exc
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise RuntimeError(f"docker command returned no inspect object: {' '.join(args)}")
    return payload[0]


def compose_config(head: str) -> bytes:
    runner = ROOT / "scripts" / "docker-compose-with-revision.sh"
    result = subprocess.run(
        [str(runner), "config", "--format", "json"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("revision-bound Compose wrapper failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("revision-bound Compose wrapper returned invalid JSON") from exc
    services = payload.get("services")
    backend = services.get("backend") if isinstance(services, dict) else None
    build = backend.get("build") if isinstance(backend, dict) else None
    build_args = build.get("args") if isinstance(build, dict) else None
    if not isinstance(build_args, dict) or build_args.get("BUILD_REVISION") != head:
        raise RuntimeError("Compose backend build arg is not bound to checkout HEAD")
    return result.stdout


def checkout_revision() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD^{commit}"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip().lower()
    if result.returncode or len(revision) not in (40, 64) or any(c not in "0123456789abcdef" for c in revision):
        raise RuntimeError("checkout HEAD is not a full hexadecimal revision")
    return revision


def image_projection(image: dict[str, Any]) -> dict[str, Any]:
    config = image.get("Config") if isinstance(image.get("Config"), dict) else {}
    labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
    return {
        "Id": image.get("Id"),
        "RepoDigests": sorted(value for value in image.get("RepoDigests", []) if isinstance(value, str)),
        "Architecture": image.get("Architecture"),
        "Os": image.get("Os"),
        "RootFS": {"Layers": image.get("RootFS", {}).get("Layers", []) if isinstance(image.get("RootFS"), dict) else []},
        "Config": {
            key: config.get(key)
            for key in ("Entrypoint", "Cmd", "WorkingDir", "User")
        },
        "Labels": {key: labels[key] for key in REVISION_FIELDS if key in labels},
    }


def container_projection(container: dict[str, Any]) -> dict[str, Any]:
    config = container.get("Config") if isinstance(container.get("Config"), dict) else {}
    labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
    return {
        "Image": container.get("Image"),
        "Compose": {
            key: labels.get(key)
            for key in ("com.docker.compose.project", "com.docker.compose.service")
            if labels.get(key) is not None
        },
        "Path": container.get("Path"),
        "Args": container.get("Args", []),
        "Entrypoint": config.get("Entrypoint"),
        "Cmd": config.get("Cmd"),
    }


def projection_hash(projection: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(projection))


def immutable_image_digest(image: dict[str, Any]) -> tuple[str, str, list[str]]:
    image_id = image.get("Id")
    if not isinstance(image_id, str) or not SHA256_PATTERN.fullmatch(image_id):
        raise RuntimeError("image Id must be a sha256 content ID")
    repo_digests = sorted(value for value in image.get("RepoDigests", []) if isinstance(value, str))
    for value in repo_digests:
        if "@" not in value or not SHA256_PATTERN.fullmatch(value.rsplit("@", 1)[-1]):
            raise RuntimeError("RepoDigests must contain sha256 immutable digests")
    return (repo_digests[0].rsplit("@", 1)[-1] if repo_digests else image_id, image_id, repo_digests)


def registry_repo_digest(repo_digests: list[str]) -> str | None:
    for value in repo_digests:
        repository, _, _digest = value.rpartition("@")
        registry = repository.split("/", 1)[0]
        if "." in registry or ":" in registry or registry == "localhost":
            return value
    return None


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    temporary.replace(path)


def runtime_projection(metrics: dict[str, Any]) -> dict[str, Any]:
    runtime = metrics.get("runtime") if isinstance(metrics.get("runtime"), dict) else {}
    return {key: runtime[key] for key in RUNTIME_FIELDS if key in runtime}


def endpoint_observation(ready: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    checks = ready.get("checks") if isinstance(ready.get("checks"), dict) else {}
    return {
        "ready": {
            "status": ready.get("status"),
            "checks": {key: checks[key] for key in READY_CHECK_FIELDS if key in checks},
            "revision": ready.get("revision"),
        },
        "metrics": {
            "status": metrics.get("status"),
            "revision": metrics.get("revision"),
            "runtime": runtime_projection(metrics),
        },
    }


def _repository_relative_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(ROOT.resolve())
        except ValueError:
            return None
    normalized = path.as_posix()
    if normalized == "" or normalized == ".." or normalized.startswith("../"):
        return None
    return normalized


def _compose_ports(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    ports: list[Any] = []
    for port in value:
        if isinstance(port, dict):
            projected = {
                key: port[key]
                for key in ("mode", "target", "published", "protocol", "host_ip")
                if key in port
            }
            if projected:
                ports.append(projected)
        elif isinstance(port, str):
            ports.append(port)
    return sorted(ports, key=lambda item: canonical_json(item))


def _compose_healthcheck(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    projected: dict[str, Any] = {}
    for key in ("test", "interval", "timeout", "retries", "start_period", "start_interval", "disable"):
        candidate = value.get(key)
        if key == "test" and isinstance(candidate, list) and all(isinstance(item, str) for item in candidate):
            projected[key] = candidate
        elif key == "disable" and isinstance(candidate, bool):
            projected[key] = candidate
        elif key in ("interval", "timeout", "start_period", "start_interval") and isinstance(candidate, str):
            projected[key] = candidate
        elif key == "retries" and isinstance(candidate, int):
            projected[key] = candidate
    return projected or None


def resolved_compose_projection(config: dict[str, Any], expected_revision: str) -> dict[str, Any]:
    services = config.get("services")
    if not isinstance(services, dict):
        raise RuntimeError("resolved Compose config has no services object")
    projected_services: dict[str, Any] = {}
    for service_name in sorted(name for name in services if isinstance(name, str)):
        service = services[service_name]
        if not isinstance(service, dict):
            continue
        projected: dict[str, Any] = {}
        image = service.get("image")
        if isinstance(image, str):
            projected["image"] = image
        build = service.get("build")
        if isinstance(build, dict):
            build_projection: dict[str, Any] = {}
            context = _repository_relative_path(build.get("context"))
            dockerfile = _repository_relative_path(build.get("dockerfile"))
            if build.get("context") is not None and context is None:
                raise RuntimeError(f"build context for {service_name} is outside the repository")
            if build.get("dockerfile") is not None and dockerfile is None:
                raise RuntimeError(f"Dockerfile for {service_name} is outside the repository")
            if context is not None:
                build_projection["context"] = context
            if dockerfile is not None:
                build_projection["dockerfile"] = dockerfile
            args = build.get("args")
            if isinstance(args, dict) and isinstance(args.get("BUILD_REVISION"), str):
                build_projection["build_revision"] = args["BUILD_REVISION"]
            if build_projection:
                projected["build"] = build_projection
        ports = _compose_ports(service.get("ports"))
        if ports:
            projected["ports"] = ports
        healthcheck = _compose_healthcheck(service.get("healthcheck"))
        if healthcheck is not None:
            projected["healthcheck"] = healthcheck
        projected_services[service_name] = projected
    if not projected_services:
        raise RuntimeError("resolved Compose config has no projectable services")
    return {
        "schema": COMPOSE_PROJECTION_SCHEMA,
        "build_revision": expected_revision,
        "services": projected_services,
    }


def export(
    *, image_name: str, container_name: str, backend_url: str, output_dir: Path
) -> dict[str, Any]:
    head = checkout_revision()
    resolved_compose = compose_config(head)
    try:
        resolved_compose_payload = json.loads(resolved_compose.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("revision-bound Compose output is not valid UTF-8 JSON") from exc
    if not isinstance(resolved_compose_payload, dict):
        raise RuntimeError("revision-bound Compose output is not a JSON object")
    resolved_compose_projection_value = resolved_compose_projection(resolved_compose_payload, head)
    resolved_compose_canonical = canonical_json(resolved_compose_projection_value)
    ready = fetch_json(urljoin(backend_url.rstrip("/") + "/", "ready"))
    metrics = fetch_json(urljoin(backend_url.rstrip("/") + "/", "metrics"))
    endpoint_revision = ready.get("revision")
    if ready.get("status") != "ready" or metrics.get("status") != "ok":
        raise RuntimeError("/ready and /metrics must be healthy")
    if not isinstance(endpoint_revision, str) or endpoint_revision != metrics.get("revision"):
        raise RuntimeError("/ready and /metrics revisions must match")
    image = docker_json(["image", "inspect", image_name])
    container = docker_json(["inspect", container_name])
    image_projection_value = image_projection(image)
    container_projection_value = container_projection(container)
    image_projection_sha = projection_hash(image_projection_value)
    container_projection_sha = projection_hash(container_projection_value)
    _selected_digest, image_id, repo_digests = immutable_image_digest(image)
    registry_digest = registry_repo_digest(repo_digests)
    image_digest = image_id
    oci_revision = image_projection_value["Labels"].get("org.opencontainers.image.revision")
    # R identifies the deployed runtime source (endpoint + OCI image).  T is
    # only the clean checkout used to resolve the experiment tooling/Compose
    # input and is intentionally allowed to differ from R.
    if not isinstance(oci_revision, str) or oci_revision != endpoint_revision:
        raise RuntimeError("OCI revision label and endpoint runtime source revision must match")
    if container.get("Image") != image_id:
        raise RuntimeError("container image ID does not match inspected image ID")
    runtime = runtime_projection(metrics)
    endpoint_observation_value = endpoint_observation(ready, metrics)
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = output_dir / "runtime-config-latest.json"
    compose_path = ROOT / "docker-compose.yml"
    dockerfile_path = ROOT / "backend" / "Dockerfile"
    config_sources = {
        "compose_file": {
            "bytes": compose_path.stat().st_size,
            "path": "docker-compose.yml",
            "sha256": sha256_bytes(compose_path.read_bytes()),
        },
        "resolved_compose": {
            "projection_schema": COMPOSE_PROJECTION_SCHEMA,
            "projection": resolved_compose_projection_value,
            "canonical_bytes": len(resolved_compose_canonical),
            "canonical_sha256": sha256_bytes(resolved_compose_canonical),
            "build_revision": head,
            "experiment_tooling_revision": head,
        },
    }
    runtime_config = {
        "config_sources": config_sources,
        "schema": "full-system.rust-runtime-config-evidence",
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "build_revision": endpoint_revision,
        "runtime_source_revision": endpoint_revision,
        "app_revision": endpoint_revision,
        "runtime_revision": endpoint_revision,
        "experiment_tooling_revision": head,
        "runtime": "rust-axum",
        "secrets_disclosed": False,
        "container_inspect_projection": {
            "schema": PROJECTION_SCHEMA,
            "projection": container_projection_value,
            "projection_sha256": container_projection_sha,
        },
        "endpoint_observation": endpoint_observation_value,
        "source": {
            "dockerfile_sha256": sha256_bytes(dockerfile_path.read_bytes()),
        },
    }
    container_image = {
        "schema": "full-system.rust-container-image-evidence",
        "schema_version": 2,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "build_revision": endpoint_revision,
        "runtime_source_revision": endpoint_revision,
        "app_revision": endpoint_revision,
        "runtime_revision": endpoint_revision,
        "experiment_tooling_revision": head,
        "runtime": "rust-axum",
        "secrets_disclosed": False,
        "image_digest": image_digest,
        "registry_repo_digest": registry_digest,
        "digest_scope": "local_image_content_id",
        "oci_revision": oci_revision,
        "endpoint_revision": endpoint_revision,
        "projection_schema": PROJECTION_SCHEMA,
        "projection": image_projection_value,
        "projection_sha256": image_projection_sha,
        "image": {
            "name": image_name,
            "image_id": image_id,
            "image_digest": image_digest,
            "registry_repo_digest": registry_digest,
            "repo_digests": repo_digests,
        },
        "container": {
            "image_id_observed": container.get("Image"),
        },
        "container_projection_sha256": container_projection_sha,
        "endpoint_observation": endpoint_observation_value,
        "source": {"image_inspect": f"docker image inspect {image_name}", "container_inspect": f"docker inspect {container_name}"},
    }
    atomic_write(config_path, runtime_config)
    atomic_write(output_dir / "container-image-latest.json", container_image)
    return {
        "runtime_source_revision": endpoint_revision,
        "app_revision": endpoint_revision,
        "build_revision": endpoint_revision,
        "runtime_revision": endpoint_revision,
        "experiment_tooling_revision": head,
        "oci_revision": oci_revision,
        "endpoint_revision": endpoint_revision,
        "image_digest": image_digest,
        "image_projection_sha256": image_projection_sha,
        "container_projection_sha256": container_projection_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="eln-backend:latest")
    parser.add_argument("--container", default="eln-backend-1")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    try:
        print(json.dumps(export(image_name=args.image, container_name=args.container, backend_url=args.backend_url, output_dir=args.output_dir), ensure_ascii=False, sort_keys=True))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Runtime evidence export failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
