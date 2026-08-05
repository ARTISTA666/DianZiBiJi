from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

import app.services.deepseek as deepseek_module
from app.services.deepseek import DeepSeekClient, DeepSeekRequestError, should_retry_status


class FailingAsyncClient:
    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, *_args, **_kwargs):
        raise httpx.ReadError("")


def settings():
    return SimpleNamespace(
        deepseek_api_base_url="https://api.deepseek.com",
        deepseek_api_key="test-key",
        normalized_deepseek_model="test-model",
    )


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(408, True), (425, True), (429, True), (500, True), (599, True), (400, False)],
)
def test_retry_policy_covers_transient_http_statuses(status_code: int, expected: bool) -> None:
    assert should_retry_status(status_code) is expected


def test_transport_error_keeps_exception_type_when_message_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        deepseek_module,
        "get_settings",
        settings,
    )
    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", FailingAsyncClient)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(deepseek_module.asyncio, "sleep", no_sleep)

    with pytest.raises(DeepSeekRequestError, match=r"ReadError: ReadError\(''\)"):
        asyncio.run(
            DeepSeekClient().generate(
                system_prompt="system",
                user_prompt="user",
            )
        )


def test_retries_rate_limit_and_server_error_using_retry_after(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")

    class SequenceAsyncClient:
        responses = [
            httpx.Response(429, headers={"retry-after": "3"}, request=request),
            httpx.Response(503, request=request),
            httpx.Response(
                200,
                request=request,
                json={
                    "id": "request-1",
                    "model": "test-model",
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"total_tokens": 2},
                },
            ),
        ]

        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def post(self, *_args, **_kwargs):
            return self.responses.pop(0)

    sleeps = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(deepseek_module, "get_settings", settings)
    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", SequenceAsyncClient)
    monkeypatch.setattr(deepseek_module.asyncio, "sleep", record_sleep)

    result = asyncio.run(DeepSeekClient().generate(system_prompt="system", user_prompt="user"))

    assert result["answer"] == "ok"
    assert sleeps == [3, 2]


def test_successful_response_must_contain_valid_json(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")

    class InvalidJsonAsyncClient(FailingAsyncClient):
        async def post(self, *_args, **_kwargs):
            return httpx.Response(200, content=b"not-json", request=request)

    monkeypatch.setattr(deepseek_module, "get_settings", settings)
    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", InvalidJsonAsyncClient)

    with pytest.raises(DeepSeekRequestError, match="invalid JSON"):
        asyncio.run(DeepSeekClient().generate(system_prompt="system", user_prompt="user"))


def test_generate_accumulates_usage_and_counts_failures(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")

    class SuccessAsyncClient(FailingAsyncClient):
        async def post(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                request=request,
                json={
                    "id": "request-usage",
                    "model": "test-model",
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
                },
            )

    monkeypatch.setattr(deepseek_module, "get_settings", settings)
    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", SuccessAsyncClient)

    before = deepseek_module.usage_snapshot()
    asyncio.run(DeepSeekClient().generate(system_prompt="system", user_prompt="user"))
    after_success = deepseek_module.usage_snapshot()

    assert after_success["requests"] == before["requests"] + 1
    assert after_success["failures"] == before["failures"]
    assert after_success["prompt_tokens"] == before["prompt_tokens"] + 11
    assert after_success["completion_tokens"] == before["completion_tokens"] + 7
    assert after_success["total_tokens"] == before["total_tokens"] + 18

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", FailingAsyncClient)
    monkeypatch.setattr(deepseek_module.asyncio, "sleep", no_sleep)

    with pytest.raises(DeepSeekRequestError):
        asyncio.run(DeepSeekClient().generate(system_prompt="system", user_prompt="user"))
    after_failure = deepseek_module.usage_snapshot()

    assert after_failure["requests"] == after_success["requests"] + 1
    assert after_failure["failures"] == after_success["failures"] + 1
    assert after_failure["total_tokens"] == after_success["total_tokens"]


def test_generate_limits_provider_concurrency(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    active = {"current": 0, "max": 0}

    class SlowAsyncClient(FailingAsyncClient):
        async def post(self, *_args, **_kwargs):
            active["current"] += 1
            active["max"] = max(active["max"], active["current"])
            await asyncio.sleep(0.01)
            active["current"] -= 1
            return httpx.Response(
                200,
                request=request,
                json={
                    "id": "request-concurrency",
                    "model": "test-model",
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"total_tokens": 1},
                },
            )

    def limited_settings():
        base = settings()
        base.deepseek_max_concurrency = 2
        return base

    monkeypatch.setattr(deepseek_module, "get_settings", limited_settings)
    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", SlowAsyncClient)

    async def run_many() -> None:
        client = DeepSeekClient()
        await asyncio.gather(
            *(client.generate(system_prompt="system", user_prompt="user") for _ in range(6))
        )

    asyncio.run(run_many())

    assert active["max"] <= 2


def test_http_client_closes_stale_loop_client(monkeypatch) -> None:
    clients = []

    class TrackingAsyncClient:
        def __init__(self, **_kwargs) -> None:
            self.closed = False
            clients.append(self)

        async def aclose(self) -> None:
            self.closed = True

    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", TrackingAsyncClient)

    async def get_client():
        return await deepseek_module._get_http_client()

    asyncio.run(get_client())
    asyncio.run(get_client())
    asyncio.run(deepseek_module.aclose())

    assert clients[0].closed is True
