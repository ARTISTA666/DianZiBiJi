"""Add unique constraint on kg_entities natural_key and index on normalized_label

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


UNIQUE_INDEX_NAME = "ux_kg_entities_project_natural_key"
LABEL_INDEX_NAME = "ix_kg_entities_project_normalized_label"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            # Deduplicate existing rows that share the same (project_id, natural_key)
            # before creating the unique index.  Keep the row with the smallest id.
            op.execute(
                """
                DELETE FROM kg_entities
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM kg_entities
                    GROUP BY project_id, natural_key
                )
                """
            )
            op.execute(
                f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {UNIQUE_INDEX_NAME} "
                "ON kg_entities (project_id, natural_key)"
            )
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {LABEL_INDEX_NAME} "
                "ON kg_entities (project_id, normalized_label)"
            )
        return

    # SQLite fallback (test environments)
    existing_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("kg_entities")}
    if UNIQUE_INDEX_NAME not in existing_indexes:
        op.create_index(
            UNIQUE_INDEX_NAME,
            "kg_entities",
            ["project_id", "natural_key"],
            unique=True,
        )
    if LABEL_INDEX_NAME not in existing_indexes:
        op.create_index(
            LABEL_INDEX_NAME,
            "kg_entities",
            ["project_id", "normalized_label"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {LABEL_INDEX_NAME}")
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {UNIQUE_INDEX_NAME}")
        return
    existing_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("kg_entities")}
    if LABEL_INDEX_NAME in existing_indexes:
        op.drop_index(LABEL_INDEX_NAME, table_name="kg_entities")
    if UNIQUE_INDEX_NAME in existing_indexes:
        op.drop_index(UNIQUE_INDEX_NAME, table_name="kg_entities")
