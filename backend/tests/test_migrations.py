from __future__ import annotations

import os
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
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


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


def test_audit_created_at_index_is_created_concurrently_outside_a_transaction() -> None:
    sql = postgresql_upgrade_sql("0010:0011")
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
            assert "IX_AUDIT_LOGS_CREATED_AT" in statement

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
        # Rust 运行时以自身 ensure 路径为权威；alembic 链仅作 legacy/开发路径镜像，head 随最新迁移前进。
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0014_formal_blind_review_batches"


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
        "ai_blind_review_batches": {
            "project_id",
            "experiment_run_id",
            "freeze_manifest_sha256",
            "reviewer_a_user_id",
            "reviewer_b_user_id",
            "status",
            "created_by",
        },
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


@pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith(("postgresql://", "postgres://")),
    reason="requires the real PostgreSQL migration test database",
)
def test_postgresql_head_contains_rust_retrieval_schema_contract(db_engine) -> None:
    """The real migration head must expose the columns used by Rust retrieval."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        db_engine.url.render_as_string(hide_password=False),
    )
    command.upgrade(config, "head")

    with db_engine.connect() as connection:
        columns = {
            (row.table_name, row.column_name): row
            for row in connection.execute(
                text(
                    """
                    SELECT table_name, column_name, data_type, character_maximum_length,
                           is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name IN ('rag_file_syncs', 'rag_document_chunks')
                    """
                )
            )
        }
        assert ("rag_file_syncs", "index_version") in columns
        assert ("rag_document_chunks", "chunk_version") in columns
        assert ("rag_document_chunks", "index_version") in columns
        for key in (
            ("rag_file_syncs", "index_version"),
            ("rag_document_chunks", "chunk_version"),
            ("rag_document_chunks", "index_version"),
        ):
            column = columns[key]
            assert column.data_type == "character varying"
            assert column.character_maximum_length == 80
            assert column.is_nullable == "NO"
            assert "legacy-unknown" in (column.column_default or "")
        assert connection.scalar(
            text(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'rag_document_chunks'
                  AND indexname = 'ix_rag_chunks_project_version'
                """
            )
        ) == 1
        assert connection.scalar(
            text(
                """
                SELECT pg_get_indexdef(oid)
                FROM pg_class
                WHERE relname = 'ix_rag_chunks_project_version'
                  AND relkind = 'i'
                """
            )
        ).endswith("(project_id, index_version, id)")


@pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith(("postgresql://", "postgres://")),
    reason="requires the real PostgreSQL migration test database",
)
def test_postgresql_legacy_rows_receive_unknown_identity_and_runtime_repair_is_idempotent(
    db_engine,
) -> None:
    """Upgrade a pre-0013 database, including a database already repaired at runtime."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        db_engine.url.render_as_string(hide_password=False),
    )
    command.upgrade(config, "0012")

    legacy_embedding = "[" + ",".join("0" for _ in range(512)) + "]"
    with db_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users (
                    id, username, password_hash, display_name, role, status, auth_version
                ) VALUES (
                    9001, 'migration-user', 'not-a-password', 'Migration User',
                    'MEMBER', 'ACTIVE', 0
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO projects (id, name, is_sensitive, status, approval_enabled, owner_user_id)
                VALUES (9001, 'migration-project', false, 'ACTIVE', true, 9001)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO files (
                    id, project_id, uploaded_by, file_category, original_filename,
                    storage_path, file_size, file_hash, status, knowledge_sync_status
                ) VALUES (
                    9001, 9001, 9001, 'KNOWLEDGE_DOCUMENT', 'migration.txt',
                    'migration.txt', 4, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'APPROVED', 'SYNCED'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO rag_file_syncs (
                    id, file_id, project_id, dify_dataset_id, sync_status, chunk_count, content_hash
                ) VALUES (9001, 9001, 9001, 'legacy-dataset', 'synced', 1, :content_hash)
                """
            ),
            {"content_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
        )
        connection.execute(
            text(
                """
                INSERT INTO rag_document_chunks (
                    id, project_id, file_id, chunk_index, content, content_hash,
                    character_count, embedding, metadata_json
                ) VALUES (
                    9001, 9001, 9001, 0, 'test',
                    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
                    4, CAST(:embedding AS vector), '{}'
                )
                """
            ),
            {"embedding": legacy_embedding},
        )
    command.upgrade(config, "head")

    with db_engine.connect() as connection:
        values = connection.execute(
            text(
                """
                SELECT r.index_version, r.sync_status, c.chunk_version, c.index_version
                FROM rag_file_syncs AS r
                JOIN rag_document_chunks AS c ON c.file_id = r.file_id
                WHERE r.id = 9001 AND c.id = 9001
                """
            )
        ).one()
        assert values == ("legacy-unknown", "stale", "legacy-unknown", "legacy-unknown")
        defaults = {
            (row.table_name, row.column_name): row.column_default
            for row in connection.execute(
                text(
                    """
                    SELECT table_name, column_name, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name IN ('rag_file_syncs', 'rag_document_chunks')
                      AND column_name IN ('chunk_version', 'index_version')
                    """
                )
            )
        }
        assert all("legacy-unknown" in (value or "") for value in defaults.values())

    # The same production-compatible repair is safe after 0013.  Explicitly
    # exercise the old marker to prove it cannot survive as provenance.
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE rag_file_syncs SET index_version = 'legacy-v1' WHERE id = 9001"))
        connection.execute(text("UPDATE rag_document_chunks SET chunk_version = 'legacy-v1', index_version = 'legacy-v1' WHERE id = 9001"))
        connection.execute(
            text(
                "ALTER TABLE rag_file_syncs ADD COLUMN IF NOT EXISTS "
                "index_version varchar(80) NOT NULL DEFAULT 'legacy-unknown'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE rag_document_chunks ADD COLUMN IF NOT EXISTS "
                "chunk_version varchar(80) NOT NULL DEFAULT 'legacy-unknown'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE rag_document_chunks ADD COLUMN IF NOT EXISTS "
                "index_version varchar(80) NOT NULL DEFAULT 'legacy-unknown'"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rag_chunks_project_version "
                "ON rag_document_chunks (project_id, index_version, id)"
            )
        )
        connection.execute(
            text(
                "UPDATE rag_file_syncs SET index_version = 'legacy-unknown' "
                "WHERE index_version = 'legacy-v1'"
            )
        )
        connection.execute(
            text(
                "UPDATE rag_document_chunks SET chunk_version = 'legacy-unknown' "
                "WHERE chunk_version = 'legacy-v1'"
            )
        )
        connection.execute(
            text(
                "UPDATE rag_document_chunks SET index_version = 'legacy-unknown' "
                "WHERE index_version = 'legacy-v1'"
            )
        )
        repaired = connection.execute(
            text(
                "SELECT r.index_version, c.chunk_version, c.index_version "
                "FROM rag_file_syncs AS r "
                "JOIN rag_document_chunks AS c ON c.file_id = r.file_id "
                "WHERE r.id = 9001 AND c.id = 9001"
            )
        ).one()
        assert repaired == ("legacy-unknown", "legacy-unknown", "legacy-unknown")
