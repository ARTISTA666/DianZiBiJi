from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import rag
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.ai import AIQueryEvaluation, AIQueryLog
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.rag import ProjectRagDataset, RagFileSync
from app.models.user import User, UserRole
from app.services.dify import DifyRequestError


class FakeDifyClient:
    fail_upload = False
    last_query = ""
    last_graph_context = ""

    async def create_dataset(self, name: str) -> dict:
        return {"id": "dify-dataset-1", "name": name}

    async def upload_document_file(self, dataset_id: str, file_path: str, filename: str) -> dict:
        if self.fail_upload:
            raise DifyRequestError("upload failed")
        return {"document": {"id": "dify-document-1"}}

    async def chat(self, query: str, user_id: str, dataset_id: str, graph_context: str | None = None) -> dict:
        self.__class__.last_query = query
        self.__class__.last_graph_context = graph_context or ""
        return {
            "answer": f"answer for {query}",
            "conversation_id": "conversation-1",
            "metadata": {
                "retriever_resources": [
                    {
                        "document_id": "dify-document-1",
                        "document_name": "protocol.pdf",
                        "content": "matched source text",
                    }
                ]
            },
        }


@pytest.fixture()
def test_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    upload_path = tmp_path / "protocol.pdf"
    upload_path.write_text("protocol", encoding="utf-8")

    db = SessionLocal()
    db.add_all(
        [
            User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
            User(id=2, username="member", password_hash="x", display_name="Member", role=UserRole.MEMBER),
            User(id=3, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
            User(id=4, username="reviewer", password_hash="x", display_name="Reviewer", role=UserRole.MEMBER),
            Project(id=1, name="Project A", owner_user_id=1),
            ProjectMember(project_id=1, user_id=2, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
            ProjectMember(project_id=1, user_id=4, project_role=ProjectRole.REVIEWER, can_read=True, can_review=True),
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
    FakeDifyClient.fail_upload = False
    FakeDifyClient.last_query = ""
    FakeDifyClient.last_graph_context = ""
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
    monkeypatch.setattr(rag, "DifyClient", FakeDifyClient)

    return TestClient(app), SessionLocal, active_user_id


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


def test_reviewer_can_init_dataset(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 4
    response = client.post("/projects/1/rag/init")
    assert response.status_code == 200
    assert response.json()["initialized"] is True
    with SessionLocal() as db:
        assert db.query(ProjectRagDataset).filter(ProjectRagDataset.project_id == 1).count() == 1


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
        assert sync.dify_document_id == "dify-document-1"


def test_sync_failure_marks_file_failed(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    FakeDifyClient.fail_upload = True
    try:
        response = client.post("/files/1/rag/sync")
    finally:
        FakeDifyClient.fail_upload = False
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
    assert body["answer"] == "answer for protocol"
    assert body["sources"][0]["filename"] == "protocol.pdf"
    assert body["rag_mode"] == "project_rag"
    assert body["graph_context"] == []
    assert body["query_log_id"] is not None
    assert body["response_ms"] >= 0
    with active_session() as db:
        log = db.get(AIQueryLog, body["query_log_id"])
        assert log is not None
        assert log.question == "protocol"
        assert log.answer == "answer for protocol"
        assert log.rag_mode == "project_rag"
        assert log.source_count == 1


def test_query_uses_knowledge_graph_context_when_available(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1
    client.post("/projects/1/rag/init")
    client.post("/files/1/rag/sync")
    with SessionLocal() as db:
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
    assert "实验知识图谱上下文" in FakeDifyClient.last_graph_context
    assert "PBS" in FakeDifyClient.last_graph_context
    assert FakeDifyClient.last_query == "这个实验用了哪些试剂？"
    with SessionLocal() as db:
        log = db.get(AIQueryLog, body["query_log_id"])
        assert log.rag_mode == "kg_enhanced_rag"
        assert log.graph_hit_count > 0
        assert log.graph_context_json[0]["target_label"] == "PBS"


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
    assert FakeDifyClient.last_graph_context == ""


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

    evaluation_response = client.post(
        f"/rag/query-logs/{log_id}/evaluation",
        json={"score": 5, "is_accurate": True, "is_traceable": True, "comment": "依据清晰"},
    )
    assert evaluation_response.status_code == 200
    assert evaluation_response.json()["score"] == 5

    logs_response = client.get("/projects/1/rag/query-logs")
    assert logs_response.json()[0]["evaluation"]["comment"] == "依据清晰"
    with SessionLocal() as db:
        assert db.query(AIQueryEvaluation).filter(AIQueryEvaluation.query_log_id == log_id).count() == 1

    active_user_id["value"] = 2
    assert client.post(f"/rag/query-logs/{log_id}/evaluation", json={"score": 1}).status_code == 403

    active_user_id["value"] = 3
    assert client.get("/projects/1/rag/query-logs").status_code == 403
    assert client.post(f"/rag/query-logs/{log_id}/evaluation", json={"score": 1}).status_code == 403


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
        json={"score": 3, "is_accurate": True, "is_traceable": False},
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
    FakeDifyClient.fail_upload = False

    original_chat = FakeDifyClient.chat

    async def fail_chat(self, query: str, user_id: str, dataset_id: str, graph_context: str | None = None) -> dict:
        raise DifyRequestError("chat failed")

    FakeDifyClient.chat = fail_chat
    try:
        response = client.post("/projects/1/rag/query", json={"query": "protocol"})
    finally:
        FakeDifyClient.chat = original_chat

    assert response.status_code == 502
    with SessionLocal() as db:
        log = db.query(AIQueryLog).order_by(AIQueryLog.id.desc()).first()
        assert log.question == "protocol"
        assert log.error_message == "chat failed"
