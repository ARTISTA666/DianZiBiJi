"""Add foreign key indexes for query performance

Revision ID: 0009_add_foreign_key_indexes
Revises: 0008_note_lock_version
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_add_foreign_key_indexes"
down_revision = "0008_note_lock_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for name, table, columns in (
        ("ix_experiment_notes_project_id", "experiment_notes", ["project_id"]),
        ("ix_files_project_id", "files", ["project_id"]),
        ("ix_audit_logs_project_id_created", "audit_logs", ["project_id", "created_at"]),
        ("ix_note_versions_note_id", "note_versions", ["note_id"]),
        ("ix_experiment_notes_owner_user_id", "experiment_notes", ["owner_user_id"]),
    ):
        existing = {item["name"] for item in inspector.get_indexes(table)}
        available_columns = {item["name"] for item in inspector.get_columns(table)}
        if name not in existing and set(columns) <= available_columns:
            op.create_index(name, table, columns)
        inspector = sa.inspect(op.get_bind())


def downgrade() -> None:
    op.drop_index("ix_experiment_notes_owner_user_id")
    op.drop_index("ix_note_versions_note_id")
    op.drop_index("ix_audit_logs_project_id_created")
    op.drop_index("ix_files_project_id")
    op.drop_index("ix_experiment_notes_project_id")
