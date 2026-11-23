# Author: Oleh Riabtsev
# File: app/studio_routes.py
# Created: 2026-11-23
# Version: 1.0.0

"""
REST API and HTML entrypoint for the Visual Document Approval Studio:
- GET /studio — serves the interactive visual workflow builder and document launcher
- GET /api/v1/studio/session — validates the signed Mattermost DM session token
- GET /api/v1/mattermost/users — searches Mattermost users for the visual stage builder
- GET /api/v1/templates — lists workflow templates with creator ownership flags
- POST /api/v1/templates — creates a new template owned by the authenticated initiator
- PUT /api/v1/templates/{template_id} — updates a template (strictly restricted to owner_id)
- DELETE /api/v1/templates/{template_id} — deletes a template (strictly restricted to owner_id)
"""

from pathlib import Path
import re
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_tokens import verify_studio_session_token
from app.config import CustomFieldDefinition, WorkflowStepConfig, get_settings
from app.database import get_db
from app.i18n import Translator
from app.mattermost_client import MattermostClient
from app.models import WorkflowTemplate

router = APIRouter(tags=["Visual Workflow Studio"])

STATIC_STUDIO_HTML = Path(__file__).resolve().parent / "static" / "studio.html"


class TemplateUpsertRequest(BaseModel):
    """Payload for creating or updating a visual workflow template."""
    name: dict[str, str] = Field(..., min_length=1)
    description: dict[str, str] = Field(default_factory=dict)
    default_lang: str = Field(default="en")
    steps: list[WorkflowStepConfig] = Field(..., min_length=1)
    default_fields: list[CustomFieldDefinition] = Field(default_factory=list)


class TemplateResponse(BaseModel):
    """Serialized workflow template with creator ownership metadata."""
    id: str
    slug: str
    name: dict[str, str]
    description: dict[str, str]
    owner_id: str
    owner_username: str
    can_edit: bool
    default_lang: str
    steps: list[dict]
    default_fields: list[dict]


def get_current_studio_user(
    request: Request,
    token: str | None = Query(default=None),
    x_studio_token: str | None = Header(default=None),
) -> dict[str, str]:
    """Resolves and verifies the Mattermost user from the signed Studio session token."""
    raw_token = x_studio_token or token or ""
    settings = get_settings()
    user_info = verify_studio_session_token(settings, raw_token)
    if not user_info:
        translator: Translator = request.app.state.translator
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=translator.t("api.err_unauthorized_studio"),
        )
    return user_info


def _slugify(text: str) -> str:
    """Builds a clean URL-safe slug for a workflow template."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    suffix = uuid.uuid4().hex[:6]
    return f"{cleaned[:40]}_{suffix}" if cleaned else f"workflow_{suffix}"


def _serialize_template(tpl: WorkflowTemplate, viewer_user_id: str) -> TemplateResponse:
    """Converts a WorkflowTemplate ORM record into an API response with ownership check."""
    return TemplateResponse(
        id=tpl.id,
        slug=tpl.slug,
        name=tpl.name,
        description=tpl.description or {},
        owner_id=tpl.owner_id,
        owner_username=tpl.owner_username,
        can_edit=(tpl.owner_id == viewer_user_id),
        default_lang=tpl.default_lang,
        steps=tpl.steps,
        default_fields=tpl.default_fields or [],
    )


@router.get("/studio", include_in_schema=False)
async def serve_studio_ui() -> FileResponse:
    """Serves the visual workflow builder & document submission single-page interface."""
    return FileResponse(STATIC_STUDIO_HTML, media_type="text/html")


@router.get("/api/v1/studio/session")
async def get_studio_session(
    current_user: dict[str, str] = Depends(get_current_studio_user),
) -> dict[str, str]:
    """Returns the authenticated Mattermost initiator profile bound to the Studio session token."""
    return current_user


@router.get("/api/v1/mattermost/users")
async def search_mattermost_users(
    request: Request,
    q: str = Query(default="", max_length=100),
    _: dict[str, str] = Depends(get_current_studio_user),
) -> list[dict]:
    """Searches active Mattermost users for approver selection in the visual pipeline builder."""
    mm_client: MattermostClient = request.app.state.mm_client
    return await mm_client.search_users(term=q, limit=30)


@router.get("/api/v1/templates", response_model=list[TemplateResponse])
async def list_workflow_templates(
    current_user: dict[str, str] = Depends(get_current_studio_user),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateResponse]:
    """Lists all available workflow templates, indicating which ones the current user owns."""
    stmt = select(WorkflowTemplate).order_by(WorkflowTemplate.created_at.asc())
    result = await db.execute(stmt)
    templates = list(result.scalars().all())
    return [_serialize_template(tpl, current_user["user_id"]) for tpl in templates]


@router.post(
    "/api/v1/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_template(
    payload: TemplateUpsertRequest,
    current_user: dict[str, str] = Depends(get_current_studio_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Creates a new workflow template owned exclusively by the current user."""
    primary_name = payload.name.get("en") or payload.name.get("de") or next(iter(payload.name.values()))
    tpl = WorkflowTemplate(
        slug=_slugify(primary_name),
        name=payload.name,
        description=payload.description,
        owner_id=current_user["user_id"],
        owner_username=current_user["username"],
        default_lang=payload.default_lang if payload.default_lang in {"en", "de"} else "en",
        steps=[s.model_dump(mode="json") for s in payload.steps],
        default_fields=[f.model_dump(mode="json") for f in payload.default_fields],
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return _serialize_template(tpl, current_user["user_id"])


@router.put("/api/v1/templates/{template_id}", response_model=TemplateResponse)
async def update_workflow_template(
    template_id: str,
    payload: TemplateUpsertRequest,
    request: Request,
    current_user: dict[str, str] = Depends(get_current_studio_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Updates an existing template. Enforces that only the template creator can edit stages."""
    translator: Translator = request.app.state.translator
    stmt = select(WorkflowTemplate).where(WorkflowTemplate.id == template_id)
    tpl = (await db.execute(stmt)).scalar_one_or_none()
    if not tpl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translator.t("api.err_template_not_found", template_id=template_id),
        )

    if tpl.owner_id != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=translator.t("api.err_template_forbidden"),
        )

    tpl.name = payload.name
    tpl.description = payload.description
    tpl.default_lang = payload.default_lang if payload.default_lang in {"en", "de"} else tpl.default_lang
    tpl.steps = [s.model_dump(mode="json") for s in payload.steps]
    tpl.default_fields = [f.model_dump(mode="json") for f in payload.default_fields]

    await db.commit()
    await db.refresh(tpl)
    return _serialize_template(tpl, current_user["user_id"])


@router.delete("/api/v1/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_template(
    template_id: str,
    request: Request,
    current_user: dict[str, str] = Depends(get_current_studio_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes a template. Enforces that only the template creator can delete it."""
    translator: Translator = request.app.state.translator
    stmt = select(WorkflowTemplate).where(WorkflowTemplate.id == template_id)
    tpl = (await db.execute(stmt)).scalar_one_or_none()
    if not tpl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translator.t("api.err_template_not_found", template_id=template_id),
        )

    if tpl.owner_id != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=translator.t("api.err_template_forbidden"),
        )

    await db.delete(tpl)
    await db.commit()
