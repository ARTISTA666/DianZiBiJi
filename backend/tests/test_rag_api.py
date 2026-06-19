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
from app.models.ai import AIExperimentRun, AIQueryEvaluation, AIQueryLog
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
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

    @staticmethod
    def format_sources(sources, max_chars: int = 6000) -> str:
        return "项目资料检索结果：\n[S1] matched source text"


class FakeDeepSeekClient:
    last_user_prompt = ""

    async def generate(self, *, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> dict:
        self.__class__.last_user_prompt = user_prompt
        question = user_prompt.rsplit("用户问题：", 1)[-1]
        return {
            "answer": f"answer for {question}",
            "request_id": "deepseek-request-1",
            "model": "deepseek-test",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
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
    FakeLocalRagService.fail_index = False
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
    monkeypatch.setattr(rag, "LocalRagService", FakeLocalRagService)
    monkeypatch.setattr(rag, "DeepSeekClient", FakeDeepSeekClient)

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
    assert "实验知识图谱上下文" in FakeDeepSeekClient.last_user_prompt
    assert "[G1]" in FakeDeepSeekClient.last_user_prompt
    assert "PBS" in FakeDeepSeekClient.last_user_prompt
    assert "用户问题：这个实验用了哪些试剂？" in FakeDeepSeekClient.last_user_prompt
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

    logs_response = client.get("/projects/1/rag/query-logs")
    assert logs_response.json()[0]["evaluation"]["comment"] == "依据清晰"
    with SessionLocal() as db:
        assert db.query(AIQueryEvaluation).filter(AIQueryEvaluation.query_log_id == log_id).count() == 1

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


def test_rag_experiment_pairs_modes_and_exports_csv(test_app):
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
            "name": "paired comparison",
            "questions": ["PBS 是什么用途？"],
            "modes": ["project_rag", "kg_enhanced_rag"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["total_cases"] == 2
    assert body["completed_cases"] == 2
    assert body["failed_cases"] == 0
    assert body["config_snapshot_json"]["prompt_version"] == rag.PROMPT_VERSION

    with SessionLocal() as db:
        run = db.get(AIExperimentRun, body["id"])
        logs = db.query(AIQueryLog).filter(AIQueryLog.experiment_run_id == run.id).all()
        assert {log.rag_mode for log in logs} == {"project_rag", "kg_enhanced_rag"}
        assert {log.experiment_case_index for log in logs} == {1}

    export = client.get(f"/rag/experiments/{body['id']}/export.csv")
    assert export.status_code == 200
    assert export.content.startswith(b"\xef\xbb\xbf")
    assert b"project_rag" in export.content
    assert b"kg_enhanced_rag" in export.content
