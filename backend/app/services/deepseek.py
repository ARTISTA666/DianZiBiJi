from __future__ import annotations

import asyncio
import json
import logging
from threading import Lock
from time import perf_counter
from typing import Any

import httpx

from app.core.config import get_settings

llm_logger = logging.getLogger("eln.llm")
deepseek_logger = logging.getLogger("eln.deepseek")

# Global gate so concurrent Agent/RAG requests cannot exhaust the provider
# quota; recreated when the running event loop changes (tests use asyncio.run).
_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None

# Reusable httpx.AsyncClient with connection-pool limits.
# Recreated when the running event loop changes so tests stay safe.
_http_client: httpx.AsyncClient | None = None
_http_client_loop: asyncio.AbstractEventLoop | None = None
_HTTP_TIMEOUT = httpx.Timeout(180, connect=30)
_HTTP_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

_usage_lock = Lock()
_usage_totals = {
    "requests": 0,
    "failures": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
}


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        limit = int(getattr(get_settings(), "deepseek_max_concurrency", 4) or 4)
        _semaphore = asyncio.Semaphore(max(1, limit))
        _semaphore_loop = loop
    return _semaphore


def _record_usage(usage: dict[str, Any] | None, *, failed: bool) -> None:
    with _usage_lock:
        _usage_totals["requests"] += 1
        if failed:
            _usage_totals["failures"] += 1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                _usage_totals[key] += int((usage or {}).get(key) or 0)
            except (TypeError, ValueError):
                continue


async def _get_http_client() -> httpx.AsyncClient:
    """Return a process-wide ``httpx.AsyncClient``, creating it lazily.

    The client is bound to the running event loop; if the loop changes
    (e.g. between ``asyncio.run`` calls in tests) a fresh client is created
    and the stale one is silently discarded.
    """
    global _http_client, _http_client_loop
    loop = asyncio.get_running_loop()
    if _http_client is None or _http_client_loop is not loop:
        if _http_client is not None:
            deepseek_logger.warning("Event loop changed; recreating httpx.AsyncClient.")
            try:
                await _http_client.aclose()
            except Exception:  # noqa: BLE001
                pass
        else:
            deepseek_logger.debug("Creating initial httpx.AsyncClient.")
        _http_client = httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            limits=_HTTP_LIMITS,
            http2=False,
        )
        _http_client_loop = loop
    return _http_client


async def aclose() -> None:
    """Close the shared HTTP client. Safe to call multiple times."""
    global _http_client, _http_client_loop
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        _http_client_loop = None


def usage_snapshot() -> dict[str, int]:
    with _usage_lock:
        return dict(_usage_totals)


def should_retry_status(status_code: int) -> bool:
    return status_code in {408, 425, 429} or 500 <= status_code <= 599


def parse_completion_response(response: httpx.Response, fallback_model: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise DeepSeekRequestError("DeepSeek returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise DeepSeekRequestError("DeepSeek returned invalid JSON")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DeepSeekRequestError("DeepSeek did not return a completion")
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    answer = str(message.get("content") or "").strip()
    if not answer:
        raise DeepSeekRequestError("DeepSeek returned an empty completion")
    provider_usage = data.get("usage")
    usage = (
        provider_usage
        if isinstance(provider_usage, dict)
        else {} if provider_usage is None else {"provider_usage": provider_usage}
    )
    return {
        "answer": answer,
        "request_id": response.headers.get("x-request-id") or data.get("id"),
        "model": data.get("model") or fallback_model,
        "usage": usage,
    }


class DeepSeekConfigError(RuntimeError):
    pass


class DeepSeekRequestError(RuntimeError):
    pass


class DeepSeekClient:
    """Small OpenAI-compatible client with explicit configuration failures."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.deepseek_api_base_url.rstrip("/")
        self.api_key = settings.deepseek_api_key.strip()
        self.model = settings.normalized_deepseek_model
        if not self.api_key:
            raise DeepSeekConfigError("DEEPSEEK_API_KEY is not configured")
        if not self.model:
            raise DeepSeekConfigError("DEEPSEEK_MODEL is not configured")

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1800,
    ) -> dict[str, Any]:
        started = perf_counter()
        async with _get_semaphore():
            try:
                result = await self._request(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                _record_usage(None, failed=True)
                llm_logger.warning(
                    json.dumps(
                        {
                            "event": "llm_failure",
                            "model": self.model,
                            "duration_ms": round((perf_counter() - started) * 1000),
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:500],
                        },
                        separators=(",", ":"),
                    )
                )
                raise
        usage = result.get("usage") or {}
        _record_usage(usage, failed=False)
        llm_logger.info(
            json.dumps(
                {
                    "event": "llm_completion",
                    "model": result.get("model"),
                    "request_id": result.get("request_id"),
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                },
                separators=(",", ":"),
            )
        )
        return result

    async def _request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        response: httpx.Response | None = None
        last_error: Exception | None = None
        client = await _get_http_client()
        for attempt in range(3):
            response = None
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if should_retry_status(response.status_code):
                    last_error = DeepSeekRequestError(
                        f"DeepSeek request failed: {response.status_code}"
                    )
                elif not response.is_success:
                    try:
                        detail = str(response.json())
                    except ValueError:
                        detail = response.text
                    raise DeepSeekRequestError(
                        f"DeepSeek request failed: {response.status_code} {detail[:1000]}"
                    )
                else:
                    try:
                        return parse_completion_response(response, self.model)
                    except DeepSeekRequestError as exc:
                        last_error = exc
            if attempt < 2:
                retry_after = response.headers.get("retry-after") if response is not None else None
                try:
                    delay = min(30.0, max(0.0, float(retry_after))) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
                await asyncio.sleep(delay)
        if response is not None and not response.is_success:
            try:
                detail = str(response.json())
            except ValueError:
                detail = response.text
            raise DeepSeekRequestError(f"DeepSeek request failed: {response.status_code} {detail[:1000]}")
        error_detail = (
            f"{type(last_error).__name__}: {str(last_error).strip() or repr(last_error)}"
            if last_error is not None
            else "unknown transport error"
        )
        raise DeepSeekRequestError(
            f"DeepSeek request failed after 3 attempts: {error_detail}"
        ) from last_error
