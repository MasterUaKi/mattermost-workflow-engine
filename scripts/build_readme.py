# Author: Oleh Riabtsev
# File: scripts/build_readme.py
# Created: 2026-11-24
# Version: 1.2.0

"""
Generates the complete README.md file in UTF-8 (without BOM) using pure-ASCII
escape literals so pasting into Windows PowerShell never truncates Unicode symbols.
"""

from pathlib import Path


def _section_header_and_overview() -> str:
    """Section 1: Header, badges, and project overview."""
    return (
        "<!--\n"
        "Author: Oleh Riabtsev\n"
        "File: README.md\n"
        "Created: 2026-11-23\n"
        "Updated: 2026-11-24\n"
        "Version: 1.4.0\n"
        "-->\n\n"
        "# Mattermost Document Approval Workflow Engine\n\n"
        "[![CI - Tests, Migrations & Docker Build]"
        "(https://github.com/MasterUaKi/mattermost-workflow-engine/actions/workflows/ci.yml/badge.svg)]"
        "(https://github.com/MasterUaKi/mattermost-workflow-engine/actions/workflows/ci.yml)\n"
        "![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)\n"
        "![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)\n"
        "![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-D71F00)\n"
        "![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)\n\n"
        "An asynchronous, event-driven document approval workflow engine integrated with "
        "**Mattermost** (REST API v4 & WebSocket Bot Listener). Built with **FastAPI**, "
        "**SQLAlchemy 2.0**, **Alembic**, and **PostgreSQL**, featuring a zero-training "
        "**Visual Workflow Studio** (`/studio`) designed for non-technical end users.\n\n"
        "---"
    )


def _section_key_capabilities(arrow: str, ru_start: str, ru_phrase: str) -> str:
    """Section 2: Core platform capabilities."""
    return (
        "## Key Capabilities\n\n"
        f"* **One-Message Bot Initiation (`start` / `{ru_start}` / `neu`):** "
        f"Users send a Direct Message to the Mattermost bot (e.g., `start`, `{ru_start}`, "
        f"`{ru_phrase}`, `neu`) and immediately receive a signed `HMAC-SHA256` magic link "
        "opening the Visual Workflow Studio authenticated as that user.\n"
        "* **Visual Pipeline Builder (`/studio`):**\n"
        f"  * Left-to-right infographic pipeline (`Document {arrow} Stages 1..N {arrow} Approved`) "
        "with real-time plain-language route summaries and pre-flight validation.\n"
        "  * Live Mattermost user search - no manual 26-character user IDs required.\n"
        "  * Unlimited approval stages supporting both **Sequential** (one by one) and "
        "**Parallel** (all at once) execution modes.\n"
        "  * **Conditional Alternative Routing on Rejection:** Any stage can either return the "
        "document to the initiator (`return_to_initiator`) or reroute it to an alternative "
        "escalation stage (`goto_step`) with an automatic escalation banner carrying the "
        "rejection reason.\n"
        "  * **Template Creator Ownership (`owner_id`):** Only the creator of a visual workflow "
        "template can modify or delete its stages; colleagues can view the visual diagram and "
        "launch documents using the template.\n"
        "  * **Unlimited Typed Document Fields:** Attach custom metadata fields "
        "(`Text`, `Number`, `Date`, `Yes/No`, `URL`) alongside PDF, DOCX, or image files.\n"
        "* **Interactive Mattermost Cards & Modals:**\n"
        "  * Delivers interactive approval cards with file attachments directly to approvers' "
        "Direct Message channels.\n"
        "  * Clicking **Reject** opens a Mattermost Interactive Dialog requiring a mandatory "
        "rejection reason.\n"
        "  * Automatically cancels sibling parallel tasks and removes action buttons once a "
        "decision is finalized.\n"
        "  * Automatically cleans up temporary uploaded files from `uploads/` once a workflow "
        "reaches `APPROVED` or `REJECTED`, while preserving audit logs and attachment metadata "
        "in PostgreSQL.\n"
        "* **Multilingual Interface & Logs:** Mattermost cards, dialogs, and Studio UI support "
        "**English (`en`)** and **German (`de`)** (plus **Russian (`ru`)** in Studio UI and "
        "console logs via `CONSOLE_LANG`).\n\n"
        "---"
    )


