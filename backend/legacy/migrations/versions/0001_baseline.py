"""Create the baseline schema without altering existing tables.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-13
"""

from alembic import op

from app.core.database import Base
from app.models import *  # noqa: F403


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=connection)


def downgrade() -> None:
    raise RuntimeError("The baseline migration cannot be downgraded without deleting user data")
