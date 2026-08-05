from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.rag import RagDocumentChunk
from app.services.embedding import EmbeddingClient
from app.services.knowledge_graph import is_collection_query
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


def _retrieval_order_key(item: RetrievedChunk) -> tuple[float, float, int]:
    """Keep equal-score evidence ordering stable across database backends."""
    return (-item.retrieval_score, -item.vector_score, item.chunk_id)


def validate_embedding_count(chunks: list[str], vectors: list[list[float]]) -> None:
    if len(vectors) != len(chunks):
        raise ValueError(
            f"Embedding backend returned {len(vectors)} vectors for {len(chunks)} chunks"
        )


class LocalRagService:
    def __init__(self, embedding_client: EmbeddingClient | None = None) -> None:
        self.settings = get_settings()
        self.embedding_client = embedding_client or EmbeddingClient()

    async def index_file(self, db: Session, record: StoredFile) -> int:
        extracted = OcrService().extract_for_indexing(db, record)
        chunks = self.chunk_text(extracted)
        if not chunks:
            raise ValueError("No extractable text was found in the document")
        vectors = await self.embedding_client.embed_documents(chunks)
        validate_embedding_count(chunks, vectors)
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
        active_query = (
            db.query(RagDocumentChunk)
            .join(StoredFile, StoredFile.id == RagDocumentChunk.file_id)
            .filter(RagDocumentChunk.project_id == project_id)
            .filter(
                StoredFile.status == FileStatus.APPROVED,
                StoredFile.file_category == FileCategory.KNOWLEDGE_DOCUMENT,
                StoredFile.knowledge_sync_status == KnowledgeSyncStatus.SYNCED.value,
            )
        )
        all_chunks = active_query.all()
        if not all_chunks:
            return []
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            vector_candidates = (
                active_query
                .order_by(
                    RagDocumentChunk.embedding.cosine_distance(query_vector),
                    RagDocumentChunk.id,
                )
                .limit(candidate_k)
                .all()
            )
        else:
            vector_candidates = list(all_chunks)
            vector_candidates.sort(
                key=lambda chunk: self._cosine(query_vector, chunk.embedding or []),
                reverse=True,
            )
            vector_candidates = vector_candidates[:candidate_k]

        raw_bm25_scores = self._bm25_scores(query, [chunk.content for chunk in all_chunks])
        bm25_by_id = {
            chunk.id: score
            for chunk, score in zip(all_chunks, raw_bm25_scores, strict=True)
        }
        lexical_candidates = sorted(
            (chunk for chunk in all_chunks if bm25_by_id[chunk.id] > 0),
            key=lambda chunk: (bm25_by_id[chunk.id], -chunk.id),
            reverse=True,
        )[:candidate_k]
        candidates = list({chunk.id: chunk for chunk in [*vector_candidates, *lexical_candidates]}.values())
        max_bm25 = max((score for score in raw_bm25_scores if score > 0), default=0.0)
        query_tokens = self._bm25_tokens(query)

        files = {
            record.id: record
            for record in db.query(StoredFile)
            .filter(StoredFile.id.in_([chunk.file_id for chunk in candidates] or [0]))
            .all()
        }
        results: list[RetrievedChunk] = []
        for chunk in candidates:
            vector_score = max(0.0, self._cosine(query_vector, chunk.embedding or []))
            lexical_score = max(0.0, bm25_by_id[chunk.id]) / max_bm25 if max_bm25 else 0.0
            retrieval_score = 0.7 * vector_score + 0.3 * lexical_score
            if retrieval_score <= 0 and query_tokens:
                continue
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
        results.sort(key=_retrieval_order_key)
        return results[: self._retrieval_limit(query)]

    async def retrieve_bm25(self, db: Session, project_id: int, query: str) -> list[RetrievedChunk]:
        chunks = (
            db.query(RagDocumentChunk)
            .join(StoredFile, StoredFile.id == RagDocumentChunk.file_id)
            .filter(RagDocumentChunk.project_id == project_id)
            .filter(
                StoredFile.status == FileStatus.APPROVED,
                StoredFile.file_category == FileCategory.KNOWLEDGE_DOCUMENT,
                StoredFile.knowledge_sync_status == KnowledgeSyncStatus.SYNCED.value,
            )
            .all()
        )
        if not chunks:
            return []
        scores = self._bm25_scores(query, [chunk.content for chunk in chunks])
        files = {
            record.id: record
            for record in db.query(StoredFile)
            .filter(StoredFile.id.in_([chunk.file_id for chunk in chunks]))
            .all()
        }
        query_tokens = set(self._bm25_tokens(query))
        results = [
            RetrievedChunk(
                chunk_id=chunk.id,
                file_id=chunk.file_id,
                filename=(files[chunk.file_id].original_filename if chunk.file_id in files else f"file-{chunk.file_id}"),
                snippet=chunk.content,
                vector_score=0.0,
                lexical_score=score,
                retrieval_score=score,
            )
            for chunk, score in zip(chunks, scores, strict=True)
            if score > 0 or query_tokens.intersection(self._bm25_tokens(chunk.content))
        ]
        results.sort(key=lambda item: (item.retrieval_score, -item.chunk_id), reverse=True)
        return results[: self._retrieval_limit(query)]

    def _retrieval_limit(self, query: str) -> int:
        default = self.settings.rag_retrieval_top_k
        if is_collection_query(query):
            return min(
                self.settings.rag_vector_candidate_k,
                max(default, self.settings.rag_collection_retrieval_top_k),
            )
        return default

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
    def format_sources(sources: list[RetrievedChunk], max_chars: int = 9000) -> str:
        if max_chars <= 0:
            return ""
        prefix = "项目资料检索结果："
        per_source_budget = max(max_chars - len(prefix), 0) // max(1, len(sources))
        output = prefix
        for index, source in enumerate(sources, start=1):
            header = (
                f"\n\n[S{index}] 文件={source.filename}; 块={source.chunk_id}; "
                f"相关度={source.retrieval_score:.3f}\n"
            )
            if len(header) > per_source_budget:
                header = header[: max(per_source_budget - 1, 0)] + ("…" if per_source_budget else "")
            snippet_limit = max(per_source_budget - len(header), 0)
            content_limit = (
                max(snippet_limit - 1, 0)
                if len(source.snippet) > snippet_limit
                else snippet_limit
            )
            output += header + source.snippet[:content_limit]
            if len(source.snippet) > content_limit and len(header) + content_limit < per_source_budget:
                output += "…"
        return output[:max_chars]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,}", text or "")
            if len(token) >= 2
        }

    @staticmethod
    def _bm25_tokens(text: str) -> list[str]:
        normalized = (text or "").lower()
        return [
            token
            for segment in jieba.cut_for_search(normalized)
            for token in re.findall(r"[a-z0-9µ><=_./-]+|[\u4e00-\u9fff]+", segment)
            if token.strip()
        ]

    @classmethod
    def _bm25_scores(cls, query: str, documents: list[str]) -> list[float]:
        tokenized_documents = [cls._bm25_tokens(document) for document in documents]
        query_tokens = cls._bm25_tokens(query)
        if not query_tokens or not any(tokenized_documents):
            return [0.0] * len(documents)
        model = BM25Okapi(tokenized_documents, k1=1.2, b=0.75)
        return [float(score) for score in model.get_scores(query_tokens)]

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
