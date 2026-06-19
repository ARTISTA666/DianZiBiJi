from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.file import StoredFile
from app.models.rag import RagDocumentChunk
from app.services.embedding import EmbeddingClient
from app.services.ocr import OcrService


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    file_id: int
    filename: str
    snippet: str
    vector_score: float
    lexical_score: float
    retrieval_score: float

    def as_source(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "file_id": self.file_id,
            "filename": self.filename,
            "snippet": self.snippet,
            "vector_score": round(self.vector_score, 6),
            "lexical_score": round(self.lexical_score, 6),
            "retrieval_score": round(self.retrieval_score, 6),
        }


class LocalRagService:
    def __init__(self, embedding_client: EmbeddingClient | None = None) -> None:
        self.settings = get_settings()
        self.embedding_client = embedding_client or EmbeddingClient()

    async def index_file(self, db: Session, record: StoredFile) -> int:
        extracted = OcrService().extract(db, record.id)["extracted_text"]
        chunks = self.chunk_text(extracted)
        if not chunks:
            raise ValueError("No extractable text was found in the document")
        vectors = await self.embedding_client.embed_documents(chunks)
        db.query(RagDocumentChunk).filter(RagDocumentChunk.file_id == record.id).delete()
        for index, (content, embedding) in enumerate(zip(chunks, vectors, strict=True)):
            db.add(
                RagDocumentChunk(
                    project_id=record.project_id,
                    file_id=record.id,
                    chunk_index=index,
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    character_count=len(content),
                    embedding=embedding,
                    metadata_json={"filename": record.original_filename},
                )
            )
        db.flush()
        return len(chunks)

    async def retrieve(self, db: Session, project_id: int, query: str) -> list[RetrievedChunk]:
        query_vector = await self.embedding_client.embed_query(query)
        candidate_k = self.settings.rag_vector_candidate_k
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            candidates = (
                db.query(RagDocumentChunk)
                .filter(RagDocumentChunk.project_id == project_id)
                .order_by(RagDocumentChunk.embedding.cosine_distance(query_vector))
                .limit(candidate_k)
                .all()
            )
        else:
            candidates = (
                db.query(RagDocumentChunk)
                .filter(RagDocumentChunk.project_id == project_id)
                .all()
            )
            candidates.sort(
                key=lambda chunk: self._cosine(query_vector, chunk.embedding or []),
                reverse=True,
            )
            candidates = candidates[:candidate_k]

        files = {
            record.id: record
            for record in db.query(StoredFile)
            .filter(StoredFile.id.in_([chunk.file_id for chunk in candidates] or [0]))
            .all()
        }
        tokens = self._tokens(query)
        results: list[RetrievedChunk] = []
        for chunk in candidates:
            vector_score = max(0.0, self._cosine(query_vector, chunk.embedding or []))
            chunk_tokens = self._tokens(chunk.content)
            lexical_score = len(tokens & chunk_tokens) / max(1, len(tokens))
            retrieval_score = 0.8 * vector_score + 0.2 * lexical_score
            file_record = files.get(chunk.file_id)
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    file_id=chunk.file_id,
                    filename=file_record.original_filename if file_record else f"file-{chunk.file_id}",
                    snippet=chunk.content,
                    vector_score=vector_score,
                    lexical_score=lexical_score,
                    retrieval_score=retrieval_score,
                )
            )
        results.sort(key=lambda item: (item.retrieval_score, item.vector_score), reverse=True)
        return results[: self.settings.rag_retrieval_top_k]

    def chunk_text(self, text: str) -> list[str]:
        normalized = re.sub(r"\r\n?", "\n", text or "").strip()
        if not normalized:
            return []
        size = max(200, self.settings.rag_chunk_size)
        overlap = min(max(0, self.settings.rag_chunk_overlap), size // 2)
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", normalized) if part.strip()]
        chunks: list[str] = []
        buffer = ""
        for paragraph in paragraphs:
            if len(paragraph) > size:
                if buffer:
                    chunks.append(buffer)
                    buffer = ""
                start = 0
                while start < len(paragraph):
                    chunk = paragraph[start : start + size].strip()
                    if chunk:
                        chunks.append(chunk)
                    if start + size >= len(paragraph):
                        break
                    start += size - overlap
                continue
            candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
            if len(candidate) <= size:
                buffer = candidate
            else:
                chunks.append(buffer)
                prefix = buffer[-overlap:].strip() if overlap else ""
                buffer = f"{prefix}\n\n{paragraph}".strip()
        if buffer:
            chunks.append(buffer)
        return [chunk for chunk in chunks if chunk]

    @staticmethod
    def format_sources(sources: list[RetrievedChunk], max_chars: int = 6000) -> str:
        lines = ["项目资料检索结果："]
        for index, source in enumerate(sources, start=1):
            lines.append(
                f"[S{index}] 文件={source.filename}; 块={source.chunk_id}; "
                f"相关度={source.retrieval_score:.3f}\n{source.snippet}"
            )
        return "\n\n".join(lines)[:max_chars]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,}", text or "")
            if len(token) >= 2
        }

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

