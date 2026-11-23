# Author: Oleh Riabtsev
# File: app/schemas.py
# Created: 2026-11-23
# Version: 1.1.0

"""
Pydantic v2 schemas for validating REST API requests and responses,
as well as incoming Mattermost Interactive Message Button and Dialog payloads.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# --- System REST API Schemas ---

class WorkflowStartResponse(BaseModel):
    """Response schema for POST /api/v1/workflows/start."""
    workflow_id: str
    workflow_type: str
    status: str
    current_step_index: int
    lang: str
    message: str


class TaskDetailSchema(BaseModel):
    """Detailed representation of an approval task."""
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
    """Metadata representation of an attached file."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    file_size: int
    created_at: datetime


class AuditLogDetailSchema(BaseModel):
    """Single entry in the workflow audit history."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str | None
    actor_id: str
    actor_username: str | None
    action: str
    details: str | None
    created_at: datetime


class WorkflowDetailResponse(BaseModel):
    """Complete workflow status and audit trail for GET /api/v1/workflows/{workflow_id}."""
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


# --- Mattermost Incoming Callback Schemas ---

class MattermostButtonPayload(BaseModel):
    """Payload sent by Mattermost when an interactive message button is clicked."""
    user_id: str
    user_name: str
    channel_id: str
    post_id: str
    trigger_id: str
    type: str | None = "button"
    context: dict[str, Any] = Field(default_factory=dict)


class MattermostDialogSubmissionPayload(BaseModel):
    """Payload sent by Mattermost when an Interactive Dialog is submitted."""
    type: str = "dialog_submission"
    callback_id: str | None = None
    state: str | None = None
    user_id: str
    channel_id: str
    submission: dict[str, Any] = Field(default_factory=dict)
    cancelled: bool = False
