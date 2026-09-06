"""Add knowledge blueprint tables (动态知识蓝图：计划态节点/边、来源优先级与解析留痕)

Revision ID: 0015_kg_blueprint
Revises: 0014_formal_blind_review_batches
Create Date: 2026-09-06 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0015_kg_blueprint"
down_revision = "0014_formal_blind_review_batches"
branch_labels = None
depends_on = None

RETIRED_FILTER = "status <> 'retired'"


def upgrade() -> None:
    op.create_table(
        "kg_blueprint_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("normalized_label", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("source_kind", sa.String(length=24), nullable=False, server_default="plan_document"),
        sa.Column("source_label", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_kg_blueprint_nodes_project",
        "kg_blueprint_nodes",
        ["project_id"],
    )
    op.create_index(
        "uq_kg_blueprint_node_label",
        "kg_blueprint_nodes",
        ["project_id", "entity_type", "normalized_label"],
        unique=True,
        postgresql_where=sa.text(RETIRED_FILTER),
        sqlite_where=sa.text(RETIRED_FILTER),
    )

    op.create_table(
        "kg_blueprint_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "source_node_id",
            sa.Integer(),
            sa.ForeignKey("kg_blueprint_nodes.id"),
            nullable=False,
        ),
        sa.Column(
            "target_node_id",
            sa.Integer(),
            sa.ForeignKey("kg_blueprint_nodes.id"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("source_kind", sa.String(length=24), nullable=False, server_default="plan_document"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_kg_blueprint_edges_project",
        "kg_blueprint_edges",
        ["project_id"],
    )
    op.create_index(
        "uq_kg_blueprint_edge",
        "kg_blueprint_edges",
        ["project_id", "source_node_id", "target_node_id", "relation_type"],
        unique=True,
        postgresql_where=sa.text(RETIRED_FILTER),
        sqlite_where=sa.text(RETIRED_FILTER),
    )

    op.create_table(
        "kg_blueprint_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_kind", sa.String(length=24), nullable=False),
        sa.Column("parse_mode", sa.String(length=16), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("edge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_kg_blueprint_documents_project",
        "kg_blueprint_documents",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_kg_blueprint_documents_project", table_name="kg_blueprint_documents")
    op.drop_table("kg_blueprint_documents")
    op.drop_index("uq_kg_blueprint_edge", table_name="kg_blueprint_edges")
    op.drop_index("ix_kg_blueprint_edges_project", table_name="kg_blueprint_edges")
    op.drop_table("kg_blueprint_edges")
    op.drop_index("uq_kg_blueprint_node_label", table_name="kg_blueprint_nodes")
    op.drop_index("ix_kg_blueprint_nodes_project", table_name="kg_blueprint_nodes")
    op.drop_table("kg_blueprint_nodes")
