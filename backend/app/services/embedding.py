from __future__ import annotations

import asyncio
from functools import lru_cache

from app.core.config import get_settings


class EmbeddingServiceError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimension
        self.cache_dir = settings.embedding_cache_path

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text])
        if not vectors:
            raise EmbeddingServiceError("Embedding backend returned no query vector")
        return vectors[0]

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = await asyncio.to_thread(
                _encode,
                texts,
                self.model,
                self.cache_dir,
                self.dimensions,
            )
        except Exception as exc:
            raise EmbeddingServiceError(f"Embedding failed: {exc}") from exc
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                raise EmbeddingServiceError(
                    f"Embedding dimension mismatch: expected {self.dimensions}"
                )
        return vectors


@lru_cache(maxsize=1)
def _model(model_name: str, cache_dir: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=4)


def _encode(texts: list[str], model_name: str, cache_dir: str, dimensions: int) -> list[list[float]]:
    import numpy as np

    vectors = np.asarray(list(_model(model_name, cache_dir).embed(texts, batch_size=min(16, len(texts)))))
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = vectors / np.maximum(norms, 1e-12)
    if normalized.shape[1] != dimensions:
        raise EmbeddingServiceError(
            f"Embedding dimension mismatch: expected {dimensions}, got {normalized.shape[1]}"
        )
    return normalized.tolist()