def _section_project_structure(
    t_branch: str, l_branch: str, v_bar: str, ru_start: str
) -> str:
    """Section 3: Repository directory tree."""
    return (
        "## Project Structure\n\n"
        "```text\n"
        "mattermost-workflow-engine/\n"
        f"{t_branch} .github/\n"
        f"{v_bar}   {l_branch} workflows/\n"
        f"{v_bar}       {l_branch} ci.yml                       # GitHub Actions CI (Alembic + Pytest + Docker build)\n"
        f"{t_branch} alembic/\n"
        f"{v_bar}   {t_branch} env.py                           # Asynchronous SQLAlchemy 2.0 Alembic environment\n"
        f"{v_bar}   {t_branch} script.py.mako                   # Migration template with mandatory file headers\n"
        f"{v_bar}   {l_branch} versions/\n"
        f"{v_bar}       {t_branch} 20261123_0001_initial_schema.py\n"
        f"{v_bar}       {l_branch} 20261123_0002_workflow_templates.py\n"
        f"{t_branch} app/\n"
        f"{v_bar}   {t_branch} static/\n"
        f"{v_bar}   {v_bar}   {l_branch} studio.html                  # Single-page Visual Workflow Studio UI\n"
        f"{v_bar}   {t_branch} api_routes.py                    # REST endpoints for starting & inspecting workflows\n"
        f"{v_bar}   {t_branch} auth_tokens.py                   # Stateless HMAC-SHA256 magic link signer/verifier\n"
        f"{v_bar}   {t_branch} bot_listener.py                  # Mattermost WebSocket DM listener ('start' / '{ru_start}')\n"
        f"{v_bar}   {t_branch} config.py                        # Pydantic v2 settings & YAML routing schemas\n"
        f"{v_bar}   {t_branch} database.py                      # Async SQLAlchemy engine & session factory\n"
        f"{v_bar}   {t_branch} i18n.py                          # Localization engine for cards, dialogs, API, and logs\n"
        f"{v_bar}   {t_branch} main.py                          # FastAPI lifespan, template seeding, global handlers\n"
        f"{v_bar}   {t_branch} mattermost_client.py             # Async Mattermost REST API v4 client\n"
        f"{v_bar}   {t_branch} models.py                        # ORM models (templates, instances, tasks, audit logs)\n"
        f"{v_bar}   {t_branch} schemas.py                       # API request/response DTOs\n"
        f"{v_bar}   {t_branch} studio_routes.py                 # Visual Studio UI & template ownership CRUD API\n"
        f"{v_bar}   {t_branch} webhook_routes.py                # Mattermost interactive button & dialog callbacks\n"
        f"{v_bar}   {l_branch} workflow_engine.py               # Finite State Machine (FSM) & attachment cleanup\n"
        f"{t_branch} docker/\n"
        f"{v_bar}   {l_branch} postgres/\n"
        f"{v_bar}       {l_branch} init-databases.sql           # Creates workflow_db and mattermost_db on first boot\n"
        f"{t_branch} scripts/\n"
        f"{v_bar}   {t_branch} auto_sync_git.ps1                # Automated 5-minute Git commit & push worker\n"
        f"{v_bar}   {t_branch} bootstrap_local_mattermost.ps1   # Seeds admin, test users, and bot token in local Docker\n"
        f"{v_bar}   {t_branch} build_readme.py                  # Generates README.md in UTF-8 without BOM\n"
        f"{v_bar}   {t_branch} deploy.sh                        # Ubuntu Linux deployment & update script\n"
        f"{v_bar}   {t_branch} register_autosync_task.ps1       # Registers Windows Task Scheduler auto-sync\n"
        f"{v_bar}   {t_branch} run_e2e_test.ps1                 # Populates workflows.yaml IDs & triggers E2E workflow\n"
        f"{v_bar}   {l_branch} stop_session.ps1                 # Stops auto-sync, pushes final commit, stops Docker\n"
        f"{t_branch} tests/\n"
        f"{v_bar}   {t_branch} conftest.py                      # In-memory async SQLite & Mattermost MockTransport\n"
        f"{v_bar}   {l_branch} test_workflow_integration.py     # 9 end-to-end integration tests\n"
        f"{t_branch} alembic.ini                          # Alembic configuration\n"
        f"{t_branch} docker-compose.yml                   # PostgreSQL 16 + Mattermost Team Edition + Engine\n"
        f"{t_branch} Dockerfile                           # Non-root Python 3.11 container running Alembic + Uvicorn\n"
        f"{t_branch} locales.yaml                         # EN / DE / RU translation dictionaries\n"
        f"{t_branch} pytest.ini                           # Pytest async test configuration\n"
        f"{t_branch} requirements.txt                     # Python dependencies\n"
        f"{l_branch} workflows.yaml                       # Initial seed workflow templates\n"
        "```\n\n"
        "---"
    )


