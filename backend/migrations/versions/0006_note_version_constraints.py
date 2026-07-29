"""Add note version unique constraint and missing foreign keys.

Revision ID: 0006_note_version_constraints
Revises: 0005_rag_chunks_hnsw_index
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op


revision = "0006_note_version_constraints"
down_revision = "0005_rag_chunks_hnsw_index"
branch_labels = None
depends_on = None


UQ_NAME = "uq_note_version_number"
FK_TEMPLATE = "fk_experiment_notes_template_id"
FK_VERSION = "fk_experiment_notes_current_version_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add unique constraint on (note_id, version_number) in note_versions
    existing_uqs = {item["name"] for item in inspector.get_unique_constraints("note_versions")}
    if UQ_NAME not in existing_uqs:
        op.create_unique_constraint(UQ_NAME, "note_versions", ["note_id", "version_number"])

    # 2. Add FK template_id -> experiment_templates.id on experiment_notes
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("experiment_notes")}
    if FK_TEMPLATE not in existing_fks:
        with op.batch_alter_table("experiment_notes") as batch_op:
            batch_op.create_foreign_key(
                FK_TEMPLATE,
                "experiment_templates",
                ["template_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # 3. Add FK current_version_id -> note_versions.id on experiment_notes
    # Re-inspect after batch alter to pick up the newly added FK
    inspector = sa.inspect(bind)
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("experiment_notes")}
    if FK_VERSION not in existing_fks:
        with op.batch_alter_table("experiment_notes") as batch_op:
            batch_op.create_foreign_key(
                FK_VERSION,
                "note_versions",
                ["current_version_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("experiment_notes")}

    # Drop FKs first (order doesn't strictly matter, but be explicit)
    if FK_VERSION in existing_fks:
        with op.batch_alter_table("experiment_notes") as batch_op:
            batch_op.drop_constraint(FK_VERSION, type_="foreignkey")

    # Re-inspect after batch alter
    inspector = sa.inspect(bind)
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("experiment_notes")}
    if FK_TEMPLATE in existing_fks:
        with op.batch_alter_table("experiment_notes") as batch_op:
            batch_op.drop_constraint(FK_TEMPLATE, type_="foreignkey")

    # Drop unique constraint
    inspector = sa.inspect(bind)
    existing_uqs = {item["name"] for item in inspector.get_unique_constraints("note_versions")}
    if UQ_NAME in existing_uqs:
        with op.batch_alter_table("note_versions") as batch_op:
            batch_op.drop_constraint(UQ_NAME, type_="unique")
