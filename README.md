<!--
Author: Oleh Riabtsev
File: README.md
Created: 2026-11-23
Version: 1.1.0
-->

# Mattermost Document Approval Workflow Engine

A configurable asynchronous Document Approval Workflow Engine integrated with **Mattermost** via REST API v4.

## Key Features
- **Declarative Routing (`workflows.yaml`):** Supports sequential (`sequential`) and parallel (`parallel`) approval stages with customizable rejection rules.
- **Mattermost REST API v4 Integration:** Authenticates via Bot Account Token, creates Direct Message channels, uploads document attachments, renders interactive cards (`Approve` / `Reject`), and opens Interactive Dialogs for mandatory rejection reasons.
- **Multi-Language Support:**
  - **UI & API (`en`, `de`):** Localized Mattermost cards, modal dialogs, direct notifications, and REST API responses (defaults to `en` when unspecified).
  - **Console & System Logs (`en`, `de`, `ru`):** Configurable via `CONSOLE_LANG` in `.env`.
- **External REST API:** Start approval workflows (`POST /api/v1/workflows/start`) and inspect full audit history (`GET /api/v1/workflows/{workflow_id}`).

## Technology Stack
- **Python 3.11+**
- **FastAPI** + **Uvicorn**
- **SQLAlchemy 2.0 (async)** + **SQLite / PostgreSQL**
- **httpx** (async HTTP client)
- **Pydantic v2** + **PyYAML**
