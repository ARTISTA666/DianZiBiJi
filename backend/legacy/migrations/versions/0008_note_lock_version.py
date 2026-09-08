"""Add lock_version column to experiment_notes for optimistic locking.

Revision ID: 0008_note_lock_version
Revises: 0007_notes_status_updated_index
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op


revision = "0008_note_lock_version"
down_revision = "0007_notes_status_updated_index"
branch_labels = None
depends_on = None


COL_NAME = "lock_version"
TABLE_NAME = "experiment_notes"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns(TABLE_NAME)}
    if COL_NAME not in existing_cols:
        op.add_column(TABLE_NAME, sa.Column(COL_NAME, sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns(TABLE_NAME)}
    if COL_NAME in existing_cols:
        op.drop_column(TABLE_NAME, COL_NAME)
