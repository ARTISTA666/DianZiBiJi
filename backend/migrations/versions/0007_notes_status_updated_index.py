"""Add composite index on experiment_notes(status, updated_at).

Revision ID: 0007_notes_status_updated_index
Revises: 0006_note_version_constraints
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op


revision = "0007_notes_status_updated_index"
down_revision = "0006_note_version_constraints"
branch_labels = None
depends_on = None


IX_NAME = "ix_notes_status_updated"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_idxs = {idx["name"] for idx in inspector.get_indexes("experiment_notes")}
    if IX_NAME not in existing_idxs:
        op.create_index(IX_NAME, "experiment_notes", ["status", "updated_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_idxs = {idx["name"] for idx in inspector.get_indexes("experiment_notes")}
    if IX_NAME in existing_idxs:
        op.drop_index(IX_NAME, table_name="experiment_notes")
