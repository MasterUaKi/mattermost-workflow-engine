# Автор: Oleh Riabtsev
# Файл: app/api_routes.py
# Дата создания: 2026-11-23
# Версия: 1.0.0

"""
Внешний REST API системы согласования документов:
- POST /api/v1/workflows/start — запуск нового процесса согласования (с поддержкой файлов)
- GET /api/v1/workflows/{workflow_id} — получение статуса и полной истории действий
"""

import json
from pathlib import Path
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.i18n import SUPPORTED_LANGUAGES, Translator
from app.schemas import WorkflowDetailResponse, WorkflowStartResponse
from app.workflow_engine import WorkflowEngine, WorkflowEngineError

router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows"])


def get_engine(request: Request) -> WorkflowEngine:
    """Извлекает экземпляр WorkflowEngine из состояния приложения FastAPI."""
    return request.app.state.workflow_engine


def get_translator(request: Request) -> Translator:
    """Извлекает экземпляр Translator из состояния приложения FastAPI."""
    return request.app.state.translator


@router.post(
    "/start",
    response_model=WorkflowStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_workflow_endpoint(
    workflow_type: str = Form(..., description="Идентификатор маршрута из workflows.yaml"),
    title: str = Form(..., description="Заголовок документа"),
    initiator_id: str = Form(..., description="Mattermost User ID инициатора"),
    description: str | None = Form(default=None, description="Описание документа"),
    lang: str | None = Form(default=None, description="Язык уведомлений: de или en"),
    document_data: str = Form(default="{}", description="JSON-строка с метаданными документа"),
    files: list[UploadFile] = File(default=[], description="Прикрепляемые файлы документа"),
    db: AsyncSession = Depends(get_db),
    engine: WorkflowEngine = Depends(get_engine),
    translator: Translator = Depends(get_translator),
) -> WorkflowStartResponse:
    """Запускает новый экземпляр процесса согласования документа."""
    if lang is not None and lang.lower() not in SUPPORTED_LANGUAGES:
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

    # Сохраняем загруженные файлы во временное хранилище для отправки в Mattermost
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
    """Возвращает текущий статус процесса согласования и полную историю действий."""
    try:
        instance = await engine.get_workflow_details(db, workflow_id)
    except WorkflowEngineError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=translator.t(exc.message_key, lang=lang, **exc.kwargs),
        )

    return WorkflowDetailResponse.model_validate(instance)
