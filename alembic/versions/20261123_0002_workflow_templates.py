# Author: Oleh Riabtsev
# File: alembic/versions/20261123_0002_workflow_templates.py
# Created: 2026-11-23
# Version: 1.0.0

"""Add workflow_templates table for visual workflow builder and creator ownership

Revision ID: 20261123_0002
Revises: 20261123_0001
Create Date: 2026-11-23 11:00:00.000000
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision: str = "20261123_0002"
down_revision: str | Sequence[str] | None = "20261123_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workflow_templates table and widen workflow_type column."""
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.JSON(), nullable=False),
        sa.Column("description", sa.JSON(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("owner_username", sa.String(length=128), nullable=False),
        sa.Column("default_lang", sa.String(length=5), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("default_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(
        op.f("ix_workflow_templates_owner_id"),
        "workflow_templates",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_templates_slug"),
        "workflow_templates",
        ["slug"],
        unique=True,
    )
    op.alter_column(
        "workflow_instances",
        "workflow_type",
        existing_type=sa.String(length=100),
        type_=sa.String(length=120),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Drop workflow_templates table."""
    op.alter_column(
        "workflow_instances",
        "workflow_type",
        existing_type=sa.String(length=120),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
    op.drop_index(op.f("ix_workflow_templates_slug"), table_name="workflow_templates")
    op.drop_index(op.f("ix_workflow_templates_owner_id"), table_name="workflow_templates")
    op.drop_table("workflow_templates")
