from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class EmbeddingServiceError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.embedding_service_url.rstrip("/")
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, kind="document")

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text], kind="query")
        return vectors[0]

    async def _embed(self, texts: list[str], *, kind: str) -> list[list[float]]:
        if not texts:
            return []
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    f"{self.base_url}/embed",
                    json={"texts": texts, "kind": kind},
                )
        except httpx.HTTPError as exc:
            raise EmbeddingServiceError(f"Embedding service unavailable: {exc}") from exc
        if not response.is_success:
            raise EmbeddingServiceError(
                f"Embedding service failed: {response.status_code} {response.text}"
            )
        payload: dict[str, Any] = response.json()
        vectors = payload.get("vectors")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingServiceError("Embedding service returned an invalid vector count")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                raise EmbeddingServiceError(
                    f"Embedding dimension mismatch: expected {self.dimensions}"
                )
        return vectors

