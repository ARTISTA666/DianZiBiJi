import asyncio
import hashlib
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import rag
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.ai import AIExperimentRun, AIQueryEvaluation, AIQueryLog
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
from app.models.note import ExperimentNote, NoteStatus
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.rag import ProjectRagDataset, RagFileSync
from app.models.user import User, UserRole
from app.services.deepseek import DeepSeekRequestError
from app.services.embedding import EmbeddingServiceError
from app.services.local_rag import RetrievedChunk


class FakeLocalRagService:
    fail_index = False

    async def index_file(self, db, record) -> int:
        if self.fail_index:
            raise EmbeddingServiceError("embedding failed")
        return 1

    async def retrieve(self, db, project_id: int, query: str):
        return [
            RetrievedChunk(
                chunk_id=1,
                file_id=1,
                filename="protocol.pdf",
                snippet="matched source text",
                vector_score=0.9,
                lexical_score=0.5,
                retrieval_score=0.82,
            )
        ]

    async def retrieve_bm25(self, db, project_id: int, query: str):
        return await self.retrieve(db, project_id, query)

    @staticmethod
    def format_sources(sources, max_chars: int = 6000) -> str:
        return "项目资料检索结果：\n[S1] matched source text"


class FakeDeepSeekClient:
    last_system_prompt = ""
    last_user_prompt = ""

    async def generate(self, *, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> dict:
        self.__class__.last_system_prompt = system_prompt
        self.__class__.last_user_prompt = user_prompt
        if "待修订回答" in user_prompt:
            return {
                "answer": "answer for protocol [S1]",
                "request_id": "deepseek-repair-1",
                "model": "deepseek-test",
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            }
        question = user_prompt.rsplit("用户问题：", 1)[-1]
        return {
            "answer": f"answer for {question}",
            "request_id": "deepseek-request-1",
            "model": "deepseek-test",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }


@pytest.fixture()
def test_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    upload_path = tmp_path / "protocol.pdf"
    upload_path.write_text("protocol", encoding="utf-8")

    db = SessionLocal()
    db.add_all(
        [
            User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
            User(id=2, username="member", password_hash="x", display_name="Member", role=UserRole.MEMBER),
            User(id=3, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
            User(id=4, username="reviewer", password_hash="x", display_name="Reviewer", role=UserRole.MEMBER),
            User(id=5, username="reviewer2", password_hash="x", display_name="Reviewer 2", role=UserRole.MEMBER),
            Project(id=1, name="Project A", owner_user_id=1),
            ProjectMember(project_id=1, user_id=2, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
            ProjectMember(
                project_id=1,
                user_id=4,
                project_role=ProjectRole.REVIEWER,
                can_read=True,
                can_evaluate=True,
            ),
            ProjectMember(
                project_id=1,
                user_id=5,
                project_role=ProjectRole.REVIEWER,
                can_read=True,
                can_evaluate=True,
            ),
            StoredFile(
                id=1,
                project_id=1,
                uploaded_by=1,
                file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                original_filename="protocol.pdf",
                storage_path=str(upload_path),
                mime_type="application/pdf",
                file_size=8,
                file_hash="hash-1",
                status=FileStatus.APPROVED,
                knowledge_sync_status=KnowledgeSyncStatus.PENDING_SYNC.value,
            ),
            StoredFile(
                id=2,
                project_id=1,
                uploaded_by=1,
                file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                original_filename="draft.pdf",
                storage_path=str(upload_path),
                file_size=8,
                file_hash="hash-2",
                status=FileStatus.UPLOADED,
                knowledge_sync_status=KnowledgeSyncStatus.PENDING_REVIEW.value,
            ),
            StoredFile(
                id=3,
                project_id=1,
                uploaded_by=1,
                file_category=FileCategory.NOTE_ATTACHMENT,
                original_filename="image.png",
                storage_path=str(upload_path),
                file_size=8,
                file_hash="hash-3",
                status=FileStatus.APPROVED,
                knowledge_sync_status=KnowledgeSyncStatus.NOT_APPLICABLE.value,
            ),
        ]
    )
    db.commit()
    db.close()

    active_user_id = {"value": 1}
    FakeLocalRagService.fail_index = False
    FakeDeepSeekClient.last_system_prompt = ""
    FakeDeepSeekClient.last_user_prompt = ""
    app = FastAPI()
    app.include_router(rag.router)

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = SessionLocal()
        try:
            return session.get(User, active_user_id["value"])
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    monkeypatch.setattr(rag.datasets, "LocalRagService", FakeLocalRagService)
    monkeypatch.setattr(rag.query, "LocalRagService", FakeLocalRagService)
    monkeypatch.setattr(rag.query, "DeepSeekClient", FakeDeepSeekClient)
    monkeypatch.setattr(rag.experiments, "SessionLocal", SessionLocal)
    final_gate = tmp_path / "final-maturity-gate-latest.json"
    final_gate.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T00:00:00+00:00",
                "passed": True,
                "scope": "final maturity gate for confirmatory human review",
                "checks": [
                    {"name": name, "passed": True, "detail": {}}
                    for name in sorted(rag.REQUIRED_FINAL_MATURITY_CHECKS)
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rag.common, "FINAL_MATURITY_GATE_REPORT", final_gate)

    return TestClient(app), SessionLocal, active_user_id


def test_graph_retrieval_thread_uses_independent_session(db_engine, monkeypatch) -> None:
    seen = []

    def fake_retrieve(graph_db, project_id, query, mode):
        seen.append((graph_db, project_id, query, mode))
        return [], None, "project_rag", ""

    monkeypatch.setattr(rag.query, "_retrieve_graph_context", fake_retrieve)

    result = rag.query._retrieve_graph_context_with_bind(
        db_engine,
        1,
        "question",
        "project_rag",
    )

    assert result == ([], None, "project_rag", "")
    assert seen[0][0].bind is db_engine


def test_unauthenticated_status_returns_401(test_app):
    _, SessionLocal, _ = test_app
    app = FastAPI()
    app.include_router(rag.router)

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    response = TestClient(app).get("/projects/1/rag/status")
    assert response.status_code == 401


def test_reader_can_view_status_but_cannot_init(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 2
    assert client.get("/projects/1/rag/status").status_code == 200
    assert client.post("/projects/1/rag/init").status_code == 403


def test_outsider_cannot_query_project(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 3
    response = client.post("/projects/1/rag/query", json={"query": "test"})
    assert response.status_code == 403


def test_evaluator_cannot_init_dataset(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 4
    response = client.post("/projects/1/rag/init")
    assert response.status_code == 403


def test_unapproved_and_attachment_files_cannot_sync(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    assert client.post("/files/2/rag/sync").status_code == 409
    assert client.post("/files/3/rag/sync").status_code == 409


def test_approved_document_sync_success(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    response = client.post("/files/1/rag/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["synced_count"] == 1
    with SessionLocal() as db:
        file_record = db.get(StoredFile, 1)
        sync = db.query(RagFileSync).filter(RagFileSync.file_id == 1).one()
        assert file_record.knowledge_sync_status == KnowledgeSyncStatus.SYNCED.value
        assert sync.dify_document_id == "local-file-1"
        assert sync.chunk_count == 1


def test_sync_failure_marks_file_failed(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    FakeLocalRagService.fail_index = True
    try:
        response = client.post("/files/1/rag/sync")
    finally:
        FakeLocalRagService.fail_index = False
    assert response.status_code == 502
    with SessionLocal() as db:
        assert db.get(StoredFile, 1).knowledge_sync_status == KnowledgeSyncStatus.FAILED.value


def test_query_returns_answer_and_sources(test_app):
    client, active_session, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    response = client.post("/projects/1/rag/query", json={"query": "protocol"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "answer for protocol [S1]"
    assert body["sources"][0]["filename"] == "protocol.pdf"
    assert body["rag_mode"] == "project_rag"
    assert body["graph_context"] == []
    assert body["query_log_id"] is not None
    assert body["response_ms"] >= 0
    assert body["citation_audit"] == {
        "passed": True,
        "citation_count": 1,
        "invalid_citations": [],
        "has_evidence": True,
        "message": "引用校验通过，共核对 1 个证据编号。",
    }
    with active_session() as db:
        log = db.get(AIQueryLog, body["query_log_id"])
        assert log is not None
        assert log.question == "protocol"
        assert log.answer == "answer for protocol [S1]"
        assert log.rag_mode == "project_rag"
        assert log.source_count == 1
        assert log.retrieval_config_json["citation_audit"]["passed"] is True
        assert log.retrieval_config_json["citation_audit"]["repair_attempted"] is True
        assert log.usage_json == {"prompt_tokens": 13, "completion_tokens": 7}


def test_query_flags_nonexistent_citations(test_app, monkeypatch: pytest.MonkeyPatch):
    client, _, active_user_id = test_app
    active_user_id["value"] = 1

    class InvalidCitationClient:
        async def generate(self, **_kwargs):
            return {
                "answer": "来源支持该结论 [S1]，另见不存在的来源 [S9] 和关系 [G2]。",
                "model": "deepseek-test",
                "usage": {},
            }

    monkeypatch.setattr(rag.query, "DeepSeekClient", InvalidCitationClient)
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    response = client.post("/projects/1/rag/query", json={"query": "protocol", "mode": "project_rag"})

    assert response.status_code == 200
    assert response.json()["citation_audit"]["passed"] is False
    assert response.json()["citation_audit"]["invalid_citations"] == ["[S9]", "[G2]"]


def test_query_uses_knowledge_graph_context_when_available(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    with SessionLocal() as db:
        db.add(
            ExperimentNote(
                id=1,
                project_id=1,
                title="PCR protocol note",
                experiment_type="PCR",
                owner_user_id=1,
                status=NoteStatus.APPROVED,
            )
        )
        note_entity = KnowledgeEntity(
            id=1,
            project_id=1,
            entity_type="note",
            label="PCR protocol note",
            normalized_label="pcr protocol note",
            natural_key="note:note:1",
            source_type="note",
            source_id=1,
        )
        reagent_entity = KnowledgeEntity(
            id=2,
            project_id=1,
            entity_type="reagent",
            label="PBS",
            normalized_label="pbs",
            natural_key="reagent:pbs",
        )
        db.add_all([note_entity, reagent_entity])
        db.flush()
        db.add(
            KnowledgeRelation(
                id=1,
                project_id=1,
                source_entity_id=note_entity.id,
                target_entity_id=reagent_entity.id,
                relation_type="uses_reagent",
                source_type="note_extraction",
                source_id=1,
                confidence=0.7,
            )
        )
        db.commit()

    response = client.post("/projects/1/rag/query", json={"query": "这个实验用了哪些试剂？"})
    assert response.status_code == 200
    body = response.json()
    assert body["rag_mode"] == "kg_enhanced_rag"
    assert body["query_log_id"] is not None
    assert body["graph_context"][0]["target_label"] == "PBS"
    assert body["graph_context"][0]["relation_type"] == "uses_reagent"
    assert "实验知识图谱上下文" in FakeDeepSeekClient.last_user_prompt
    assert "[G1]" in FakeDeepSeekClient.last_user_prompt
    assert "PBS" in FakeDeepSeekClient.last_user_prompt
    assert "用户问题：这个实验用了哪些试剂？" in FakeDeepSeekClient.last_user_prompt
    assert "不要把非答案候选样本" in FakeDeepSeekClient.last_system_prompt
    assert "若证据只能支持部分答案" in FakeDeepSeekClient.last_system_prompt
    with SessionLocal() as db:
        log = db.get(AIQueryLog, body["query_log_id"])
        assert log.rag_mode == "kg_enhanced_rag"
        assert log.graph_hit_count > 0
        assert log.graph_context_json[0]["target_label"] == "PBS"


def test_query_repairs_graph_only_answer_when_sources_exist(test_app, monkeypatch: pytest.MonkeyPatch):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1

    class GraphOnlyThenSourceClient:
        async def generate(self, *, user_prompt: str, **_kwargs):
            if "待修订回答" in user_prompt:
                return {"answer": "使用 PBS [S1][G1]", "model": "deepseek-test", "usage": {}}
            return {"answer": "使用 PBS [G1]", "model": "deepseek-test", "usage": {}}

    monkeypatch.setattr(rag.query, "DeepSeekClient", GraphOnlyThenSourceClient)
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    with SessionLocal() as db:
        db.add(
            ExperimentNote(
                id=21,
                project_id=1,
                title="PCR protocol note",
                experiment_type="PCR",
                owner_user_id=1,
                status=NoteStatus.APPROVED,
            )
        )
        db.add_all(
            [
                KnowledgeEntity(
                    id=21,
                    project_id=1,
                    entity_type="note",
                    label="PCR protocol note",
                    normalized_label="pcr protocol note",
                    natural_key="note:note:21",
                    source_type="note",
                    source_id=21,
                ),
                KnowledgeEntity(
                    id=22,
                    project_id=1,
                    entity_type="reagent",
                    label="PBS",
                    normalized_label="pbs",
                    natural_key="reagent:pbs:repair",
                ),
            ]
        )
        db.flush()
        db.add(
            KnowledgeRelation(
                id=21,
                project_id=1,
                source_entity_id=21,
                target_entity_id=22,
                relation_type="uses_reagent",
                source_type="note_extraction",
                source_id=21,
                confidence=0.7,
            )
        )
        db.commit()

    response = client.post("/projects/1/rag/query", json={"query": "这个实验用了哪些试剂？"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "使用 PBS [S1][G1]"
    with SessionLocal() as db:
        log = db.get(AIQueryLog, body["query_log_id"])
        assert log.retrieval_config_json["citation_audit"]["repair_attempted"] is True


def test_query_repairs_source_only_answer_when_graph_context_exists(test_app, monkeypatch: pytest.MonkeyPatch):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1

    class SourceOnlyThenGraphClient:
        async def generate(self, *, user_prompt: str, **_kwargs):
            if "待修订回答" in user_prompt:
                return {"answer": "使用 PBS [S1][G1]", "model": "deepseek-test", "usage": {}}
            return {"answer": "使用 PBS [S1]", "model": "deepseek-test", "usage": {}}

    monkeypatch.setattr(rag.query, "DeepSeekClient", SourceOnlyThenGraphClient)
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    with SessionLocal() as db:
        db.add(
            ExperimentNote(
                id=31,
                project_id=1,
                title="PCR protocol note",
                experiment_type="PCR",
                owner_user_id=1,
                status=NoteStatus.APPROVED,
            )
        )
        db.add_all(
            [
                KnowledgeEntity(
                    id=31,
                    project_id=1,
                    entity_type="note",
                    label="PCR protocol note",
                    normalized_label="pcr protocol note",
                    natural_key="note:note:31",
                    source_type="note",
                    source_id=31,
                ),
                KnowledgeEntity(
                    id=32,
                    project_id=1,
                    entity_type="reagent",
                    label="PBS",
                    normalized_label="pbs",
                    natural_key="reagent:pbs:graph-repair",
                ),
            ]
        )
        db.flush()
        db.add(
            KnowledgeRelation(
                id=31,
                project_id=1,
                source_entity_id=31,
                target_entity_id=32,
                relation_type="uses_reagent",
                source_type="note_extraction",
                source_id=31,
                confidence=0.7,
            )
        )
        db.commit()

    response = client.post("/projects/1/rag/query", json={"query": "这个实验用了哪些试剂？"})

    assert response.status_code == 200
    assert response.json()["answer"] == "使用 PBS [S1][G1]"


def test_query_can_force_project_rag_without_graph_context(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    with SessionLocal() as db:
        db.add_all(
            [
                KnowledgeEntity(
                    id=11,
                    project_id=1,
                    entity_type="note",
                    label="PCR protocol note",
                    normalized_label="pcr protocol note",
                    natural_key="note:note:11",
                    source_type="note",
                    source_id=1,
                ),
                KnowledgeEntity(
                    id=12,
                    project_id=1,
                    entity_type="reagent",
                    label="PBS",
                    normalized_label="pbs",
                    natural_key="reagent:pbs",
                ),
            ]
        )
        db.flush()
        db.add(
            KnowledgeRelation(
                id=11,
                project_id=1,
                source_entity_id=11,
                target_entity_id=12,
                relation_type="uses_reagent",
                source_type="note_extraction",
                source_id=1,
                confidence=0.7,
            )
        )
        db.commit()

    response = client.post("/projects/1/rag/query", json={"query": "PBS", "mode": "project_rag"})
    assert response.status_code == 200
    body = response.json()
    assert body["rag_mode"] == "project_rag"
    assert body["graph_context"] == []
    assert "本次未检索到达到阈值的相关关系" in FakeDeepSeekClient.last_user_prompt


def test_query_can_force_kg_mode_with_visible_document_fallback(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")

    response = client.post(
        "/projects/1/rag/query",
        json={"query": "没有图谱命中的资料问题", "mode": "kg_enhanced_rag"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rag_mode"] == "kg_enhanced_rag"
    assert body["graph_context"] == []
    assert "continued with project documents only" in body["fallback_reason"]
    with SessionLocal() as db:
        log = db.get(AIQueryLog, body["query_log_id"])
        assert log.rag_mode == "kg_enhanced_rag"
        assert log.graph_hit_count == 0
        assert log.fallback_reason == body["fallback_reason"]


def test_query_logs_are_project_scoped_and_evaluable(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    query_response = client.post("/projects/1/rag/query", json={"query": "protocol"})
    log_id = query_response.json()["query_log_id"]

    logs_response = client.get("/projects/1/rag/query-logs")
    assert logs_response.status_code == 200
    assert logs_response.json()[0]["id"] == log_id
    assert logs_response.json()[0]["evaluation"] is None

    incomplete_evaluation = client.post(
        f"/rag/query-logs/{log_id}/evaluation",
        json={"score": 5},
    )
    assert incomplete_evaluation.status_code == 422

    evaluation_response = client.post(
        f"/rag/query-logs/{log_id}/evaluation",
        json={"score": 5, "is_accurate": True, "is_traceable": True, "comment": "依据清晰"},
    )
    assert evaluation_response.status_code == 200
    assert evaluation_response.json()["score"] == 5
    assert evaluation_response.json()["review_protocol"] == "unblinded"

    logs_response = client.get("/projects/1/rag/query-logs")
    assert logs_response.json()[0]["evaluation"]["comment"] == "依据清晰"
    with SessionLocal() as db:
        assert db.query(AIQueryEvaluation).filter(AIQueryEvaluation.query_log_id == log_id).count() == 1

    active_user_id["value"] = 4
    evaluator_response = client.post(
        f"/rag/query-logs/{log_id}/evaluation",
        json={"score": 4, "is_accurate": True, "is_traceable": True, "comment": "独立复核"},
    )
    assert evaluator_response.status_code == 403

    active_user_id["value"] = 2
    assert client.post(
        f"/rag/query-logs/{log_id}/evaluation",
        json={"score": 1, "is_accurate": False, "is_traceable": False},
    ).status_code == 403

    active_user_id["value"] = 3
    assert client.get("/projects/1/rag/query-logs").status_code == 403
    assert client.post(
        f"/rag/query-logs/{log_id}/evaluation",
        json={"score": 1, "is_accurate": False, "is_traceable": False},
    ).status_code == 403


def test_evaluator_only_account_uses_method_masked_review_api(test_app):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        run = AIExperimentRun(
            id=99,
            project_id=1,
            created_by=1,
            name="Paired evaluation",
            status="completed",
            questions_json=["哪个样本使用 PBS？"],
            modes_json=["project_rag", "kg_enhanced_rag"],
            total_cases=1,
            completed_cases=1,
        )
        log = AIQueryLog(
            id=999,
            project_id=1,
            user_id=1,
            question="哪个样本使用 PBS？",
            answer="图谱关系显示样本 A 使用 PBS [G1]，原始资料也有记录 [S1]。",
            rag_mode="kg_enhanced_rag",
            graph_hit_count=1,
            source_count=1,
            response_ms=120,
            sources_json=[{"filename": "protocol.pdf", "snippet": "样本 A 使用 PBS"}],
            graph_context_json=[
                {
                    "relation_id": 88,
                    "source_label": "样本 A",
                    "relation_label": "使用试剂",
                    "target_label": "PBS",
                }
            ],
            provider="deepseek",
            model_name="deepseek-test",
            prompt_version="rag-test",
            experiment_run_id=99,
            experiment_case_index=1,
        )
        db.add_all([run, log])
        db.commit()

    active_user_id["value"] = 4
    assert client.get("/projects/1/rag/query-logs").status_code == 403
    assert client.get("/projects/1/rag/analytics").status_code == 403
    assert client.get("/projects/1/rag/experiments").status_code == 403
    assert client.get("/rag/experiments/99/export.csv").status_code == 403
    assert client.post(
        "/projects/1/rag/query",
        json={"query": "PBS", "mode": "kg_enhanced_rag"},
    ).status_code == 403

    batches_response = client.get("/projects/1/rag/blind-review/batches")
    assert batches_response.status_code == 200
    batch = batches_response.json()[0]
    assert re.fullmatch(r"R[A-F0-9]{12}", batch["batch_id"])
    assert set(batch) == {"batch_id", "total_items", "completed_items"}
    assert batch["total_items"] == 1
    assert batch["completed_items"] == 0

    items_response = client.get(
        "/projects/1/rag/blind-review/items",
        params={"batch_id": batch["batch_id"], "pending_only": "false"},
    )
    assert items_response.status_code == 200
    item = items_response.json()[0]
    assert re.fullmatch(r"B[A-F0-9]{12}", item["blind_id"])
    assert set(item) == {"blind_id", "question", "answer", "evidence", "evaluation"}
    assert item["answer"] == "证据显示样本 A 使用 PBS [E2]，原始资料也有记录 [E1]。"
    assert [evidence["evidence_id"] for evidence in item["evidence"]] == ["E1", "E2"]
    serialized = json.dumps(item, ensure_ascii=False)
    for forbidden in ("rag_mode", "query_log", "model_name", "relation_id", "[G1]", "图谱"):
        assert forbidden not in serialized

    evaluation_response = client.post(
        f"/projects/1/rag/blind-review/items/{item['blind_id']}/evaluation",
        json={"score": 4, "is_accurate": True, "is_traceable": True, "comment": "证据可核对"},
    )
    assert evaluation_response.status_code == 200
    assert set(evaluation_response.json()) == {
        "score",
        "is_accurate",
        "is_traceable",
        "comment",
        "updated_at",
    }
    assert client.post(
        f"/projects/1/rag/blind-review/items/{item['blind_id']}/evaluation",
        json={"score": 1, "is_accurate": False, "is_traceable": False, "comment": "重复提交"},
    ).status_code == 409
    assert client.get(
        "/projects/1/rag/blind-review/items",
        params={"batch_id": batch["batch_id"]},
    ).json() == []
    with SessionLocal() as db:
        evaluation = db.query(AIQueryEvaluation).filter(AIQueryEvaluation.query_log_id == 999).one()
        assert evaluation.evaluator_user_id == 4
        assert evaluation.review_protocol == "method_masked"

    active_user_id["value"] = 1
    incomplete_export = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")
    assert incomplete_export.status_code == 409
    assert "not complete" in incomplete_export.text

    active_user_id["value"] = 5
    second_items = client.get(
        "/projects/1/rag/blind-review/items",
        params={"batch_id": batch["batch_id"]},
    ).json()
    assert [review_item["blind_id"] for review_item in second_items] == [item["blind_id"]]
    second_response = client.post(
        f"/projects/1/rag/blind-review/items/{item['blind_id']}/evaluation",
        json={"score": 2, "is_accurate": False, "is_traceable": False, "comment": "事实不一致"},
    )
    assert second_response.status_code == 200

    with SessionLocal() as db:
        evaluations = (
            db.query(AIQueryEvaluation)
            .filter(AIQueryEvaluation.query_log_id == 999)
            .order_by(AIQueryEvaluation.evaluator_user_id)
            .all()
        )
        assert [evaluation.evaluator_user_id for evaluation in evaluations] == [4, 5]
        assert {evaluation.review_protocol for evaluation in evaluations} == {"method_masked"}

    active_user_id["value"] = 1
    manager_batches = client.get("/projects/1/rag/blind-review/batches")
    assert manager_batches.status_code == 200
    assert manager_batches.json()[0] == {
        "batch_id": batch["batch_id"],
        "total_items": 1,
        "completed_items": 1,
    }
    analytics = client.get("/projects/1/rag/analytics").json()
    assert analytics["evaluated_queries"] == 1
    assert analytics["evaluation_count"] == 2
    assert analytics["evaluator_count"] == 2
    assert analytics["avg_score"] == 3
    assert analytics["accurate_rate"] == 0.5
    assert analytics["accuracy_agreement"] == {
        "paired_ratings": 1,
        "agreement_rate": 0,
        "cohens_kappa": 0,
    }
    raw_log = next(log for log in client.get("/projects/1/rag/query-logs").json() if log["id"] == 999)
    assert raw_log["evaluation"] is None
    assert [evaluation["evaluator_user_id"] for evaluation in raw_log["evaluations"]] == [4, 5]
    assert {evaluation["review_protocol"] for evaluation in raw_log["evaluations"]} == {"method_masked"}
    with SessionLocal() as db:
        db.add(
            AIQueryEvaluation(
                query_log_id=999,
                evaluator_user_id=1,
                score=5,
                is_accurate=True,
                is_traceable=True,
                comment="manager note",
                review_protocol="unblinded",
            )
        )
        db.commit()
    export = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")
    assert export.status_code == 200
    assert export.content.startswith(b"\xef\xbb\xbf")
    assert b"question_index" in export.content
    assert b"evaluations_json" in export.content
    assert b"review_batch_id" in export.content
    assert b"export_protocol" in export.content
    assert b"final_maturity_gate_sha256" in export.content
    final_gate_hash = hashlib.sha256(rag.common.FINAL_MATURITY_GATE_REPORT.read_bytes()).hexdigest()
    assert final_gate_hash.encode("utf-8") in export.content
    assert batch["batch_id"].encode("utf-8") in export.content
    assert b"confirmatory_human_review_v1" in export.content
    assert b"method_masked" in export.content
    assert b"unblinded" not in export.content
    assert b"manager note" not in export.content
    assert b"project_rag" in export.content
    assert export.headers["content-disposition"] == 'attachment; filename="confirmatory-human-review-export.csv"'
    with SessionLocal() as db:
        audit = db.query(AuditLog).filter(AuditLog.action == "export_blind_review_batch").one()
        assert audit.actor_user_id == 1
        assert audit.project_id == 1
        assert audit.target_type == "ai_experiment_run"
        assert audit.target_id == 99
        assert audit.detail_json == {
            "batch_id": batch["batch_id"],
            "filename": "confirmatory-human-review-export.csv",
            "final_maturity_gate_sha256": final_gate_hash,
            "total_items": 1,
            "reviewer_user_ids": [4, 5],
            "review_protocol": "method_masked",
        }

    active_user_id["value"] = 4
    assert client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv").status_code == 403
    active_user_id["value"] = 1
    assert client.get("/projects/1/rag/blind-review/batches").status_code == 200


def test_blind_review_progress_ignores_unblinded_ratings(test_app):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        db.add_all(
            [
                AIExperimentRun(
                    id=499,
                    project_id=1,
                    created_by=1,
                    name="Protocol-aware progress",
                    status="completed",
                    questions_json=["Q1"],
                    modes_json=["project_rag"],
                    total_cases=1,
                    completed_cases=1,
                ),
                AIQueryLog(
                    id=4991,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 [S1]",
                    rag_mode="project_rag",
                    experiment_run_id=499,
                    experiment_case_index=1,
                    experiment_execution_order=1,
                ),
                AIQueryEvaluation(
                    query_log_id=4991,
                    evaluator_user_id=4,
                    score=5,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="unblinded",
                ),
            ]
        )
        db.commit()

    active_user_id["value"] = 4
    response = client.get("/projects/1/rag/blind-review/batches")
    assert response.status_code == 200
    batch = next(item for item in response.json() if item["total_items"] == 1)
    assert batch["completed_items"] == 0


def test_blind_review_export_rejects_inconsistent_reviewer_sets(test_app):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        db.add_all(
            [
                User(id=6, username="reviewer3", password_hash="x", display_name="Reviewer 3", role=UserRole.MEMBER),
                ProjectMember(
                    project_id=1,
                    user_id=6,
                    project_role=ProjectRole.REVIEWER,
                    can_read=True,
                    can_evaluate=True,
                ),
                AIExperimentRun(
                    id=199,
                    project_id=1,
                    created_by=1,
                    name="Inconsistent reviewers",
                    status="completed",
                    questions_json=["Q1", "Q2"],
                    modes_json=["project_rag"],
                    total_cases=2,
                    completed_cases=2,
                ),
                AIQueryLog(
                    id=1991,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=199,
                    experiment_case_index=1,
                    experiment_execution_order=1,
                ),
                AIQueryLog(
                    id=1992,
                    project_id=1,
                    user_id=1,
                    question="Q2",
                    answer="A2 [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=199,
                    experiment_case_index=2,
                    experiment_execution_order=2,
                ),
                AIQueryEvaluation(
                    query_log_id=1991,
                    evaluator_user_id=4,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
                AIQueryEvaluation(
                    query_log_id=1991,
                    evaluator_user_id=5,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
                AIQueryEvaluation(
                    query_log_id=1992,
                    evaluator_user_id=4,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
                AIQueryEvaluation(
                    query_log_id=1992,
                    evaluator_user_id=6,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
            ]
        )
        db.commit()

    active_user_id["value"] = 1
    batch = next(batch for batch in client.get("/projects/1/rag/blind-review/batches").json() if batch["total_items"] == 2)
    response = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")

    assert response.status_code == 409
    assert "inconsistent reviewer sets" in response.text


def test_blind_review_export_requires_final_maturity_gate(test_app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        db.add_all(
            [
                AIExperimentRun(
                    id=189,
                    project_id=1,
                    created_by=1,
                    name="Complete review before final gate",
                    status="completed",
                    questions_json=["Q1"],
                    modes_json=["project_rag"],
                    total_cases=1,
                    completed_cases=1,
                    failed_cases=0,
                ),
                AIQueryLog(
                    id=1891,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=189,
                    experiment_case_index=1,
                    experiment_execution_order=1,
                ),
                AIQueryEvaluation(
                    query_log_id=1891,
                    evaluator_user_id=4,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
                AIQueryEvaluation(
                    query_log_id=1891,
                    evaluator_user_id=5,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
            ]
        )
        db.commit()

    final_gate = tmp_path / "failed-final-gate.json"
    final_gate.write_text('{"passed": false, "failures": [{"name": "long soak evidence passed"}]}', encoding="utf-8")
    monkeypatch.setattr(rag.common, "FINAL_MATURITY_GATE_REPORT", final_gate)
    active_user_id["value"] = 1
    batch = next(batch for batch in client.get("/projects/1/rag/blind-review/batches").json() if batch["total_items"] == 1)
    response = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")

    assert response.status_code == 409
    assert "Final maturity gate has not passed" in response.text


def test_blind_review_export_rejects_legacy_final_gate_without_timestamp(test_app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        db.add_all(
            [
                AIExperimentRun(
                    id=190,
                    project_id=1,
                    created_by=1,
                    name="Legacy final gate report",
                    status="completed",
                    questions_json=["Q1"],
                    modes_json=["project_rag"],
                    total_cases=1,
                    completed_cases=1,
                    failed_cases=0,
                ),
                AIQueryLog(
                    id=1901,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=190,
                    experiment_case_index=1,
                    experiment_execution_order=1,
                ),
                AIQueryEvaluation(
                    query_log_id=1901,
                    evaluator_user_id=4,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
                AIQueryEvaluation(
                    query_log_id=1901,
                    evaluator_user_id=5,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
            ]
        )
        db.commit()

    final_gate = tmp_path / "legacy-final-gate.json"
    final_gate.write_text('{"passed": true, "failures": []}', encoding="utf-8")
    monkeypatch.setattr(rag.common, "FINAL_MATURITY_GATE_REPORT", final_gate)
    active_user_id["value"] = 1
    batch = next(batch for batch in client.get("/projects/1/rag/blind-review/batches").json() if batch["total_items"] == 1)
    response = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")

    assert response.status_code == 409
    assert "Final maturity gate has not passed" in response.text


def test_blind_review_export_rejects_minimal_final_gate_pass(test_app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        db.add_all(
            [
                AIExperimentRun(
                    id=191,
                    project_id=1,
                    created_by=1,
                    name="Minimal final gate report",
                    status="completed",
                    questions_json=["Q1"],
                    modes_json=["project_rag"],
                    total_cases=1,
                    completed_cases=1,
                    failed_cases=0,
                ),
                AIQueryLog(
                    id=1911,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=191,
                    experiment_case_index=1,
                    experiment_execution_order=1,
                ),
                AIQueryEvaluation(
                    query_log_id=1911,
                    evaluator_user_id=4,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
                AIQueryEvaluation(
                    query_log_id=1911,
                    evaluator_user_id=5,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
            ]
        )
        db.commit()

    final_gate = tmp_path / "minimal-final-gate.json"
    final_gate.write_text('{"generated_at": "2026-07-18T00:00:00+00:00", "passed": true, "failures": []}', encoding="utf-8")
    monkeypatch.setattr(rag.common, "FINAL_MATURITY_GATE_REPORT", final_gate)
    active_user_id["value"] = 1
    batch = next(batch for batch in client.get("/projects/1/rag/blind-review/batches").json() if batch["total_items"] == 1)
    response = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")

    assert response.status_code == 409
    assert "Final maturity gate has not passed" in response.text


def test_blind_review_export_rejects_final_gate_missing_required_checks(
    test_app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        db.add_all(
            [
                AIExperimentRun(
                    id=192,
                    project_id=1,
                    created_by=1,
                    name="Incomplete final gate report",
                    status="completed",
                    questions_json=["Q1"],
                    modes_json=["project_rag"],
                    total_cases=1,
                    completed_cases=1,
                    failed_cases=0,
                ),
                AIQueryLog(
                    id=1921,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=192,
                    experiment_case_index=1,
                    experiment_execution_order=1,
                ),
                AIQueryEvaluation(
                    query_log_id=1921,
                    evaluator_user_id=4,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
                AIQueryEvaluation(
                    query_log_id=1921,
                    evaluator_user_id=5,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
            ]
        )
        db.commit()

    final_gate = tmp_path / "incomplete-final-gate.json"
    final_gate.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T00:00:00+00:00",
                "passed": True,
                "scope": "final maturity gate for confirmatory human review",
                "checks": [{"name": "all evidence", "passed": True, "detail": {}}],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rag.common, "FINAL_MATURITY_GATE_REPORT", final_gate)
    active_user_id["value"] = 1
    batch = next(batch for batch in client.get("/projects/1/rag/blind-review/batches").json() if batch["total_items"] == 1)
    response = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")

    assert response.status_code == 409
    assert "Final maturity gate has not passed" in response.text


def test_blind_review_export_rejects_incomplete_experiment_batch(test_app):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        db.add_all(
            [
                AIExperimentRun(
                    id=299,
                    project_id=1,
                    created_by=1,
                    name="Incomplete experiment",
                    status="completed_with_errors",
                    questions_json=["Q1", "Q2"],
                    modes_json=["project_rag"],
                    total_cases=2,
                    completed_cases=1,
                    failed_cases=1,
                ),
                AIQueryLog(
                    id=2991,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=299,
                    experiment_case_index=1,
                    experiment_execution_order=1,
                ),
                AIQueryEvaluation(
                    query_log_id=2991,
                    evaluator_user_id=4,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
                AIQueryEvaluation(
                    query_log_id=2991,
                    evaluator_user_id=5,
                    score=4,
                    is_accurate=True,
                    is_traceable=True,
                    review_protocol="method_masked",
                ),
            ]
        )
        db.commit()

    active_user_id["value"] = 1
    batch = next(batch for batch in client.get("/projects/1/rag/blind-review/batches").json() if batch["total_items"] == 2)
    assert batch["completed_items"] == 1
    response = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")

    assert response.status_code == 409
    assert "not cleanly completed" in response.text


def test_blind_review_export_rejects_repeated_question_mode_items(test_app):
    client, SessionLocal, active_user_id = test_app
    with SessionLocal() as db:
        db.add_all(
            [
                AIExperimentRun(
                    id=399,
                    project_id=1,
                    created_by=1,
                    name="Repeated formal item",
                    status="completed",
                    questions_json=["Q1"],
                    modes_json=["project_rag"],
                    total_cases=2,
                    completed_cases=2,
                    failed_cases=0,
                ),
                AIQueryLog(
                    id=3991,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=399,
                    experiment_case_index=1,
                    experiment_repetition_index=1,
                    experiment_execution_order=1,
                ),
                AIQueryLog(
                    id=3992,
                    project_id=1,
                    user_id=1,
                    question="Q1",
                    answer="A1 repeat [S1]",
                    rag_mode="project_rag",
                    source_count=1,
                    response_ms=10,
                    sources_json=[],
                    graph_context_json=[],
                    provider="deepseek",
                    prompt_version="rag-test",
                    experiment_run_id=399,
                    experiment_case_index=1,
                    experiment_repetition_index=2,
                    experiment_execution_order=2,
                ),
            ]
        )
        for log_id in (3991, 3992):
            db.add_all(
                [
                    AIQueryEvaluation(
                        query_log_id=log_id,
                        evaluator_user_id=4,
                        score=4,
                        is_accurate=True,
                        is_traceable=True,
                        review_protocol="method_masked",
                    ),
                    AIQueryEvaluation(
                        query_log_id=log_id,
                        evaluator_user_id=5,
                        score=4,
                        is_accurate=True,
                        is_traceable=True,
                        review_protocol="method_masked",
                    ),
                ]
            )
        db.commit()

    active_user_id["value"] = 1
    batch = next(batch for batch in client.get("/projects/1/rag/blind-review/batches").json() if batch["total_items"] == 2)
    assert batch["completed_items"] == 2
    response = client.get(f"/projects/1/rag/blind-review/batches/{batch['batch_id']}/export.csv")

    assert response.status_code == 409
    assert "repeated question/mode" in response.text


def test_query_analytics_summarizes_modes_and_evaluations(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    project_rag_log_id = client.post("/projects/1/rag/query", json={"query": "protocol", "mode": "project_rag"}).json()[
        "query_log_id"
    ]
    with SessionLocal() as db:
        note_entity = KnowledgeEntity(
            id=21,
            project_id=1,
            entity_type="note",
            label="PCR protocol note",
            normalized_label="pcr protocol note",
            natural_key="note:note:21",
            source_type="note",
            source_id=1,
        )
        reagent_entity = KnowledgeEntity(
            id=22,
            project_id=1,
            entity_type="reagent",
            label="PBS",
            normalized_label="pbs",
            natural_key="reagent:pbs:22",
        )
        db.add_all([note_entity, reagent_entity])
        db.flush()
        db.add(
            KnowledgeRelation(
                id=21,
                project_id=1,
                source_entity_id=note_entity.id,
                target_entity_id=reagent_entity.id,
                relation_type="uses_reagent",
                confidence=0.8,
            )
        )
        db.commit()
    kg_log_id = client.post("/projects/1/rag/query", json={"query": "PBS"}).json()["query_log_id"]
    client.post(
        f"/rag/query-logs/{project_rag_log_id}/evaluation",
        json={"score": 3, "is_accurate": True, "is_traceable": False, "comment": "缺少完整证据"},
    )
    client.post(
        f"/rag/query-logs/{kg_log_id}/evaluation",
        json={"score": 5, "is_accurate": True, "is_traceable": True},
    )

    response = client.get("/projects/1/rag/analytics")
    assert response.status_code == 200
    body = response.json()
    assert body["total_queries"] == 2
    assert body["evaluated_queries"] == 2
    assert body["evaluation_rate"] == 1
    assert body["project_rag_queries"] == 1
    assert body["kg_enhanced_queries"] == 1
    assert body["avg_score"] == 4
    assert body["traceable_rate"] == 0.5
    mode_stats = {item["rag_mode"]: item for item in body["mode_stats"]}
    assert mode_stats["project_rag"]["avg_score"] == 3
    assert mode_stats["kg_enhanced_rag"]["avg_score"] == 5
    assert mode_stats["kg_enhanced_rag"]["avg_graph_hit_count"] > 0


def test_query_failure_is_logged(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    original_generate = FakeDeepSeekClient.generate

    async def fail_generate(self, *, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> dict:
        raise DeepSeekRequestError("chat failed")

    FakeDeepSeekClient.generate = fail_generate
    try:
        response = client.post("/projects/1/rag/query", json={"query": "protocol"})
    finally:
        FakeDeepSeekClient.generate = original_generate

    assert response.status_code == 502
    with SessionLocal() as db:
        log = db.query(AIQueryLog).order_by(AIQueryLog.id.desc()).first()
        assert log.question == "protocol"
        assert log.error_message == "chat failed"


def test_rag_experiment_runs_four_modes_and_exports_csv(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    with SessionLocal() as db:
        db.add_all(
            [
                KnowledgeEntity(
                    id=31,
                    project_id=1,
                    entity_type="note",
                    label="PCR protocol note",
                    normalized_label="pcr protocol note",
                    natural_key="note:note:31",
                    source_type="note",
                    source_id=1,
                ),
                KnowledgeEntity(
                    id=32,
                    project_id=1,
                    entity_type="reagent",
                    label="PBS",
                    normalized_label="pbs",
                    natural_key="reagent:pbs:32",
                ),
            ]
        )
        db.flush()
        db.add(
            KnowledgeRelation(
                id=31,
                project_id=1,
                source_entity_id=31,
                target_entity_id=32,
                relation_type="uses_reagent",
                confidence=0.8,
            )
        )
        db.commit()

    response = client.post(
        "/projects/1/rag/experiments",
        json={
            "name": "four-mode comparison",
            "questions": ["PBS 是什么用途？"],
            "modes": [
                "pure_llm",
                "bm25_rag",
                "project_rag",
                "structured_query",
                "kg_enhanced_rag",
            ],
        },
    )
    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    body = client.get(f"/rag/experiments/{queued['id']}").json()
    assert body["status"] == "completed"
    assert body["total_cases"] == 5
    assert body["completed_cases"] == 5
    assert body["failed_cases"] == 0
    assert body["config_snapshot_json"]["prompt_version"] == rag.common.PROMPT_VERSION

    with SessionLocal() as db:
        run = db.get(AIExperimentRun, body["id"])
        logs = db.query(AIQueryLog).filter(AIQueryLog.experiment_run_id == run.id).all()
        assert {log.rag_mode for log in logs} == {
            "pure_llm",
            "bm25_rag",
            "project_rag",
            "structured_query",
            "kg_enhanced_rag",
        }
        assert {log.experiment_case_index for log in logs} == {1}
        pure_llm = next(log for log in logs if log.rag_mode == "pure_llm")
        bm25 = next(log for log in logs if log.rag_mode == "bm25_rag")
        structured = next(log for log in logs if log.rag_mode == "structured_query")
        assert pure_llm.source_count == 0
        assert pure_llm.graph_hit_count == 0
        assert pure_llm.prompt_version == rag.common.PURE_LLM_PROMPT_VERSION
        assert bm25.source_count == 1
        assert bm25.prompt_version == rag.common.BM25_PROMPT_VERSION
        assert structured.provider == "deepseek"
        assert structured.model_name == "deepseek-test"
        assert structured.source_count == 0
        assert structured.graph_hit_count == 1
        assert structured.prompt_version == rag.common.STRUCTURED_QUERY_VERSION

    export = client.get(f"/rag/experiments/{body['id']}/export.csv")
    assert export.status_code == 200
    assert export.content.startswith(b"\xef\xbb\xbf")
    assert b"evaluations_json" in export.content
    assert b"pure_llm" in export.content
    assert b"bm25_rag" in export.content
    assert b"project_rag" in export.content
    assert b"structured_query" in export.content
    assert b"kg_enhanced_rag" in export.content


def test_experiment_repeats_randomizes_and_exports_execution_metadata(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")

    response = client.post(
        "/projects/1/rag/experiments",
        json={
            "name": "preregistered repeated comparison",
            "questions": ["第一题", "第二题"],
            "modes": ["project_rag", "kg_enhanced_rag"],
            "repetitions": 3,
            "randomize_order": True,
            "random_seed": 20260712,
        },
    )

    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    body = client.get(f"/rag/experiments/{queued['id']}").json()
    assert body["total_cases"] == 12
    protocol = body["config_snapshot_json"]["experiment_protocol"]
    assert protocol["repetitions"] == 3
    assert protocol["random_seed"] == 20260712
    assert protocol["randomize_order"] is True
    assert len(protocol["execution_plan_hash"]) == 64

    execution_plan = body["summary_json"]["execution_plan"]
    assert {case["execution_order"] for case in execution_plan} == set(range(1, 13))
    assert {
        (case["question_index"], case["repetition_index"], case["mode"])
        for case in execution_plan
    } == {
        (question_index, repetition_index, mode)
        for question_index in (1, 2)
        for repetition_index in (1, 2, 3)
        for mode in ("project_rag", "kg_enhanced_rag")
    }

    with SessionLocal() as db:
        logs = db.query(AIQueryLog).filter(AIQueryLog.experiment_run_id == body["id"]).all()
        assert len(logs) == 12
        assert {log.experiment_repetition_index for log in logs} == {1, 2, 3}
        assert {log.experiment_execution_order for log in logs} == set(range(1, 13))

    export = client.get(f"/rag/experiments/{body['id']}/export.csv")
    assert export.status_code == 200
    header = export.content.decode("utf-8-sig").splitlines()[0]
    assert "repetition_index" in header
    assert "execution_order" in header


def test_experiment_records_unexpected_failure_instead_of_staying_running(test_app, monkeypatch):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")

    async def crash_query(*_args, **_kwargs):
        raise RuntimeError("unexpected executor crash")

    monkeypatch.setattr(rag.query, "_execute_rag_query", crash_query)
    response = client.post(
        "/projects/1/rag/experiments",
        json={
            "name": "failure bookkeeping",
            "questions": ["question"],
            "modes": ["project_rag"],
        },
    )

    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    body = client.get(f"/rag/experiments/{queued['id']}").json()
    assert body["status"] == "failed"
    assert body["failed_cases"] == 1
    assert body["completed_at"] is not None
    assert body["summary_json"]["unexecuted_cases"] == 0
    assert "RuntimeError" in body["summary_json"]["fatal_error"]["error"]
    with SessionLocal() as db:
        assert db.get(AIExperimentRun, body["id"]).status == "failed"


def test_experiment_rejects_a_second_active_run(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    with SessionLocal() as db:
        db.add(
            AIExperimentRun(
                project_id=1,
                created_by=1,
                name="already active",
                status="running",
                total_cases=1,
            )
        )
        db.commit()

    response = client.post(
        "/projects/1/rag/experiments",
        json={"name": "second run", "questions": ["question"], "modes": ["pure_llm"]},
    )

    assert response.status_code == 409
    assert "already queued or running" in response.json()["detail"]


def test_queued_experiment_is_claimed_only_once(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    with SessionLocal() as db:
        run = AIExperimentRun(
            project_id=1,
            created_by=1,
            name="claim once",
            status="queued",
            questions_json=["probe"],
            modes_json=["pure_llm"],
            total_cases=1,
            summary_json={
                "errors": [],
                "execution_plan": [
                    {
                        "question_index": 1,
                        "question": "probe",
                        "repetition_index": 1,
                        "mode": "pure_llm",
                        "execution_order": 1,
                    }
                ],
            },
        )
        db.add(run)
        db.commit()
        run_id = run.id

    async def claim_twice() -> None:
        await asyncio.gather(rag.experiments._run_queued_experiment(run_id), rag.experiments._run_queued_experiment(run_id))

    asyncio.run(claim_twice())

    with SessionLocal() as db:
        assert db.get(AIExperimentRun, run_id).status == "completed"
        assert db.query(AIQueryLog).filter(AIQueryLog.experiment_run_id == run_id).count() == 1


def test_interrupted_experiment_can_resume_remaining_cases(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    with SessionLocal() as db:
        run = AIExperimentRun(
            project_id=1,
            created_by=1,
            name="resume probe",
            status="interrupted",
            questions_json=["protocol"],
            modes_json=["project_rag"],
            total_cases=1,
            summary_json={
                "errors": [],
                "execution_plan": [
                    {
                        "question_index": 1,
                        "question": "protocol",
                        "repetition_index": 1,
                        "mode": "project_rag",
                        "execution_order": 1,
                    }
                ],
            },
        )
        db.add(run)
        db.commit()
        run_id = run.id

    export = client.get(f"/rag/experiments/{run_id}/export.csv")
    assert "not_executed" in export.text

    response = client.post(f"/rag/experiments/{run_id}/resume")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    completed = client.get(f"/rag/experiments/{run_id}").json()
    assert completed["status"] == "completed"
    assert completed["completed_cases"] == 1
    with SessionLocal() as db:
        assert db.query(AIQueryLog).filter(AIQueryLog.experiment_run_id == run_id).count() == 1
