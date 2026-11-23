# Author: Oleh Riabtsev
# File: app/main.py
# Created: 2026-11-23
# Version: 1.3.0

"""
FastAPI application entrypoint.
Initializes database, seeds default YAML templates, starts the Mattermost Bot WebSocket
listener for DM commands ('start' / 'старт'), and mounts all REST and Studio routes.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api_routes import router as workflows_router
from app.bot_listener import BotWebSocketListener
from app.config import WorkflowsConfig, get_settings, get_workflows_config
from app.database import AsyncSessionLocal, init_db
from app.i18n import Translator
from app.mattermost_client import MattermostAPIError, MattermostClient
from app.models import WorkflowTemplate
from app.studio_routes import router as studio_router
from app.webhook_routes import router as mattermost_router
from app.workflow_engine import WorkflowEngine

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("workflow_engine.main")


async def seed_default_templates(workflows_config: WorkflowsConfig) -> None:
    """Seeds initial templates from workflows.yaml into PostgreSQL if not already present."""
    try:
        async with AsyncSessionLocal() as session:
            for slug, wf_def in workflows_config.workflows.items():
                existing = (
                    await session.execute(
                        select(WorkflowTemplate).where(WorkflowTemplate.slug == slug)
                    )
                ).scalar_one_or_none()
                if not existing:
                    session.add(
                        WorkflowTemplate(
                            slug=slug,
                            name=wf_def.name,
                            description=wf_def.description or {},
                            owner_id="system",
                            owner_username="system",
                            default_lang=wf_def.default_lang or workflows_config.default_lang,
                            steps=[s.model_dump(mode="json") for s in wf_def.steps],
                            default_fields=[f.model_dump(mode="json") for f in wf_def.default_fields],
                        )
                    )
            await session.commit()
    except Exception as exc:
        logger.warning(f"Template seeding skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and graceful shutdown of external resources."""
    translator = Translator(
        locales_path=settings.LOCALES_PATH,
        default_lang=settings.DEFAULT_LANG,
        console_lang=settings.CONSOLE_LANG,
    )
    workflows_config = get_workflows_config()
    mm_client = MattermostClient(settings=settings, translator=translator)
    workflow_engine = WorkflowEngine(
        workflows_config=workflows_config,
        mm_client=mm_client,
        translator=translator,
    )
    bot_listener = BotWebSocketListener(
        settings=settings,
        mm_client=mm_client,
        translator=translator,
    )

    app.state.translator = translator
    app.state.mm_client = mm_client
    app.state.workflow_engine = workflow_engine

    if settings.AUTO_CREATE_TABLES:
        await init_db()

    await seed_default_templates(workflows_config)

    try:
        bot_id = await mm_client.get_bot_user_id()
        logger.info(translator.t_log("app_startup", bot_id=bot_id))
        bot_listener.start()
    except Exception as exc:
        logger.warning(translator.t_log("mm_startup_check_failed", detail=str(exc)))

    yield

    await bot_listener.stop()
    await mm_client.close()
    logger.info(translator.t_log("app_shutdown"))


app = FastAPI(
    title=settings.APP_NAME,
    version="1.3.0",
    lifespan=lifespan,
)


@app.exception_handler(MattermostAPIError)
async def mattermost_error_handler(request: Request, exc: MattermostAPIError) -> JSONResponse:
    """Global exception handler for Mattermost REST API v4 communication errors."""
    translator: Translator = request.app.state.translator
    lang = request.query_params.get("lang") or settings.DEFAULT_LANG
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": translator.t("api.err_mattermost_api", lang=lang, detail=exc.message),
            "mattermost_endpoint": exc.endpoint,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unexpected internal server errors."""
    translator: Translator = request.app.state.translator
    logger.exception(translator.t_log("unhandled_exception"), exc_info=exc)
    lang = request.query_params.get("lang") or settings.DEFAULT_LANG
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": translator.t("api.err_internal", lang=lang)},
    )


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Service health check endpoint."""
    return {"status": "ok"}


app.include_router(workflows_router)
app.include_router(mattermost_router)
app.include_router(studio_router)
