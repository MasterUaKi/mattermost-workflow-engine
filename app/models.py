# Автор: Oleh Riabtsev
# Файл: app/models.py
# Дата создания: 2026-11-23
# Версия: 1.0.0

"""
Модели базы данных SQLAlchemy 2.0 для хранения состояния процессов согласования,
индивидуальных задач проверяющих, вложений и журнала аудита.
"""

from datetime import datetime, timezone
from enum import Enum
import uuid
from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    """Возвращает текущее время в часовом поясе UTC."""
    return datetime.now(timezone.utc)


class WorkflowStatus(str, Enum):
    """Жизненный цикл экземпляра процесса согласования."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TaskStatus(str, Enum):
    """Статус отдельной задачи согласования, назначенной конкретному пользователю."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class WorkflowInstance(Base):
    """Экземпляр запущенного процесса согласования документа."""
    __tablename__ = "workflow_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    initiator_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="de")
    status: Mapped[WorkflowStatus] = mapped_column(
        SQLEnum(WorkflowStatus), nullable=False, default=WorkflowStatus.IN_PROGRESS
    )
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    # Связи с дочерними таблицами
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
    """Задача согласования для конкретного согласующего на определенном этапе."""
    __tablename__ = "approval_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str] = mapped_column(String(100), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Идентификаторы личного канала и поста в Mattermost для последующего обновления карточки
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
    """Метаданные прикрепленных файлов документа, сохраненных на диске."""
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
    """Неизменяемый журнал истории всех действий по процессу согласования."""
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
