<!--
Author: Oleh Riabtsev
File: README.md
Created: 2026-11-23
Updated: 2026-11-24
Version: 1.4.0
-->

# Mattermost Document Approval Workflow Engine

[![CI - Tests, Migrations & Docker Build](https://github.com/MasterUaKi/mattermost-workflow-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/MasterUaKi/mattermost-workflow-engine/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)
![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0%20Async-D71F00)
![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)

An asynchronous, event-driven document approval workflow engine integrated with **Mattermost** (REST API v4 & WebSocket Bot Listener). Built with **FastAPI**, **SQLAlchemy 2.0**, **Alembic**, and **PostgreSQL**, featuring a zero-training **Visual Workflow Studio** (`/studio`) designed for non-technical end users.

---

## Key Capabilities

* **One-Message Bot Initiation (`start` / `старт` / `neu`):** Users send a Direct Message to the Mattermost bot (e.g., `start`, `старт`, `хочу начать согласование`, `neu`) and immediately receive a signed `HMAC-SHA256` magic link opening the Visual Workflow Studio authenticated as that user.
* **Visual Pipeline Builder (`/studio`):**
  * Left-to-right infographic pipeline (`Document ➔ Stages 1..N ➔ Approved`) with real-time plain-language route summaries and pre-flight validation.
  * Live Mattermost user search - no manual 26-character user IDs required.
  * Unlimited approval stages supporting both **Sequential** (one by one) and **Parallel** (all at once) execution modes.
  * **Conditional Alternative Routing on Rejection:** Any stage can either return the document to the initiator (`return_to_initiator`) or reroute it to an alternative escalation stage (`goto_step`) with an automatic escalation banner carrying the rejection reason.
  * **Template Creator Ownership (`owner_id`):** Only the creator of a visual workflow template can modify or delete its stages; colleagues can view the visual diagram and launch documents using the template.
  * **Unlimited Typed Document Fields:** Attach custom metadata fields (`Text`, `Number`, `Date`, `Yes/No`, `URL`) alongside PDF, DOCX, or image files.
* **Interactive Mattermost Cards & Modals:**
  * Delivers interactive approval cards with file attachments directly to approvers' Direct Message channels.
  * Clicking **Reject** opens a Mattermost Interactive Dialog requiring a mandatory rejection reason.
  * Automatically cancels sibling parallel tasks and removes action buttons once a decision is finalized.
  * Automatically cleans up temporary uploaded files from `uploads/` once a workflow reaches `APPROVED` or `REJECTED`, while preserving audit logs and attachment metadata in PostgreSQL.
* **Multilingual Interface & Logs:** Mattermost cards, dialogs, and Studio UI support **English (`en`)** and **German (`de`)** (plus **Russian (`ru`)** in Studio UI and console logs via `CONSOLE_LANG`).

---

## Project Structure

```text
mattermost-workflow-engine/
├── .github/
│   └── workflows/
│       └── ci.yml                       # GitHub Actions CI (Alembic + Pytest + Docker build)
├── alembic/
│   ├── env.py                           # Asynchronous SQLAlchemy 2.0 Alembic environment
│   ├── script.py.mako                   # Migration template with mandatory file headers
│   └── versions/
│       ├── 20261123_0001_initial_schema.py
│       └── 20261123_0002_workflow_templates.py
├── app/
│   ├── static/
│   │   └── studio.html                  # Single-page Visual Workflow Studio UI
│   ├── api_routes.py                    # REST endpoints for starting & inspecting workflows
│   ├── auth_tokens.py                   # Stateless HMAC-SHA256 magic link signer/verifier
│   ├── bot_listener.py                  # Mattermost WebSocket DM listener ('start' / 'старт')
│   ├── config.py                        # Pydantic v2 settings & YAML routing schemas
│   ├── database.py                      # Async SQLAlchemy engine & session factory
│   ├── i18n.py                          # Localization engine for cards, dialogs, API, and logs
│   ├── main.py                          # FastAPI lifespan, template seeding, global handlers
│   ├── mattermost_client.py             # Async Mattermost REST API v4 client
│   ├── models.py                        # ORM models (templates, instances, tasks, audit logs)
│   ├── schemas.py                       # API request/response DTOs
│   ├── studio_routes.py                 # Visual Studio UI & template ownership CRUD API
│   ├── webhook_routes.py                # Mattermost interactive button & dialog callbacks
│   └── workflow_engine.py               # Finite State Machine (FSM) & attachment cleanup
├── docker/
│   └── postgres/
│       └── init-databases.sql           # Creates workflow_db and mattermost_db on first boot
├── scripts/
│   ├── auto_sync_git.ps1                # Automated 5-minute Git commit & push worker
│   ├── bootstrap_local_mattermost.ps1   # Seeds admin, test users, and bot token in local Docker
│   ├── build_readme.py                  # Generates README.md in UTF-8 without BOM
│   ├── deploy.sh                        # Ubuntu Linux deployment & update script
│   ├── register_autosync_task.ps1       # Registers Windows Task Scheduler auto-sync
│   ├── run_e2e_test.ps1                 # Populates workflows.yaml IDs & triggers E2E workflow
│   └── stop_session.ps1                 # Stops auto-sync, pushes final commit, stops Docker
├── tests/
│   ├── conftest.py                      # In-memory async SQLite & Mattermost MockTransport
│   └── test_workflow_integration.py     # 9 end-to-end integration tests
├── alembic.ini                          # Alembic configuration
├── docker-compose.yml                   # PostgreSQL 16 + Mattermost Team Edition + Engine
├── Dockerfile                           # Non-root Python 3.11 container running Alembic + Uvicorn
├── locales.yaml                         # EN / DE / RU translation dictionaries
├── pytest.ini                           # Pytest async test configuration
├── requirements.txt                     # Python dependencies
└── workflows.yaml                       # Initial seed workflow templates
```

---

## Quick Start: Local Docker Lab (Windows PowerShell)

The `docker-compose.yml` includes **PostgreSQL 16**, a bundled **Mattermost Team Edition** test server (`http://localhost:8065`), and the **Workflow Engine** (`http://localhost:8000`) so you can test everything locally without touching a production Mattermost instance.

### 1. Start Containers & Bootstrap Local Mattermost

```powershell
# 1. Create environment configuration
Copy-Item .env.example .env

# 2. Build and start PostgreSQL, local Mattermost, and Workflow Engine
docker compose up -d --build

# 3. Automatically create admin, test users, and bot token (writes token to .env)
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_local_mattermost.ps1

# 4. Recreate workflow-engine to load the generated MATTERMOST_BOT_TOKEN
docker compose up -d --force-recreate workflow-engine
```

### 2. Launch via Mattermost Bot & Visual Studio

1. Open `http://localhost:8065` in your browser and log in as **`initiator_user`** (password: `TestUser2026!`).
2. Open a Direct Message with **`@approval-bot`** (`Document Approval Bot`) and send **`start`** or **`старт`**.
3. Click the **Open Approval Studio** link returned by the bot to open `http://localhost:8000/studio?token=...`.
4. Build a visual pipeline (or pick an existing template), attach files, add custom fields, and click **Send for Approval**.
5. Log in as the assigned approver (`dept_head_user`, `legal_user`, `finance_user`, `ceo_user` - password `TestUser2026!`) to test **Approve** and **Reject** actions.

*(Optional)* Trigger an automated CLI end-to-end test via:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_e2e_test.ps1 -WorkflowType contract_approval_multistep -DocLang de
```

---

## Database Migrations (Alembic)

The container entrypoint automatically runs `alembic upgrade head` before starting Uvicorn. For manual schema management:

```powershell
# Check current database revision
docker compose exec workflow-engine alembic current

# Apply all pending migrations
docker compose exec workflow-engine alembic upgrade head

# Auto-generate a new migration after editing app/models.py
docker compose exec workflow-engine alembic revision --autogenerate -m "describe_schema_change"

# Roll back the most recent migration by one step
docker compose exec workflow-engine alembic downgrade -1
```

---

## Integration Testing (Pytest)

All FSM transitions, parallel synchronization barriers, rejection dialogs, alternative escalation routes, temporary file cleanups, template ownership rules, and Mattermost bot DM commands are verified by 9 asynchronous integration tests using `httpx.MockTransport` and an isolated in-memory SQLite database.

```powershell
# Run the full test suite inside the Docker container
docker compose exec workflow-engine pytest
```

Every push and pull request to `main` automatically runs PostgreSQL 16 migration verification (`upgrade` ➔ `downgrade` ➔ `upgrade`), `pytest`, and a Docker image build check via **GitHub Actions** (`.github/workflows/ci.yml`).

---

## Production Deployment on Ubuntu Linux

To deploy or update the service on an Ubuntu server connected to an institutional Mattermost instance:

```bash
sudo mkdir -p /opt/mattermost-workflow-engine
sudo chown -R "$USER":"$USER" /opt/mattermost-workflow-engine
git clone [https://github.com/MasterUaKi/mattermost-workflow-engine.git](https://github.com/MasterUaKi/mattermost-workflow-engine.git) /opt/mattermost-workflow-engine
cd /opt/mattermost-workflow-engine
chmod +x scripts/deploy.sh

# First run generates .env from .env.example
./scripts/deploy.sh

# Configure production MATTERMOST_URL, MATTERMOST_BOT_TOKEN, PUBLIC_BASE_URL, and STUDIO_PUBLIC_URL
nano .env

# Build image, apply Alembic migrations, and start PostgreSQL + Workflow Engine
./scripts/deploy.sh
```

Subsequent updates from GitHub require only running `/opt/mattermost-workflow-engine/scripts/deploy.sh`.

---

## Session Management Scripts (Windows PowerShell)

```powershell
# Resume background 5-minute Git auto-sync task
powershell -ExecutionPolicy Bypass -File .\scripts\register_autosync_task.ps1

# Pause development session: stop auto-sync task, push final commit, and stop Docker containers
powershell -ExecutionPolicy Bypass -File .\scripts\stop_session.ps1 -StopDocker
```

---

## API & Webhook Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service health check (`{"status": "ok"}`) |
| `GET` | `/studio` | Visual Workflow Studio web interface |
| `GET` | `/api/v1/studio/session` | Validates signed Mattermost DM session token |
| `GET` | `/api/v1/mattermost/users` | Searches active Mattermost users for the visual builder |
| `GET` | `/api/v1/templates` | Lists workflow templates with `can_edit` ownership flags |
| `POST` | `/api/v1/templates` | Creates a new workflow template owned by the current user |
| `PUT` | `/api/v1/templates/{id}` | Updates a template (restricted to `owner_id`) |
| `DELETE` | `/api/v1/templates/{id}` | Deletes a template (restricted to `owner_id`) |
| `POST` | `/api/v1/workflows/start` | Starts a workflow (`multipart/form-data` with files & JSON metadata) |
| `GET` | `/api/v1/workflows/{id}` | Retrieves workflow status, tasks, attachments, and audit trail |
| `POST` | `/api/v1/mattermost/actions` | Webhook callback for Mattermost **Approve** / **Reject** buttons |
| `POST` | `/api/v1/mattermost/dialogs/reject` | Callback for Mattermost mandatory rejection reason modal |
