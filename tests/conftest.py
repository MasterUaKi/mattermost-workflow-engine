# Author: Oleh Riabtsev
# File: tests/conftest.py
# Created: 2026-11-23
# Version: 1.0.0

"""
Pytest fixtures providing:
- An isolated in-memory async SQLite database per test function.
- A stateful Mattermost REST API v4 mock server via httpx.MockTransport.
- Deterministic workflow definitions covering sequential, multi-approver sequential, and parallel stages.
- An async HTTP client bound directly to the FastAPI ASGI application.
"""

from collections.abc import AsyncGenerator
import json
from pathlib import Path
from typing import Any
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import (
    RejectBehavior,
    StepType,
    WorkflowDefinition,
    WorkflowsConfig,
    WorkflowStepConfig,
    get_settings,
)
from app.database import Base, get_db
from app.i18n import Translator
from app.main import app
from app.mattermost_client import MattermostClient
from app.workflow_engine import WorkflowEngine


class FakeMattermostServer:
    """
    In-memory stateful simulator of Mattermost REST API v4 endpoints.
    Records all outgoing calls made by MattermostClient for strict test assertions.
    """

    def __init__(self) -> None:
        self.bot_user_id = "bot_user_001"
        self.posts: dict[str, dict[str, Any]] = {}
        self.updated_posts: list[dict[str, Any]] = []
        self.opened_dialogs: list[dict[str, Any]] = []
        self.uploaded_files: list[dict[str, Any]] = []
        self.direct_channels: dict[str, str] = {}
        self._post_counter = 0
        self._file_counter = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Intercepts and processes Mattermost API v4 HTTP requests."""
        assert request.headers.get("Authorization") == "Bearer test_bot_token"
        path = request.url.path
        method = request.method

        # GET /api/v4/users/me
        if method == "GET" and path == "/api/v4/users/me":
            return httpx.Response(200, json={"id": self.bot_user_id, "username": "approval-bot"})

        # GET /api/v4/users/{user_id}
        if method == "GET" and path.startswith("/api/v4/users/"):
            user_id = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"id": user_id, "username": f"username_{user_id}"})

        # POST /api/v4/channels/direct
        if method == "POST" and path == "/api/v4/channels/direct":
            members = json.loads(request.content.decode("utf-8"))
            target_user_id = next((m for m in members if m != self.bot_user_id), members[0])
            channel_id = f"dm_{target_user_id}"
            self.direct_channels[target_user_id] = channel_id
            return httpx.Response(200, json={"id": channel_id})

        # POST /api/v4/files
        if method == "POST" and path == "/api/v4/files":
            self._file_counter += 1
            file_id = f"mm_file_{self._file_counter}"
            channel_id = request.url.params.get("channel_id", "")
            self.uploaded_files.append(
                {
                    "file_id": file_id,
                    "channel_id": channel_id,
                    "body_size": len(request.content),
                }
            )
            return httpx.Response(201, json={"file_infos": [{"id": file_id}]})

        # POST /api/v4/posts
        if method == "POST" and path == "/api/v4/posts":
            self._post_counter += 1
            post_id = f"post_{self._post_counter}"
            payload = json.loads(request.content.decode("utf-8"))
            stored_post = {"id": post_id, **payload}
            self.posts[post_id] = stored_post
            return httpx.Response(201, json=stored_post)

        # PUT /api/v4/posts/{post_id}
        if method == "PUT" and path.startswith("/api/v4/posts/"):
            post_id = path.rsplit("/", 1)[-1]
            payload = json.loads(request.content.decode("utf-8"))
            self.posts[post_id] = payload
            self.updated_posts.append(payload)
            return httpx.Response(200, json=payload)

        # POST /api/v4/actions/dialogs/open
        if method == "POST" and path == "/api/v4/actions/dialogs/open":
            payload = json.loads(request.content.decode("utf-8"))
            self.opened_dialogs.append(payload)
            return httpx.Response(200, json={"status": "OK"})

        return httpx.Response(404, json={"message": f"Unhandled mock route: {method} {path}"})


@pytest.fixture
def fake_mm_server() -> FakeMattermostServer:
    """Provides a fresh stateful Mattermost API simulator for each test."""
    return FakeMattermostServer()


@pytest.fixture
def test_workflows_config() -> WorkflowsConfig:
    """Provides deterministic workflow routing definitions for testing."""
    return WorkflowsConfig(
        default_lang="en",
        workflows={
            "single_step_seq": WorkflowDefinition(
                name={"en": "Single Step Expense", "de": "Einfache Spesen"},
                default_lang="en",
                steps=[
                    WorkflowStepConfig(
                        id="manager_review",
                        name={"en": "Manager Review", "de": "Manager-Prüfung"},
                        type=StepType.SEQUENTIAL,
                        approvers=["user_mgr_1"],
                        on_reject=RejectBehavior.RETURN_TO_INITIATOR,
                    )
                ],
            ),
            "multi_approver_seq": WorkflowDefinition(
                name={"en": "Ordered Two-Person Sequential", "de": "Sequenzielle Zweierprüfung"},
                default_lang="en",
                steps=[
                    WorkflowStepConfig(
                        id="ordered_chain",
                        name={"en": "Ordered Chain", "de": "Geordnete Kette"},
                        type=StepType.SEQUENTIAL,
                        approvers=["user_seq_1", "user_seq_2"],
                        on_reject=RejectBehavior.RETURN_TO_INITIATOR,
                    )
                ],
            ),
            "multistep_mixed": WorkflowDefinition(
                name={"en": "Multi-Step Contract", "de": "Mehrstufiger Vertrag"},
                default_lang="de",
                steps=[
                    WorkflowStepConfig(
                        id="dept_head",
                        name={"en": "Department Head", "de": "Abteilungsleiter"},
                        type=StepType.SEQUENTIAL,
                        approvers=["user_dept"],
                        on_reject=RejectBehavior.RETURN_TO_INITIATOR,
                    ),
                    WorkflowStepConfig(
                        id="legal_and_finance",
                        name={"en": "Legal & Finance", "de": "Recht & Finanzen"},
                        type=StepType.PARALLEL,
                        approvers=["user_legal", "user_finance"],
                        on_reject=RejectBehavior.RETURN_TO_INITIATOR,
                    ),
                    WorkflowStepConfig(
                        id="ceo_signoff",
                        name={"en": "CEO Sign-Off", "de": "Geschäftsführung"},
                        type=StepType.SEQUENTIAL,
                        approvers=["user_ceo"],
                        on_reject=RejectBehavior.RETURN_TO_INITIATOR,
                    ),
                ],
            ),
        },
    )


@pytest.fixture
async def db_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Creates an isolated in-memory SQLite database schema for each test case."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.fixture
async def api_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_mm_server: FakeMattermostServer,
    test_workflows_config: WorkflowsConfig,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Configures FastAPI dependencies, temporary upload storage, and Mattermost MockTransport,
    returning an async HTTP client for integration tests.
    """
    settings = get_settings()
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(settings, "MATTERMOST_URL", "http://mattermost.test")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "http://engine.test")
    monkeypatch.setattr(settings, "MATTERMOST_BOT_TOKEN", "test_bot_token")
    monkeypatch.setattr(settings, "MATTERMOST_WEBHOOK_SECRET", "test_secret_token")

    translator = Translator(locales_path="locales.yaml", default_lang="en", console_lang="en")
    mm_client = MattermostClient(settings=settings, translator=translator)
    await mm_client.close()

    # Replace underlying httpx client with MockTransport connected to FakeMattermostServer
    mm_client._client = httpx.AsyncClient(
        base_url="http://mattermost.test/api/v4",
        headers={
            "Authorization": "Bearer test_bot_token",
            "Accept": "application/json",
        },
        transport=httpx.MockTransport(fake_mm_server.handler),
    )

    workflow_engine = WorkflowEngine(
        workflows_config=test_workflows_config,
        mm_client=mm_client,
        translator=translator,
    )

    app.state.translator = translator
    app.state.mm_client = mm_client
    app.state.workflow_engine = workflow_engine

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
    await mm_client.close()
