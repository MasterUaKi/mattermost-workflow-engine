# Author: Oleh Riabtsev
# File: alembic/versions/20261123_0001_initial_schema.py
# Created: 2026-11-23
# Version: 1.0.0

"""Initial database schema for Mattermost Document Approval Workflow Engine

Revision ID: 20261123_0001
Revises:
Create Date: 2026-11-23 10:15:00.000000
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision: str = "20261123_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create core workflow tables, indexes, and enum types."""
    op.create_table(
        "workflow_instances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("document_data", sa.JSON(), nullable=False),
        sa.Column("initiator_id", sa.String(length=64), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "IN_PROGRESS", "APPROVED", "REJECTED", name="workflowstatus"),
            nullable=False,
        ),
        sa.Column("current_step_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_instances_initiator_id"),
        "workflow_instances",
        ["initiator_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_instances_workflow_type"),
        "workflow_instances",
        ["workflow_type"],
        unique=False,
    )

    op.create_table(
        "approval_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.String(length=100), nullable=False),
        sa.Column("approver_id", sa.String(length=64), nullable=False),
        sa.Column("dm_channel_id", sa.String(length=64), nullable=True),
        sa.Column("post_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", "CANCELLED", name="taskstatus"),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_approval_tasks_approver_id"),
        "approval_tasks",
        ["approver_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_tasks_post_id"),
        "approval_tasks",
        ["post_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_tasks_workflow_id"),
        "approval_tasks",
        ["workflow_id"],
        unique=False,
    )

    op.create_table(
        "document_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_attachments_workflow_id"),
        "document_attachments",
        ["workflow_id"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_username", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_audit_logs_workflow_id"),
        "audit_logs",
        ["workflow_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop core workflow tables, indexes, and PostgreSQL enum types."""
    op.drop_index(op.f("ix_audit_logs_workflow_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_document_attachments_workflow_id"), table_name="document_attachments")
    op.drop_table("document_attachments")

    op.drop_index(op.f("ix_approval_tasks_workflow_id"), table_name="approval_tasks")
    op.drop_index(op.f("ix_approval_tasks_post_id"), table_name="approval_tasks")
    op.drop_index(op.f("ix_approval_tasks_approver_id"), table_name="approval_tasks")
    op.drop_table("approval_tasks")

    op.drop_index(op.f("ix_workflow_instances_workflow_type"), table_name="workflow_instances")
    op.drop_index(op.f("ix_workflow_instances_initiator_id"), table_name="workflow_instances")
    op.drop_table("workflow_instances")

    # Clean up native PostgreSQL enum types
    op.execute("DROP TYPE IF EXISTS taskstatus")
    op.execute("DROP TYPE IF EXISTS workflowstatus")
