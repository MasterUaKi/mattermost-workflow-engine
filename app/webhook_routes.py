# Author: Oleh Riabtsev
# File: app/webhook_routes.py
# Created: 2026-11-23
# Version: 1.1.0

"""
Mattermost callback handlers:
- POST /api/v1/mattermost/actions — handles interactive button clicks (Approve / Reject)
- POST /api/v1/mattermost/dialogs/reject — handles Interactive Dialog submissions with rejection reasons
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.i18n import Translator
from app.schemas import MattermostButtonPayload, MattermostDialogSubmissionPayload
from app.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/api/v1/mattermost", tags=["Mattermost Callbacks"])


def verify_webhook_secret(
    request: Request,
    token: str | None = Query(default=None),
) -> None:
    """Validates the secret query token on Mattermost callback URLs when configured."""
    settings = get_settings()
    if settings.MATTERMOST_WEBHOOK_SECRET and token != settings.MATTERMOST_WEBHOOK_SECRET:
        translator: Translator = request.app.state.translator
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translator.t("api.err_unauthorized_webhook"),
        )


@router.post("/actions")
async def mattermost_interactive_action(
    payload: MattermostButtonPayload,
    request: Request,
    _: None = Depends(verify_webhook_secret),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receives button click events from Mattermost approval cards."""
    engine: WorkflowEngine = request.app.state.workflow_engine
    action = payload.context.get("action")
    task_id = payload.context.get("task_id")

    if not task_id or action not in {"approve", "reject"}:
        return {}

    if action == "approve":
        ephemeral_msg = await engine.handle_approve_button(
            db,
            task_id=task_id,
            actor_user_id=payload.user_id,
            actor_username=payload.user_name,
        )
        if ephemeral_msg:
            return {"ephemeral_text": ephemeral_msg}
        return {}

    # Open an Interactive Dialog modal when the Reject button is clicked
    ephemeral_msg = await engine.open_reject_modal(
        db,
        task_id=task_id,
        actor_user_id=payload.user_id,
        trigger_id=payload.trigger_id,
    )
    if ephemeral_msg:
        return {"ephemeral_text": ephemeral_msg}
    return {}


@router.post("/dialogs/reject")
async def mattermost_reject_dialog_submission(
    payload: MattermostDialogSubmissionPayload,
    request: Request,
    _: None = Depends(verify_webhook_secret),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Processes submission of the rejection reason modal dialog."""
    if payload.cancelled:
        return {}

    engine: WorkflowEngine = request.app.state.workflow_engine
    translator: Translator = request.app.state.translator

    state_data: dict = {}
    if payload.state:
        try:
            state_data = json.loads(payload.state)
        except json.JSONDecodeError:
            return {}

    task_id = state_data.get("task_id")
    if not task_id:
        return {}

    # Resolve workflow language to localize field validation errors
    task = await engine._load_task_with_workflow(db, task_id)
    lang = task.workflow.lang if task else None

    rejection_reason = str(payload.submission.get("rejection_reason", "")).strip()
    if not rejection_reason:
        # Native Mattermost Interactive Dialog field error response format
        return {
            "errors": {
                "rejection_reason": translator.t("dialog.error_empty_reason", lang=lang)
            }
        }

    # Fetch Mattermost username by user_id (dialog_submission payload only provides user_id)
    actor_username = await engine.mm_client.get_username(payload.user_id)

    await engine.handle_reject_dialog_submission(
        db,
        task_id=task_id,
        actor_user_id=payload.user_id,
        actor_username=actor_username,
        rejection_reason=rejection_reason,
    )
    return {}
