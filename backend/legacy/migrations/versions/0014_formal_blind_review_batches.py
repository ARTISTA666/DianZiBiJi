"""Add formal blind-review batch assignments

Revision ID: 0014_formal_blind_review_batches
Revises: 0013_rust_retrieval_identity
Create Date: 2026-08-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_formal_blind_review_batches"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_blind_review_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "experiment_run_id",
            sa.Integer(),
            sa.ForeignKey("ai_experiment_runs.id"),
            nullable=False,
        ),
        sa.Column("freeze_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("reviewer_a_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewer_b_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="LOCKED",
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("unblinded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unblinded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("experiment_run_id", name="uq_ai_blind_review_batches_experiment_run"),
        sa.CheckConstraint("reviewer_a_user_id <> reviewer_b_user_id", name="ck_ai_blind_review_batches_distinct_reviewers"),
        sa.CheckConstraint("status IN ('LOCKED', 'UNBLINDED')", name="ck_ai_blind_review_batches_status"),
    )
    op.create_index(
        "ix_ai_blind_review_batches_project_id",
        "ai_blind_review_batches",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_blind_review_batches_project_id", table_name="ai_blind_review_batches")
    op.drop_table("ai_blind_review_batches")
