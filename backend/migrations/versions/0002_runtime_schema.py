"""Replace startup-time schema patches with a tracked migration.

Revision ID: 0002_runtime_schema
Revises: 0001_baseline
Create Date: 2026-07-13
"""

from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op


revision = "0002_runtime_schema"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _add_columns(table_name: str, columns: Iterable[sa.Column]) -> None:
    existing = _column_names(table_name)
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def _ensure_index(name: str, table_name: str, columns: list[str]) -> None:
    existing = {index["name"] for index in _inspector().get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=False)


def _ensure_query_log_foreign_key() -> None:
    foreign_keys = _inspector().get_foreign_keys("ai_query_logs")
    if any(
        item.get("constrained_columns") == ["experiment_run_id"]
        and item.get("referred_table") == "ai_experiment_runs"
        for item in foreign_keys
    ):
        return
    name = "fk_ai_query_logs_experiment_run_id_ai_experiment_runs"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("ai_query_logs") as batch:
            batch.create_foreign_key(name, "ai_experiment_runs", ["experiment_run_id"], ["id"])
    else:
        op.create_foreign_key(
            name,
            "ai_query_logs",
            "ai_experiment_runs",
            ["experiment_run_id"],
            ["id"],
        )


def _upgrade_evaluation_constraint() -> None:
    constraints = {
        item.get("name"): tuple(item.get("column_names") or [])
        for item in _inspector().get_unique_constraints("ai_query_evaluations")
    }
    legacy = "uq_ai_query_evaluation_log"
    current = "uq_ai_query_evaluation_log_evaluator"
    needs_legacy_drop = legacy in constraints
    needs_current = constraints.get(current) != ("query_log_id", "evaluator_user_id")
    if not needs_legacy_drop and not needs_current:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("ai_query_evaluations") as batch:
            if needs_legacy_drop:
                batch.drop_constraint(legacy, type_="unique")
            if needs_current:
                batch.create_unique_constraint(current, ["query_log_id", "evaluator_user_id"])
        return
    if needs_legacy_drop:
        op.drop_constraint(legacy, "ai_query_evaluations", type_="unique")
    if needs_current:
        op.create_unique_constraint(
            current,
            "ai_query_evaluations",
            ["query_log_id", "evaluator_user_id"],
        )


def upgrade() -> None:
    json_default = sa.text("'{}'")
    _add_columns(
        "files",
        [
            sa.Column("knowledge_sync_status", sa.String(40), nullable=False, server_default="not_applicable"),
            sa.Column("knowledge_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("knowledge_sync_message", sa.Text(), nullable=True),
        ],
    )
    _add_columns(
        "project_members",
        [sa.Column("can_evaluate", sa.Boolean(), nullable=False, server_default=sa.false())],
    )
    _add_columns(
        "project_rag_datasets",
        [
            sa.Column("provider", sa.String(40), nullable=False, server_default="local_deepseek"),
            sa.Column("embedding_model", sa.String(160), nullable=False, server_default="BAAI/bge-small-zh-v1.5"),
            sa.Column("generation_model", sa.String(120), nullable=False, server_default="deepseek-v4-flash"),
        ],
    )
    _add_columns(
        "rag_file_syncs",
        [
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("content_hash", sa.String(64), nullable=True),
        ],
    )
    _add_columns(
        "ai_query_logs",
        [
            sa.Column("provider", sa.String(40), nullable=False, server_default="deepseek"),
            sa.Column("model_name", sa.String(120), nullable=True),
            sa.Column("prompt_version", sa.String(40), nullable=False, server_default="rag-v1"),
            sa.Column("retrieval_config_json", sa.JSON(), nullable=False, server_default=json_default),
            sa.Column("usage_json", sa.JSON(), nullable=False, server_default=json_default),
            sa.Column("fallback_reason", sa.Text(), nullable=True),
            sa.Column("experiment_run_id", sa.Integer(), nullable=True),
            sa.Column("experiment_case_index", sa.Integer(), nullable=True),
            sa.Column("experiment_repetition_index", sa.Integer(), nullable=True),
            sa.Column("experiment_execution_order", sa.Integer(), nullable=True),
        ],
    )
    _add_columns(
        "ai_query_evaluations",
        [sa.Column("review_protocol", sa.String(40), nullable=False, server_default="unblinded")],
    )
    _add_columns(
        "agent_generation_runs",
        [
            sa.Column("provider", sa.String(40), nullable=False, server_default="deepseek"),
            sa.Column("model_name", sa.String(120), nullable=True),
            sa.Column("prompt_version", sa.String(40), nullable=False, server_default="agent-v1"),
            sa.Column("usage_json", sa.JSON(), nullable=False, server_default=json_default),
        ],
    )

    _ensure_query_log_foreign_key()
    _upgrade_evaluation_constraint()
    for name, table, columns in (
        ("ix_files_knowledge_sync_status", "files", ["knowledge_sync_status"]),
        ("ix_project_rag_datasets_provider", "project_rag_datasets", ["provider"]),
        ("ix_rag_file_syncs_content_hash", "rag_file_syncs", ["content_hash"]),
        ("ix_ai_query_logs_provider", "ai_query_logs", ["provider"]),
        ("ix_ai_query_logs_model_name", "ai_query_logs", ["model_name"]),
        ("ix_ai_query_logs_experiment_run_id", "ai_query_logs", ["experiment_run_id"]),
        ("ix_ai_query_evaluations_review_protocol", "ai_query_evaluations", ["review_protocol"]),
        ("ix_agent_generation_runs_provider", "agent_generation_runs", ["provider"]),
    ):
        _ensure_index(name, table, columns)


def downgrade() -> None:
    raise RuntimeError("Runtime schema downgrade is intentionally disabled to protect existing data")
