from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import agents
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.ai import AgentGenerationRun, AgentTaskType
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
from app.models.note import ExperimentNote, NoteStatus, NoteVersion
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User, UserRole
from app.services import agent as agent_service
from app.services.deepseek import DeepSeekRequestError


def test_agent_relation_citations_match_visible_relation_budget():
    relations = [SimpleNamespace(id=index) for index in range(1, 41)]

    relation_ids = agent_service.AgentGenerationService()._select_relation_ids(
        [], relations, [], AgentTaskType.GRAPH_OVERVIEW.value
    )

    assert relation_ids == list(range(1, agent_service.MAX_OVERVIEW_RELATIONS + 1))


class FakeDeepSeekClient:
    last_user_prompt = ""

    async def generate(self, *, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> dict:
        FakeDeepSeekClient.last_user_prompt = user_prompt
        return {
            "answer": user_prompt,
            "request_id": "agent-request-1",
            "model": "deepseek-test",
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }


@pytest.fixture()
def test_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    upload_path = tmp_path / "paper.pdf"
    upload_path.write_text("paper", encoding="utf-8")

    db = SessionLocal()
    db.add_all(
        [
            User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
            User(id=2, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
            User(id=3, username="reader", password_hash="x", display_name="Reader", role=UserRole.MEMBER),
            Project(id=1, name="Project A", owner_user_id=1),
            Project(id=2, name="Project B", owner_user_id=1),
            ProjectMember(project_id=1, user_id=3, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
        ]
    )
    db.flush()
    note = ExperimentNote(
        id=1,
        project_id=1,
        title="Cell viability assay",
        experiment_type="Cell assay",
        experiment_date=date(2026, 6, 5),
        owner_user_id=1,
        status=NoteStatus.APPROVED,
    )
    draft_note = ExperimentNote(
        id=2,
        project_id=1,
        title="Draft note",
        experiment_type="PCR",
        experiment_date=date(2026, 6, 5),
        owner_user_id=1,
        status=NoteStatus.DRAFT,
    )
    db.add_all([note, draft_note])
    db.flush()
    version = NoteVersion(
        id=1,
        note_id=1,
        version_number=1,
        fixed_fields_json={"reagents": "PBS", "result": "Cells remained viable"},
        content_json={"text": "结果: Cells remained viable"},
        created_by=1,
        is_locked=True,
    )
    db.add(version)
    db.flush()
    note.current_version_id = version.id
    db.add(
        StoredFile(
            id=1,
            project_id=1,
            uploaded_by=1,
            file_category=FileCategory.KNOWLEDGE_DOCUMENT,
            original_filename="paper.pdf",
            storage_path=str(upload_path),
            file_size=5,
            file_hash="hash-1",
            status=FileStatus.APPROVED,
            knowledge_sync_status=KnowledgeSyncStatus.SYNCED.value,
        )
    )
    note_entity = KnowledgeEntity(
        id=1,
        project_id=1,
        entity_type="note",
        label="Cell viability assay",
        normalized_label="cell viability assay",
        natural_key="note:note:1",
        source_type="note",
        source_id=1,
    )
    result_entity = KnowledgeEntity(
        id=2,
        project_id=1,
        entity_type="result",
        label="Cells remained viable",
        normalized_label="cells remained viable",
        natural_key="result:cells remained viable",
    )
    db.add_all([note_entity, result_entity])
    db.flush()
    db.add(
        KnowledgeRelation(
            id=1,
            project_id=1,
            source_entity_id=1,
            target_entity_id=2,
            relation_type="produces_result",
            source_type="note_extraction",
            source_id=1,
            confidence=0.7,
        )
    )
    db.commit()
    db.close()

    active_user_id = {"value": 1}
    app = FastAPI()
    app.include_router(agents.router)

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
    monkeypatch.setattr(agent_service, "DeepSeekClient", FakeDeepSeekClient)
    return TestClient(app), SessionLocal, active_user_id


def test_agent_generation_uses_approved_notes_and_records_run(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1

    response = client.post(
        "/api/agents/generate",
        json={"project_id": 1, "task_type": "experiment_summary", "date_from": "2026-06-01", "date_to": "2026-06-06"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "experiment_summary"
    assert body["source_note_ids_json"] == [1]
    assert body["source_file_ids_json"] == [1]
    assert body["source_graph_relation_ids_json"] == [1]
    assert "[N1]" in FakeDeepSeekClient.last_user_prompt
    assert "[F1]" in FakeDeepSeekClient.last_user_prompt
    assert "[R1]" in FakeDeepSeekClient.last_user_prompt
    assert "Cell viability assay" in body["body"]
    assert "Draft note" not in body["body"]
    steps = body["input_params_json"]["collaboration_steps"]
    assert [step["key"] for step in steps] == ["evidence", "writer", "reviewer"]
    assert [step["status"] for step in steps] == ["completed", "completed", "completed"]
    assert body["input_params_json"]["review_result"]["passed"] is True

    with SessionLocal() as db:
        run = db.get(AgentGenerationRun, body["id"])
        assert run is not None
        assert run.status == "completed"

    history_response = client.get("/projects/1/agents/runs")
    assert history_response.status_code == 200
    assert history_response.json()[0]["id"] == body["id"]


def test_agent_generation_records_empty_range(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 1

    response = client.post(
        "/api/agents/generate",
        json={"project_id": 1, "task_type": "weekly_report", "date_from": "2026-05-01", "date_to": "2026-05-02"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_note_ids_json"] == []
    assert body["message"] == "No approved notes in selected range"
    assert "暂无已审核实验笔记" in body["body"]


def test_outsider_cannot_generate_or_view_agent_runs(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 2

    assert client.post("/api/agents/generate", json={"project_id": 1, "task_type": "experiment_summary"}).status_code == 403
    assert client.get("/projects/1/agents/runs").status_code == 403


def test_reader_can_view_but_cannot_generate_agent_runs(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 3

    assert client.get("/projects/1/agents/runs").status_code == 200
    assert client.post("/api/agents/generate", json={"project_id": 1, "task_type": "experiment_summary"}).status_code == 403


def test_agent_failure_is_persisted(test_app, monkeypatch: pytest.MonkeyPatch):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1

    class FailingDeepSeekClient:
        async def generate(self, **_kwargs):
            raise DeepSeekRequestError("upstream unavailable")

    monkeypatch.setattr(agent_service, "DeepSeekClient", FailingDeepSeekClient)
    response = client.post(
        "/api/agents/generate",
        json={"project_id": 1, "task_type": "experiment_summary"},
    )
    assert response.status_code == 502
    with SessionLocal() as db:
        run = db.query(AgentGenerationRun).order_by(AgentGenerationRun.id.desc()).first()
        assert run.status == "failed"
        assert run.message == "upstream unavailable"
        assert run.input_params_json["collaboration_steps"][1]["status"] == "failed"


def test_agent_reviewer_records_invalid_citations(test_app, monkeypatch: pytest.MonkeyPatch):
    client, _, active_user_id = test_app
    active_user_id["value"] = 1

    class InvalidCitationClient:
        async def generate(self, **_kwargs):
            return {"answer": "错误来源 [N999]，有效来源 [R1]。", "model": "deepseek-test", "usage": {}}

    monkeypatch.setattr(agent_service, "DeepSeekClient", InvalidCitationClient)
    response = client.post(
        "/api/agents/generate",
        json={"project_id": 1, "task_type": "experiment_summary"},
    )
    assert response.status_code == 200
    review = response.json()["input_params_json"]["review_result"]
    assert review["passed"] is False
    assert review["invalid_citations"] == ["[N999]"]
    assert response.json()["input_params_json"]["collaboration_steps"][-1]["status"] == "warning"
    assert response.json()["input_params_json"]["repair_attempted"] is True
    assert response.json()["status"] == "needs_review"


def test_agent_repairs_invalid_citations_once(test_app, monkeypatch: pytest.MonkeyPatch):
    client, _, active_user_id = test_app
    active_user_id["value"] = 1

    class RepairingCitationClient:
        calls = 0

        async def generate(self, **_kwargs):
            self.__class__.calls += 1
            answer = "错误来源 [N999]。" if self.__class__.calls == 1 else "修订后结论 [N1] [F1] [R1]。"
            return {"answer": answer, "model": "deepseek-test", "usage": {"completion_tokens": 5}}

    monkeypatch.setattr(agent_service, "DeepSeekClient", RepairingCitationClient)
    response = client.post(
        "/api/agents/generate",
        json={"project_id": 1, "task_type": "experiment_summary"},
    )

    assert response.status_code == 200
    body = response.json()
    assert RepairingCitationClient.calls == 2
    assert body["body"] == "修订后结论 [N1] [F1] [R1]。"
    assert body["input_params_json"]["review_result"]["passed"] is True
    assert body["status"] == "completed"
    assert [step["key"] for step in body["input_params_json"]["collaboration_steps"]][-2:] == ["repair", "recheck"]
