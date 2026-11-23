# Author: Oleh Riabtsev
# File: app/api_routes.py
# Created: 2026-11-23
# Version: 1.1.0

"""
External REST API endpoints for the Document Approval Workflow Engine:
- POST /api/v1/workflows/start — starts a new workflow instance with optional attachments
- GET /api/v1/workflows/{workflow_id} — returns current workflow status and complete action history
"""

import json
from pathlib import Path
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.i18n import Translator, UI_SUPPORTED_LANGUAGES
from app.schemas import WorkflowDetailResponse, WorkflowStartResponse
from app.workflow_engine import WorkflowEngine, WorkflowEngineError

router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows"])


def get_engine(request: Request) -> WorkflowEngine:
    """Retrieves the WorkflowEngine instance from FastAPI application state."""
    return request.app.state.workflow_engine


def get_translator(request: Request) -> Translator:
    """Retrieves the Translator instance from FastAPI application state."""
    return request.app.state.translator


@router.post(
    "/start",
    response_model=WorkflowStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_workflow_endpoint(
    workflow_type: str = Form(..., description="Workflow route identifier from workflows.yaml"),
    title: str = Form(..., description="Document title"),
    initiator_id: str = Form(..., description="Mattermost User ID of the initiator"),
    description: str | None = Form(default=None, description="Optional document description"),
    lang: str | None = Form(default=None, description="Notification language: en or de (defaults to en)"),
    document_data: str = Form(default="{}", description="JSON object string containing document metadata"),
    files: list[UploadFile] = File(default=[], description="Document files to attach"),
    db: AsyncSession = Depends(get_db),
    engine: WorkflowEngine = Depends(get_engine),
    translator: Translator = Depends(get_translator),
) -> WorkflowStartResponse:
    """Starts a new document approval workflow instance."""
    if lang is not None and lang.lower() not in UI_SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translator.t("api.err_unsupported_lang", requested_lang=lang),
        )

    try:
        parsed_data = json.loads(document_data) if document_data else {}
        if not isinstance(parsed_data, dict):
            raise ValueError("document_data must be a JSON object")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translator.t("api.err_invalid_json_metadata", lang=lang),
        )

    # Persist uploaded files locally before dispatching to Mattermost
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_files: list[dict] = []
    for upload in files:
        if not upload.filename:
            continue
        content = await upload.read()
        unique_name = f"{uuid.uuid4()}_{Path(upload.filename).name}"
        file_path = upload_dir / unique_name
        file_path.write_bytes(content)

        saved_files.append(
            {
                "filename": upload.filename,
                "content_type": upload.content_type or "application/octet-stream",
                "storage_path": str(file_path),
                "file_size": len(content),
            }
        )

    try:
        instance = await engine.start_workflow(
            db,
            workflow_type=workflow_type,
            title=title,
            description=description,
            document_data=parsed_data,
            initiator_id=initiator_id,
            lang=lang,
            saved_files=saved_files,
        )
    except WorkflowEngineError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=translator.t(exc.message_key, lang=lang, **exc.kwargs),
        )

    return WorkflowStartResponse(
        workflow_id=instance.id,
        workflow_type=instance.workflow_type,
        status=instance.status.value,
        current_step_index=instance.current_step_index,
        lang=instance.lang,
        message=translator.t("api.workflow_started", lang=instance.lang),
    )


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow_status_endpoint(
    workflow_id: str,
    lang: str | None = None,
    db: AsyncSession = Depends(get_db),
    engine: WorkflowEngine = Depends(get_engine),
    translator: Translator = Depends(get_translator),
) -> WorkflowDetailResponse:
    """Returns the current approval workflow status and complete action history."""
    try:
        instance = await engine.get_workflow_details(db, workflow_id)
    except WorkflowEngineError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=translator.t(exc.message_key, lang=lang, **exc.kwargs),
        )

    return WorkflowDetailResponse.model_validate(instance)
