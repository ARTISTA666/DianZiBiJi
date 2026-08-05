from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.embedding import EmbeddingClient, EmbeddingServiceError


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> EmbeddingClient:
    """Return an EmbeddingClient with settings injected, no real model loaded."""
    monkeypatch.setattr(
        "app.services.embedding.get_settings",
        lambda: MagicMock(
            embedding_model="fake-model",
            embedding_dimension=4,
            embedding_cache_path="/tmp/fake-cache",
        ),
    )
    return EmbeddingClient()


# ------------------------------------------------------------------
# 1. Empty text list
# ------------------------------------------------------------------

def test_embed_documents_empty列表返回空结果(client: EmbeddingClient) -> None:
    result = asyncio.run(client.embed_documents([]))
    assert result == []


def test_embed_query_empty_string_still_calls_model(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """embed_query always wraps text into [text], so even '' hits the model."""
    raw = np.array([[0.5, 0.5, 0.5, 0.5]], dtype=np.float32)
    fake_model = MagicMock()
    fake_model.embed.return_value = iter(raw)
    monkeypatch.setattr("app.services.embedding._model", lambda *_: fake_model)

    vec = asyncio.run(client.embed_query(""))

    fake_model.embed.assert_called_once()
    assert len(vec) == 4


def test_embed_query_rejects_empty_backend_result(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.embedding._encode", lambda *_: [])

    with pytest.raises(EmbeddingServiceError, match="no query vector"):
        asyncio.run(client.embed_query("hello"))


# ------------------------------------------------------------------
# 2. Dimension mismatch raises EmbeddingServiceError
# ------------------------------------------------------------------

def test_dimension_mismatch_raises_in_encode(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_encode raises EmbeddingServiceError when model output dims differ from expected."""
    # Return vectors with 3 dims but client expects 4
    bad_vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)

    fake_model = MagicMock()
    fake_model.embed.return_value = iter(bad_vectors)
    monkeypatch.setattr("app.services.embedding._model", lambda *_: fake_model)

    with pytest.raises(EmbeddingServiceError, match="dimension mismatch"):
        asyncio.run(client.embed_documents(["hello"]))


def test_post_encode_dimension_check_in_embed(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_embed performs a secondary dimension check after _encode returns."""
    # Bypass _encode entirely – return wrong-dim vectors directly
    monkeypatch.setattr(
        "app.services.embedding._encode",
        lambda *_: [[0.1, 0.2, 0.3]],  # 3 dims, expected 4
    )

    with pytest.raises(EmbeddingServiceError, match="dimension mismatch"):
        asyncio.run(client.embed_documents(["hello"]))


def test_embed_query_dimension_mismatch(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """embed_query must also raise when model returns wrong-dimension vectors."""
    bad_vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)  # 3 dims, expected 4

    fake_model = MagicMock()
    fake_model.embed.return_value = iter(bad_vectors)
    monkeypatch.setattr("app.services.embedding._model", lambda *_: fake_model)

    with pytest.raises(EmbeddingServiceError, match="dimension mismatch"):
        asyncio.run(client.embed_query("hello"))


# ------------------------------------------------------------------
# 3. Normalized vectors have L2 norm ≈ 1.0
# ------------------------------------------------------------------

def test_embed_documents_returns_normalized_vectors(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = np.array([[3.0, 4.0, 0.0, 0.0], [0.0, 0.0, 5.0, 12.0]], dtype=np.float32)

    fake_model = MagicMock()
    fake_model.embed.return_value = iter(raw)
    monkeypatch.setattr("app.services.embedding._model", lambda *_: fake_model)

    vectors = asyncio.run(client.embed_documents(["a", "b"]))

    assert len(vectors) == 2
    for vec in vectors:
        norm = float(np.linalg.norm(vec))
        assert norm == pytest.approx(1.0, abs=1e-5)


def test_embed_query_returns_single_normalized_vector(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = np.array([[1.0, 1.0, 1.0, 1.0]], dtype=np.float32)

    fake_model = MagicMock()
    fake_model.embed.return_value = iter(raw)
    monkeypatch.setattr("app.services.embedding._model", lambda *_: fake_model)

    vec = asyncio.run(client.embed_query("test"))

    assert len(vec) == 4
    assert float(np.linalg.norm(vec)) == pytest.approx(1.0, abs=1e-5)


# ------------------------------------------------------------------
# 4. Underlying exceptions are wrapped in EmbeddingServiceError
# ------------------------------------------------------------------

def test_model_exception_wrapped(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_model = MagicMock()
    fake_model.embed.side_effect = RuntimeError("GPU out of memory")
    monkeypatch.setattr("app.services.embedding._model", lambda *_: fake_model)

    with pytest.raises(EmbeddingServiceError, match="Embedding failed") as exc_info:
        asyncio.run(client.embed_documents(["test"]))

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "GPU out of memory" in str(exc_info.value.__cause__)


def test_import_error_wrapped(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If fastembed is not installed the ImportError must be wrapped too."""
    fake_model = MagicMock()
    fake_model.embed.side_effect = ImportError("No module named 'fastembed'")
    monkeypatch.setattr("app.services.embedding._model", lambda *_: fake_model)

    with pytest.raises(EmbeddingServiceError, match="Embedding failed") as exc_info:
        asyncio.run(client.embed_documents(["test"]))

    assert isinstance(exc_info.value.__cause__, ImportError)


def test_embed_query_also_wraps_exceptions(
    client: EmbeddingClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_model = MagicMock()
    fake_model.embed.side_effect = ValueError("bad input")
    monkeypatch.setattr("app.services.embedding._model", lambda *_: fake_model)

    with pytest.raises(EmbeddingServiceError):
        asyncio.run(client.embed_query("test"))
