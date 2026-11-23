# Автор: Oleh Riabtsev
# Файл: app/main.py
# Дата создания: 2026-11-23
# Версия: 1.0.0

"""
Точка входа FastAPI-приложения.
Инициализирует БД, клиент Mattermost, систему локализации, движок согласования
и глобальные обработчики исключений.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api_routes import router as workflows_router
from app.config import get_settings, get_workflows_config
from app.database import init_db
from app.i18n import Translator
from app.mattermost_client import MattermostAPIError, MattermostClient
from app.webhook_routes import router as mattermost_router
from app.workflow_engine import WorkflowEngine

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("workflow_engine.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управляет запуском и корректным завершением ресурсов приложения."""
    translator = Translator(
        locales_path=settings.LOCALES_PATH,
        default_lang=settings.DEFAULT_LANG,
    )
    workflows_config = get_workflows_config()
    mm_client = MattermostClient(settings=settings, translator=translator)
    workflow_engine = WorkflowEngine(
        workflows_config=workflows_config,
        mm_client=mm_client,
        translator=translator,
    )

    app.state.translator = translator
    app.state.mm_client = mm_client
    app.state.workflow_engine = workflow_engine

    await init_db()

    try:
        bot_id = await mm_client.get_bot_user_id()
        logger.info(translator.t("logs.app_startup", bot_id=bot_id))
    except Exception as exc:
        logger.warning(f"Mattermost connection check skipped or failed at startup: {exc}")

    yield

    await mm_client.close()
    logger.info(translator.t("logs.app_shutdown"))


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(MattermostAPIError)
async def mattermost_error_handler(request: Request, exc: MattermostAPIError) -> JSONResponse:
    """Глобальный перехватчик ошибок взаимодействия с Mattermost REST API v4."""
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
    """Глобальный перехватчик непредвиденных исключений."""
    logger.exception("Unhandled server exception", exc_info=exc)
    translator: Translator = request.app.state.translator
    lang = request.query_params.get("lang") or settings.DEFAULT_LANG
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": translator.t("api.err_internal", lang=lang)},
    )


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Эндпоинт проверки работоспособности сервиса."""
    return {"status": "ok"}


app.include_router(workflows_router)
app.include_router(mattermost_router)
