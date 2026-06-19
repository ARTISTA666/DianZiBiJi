from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings


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
        for attempt in range(3):
            try:
                timeout = httpx.Timeout(180, connect=30)
                async with httpx.AsyncClient(timeout=timeout, http2=False) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                if response.status_code != 429 and response.status_code < 500:
                    break
            except httpx.HTTPError as exc:
                last_error = exc
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        if response is None:
            raise DeepSeekRequestError(f"DeepSeek request failed after 3 attempts: {last_error}") from last_error
        if not response.is_success:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise DeepSeekRequestError(f"DeepSeek request failed: {response.status_code} {detail}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise DeepSeekRequestError("DeepSeek did not return a completion")
        message = choices[0].get("message") or {}
        return {
            "answer": str(message.get("content") or ""),
            "request_id": response.headers.get("x-request-id") or data.get("id"),
            "model": data.get("model") or self.model,
            "usage": data.get("usage") or {},
        }
