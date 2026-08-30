#!/usr/bin/env python3
"""Run a safe, read-only health check for a local ELN deployment.

The command intentionally separates "the local stack is usable" from
"production configuration is complete".  Development defaults can therefore
be used for a quick smoke check without being reported as production-ready.
No secret values are emitted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"
REVISION_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def read_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fetch(url: str, timeout: float) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "eln-local-health-check/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            payload: object = {}
            if "json" in content_type:
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = {}
            return {"url": url, "status": response.status, "payload": payload, "error": None}
    except urllib.error.HTTPError as exc:
        return {"url": url, "status": exc.code, "payload": {}, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a health check must report all probe failures
        return {"url": url, "status": None, "payload": {}, "error": str(exc)}


def check_result(name: str, passed: bool, detail: str, *, severity: str = "error") -> dict[str, object]:
    return {"name": name, "passed": passed, "severity": severity, "detail": detail}


def checkout_revision() -> str | None:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD^{commit}"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip().lower()
    return revision if result.returncode == 0 and REVISION_PATTERN.fullmatch(revision) else None


def evaluate_host_consistency(frontend_base: str, configured_api_base: str) -> tuple[bool, str]:
    frontend_host = urlparse(frontend_base).hostname
    api_host = urlparse(configured_api_base).hostname
    if not frontend_host or not api_host:
        return False, "前端入口或前端 API 地址缺少有效 hostname"
    if frontend_host == api_host:
        return True, f"frontend={frontend_host} / api={api_host}"
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    if frontend_host in loopback_hosts and api_host in loopback_hosts:
        return False, f"loopback host 不一致：frontend={frontend_host} / api={api_host}；请统一使用 localhost 或 127.0.0.1"
    return False, f"host 不一致：frontend={frontend_host} / api={api_host}"


def evaluate(
    ready_probe: dict[str, object],
    metrics_probe: dict[str, object],
    frontend_probe: dict[str, object],
    env: dict[str, str],
    *,
    frontend_base: str = "http://localhost:3000",
    configured_api_base: str = "http://localhost:8001",
    expected_revision: str | None = None,
) -> dict[str, object]:
    ready = ready_probe.get("payload") if isinstance(ready_probe.get("payload"), dict) else {}
    ready_checks = ready.get("checks") if isinstance(ready.get("checks"), dict) else {}
    metrics = metrics_probe.get("payload") if isinstance(metrics_probe.get("payload"), dict) else {}
    runtime = metrics.get("runtime") if isinstance(metrics.get("runtime"), dict) else {}
    ready_revision = ready.get("revision")
    metrics_revision = metrics.get("revision")
    revisions_match = (
        isinstance(ready_revision, str)
        and isinstance(metrics_revision, str)
        and bool(REVISION_PATTERN.fullmatch(ready_revision.lower()))
        and ready_revision.lower() == metrics_revision.lower()
    )
    checkout_match = (
        expected_revision is None
        or (
            revisions_match
            and isinstance(ready_revision, str)
            and ready_revision.lower() == expected_revision.lower()
        )
    )

    checks = [
        check_result(
            "Rust API 就绪",
            ready_probe.get("status") == 200 and ready.get("status") == "ready",
            f"HTTP {ready_probe.get('status') or '不可达'} / status={ready.get('status', 'unknown')}",
        ),
        check_result(
            "PostgreSQL",
            ready_checks.get("database") == "ok",
            f"database={ready_checks.get('database', 'unknown')}",
        ),
        check_result(
            "持久化存储",
            ready_checks.get("storage") == "ok",
            f"storage={ready_checks.get('storage', 'unknown')}",
        ),
        check_result(
            "前端首页",
            frontend_probe.get("status") == 200,
            f"HTTP {frontend_probe.get('status') or '不可达'}",
        ),
        check_result(
            "前端/API host 一致",
            *evaluate_host_consistency(frontend_base, configured_api_base),
        ),
        check_result(
            "运行指标",
            metrics_probe.get("status") == 200 and metrics.get("status") == "ok",
            f"HTTP {metrics_probe.get('status') or '不可达'} / status={metrics.get('status', 'unknown')}",
        ),
        check_result(
            "Axum 对外运行时",
            runtime.get("api_runtime") == "rust-axum",
            f"api_runtime={runtime.get('api_runtime', 'unknown')}",
        ),
        check_result(
            "编译 revision 已绑定",
            checkout_match,
            f"ready={ready_revision or 'unknown'} / metrics={metrics_revision or 'unknown'} / checkout={expected_revision or 'not checked'}",
        ),
    ]

    app_env = env.get("APP_ENV") or os.environ.get("APP_ENV", "development")
    production_checks = {
        "APP_ENV=production": app_env == "production",
        "SEED_DEMO_DATA=false": env.get("SEED_DEMO_DATA", "").lower() == "false",
        "endpoint 编译 revision 已绑定": checkout_match,
        "DeepSeek API key 已配置": bool(env.get("DEEPSEEK_API_KEY", "").strip()),
        "生产 embedding=OpenAI-compatible/BAAI/bge-m3/1024": (
            env.get("EMBEDDING_BACKEND") == "openai_compatible"
            and env.get("EMBEDDING_MODEL") == "BAAI/bge-m3"
            and env.get("EMBEDDING_DIMENSION") == "1024"
        ),
    }
    if app_env != "production":
        production_status = "not_production_mode"
        production_note = f"当前 APP_ENV={app_env}，未执行生产发布判断。"
    else:
        production_status = "passed" if all(production_checks.values()) else "blocked"
        production_note = "生产配置静态检查通过。" if production_status == "passed" else "生产配置仍有未满足项。"

    local_ready = all(bool(item["passed"]) for item in checks)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_ready": local_ready,
        "status": "ready" if local_ready else "blocked",
        "build_revision": expected_revision or None,
        "app_revision": ready_revision,
        "runtime_revision": metrics_revision,
        "secrets_disclosed": False,
        "app_env": app_env,
        "production_readiness": {
            "status": production_status,
            "note": production_note,
            "checks": production_checks,
        },
        "runtime": {
            "api_runtime": runtime.get("api_runtime"),
            "revision": metrics.get("revision"),
            "embedding_backend": runtime.get("embedding_backend"),
            "embedding_model": runtime.get("embedding_model"),
            "embedding_dimension": runtime.get("embedding_dimension"),
        },
        "checks": checks,
        "sources": {
            "ready": ready_probe.get("url"),
            "metrics": metrics_probe.get("url"),
            "frontend": frontend_probe.get("url"),
        },
    }


def run(
    api_base: str,
    frontend_base: str,
    env_file: Path | None = None,
    timeout: float = 5,
    output: Path | None = None,
    expected_runtime_revision: str | None = None,
    tooling_revision: str | None = None,
) -> dict[str, object]:
    api_root = api_base.rstrip("/") + "/"
    frontend_root = frontend_base.rstrip("/") + "/"
    result = evaluate(
        fetch(urljoin(api_root, "ready"), timeout),
        fetch(urljoin(api_root, "metrics"), timeout),
        fetch(frontend_root, timeout),
        read_env_file(env_file),
        frontend_base=frontend_base,
        configured_api_base=(read_env_file(env_file).get("NEXT_PUBLIC_API_BASE_URL") if env_file else None)
        or os.environ.get("NEXT_PUBLIC_API_BASE_URL")
        or api_base,
        expected_revision=expected_runtime_revision or checkout_revision() or "",
    )
    result["runtime_source_revision"] = expected_runtime_revision or result["app_revision"]
    result["experiment_tooling_revision"] = tooling_revision or checkout_revision()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def render_human(result: dict[str, object]) -> str:
    lines = [
        f"本地自检：{'通过' if result.get('local_ready') else '失败'}",
        f"运行模式：{result.get('app_env', 'unknown')}",
    ]
    for item in result.get("checks", []):
        marker = "通过" if item.get("passed") else "失败"
        lines.append(f"[{marker}] {item.get('name')}: {item.get('detail')}")
    production = result.get("production_readiness", {})
    lines.append(f"生产判断：{production.get('status', 'unknown')}（{production.get('note', '')}）")
    if production.get("status") == "blocked":
        failed = [name for name, passed in production.get("checks", {}).items() if not passed]
        lines.append("生产未满足项：" + "、".join(failed))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.environ.get("ELN_API_BASE", "http://localhost:8001"))
    parser.add_argument("--frontend-base", default=os.environ.get("ELN_FRONTEND_BASE", "http://localhost:3000"))
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE if DEFAULT_ENV_FILE.is_file() else None)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-runtime-revision")
    parser.add_argument("--tooling-revision")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--require-production", action="store_true")
    args = parser.parse_args()
    result = run(
        args.api_base,
        args.frontend_base,
        args.env_file,
        args.timeout,
        args.output,
        args.expected_runtime_revision,
        args.tooling_revision,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json_output else render_human(result))
    if not result["local_ready"]:
        return 1
    if args.require_production and result["production_readiness"]["status"] != "passed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
