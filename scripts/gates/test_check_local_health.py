from __future__ import annotations

import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("check_local_health", Path(__file__).with_name("check_local_health.py"))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def probe(status: int, payload: dict) -> dict:
    return {"url": "http://example.test", "status": status, "payload": payload, "error": None}


def healthy_probes() -> tuple[dict, dict, dict]:
    return (
        probe(200, {"status": "ready", "checks": {"database": "ok", "storage": "ok"}, "revision": "a" * 40}),
        probe(
            200,
            {
                "status": "ok",
                "revision": "a" * 40,
                "runtime": {
                    "api_runtime": "rust-axum",
                    "embedding_backend": "hash",
                    "embedding_model": "rust-hash-512-v1",
                    "embedding_dimension": 512,
                },
            },
        ),
        probe(200, {}),
    )


def test_evaluate_marks_local_stack_ready_but_dev_not_production() -> None:
    result = MODULE.evaluate(*healthy_probes(), {"APP_ENV": "development"})

    assert result["local_ready"] is True
    assert result["production_readiness"]["status"] == "not_production_mode"
    assert all(item["passed"] for item in result["checks"])


def test_evaluate_detects_storage_failure_without_calling_it_production_ready() -> None:
    ready, metrics, frontend = healthy_probes()
    ready["payload"]["checks"]["storage"] = "error"

    result = MODULE.evaluate(ready, metrics, frontend, {"APP_ENV": "production", "SEED_DEMO_DATA": "false"})

    assert result["local_ready"] is False
    assert result["status"] == "blocked"
    assert result["production_readiness"]["status"] == "blocked"
    assert any(item["name"] == "持久化存储" and not item["passed"] for item in result["checks"])


def test_render_human_is_secret_free_and_actionable() -> None:
    result = MODULE.evaluate(*healthy_probes(), {"APP_ENV": "development", "DEEPSEEK_API_KEY": "do-not-print"})

    rendered = MODULE.render_human(result)
    assert "本地自检：通过" in rendered
    assert "生产判断：not_production_mode" in rendered
    assert "do-not-print" not in rendered


def test_evaluate_detects_loopback_host_mismatch_before_browser_login() -> None:
    result = MODULE.evaluate(
        *healthy_probes(),
        {"APP_ENV": "development"},
        frontend_base="http://127.0.0.1:3000",
        configured_api_base="http://localhost:8001",
    )

    assert result["local_ready"] is False
    assert any(item["name"] == "前端/API host 一致" and not item["passed"] for item in result["checks"])


def test_evaluate_rejects_runtime_from_another_checkout() -> None:
    result = MODULE.evaluate(
        *healthy_probes(),
        {"APP_ENV": "development"},
        expected_revision="b" * 40,
    )

    assert result["local_ready"] is False
    assert any(item["name"] == "编译 revision 已绑定" and not item["passed"] for item in result["checks"])
