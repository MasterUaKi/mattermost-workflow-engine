# Author: Oleh Riabtsev
# File: app/models.py
# Created: 2026-11-23
# Version: 1.1.0

"""
SQLAlchemy 2.0 ORM models for persisting workflow instances, individual approver tasks,
document attachments, and immutable audit logs.
"""

from datetime import datetime, timezone
from enum import Enum
import uuid
from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    """Returns the current UTC timestamp."""
    return datetime.now(timezone.utc)


class WorkflowStatus(str, Enum):
    """Lifecycle status of a workflow instance."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TaskStatus(str, Enum):
    """Status of an individual approval task assigned to an approver."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class WorkflowInstance(Base):
    """Represents a running or completed document approval workflow instance."""
    __tablename__ = "workflow_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    initiator_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    status: Mapped[WorkflowStatus] = mapped_column(
        SQLEnum(WorkflowStatus), nullable=False, default=WorkflowStatus.IN_PROGRESS
    )
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    # Relationships to child tables
    tasks: Mapped[list["ApprovalTask"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="ApprovalTask.step_index, ApprovalTask.created_at",
    )
    attachments: Mapped[list["DocumentAttachment"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan", order_by="AuditLog.id"
    )


class ApprovalTask(Base):
    """Represents an approval task assigned to a specific user at a workflow step."""
    __tablename__ = "approval_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str] = mapped_column(String(100), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Mattermost DM channel and post IDs used for updating interactive cards
    dm_channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    post_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus), nullable=False, default=TaskStatus.PENDING
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped["WorkflowInstance"] = relationship(back_populates="tasks")


class DocumentAttachment(Base):
    """Metadata for document files uploaded and stored on disk."""
    __tablename__ = "document_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    workflow: Mapped["WorkflowInstance"] = relationship(back_populates="attachments")


class AuditLog(Base):
    """Immutable audit log recording all actions across a workflow lifecycle."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    workflow: Mapped["WorkflowInstance"] = relationship(back_populates="audit_logs")
