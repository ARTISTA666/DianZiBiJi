from __future__ import annotations

import asyncio
import hashlib
import math
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
            if self.model == "rust-hash-512-v1":
                vectors = await asyncio.to_thread(_hash_encode, texts, self.dimensions)
            else:
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


def _hash_encode(texts: list[str], dimensions: int) -> list[list[float]]:
    """Match the Rust ``rust-hash-512-v1`` embedding backend."""
    size = max(1, dimensions)
    encoded: list[list[float]] = []
    for text in texts:
        lowered = text.lower()
        tokens: list[str] = []
        current: list[str] = []
        for character in lowered:
            if character.isalnum():
                current.append(character)
            elif current:
                tokens.append("".join(current))
                current = []
        if current:
            tokens.append("".join(current))
        chinese = "".join(character for character in lowered if "\u4e00" <= character <= "\u9fff")
        tokens.extend(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
        if not tokens and lowered:
            tokens.append(lowered)

        vector = [0.0] * size
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], byteorder="big") % size
            vector[index] += 1.0 if digest[8] & 1 == 0 else -1.0
        norm = max(math.sqrt(sum(value * value for value in vector)), 1e-12)
        encoded.append([value / norm for value in vector])
    return encoded
