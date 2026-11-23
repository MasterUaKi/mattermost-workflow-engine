# Автор: Oleh Riabtsev
# Файл: app/schemas.py
# Дата создания: 2026-11-23
# Версия: 1.0.0

"""
Pydantic v2 схемы для валидации запросов и ответов REST API системы,
а также входящих событий от Interactive Message Buttons и Interactive Dialogs Mattermost.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# --- Схемы REST API самой системы ---

class WorkflowStartResponse(BaseModel):
    """Ответ эндпоинта POST /api/v1/workflows/start."""
    workflow_id: str
    workflow_type: str
    status: str
    current_step_index: int
    lang: str
    message: str


class TaskDetailSchema(BaseModel):
    """Детальная информация о задаче согласующего."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    step_index: int
    step_id: str
    approver_id: str
    dm_channel_id: str | None
    post_id: str | None
    status: str
    comment: str | None
    created_at: datetime
    decided_at: datetime | None


class AttachmentDetailSchema(BaseModel):
    """Информация о прикрепленном файле."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    file_size: int
    created_at: datetime


class AuditLogDetailSchema(BaseModel):
    """Запись журнала аудита."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str | None
    actor_id: str
    actor_username: str | None
    action: str
    details: str | None
    created_at: datetime


class WorkflowDetailResponse(BaseModel):
    """Полная карточка процесса и история действий для GET /api/v1/workflows/{id}."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_type: str
    title: str
    description: str | None
    document_data: dict[str, Any]
    initiator_id: str
    lang: str
    status: str
    current_step_index: int
    created_at: datetime
    updated_at: datetime
    tasks: list[TaskDetailSchema]
    attachments: list[AttachmentDetailSchema]
    audit_logs: list[AuditLogDetailSchema]


# --- Схемы входящих вебхуков Mattermost ---

class MattermostButtonPayload(BaseModel):
    """Полезная нагрузка при нажатии интерактивной кнопки в сообщении Mattermost."""
    user_id: str
    user_name: str
    channel_id: str
    post_id: str
    trigger_id: str
    type: str | None = "button"
    context: dict[str, Any] = Field(default_factory=dict)


class MattermostDialogSubmissionPayload(BaseModel):
    """Полезная нагрузка при отправке модального окна (Interactive Dialog) Mattermost."""
    type: str = "dialog_submission"
    callback_id: str | None = None
    state: str | None = None
    user_id: str
    channel_id: str
    submission: dict[str, Any] = Field(default_factory=dict)
    cancelled: bool = False
