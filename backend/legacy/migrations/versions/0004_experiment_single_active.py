"""Enforce one queued or running experiment per project.

Revision ID: 0004_experiment_single_active
Revises: 0003_user_auth_version
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op


revision = "0004_experiment_single_active"
down_revision = "0003_user_auth_version"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_ai_experiment_runs_one_active_per_project"
LEASE_INDEX_NAME = "ix_ai_experiment_runs_lease"
ACTIVE_PREDICATE = sa.text("status IN ('queued', 'running')")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("ai_experiment_runs")}
    for column in (
        sa.Column("worker_id", sa.String(length=80), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    ):
        if column.name not in columns:
            op.add_column("ai_experiment_runs", column)

    indexes = {item["name"] for item in inspector.get_indexes("ai_experiment_runs")}
    if INDEX_NAME not in indexes:
        op.create_index(
            INDEX_NAME,
            "ai_experiment_runs",
            ["project_id"],
            unique=True,
            postgresql_where=ACTIVE_PREDICATE,
            sqlite_where=ACTIVE_PREDICATE,
        )
    if LEASE_INDEX_NAME not in indexes:
        op.create_index(
            LEASE_INDEX_NAME,
            "ai_experiment_runs",
            ["status", "lease_expires_at"],
            unique=False,
        )


def downgrade() -> None:
    raise RuntimeError("Experiment concurrency downgrade is intentionally disabled")
