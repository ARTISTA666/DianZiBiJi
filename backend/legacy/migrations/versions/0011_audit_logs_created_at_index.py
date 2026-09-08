"""Add created_at DESC index on audit_logs for time-ordered listings

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_audit_logs_created_at"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # CREATE INDEX CONCURRENTLY cannot run inside a transaction; the
        # IF NOT EXISTS clause keeps the migration idempotent (and usable in
        # offline --sql mode, where reflection is unavailable).
        with op.get_context().autocommit_block():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                "ON audit_logs (created_at DESC)"
            )
        return
    existing = {item["name"] for item in sa.inspect(bind).get_indexes("audit_logs")}
    if INDEX_NAME in existing:
        return
    op.create_index(INDEX_NAME, "audit_logs", [sa.text("created_at DESC")])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
        return
    existing = {item["name"] for item in sa.inspect(bind).get_indexes("audit_logs")}
    if INDEX_NAME not in existing:
        return
    op.drop_index(INDEX_NAME, table_name="audit_logs")