def _section_quick_start(ru_start: str) -> str:
    """Section 4: Local Docker lab setup and launching via Mattermost bot & Visual Studio."""
    return (
        "## Quick Start: Local Docker Lab (Windows PowerShell)\n\n"
        "The `docker-compose.yml` includes **PostgreSQL 16**, a bundled "
        "**Mattermost Team Edition** test server (`http://localhost:8065`), and the "
        "**Workflow Engine** (`http://localhost:8000`) so you can test everything locally "
        "without touching a production Mattermost instance.\n\n"
        "### 1. Start Containers & Bootstrap Local Mattermost\n\n"
        "```powershell\n"
        "# 1. Create environment configuration\n"
        "Copy-Item .env.example .env\n\n"
        "# 2. Build and start PostgreSQL, local Mattermost, and Workflow Engine\n"
        "docker compose up -d --build\n\n"
        "# 3. Automatically create admin, test users, and bot token (writes token to .env)\n"
        "powershell -ExecutionPolicy Bypass -File .\\scripts\\bootstrap_local_mattermost.ps1\n\n"
        "# 4. Recreate workflow-engine to load the generated MATTERMOST_BOT_TOKEN\n"
        "docker compose up -d --force-recreate workflow-engine\n"
        "```\n\n"
        "### 2. Launch via Mattermost Bot & Visual Studio\n\n"
        "1. Open `http://localhost:8065` in your browser and log in as "
        "**`initiator_user`** (password: `TestUser2026!`).\n"
        "2. Open a Direct Message with **`@approval-bot`** (`Document Approval Bot`) "
        f"and send **`start`** or **`{ru_start}`**.\n"
        "3. Click the **Open Approval Studio** link returned by the bot to open "
        "`http://localhost:8000/studio?token=...`.\n"
        "4. Build a visual pipeline (or pick an existing template), attach files, add custom "
        "fields, and click **Send for Approval**.\n"
        "5. Log in as the assigned approver (`dept_head_user`, `legal_user`, "
        "`finance_user`, `ceo_user` - password `TestUser2026!`) to test **Approve** and "
        "**Reject** actions.\n\n"
        "*(Optional)* Trigger an automated CLI end-to-end test via:\n"
        "```powershell\n"
        "powershell -ExecutionPolicy Bypass -File .\\scripts\\run_e2e_test.ps1 "
        "-WorkflowType contract_approval_multistep -DocLang de\n"
        "```\n\n"
        "---"
    )


def _section_migrations_and_testing(arrow: str) -> str:
    """Section 5: Alembic database migrations and Pytest integration testing."""
    return (
        "## Database Migrations (Alembic)\n\n"
        "The container entrypoint automatically runs `alembic upgrade head` before starting "
        "Uvicorn. For manual schema management:\n\n"
        "```powershell\n"
        "# Check current database revision\n"
        "docker compose exec workflow-engine alembic current\n\n"
        "# Apply all pending migrations\n"
        "docker compose exec workflow-engine alembic upgrade head\n\n"
        "# Auto-generate a new migration after editing app/models.py\n"
        'docker compose exec workflow-engine alembic revision --autogenerate -m "describe_schema_change"\n\n'
        "# Roll back the most recent migration by one step\n"
        "docker compose exec workflow-engine alembic downgrade -1\n"
        "```\n\n"
        "---\n\n"
        "## Integration Testing (Pytest)\n\n"
        "All FSM transitions, parallel synchronization barriers, rejection dialogs, "
        "alternative escalation routes, temporary file cleanups, template ownership rules, "
        "and Mattermost bot DM commands are verified by 9 asynchronous integration tests "
        "using `httpx.MockTransport` and an isolated in-memory SQLite database.\n\n"
        "```powershell\n"
        "# Run the full test suite inside the Docker container\n"
        "docker compose exec workflow-engine pytest\n"
        "```\n\n"
        "Every push and pull request to `main` automatically runs PostgreSQL 16 migration "
        f"verification (`upgrade` {arrow} `downgrade` {arrow} `upgrade`), `pytest`, and a "
        "Docker image build check via **GitHub Actions** (`.github/workflows/ci.yml`).\n\n"
        "---"
    )


