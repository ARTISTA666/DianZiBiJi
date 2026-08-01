"""Add foreign key indexes for query performance

Revision ID: 0009_add_foreign_key_indexes
Revises: 0008_note_lock_version
Create Date: 2026-07-30
"""

from alembic import op

revision = "0009_add_foreign_key_indexes"
down_revision = "0008_note_lock_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_experiment_notes_project_id", "experiment_notes", ["project_id"])
    op.create_index("ix_files_project_id", "files", ["project_id"])
    op.create_index("ix_audit_logs_project_id_created", "audit_logs", ["project_id", "created_at"])
    op.create_index("ix_note_versions_note_id", "note_versions", ["note_id"])
    op.create_index("ix_experiment_notes_owner_user_id", "experiment_notes", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_experiment_notes_owner_user_id")
    op.drop_index("ix_note_versions_note_id")
    op.drop_index("ix_audit_logs_project_id_created")
    op.drop_index("ix_files_project_id")
    op.drop_index("ix_experiment_notes_project_id")
