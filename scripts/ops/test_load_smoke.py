from __future__ import annotations

import importlib.util
import sys
import json
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "load_smoke.py"
SPEC = importlib.util.spec_from_file_location("load_smoke", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_summary_uses_nearest_rank_p95_and_keeps_errors() -> None:
    report = MODULE.summarize(list(range(1, 101)), ["one error"])

    assert report == {
        "requests": 101,
        "successful": 100,
        "errors": ["one error"],
        "p95_ms": 95,
        "max_ms": 100,
    }


def test_main_can_write_output_file(tmp_path, monkeypatch) -> None:
    output = tmp_path / "load.json"

    monkeypatch.setattr(
        MODULE,
        "run",
        lambda *_args, **_kwargs: {"requests": 1, "successful": 1, "errors": [], "p95_ms": 1, "max_ms": 1},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["load_smoke.py", "--password", "x", "--output", str(output)],
    )

    assert MODULE.main() == 0
    assert '"p95_ms": 1' in output.read_text(encoding="utf-8")


def test_run_keeps_each_attempt_including_http_failure_and_timeout(monkeypatch) -> None:
    def handle(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "local-test-token"})
        if request.url.path == "/projects":
            raise httpx.ReadTimeout("local timeout", request=request)
        status = 503 if request.url.path == "/ready" else 200
        return httpx.Response(status, headers={"x-request-id": request.headers["x-request-id"]})

    client_type = httpx.Client
    monkeypatch.setattr(MODULE.httpx, "Client", lambda **kwargs: client_type(**kwargs, transport=httpx.MockTransport(handle)))
    report = MODULE.run("http://local.test", "admin", "dummy", 3, 1)

    assert len(report["records"]) == 3
    assert report["successful"] == 1
    assert [r["status_code"] for r in report["records"]] == [200, 503, None]
    assert "ReadTimeout" in report["records"][2]["error"]
    assert all(r["monotonic_end"] >= r["monotonic_start"] and r["latency_ms"] >= 0 for r in report["records"])
    assert len({r["request_id"] for r in report["records"]}) == 3
    assert report["latency_population"] == "all_attempts"
    assert "local-test-token" not in json.dumps(report)


def test_request_plan_rejects_absolute_url_before_login() -> None:
    with pytest.raises(ValueError, match="relative"):
        MODULE.run("http://local.test", "admin", "dummy", 1, 1,
                   request_plan=[{"path": "https://elsewhere.test/projects"}])


def test_main_writes_raw_jsonl_without_overwriting_previous_batch(tmp_path, monkeypatch) -> None:
    output = tmp_path / "requests.jsonl"
    records = [{"request_id": "batch-0", "latency_ms": 1, "error": None}]
    monkeypatch.setattr(MODULE, "run", lambda *_args, **_kwargs: {
        "requests": 1, "successful": 1, "errors": [], "p95_ms": 1, "max_ms": 1, "records": records})
    monkeypatch.setattr(sys, "argv", ["load_smoke.py", "--password", "dummy", "--raw-output", str(output)])
    assert MODULE.main() == 0
    assert [json.loads(line) for line in output.read_text().splitlines()] == records
    with pytest.raises(FileExistsError):
        MODULE.main()