def _section_deployment_and_scripts() -> str:
    """Section 6: Ubuntu production deployment and Windows session management scripts."""
    return (
        "## Production Deployment on Ubuntu Linux\n\n"
        "To deploy or update the service on an Ubuntu server connected to an institutional "
        "Mattermost instance:\n\n"
        "```bash\n"
        "sudo mkdir -p /opt/mattermost-workflow-engine\n"
        'sudo chown -R "$USER":"$USER" /opt/mattermost-workflow-engine\n'
        "git clone [https://github.com/MasterUaKi/mattermost-workflow-engine.git](https://github.com/MasterUaKi/mattermost-workflow-engine.git) /opt/mattermost-workflow-engine\n"
        "cd /opt/mattermost-workflow-engine\n"
        "chmod +x scripts/deploy.sh\n\n"
        "# First run generates .env from .env.example\n"
        "./scripts/deploy.sh\n\n"
        "# Configure production MATTERMOST_URL, MATTERMOST_BOT_TOKEN, PUBLIC_BASE_URL, and STUDIO_PUBLIC_URL\n"
        "nano .env\n\n"
        "# Build image, apply Alembic migrations, and start PostgreSQL + Workflow Engine\n"
        "./scripts/deploy.sh\n"
        "```\n\n"
        "Subsequent updates from GitHub require only running "
        "`/opt/mattermost-workflow-engine/scripts/deploy.sh`.\n\n"
        "---\n\n"
        "## Session Management Scripts (Windows PowerShell)\n\n"
        "```powershell\n"
        "# Resume background 5-minute Git auto-sync task\n"
        "powershell -ExecutionPolicy Bypass -File .\\scripts\\register_autosync_task.ps1\n\n"
        "# Pause development session: stop auto-sync task, push final commit, and stop Docker containers\n"
        "powershell -ExecutionPolicy Bypass -File .\\scripts\\stop_session.ps1 -StopDocker\n"
        "```\n\n"
        "---"
    )


def _section_api_reference() -> str:
    """Section 7: Complete REST API and Mattermost webhook endpoint reference."""
    return (
        "## API & Webhook Reference\n\n"
        "| Method | Endpoint | Description |\n"
        "| :--- | :--- | :--- |\n"
        '| `GET` | `/health` | Service health check (`{"status": "ok"}`) |\n'
        "| `GET` | `/studio` | Visual Workflow Studio web interface |\n"
        "| `GET` | `/api/v1/studio/session` | Validates signed Mattermost DM session token |\n"
        "| `GET` | `/api/v1/mattermost/users` | Searches active Mattermost users for the visual builder |\n"
        "| `GET` | `/api/v1/templates` | Lists workflow templates with `can_edit` ownership flags |\n"
        "| `POST` | `/api/v1/templates` | Creates a new workflow template owned by the current user |\n"
        "| `PUT` | `/api/v1/templates/{id}` | Updates a template (restricted to `owner_id`) |\n"
        "| `DELETE` | `/api/v1/templates/{id}` | Deletes a template (restricted to `owner_id`) |\n"
        "| `POST` | `/api/v1/workflows/start` | Starts a workflow (`multipart/form-data` with files & JSON metadata) |\n"
        "| `GET` | `/api/v1/workflows/{id}` | Retrieves workflow status, tasks, attachments, and audit trail |\n"
        "| `POST` | `/api/v1/mattermost/actions` | Webhook callback for Mattermost **Approve** / **Reject** buttons |\n"
        "| `POST` | `/api/v1/mattermost/dialogs/reject` | Callback for Mattermost mandatory rejection reason modal |\n"
    )


def build_readme_text() -> str:
    """Assembles all documentation sections into the complete README.md string."""
    arrow = "\u2794"
    t_branch = "\u251c\u2500\u2500"
    l_branch = "\u2514\u2500\u2500"
    v_bar = "\u2502"
    ru_start = "\u0441\u0442\u0430\u0440\u0442"
    ru_phrase = (
        "\u0445\u043e\u0447\u0443 \u043d\u0430\u0447\u0430\u0442\u044c "
        "\u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u0438\u0435"
    )

    parts = [
        _section_header_and_overview(),
        _section_key_capabilities(arrow=arrow, ru_start=ru_start, ru_phrase=ru_phrase),
        _section_project_structure(
            t_branch=t_branch,
            l_branch=l_branch,
            v_bar=v_bar,
            ru_start=ru_start,
        ),
        _section_quick_start(ru_start=ru_start),
        _section_migrations_and_testing(arrow=arrow),
        _section_deployment_and_scripts(),
        _section_api_reference(),
    ]
    return "\n\n".join(parts)


def main() -> None:
    """Writes README.md in UTF-8 without BOM and verifies all sections are present."""
    repo_root = Path(__file__).resolve().parent.parent
    target = repo_root / "README.md"
    content = build_readme_text()
    target.write_text(content, encoding="utf-8", newline="\n")

    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert "## Quick Start: Local Docker Lab (Windows PowerShell)" in text
    assert "## Database Migrations (Alembic)" in text
    assert "## Integration Testing (Pytest)" in text
    assert "## Production Deployment on Ubuntu Linux" in text
    assert "## Session Management Scripts (Windows PowerShell)" in text
    assert "## API & Webhook Reference" in text
    assert lines[-1].startswith("| `POST` | `/api/v1/mattermost/dialogs/reject`")
    print(f"README.md created successfully: {len(lines)} lines, {target.stat().st_size} bytes.")


if __name__ == "__main__":
    main()