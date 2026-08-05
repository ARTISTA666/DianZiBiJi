from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import *  # noqa: F403
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.project import Project
from app.models.rag import RagDocumentChunk
from app.models.user import User, UserRole
from app.services.local_rag import LocalRagService, RetrievedChunk, validate_embedding_count


class FakeEmbeddingClient:
    async def embed_query(self, _query: str) -> list[float]:
        return [1.0, 0.0]


def test_collection_questions_expand_retrieval_without_exceeding_candidates() -> None:
    service = LocalRagService(embedding_client=object())
    service.settings = SimpleNamespace(
        rag_retrieval_top_k=6,
        rag_collection_retrieval_top_k=12,
        rag_vector_candidate_k=30,
    )

    assert service._retrieval_limit("这个样本的处理条件是什么？") == 6
    assert service._retrieval_limit("四个样本分别对应哪些 SRA 登录号？") == 12

    service.settings.rag_collection_retrieval_top_k = 50
    assert service._retrieval_limit("列出全部样本") == 30


def test_source_prompt_keeps_twelve_standard_chunks() -> None:
    sources = [
        RetrievedChunk(
            chunk_id=index,
            file_id=1,
            filename="samples.csv",
            snippet=f"chunk-{index} " + "x" * 600,
            vector_score=0.8,
            lexical_score=0.5,
            retrieval_score=0.7,
        )
        for index in range(1, 13)
    ]

    prompt = LocalRagService.format_sources(sources)

    assert "chunk-1" in prompt
    assert "chunk-12" in prompt


def test_bm25_scores_rank_matching_document_first() -> None:
    scores = LocalRagService._bm25_scores(
        "PCR 退火温度",
        [
            "PCR 实验的退火温度为 58℃",
            "细胞培养使用 DMEM 培养基",
            "Western Blot 使用一抗和二抗",
            "流式细胞术检测细胞凋亡",
        ],
    )

    assert scores.index(max(scores)) == 0
    assert LocalRagService._bm25_scores("PCR", ["...", "---"]) == [0.0, 0.0]


def test_indexing_rejects_embedding_count_mismatch() -> None:
    with pytest.raises(ValueError, match="Embedding backend returned 0 vectors for 1 chunks"):
        validate_embedding_count(["chunk"], [])


def test_retrieval_excludes_stale_chunks_from_archived_files(db_engine) -> None:
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)
    with SessionLocal() as db:
        db.add(User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN))
        db.add(Project(id=1, name="RAG project", owner_user_id=1))
        db.add_all(
            [
                StoredFile(
                    id=1,
                    project_id=1,
                    uploaded_by=1,
                    file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                    original_filename="active.txt",
                    storage_path="/tmp/active.txt",
                    file_hash="active",
                    status=FileStatus.APPROVED,
                    knowledge_sync_status=KnowledgeSyncStatus.SYNCED.value,
                ),
                StoredFile(
                    id=2,
                    project_id=1,
                    uploaded_by=1,
                    file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                    original_filename="archived.txt",
                    storage_path="/tmp/archived.txt",
                    file_hash="archived",
                    status=FileStatus.ARCHIVED,
                    knowledge_sync_status=KnowledgeSyncStatus.SYNCED.value,
                ),
            ]
        )
        db.add_all(
            [
                RagDocumentChunk(
                    project_id=1,
                    file_id=1,
                    chunk_index=0,
                    content="PCR active evidence",
                    content_hash="active-chunk",
                    embedding=[1.0, 0.0],
                ),
                RagDocumentChunk(
                    project_id=1,
                    file_id=2,
                    chunk_index=0,
                    content="PCR archived evidence",
                    content_hash="archived-chunk",
                    embedding=[1.0, 0.0],
                ),
            ]
        )
        db.commit()

        service = LocalRagService(embedding_client=FakeEmbeddingClient())
        vector_results = asyncio.run(service.retrieve(db, 1, "PCR"))
        bm25_results = asyncio.run(service.retrieve_bm25(db, 1, "PCR"))
        empty_bm25_results = asyncio.run(service.retrieve_bm25(db, 1, "unmatched"))

        assert {result.file_id for result in vector_results} == {1}
        assert {result.file_id for result in bm25_results} == {1}
        assert empty_bm25_results == []


def test_hybrid_retrieval_unions_vector_and_bm25_candidates(db_engine) -> None:
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)
    with SessionLocal() as db:
        db.add(User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN))
        db.add(Project(id=1, name="Hybrid project", owner_user_id=1))
        for file_id in (1, 2, 3):
            db.add(
                StoredFile(
                    id=file_id,
                    project_id=1,
                    uploaded_by=1,
                    file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                    original_filename=f"source-{file_id}.txt",
                    storage_path=f"/tmp/source-{file_id}.txt",
                    file_hash=f"source-{file_id}",
                    status=FileStatus.APPROVED,
                    knowledge_sync_status=KnowledgeSyncStatus.SYNCED.value,
                )
            )
        db.add_all(
            [
                RagDocumentChunk(
                    project_id=1,
                    file_id=1,
                    chunk_index=0,
                    content="unrelated vector-nearest content",
                    content_hash="chunk-1",
                    embedding=[1.0, 0.0],
                ),
                RagDocumentChunk(
                    project_id=1,
                    file_id=2,
                    chunk_index=0,
                    content="raremarker exact lexical evidence",
                    content_hash="chunk-2",
                    embedding=[0.0, 1.0],
                ),
                RagDocumentChunk(
                    project_id=1,
                    file_id=3,
                    chunk_index=0,
                    content="another unrelated document",
                    content_hash="chunk-3",
                    embedding=[0.0, 1.0],
                ),
            ]
        )
        db.commit()

        service = LocalRagService(embedding_client=FakeEmbeddingClient())
        service.settings = SimpleNamespace(
            rag_vector_candidate_k=1,
            rag_retrieval_top_k=2,
            rag_collection_retrieval_top_k=2,
        )
        results = asyncio.run(service.retrieve(db, 1, "raremarker"))

        assert {result.file_id for result in results} == {1, 2}
        lexical_result = next(result for result in results if result.file_id == 2)
        assert lexical_result.lexical_score == 1.0
