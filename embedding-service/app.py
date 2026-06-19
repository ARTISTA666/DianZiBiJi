from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI
from fastembed import TextEmbedding
import numpy as np
from pydantic import BaseModel, Field


MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
CACHE_DIR = os.getenv("FASTEMBED_CACHE_PATH", "/models/fastembed")
EXPECTED_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "512"))

app = FastAPI(title="ELN Embedding Service", version="1.0.0")


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=128)
    kind: Literal["query", "document"] = "document"


@lru_cache(maxsize=1)
def get_model() -> TextEmbedding:
    return TextEmbedding(model_name=MODEL_NAME, cache_dir=CACHE_DIR, threads=4)


def encode(texts: list[str]) -> list[list[float]]:
    vectors = np.asarray(list(get_model().embed(texts, batch_size=min(16, len(texts)))))
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = vectors / np.maximum(norms, 1e-12)
    if normalized.shape[1] != EXPECTED_DIMENSIONS:
        raise RuntimeError(
            f"Embedding dimension mismatch: expected {EXPECTED_DIMENSIONS}, got {normalized.shape[1]}"
        )
    return normalized.tolist()


@app.get("/health")
def health() -> dict:
    encode(["health check"])
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "runtime": "fastembed-onnx-cpu",
        "dimensions": EXPECTED_DIMENSIONS,
    }


@app.post("/embed")
def embed(payload: EmbedRequest) -> dict:
    vectors = encode(payload.texts)
    return {
        "model": MODEL_NAME,
        "dimensions": EXPECTED_DIMENSIONS,
        "vectors": vectors,
    }
