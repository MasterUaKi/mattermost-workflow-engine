<!--
Автор: Oleh Riabtsev
Файл: README.md
Дата создания: 2026-11-23
Версия: 1.0.0
-->

# Mattermost Document Approval Workflow Engine

Настраиваемая асинхронная система согласования документов (**Workflow Engine**) с интеграцией в корпоративный мессенджер **Mattermost** через REST API v4.

## Основные возможности
- **Декларативная маршрутизация (`workflows.yaml`):** поддержка последовательных (`sequential`) и параллельных (`parallel`) этапов согласования.
- **Интеграция с Mattermost API v4:** авторизация через Bot Account Token, отправка карточек в личные каналы (Direct Messages), загрузка вложений, обработка интерактивных кнопок (`Approve` / `Reject`) и модальных диалогов (`Interactive Dialogs`) для указания причины отклонения.
- **Двуязычность (`de` / `en`):** полная локализация карточек, модальных окон, системных логов и ответов REST API.
- **Внешний REST API:** запуск процессов (`POST /api/v1/workflows/start`) и получение полной истории согласования (`GET /api/v1/workflows/{id}`).

## Технологический стек
- **Python 3.11+**
- **FastAPI** + **Uvicorn**
- **SQLAlchemy 2.0 (async)** + **SQLite / PostgreSQL**
- **httpx** (асинхронный HTTP-клиент)
- **Pydantic v2** + **PyYAML**
