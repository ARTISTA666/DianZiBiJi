from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.database import Base
from app.models import *  # noqa: F403
from scripts.verify_runtime_schema import build_report


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def upgrade(database_path: Path) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")


def postgresql_upgrade_sql(revision: str) -> str:
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", "postgresql://eln:eln@localhost/eln")
    with redirect_stdout(output):
        command.upgrade(config, revision, sql=True)
    return output.getvalue()


def test_hnsw_concurrent_index_is_created_outside_a_transaction() -> None:
    sql = postgresql_upgrade_sql(
        "0004_experiment_single_active:0005_rag_chunks_hnsw_index"
    )
    transaction_open = False
    index_seen = False
    for line in sql.splitlines():
        statement = line.strip().upper()
        if statement == "BEGIN;":
            transaction_open = True
        elif statement == "COMMIT;":
            transaction_open = False
        elif statement.startswith("CREATE INDEX CONCURRENTLY"):
            index_seen = True
            assert transaction_open is False

    assert index_seen is True


def test_empty_database_upgrades_to_current_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh.db"

    upgrade(database_path)
    upgrade(database_path)

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert set(Base.metadata.tables) <= set(inspector.get_table_names())
    assert build_report(inspector, "sqlite")["ok"] is True
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0007_notes_status_updated_index"


def test_one_active_experiment_per_project_is_database_enforced(tmp_path: Path) -> None:
    database_path = tmp_path / "active-experiment.db"
    upgrade(database_path)
    engine = create_engine(f"sqlite:///{database_path}")

    insert = text(
        """
        INSERT INTO ai_experiment_runs (
            project_id, created_by, name, status, questions_json, modes_json,
            config_snapshot_json, summary_json, total_cases, completed_cases,
            failed_cases, completed_at
        ) VALUES (
            :project_id, 1, :name, :status, '[]', '[]', '{}', '{}', 0, 0, 0, NULL
        )
        """
    )
    with engine.begin() as connection:
        connection.execute(
            insert,
            {"project_id": 101, "name": "first", "status": "queued"},
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                insert,
                {"project_id": 101, "name": "second", "status": "running"},
            )
    with engine.begin() as connection:
        connection.execute(
            insert,
            {"project_id": 102, "name": "other project", "status": "queued"},
        )
        connection.execute(
            insert,
            {"project_id": 101, "name": "terminal", "status": "completed"},
        )

    indexes = {item["name"]: item for item in inspect(engine).get_indexes("ai_experiment_runs")}
    assert indexes["uq_ai_experiment_runs_one_active_per_project"]["unique"] == 1


def test_legacy_database_keeps_rows_and_receives_runtime_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path}")
    legacy_tables = (
        "CREATE TABLE files (id INTEGER PRIMARY KEY)",
        "CREATE TABLE project_members (id INTEGER PRIMARY KEY)",
        "CREATE TABLE project_rag_datasets (id INTEGER PRIMARY KEY)",
        "CREATE TABLE rag_file_syncs (id INTEGER PRIMARY KEY)",
        "CREATE TABLE ai_query_logs (id INTEGER PRIMARY KEY)",
        "CREATE TABLE ai_query_evaluations ("
        "id INTEGER PRIMARY KEY, query_log_id INTEGER NOT NULL, evaluator_user_id INTEGER NOT NULL, "
        "CONSTRAINT uq_ai_query_evaluation_log UNIQUE (query_log_id))",
        "CREATE TABLE agent_generation_runs (id INTEGER PRIMARY KEY)",
    )
    with engine.begin() as connection:
        for statement in legacy_tables:
            connection.execute(text(statement))
        connection.execute(text("INSERT INTO files (id) VALUES (7)"))
        connection.execute(text("INSERT INTO ai_query_logs (id) VALUES (11)"))
        connection.execute(
            text(
                "INSERT INTO ai_query_evaluations "
                "(id, query_log_id, evaluator_user_id) VALUES (13, 11, 2)"
            )
        )

    upgrade(database_path)

    inspector = inspect(engine)
    expected_columns = {
        "files": {"knowledge_sync_status", "knowledge_synced_at", "knowledge_sync_message"},
        "project_members": {"can_evaluate"},
        "project_rag_datasets": {"provider", "embedding_model", "generation_model"},
        "rag_file_syncs": {"chunk_count", "content_hash"},
        "ai_query_logs": {
            "provider",
            "model_name",
            "prompt_version",
            "retrieval_config_json",
            "usage_json",
            "fallback_reason",
            "experiment_run_id",
            "experiment_case_index",
            "experiment_repetition_index",
            "experiment_execution_order",
        },
        "ai_query_evaluations": {"review_protocol"},
        "agent_generation_runs": {"provider", "model_name", "prompt_version", "usage_json"},
    }
    for table_name, expected in expected_columns.items():
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        assert expected <= actual

    constraints = {
        item["name"]: tuple(item["column_names"])
        for item in inspector.get_unique_constraints("ai_query_evaluations")
    }
    assert "uq_ai_query_evaluation_log" not in constraints
    assert constraints["uq_ai_query_evaluation_log_evaluator"] == (
        "query_log_id",
        "evaluator_user_id",
    )
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT knowledge_sync_status FROM files WHERE id = 7")) == "not_applicable"
        saved = connection.execute(
            text(
                "SELECT query_log_id, evaluator_user_id, review_protocol "
                "FROM ai_query_evaluations WHERE id = 13"
            )
        ).one()
        assert saved == (11, 2, "unblinded")
