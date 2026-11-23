# Автор: Oleh Riabtsev
# Файл: app/mattermost_client.py
# Дата создания: 2026-11-23
# Версия: 1.0.0

"""
Асинхронный клиент для взаимодействия с Mattermost REST API v4 на базе httpx.
Реализует авторизацию через Bot Token, создание DM-каналов, загрузку файлов,
отправку карточек с интерактивными кнопками, обновление постов и открытие модальных окон.
"""

import json
import logging
from typing import Any
from urllib.parse import urlencode
import httpx
from app.config import Settings
from app.i18n import Translator

logger = logging.getLogger("workflow_engine.mattermost")


class MattermostAPIError(Exception):
    """Исключение при получении ошибки от Mattermost REST API v4."""

    def __init__(self, status_code: int, message: str, endpoint: str) -> None:
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"Mattermost API error ({status_code}) on {endpoint}: {message}")


class MattermostClient:
    """Асинхронный клиент Mattermost API v4."""

    def __init__(self, settings: Settings, translator: Translator) -> None:
        self.settings = settings
        self.translator = translator
        self.base_url = settings.MATTERMOST_URL.rstrip("/")
        self._bot_user_id: str | None = None
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v4",
            headers={
                "Authorization": f"Bearer {settings.MATTERMOST_BOT_TOKEN}",
                "Accept": "application/json",
            },
            timeout=20.0,
        )

    async def close(self) -> None:
        """Закрывает пул HTTP-соединений."""
        await self._client.aclose()

    def _build_callback_url(self, path: str) -> str:
        """Формирует публичный URL для коллбэков Mattermost с опциональным секретным токеном."""
        base = f"{self.settings.PUBLIC_BASE_URL.rstrip('/')}{path}"
        if self.settings.MATTERMOST_WEBHOOK_SECRET:
            query = urlencode({"token": self.settings.MATTERMOST_WEBHOOK_SECRET})
            return f"{base}?{query}"
        return base

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        """Выполняет HTTP-запрос к Mattermost API v4 с единой обработкой ошибок."""
        response = await self._client.request(method, endpoint, **kwargs)
        if response.status_code >= 400:
            try:
                error_data = response.json()
                detail = error_data.get("message", response.text)
            except Exception:
                detail = response.text

            logger.error(
                self.translator.t(
                    "logs.mm_api_error",
                    endpoint=endpoint,
                    status_code=response.status_code,
                    message=detail,
                )
            )
            raise MattermostAPIError(response.status_code, detail, endpoint)

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def get_bot_user_id(self) -> str:
        """Получает и кеширует ID учетной записи бота (GET /api/v4/users/me)."""
        if self._bot_user_id is None:
            data = await self._request("GET", "/users/me")
            self._bot_user_id = data["id"]
        return self._bot_user_id

    async def get_username(self, user_id: str) -> str:
        """Получает логин пользователя Mattermost по его ID (GET /api/v4/users/{user_id})."""
        try:
            data = await self._request("GET", f"/users/{user_id}")
            return data.get("username", user_id)
        except MattermostAPIError:
            return user_id

    async def get_or_create_direct_channel(self, target_user_id: str) -> str:
        """
        Создает или возвращает существующий личный канал (Direct Message)
        между ботом и целевым пользователем (POST /api/v4/channels/direct).
        """
        bot_id = await self.get_bot_user_id()
        data = await self._request("POST", "/channels/direct", json=[bot_id, target_user_id])
        return data["id"]

    async def upload_file(
        self,
        channel_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Загружает файл в указанный канал Mattermost (POST /api/v4/files)
        и возвращает его file_id для прикрепления к посту.
        """
        files = {"files": (filename, content, content_type)}
        data = await self._request(
            "POST",
            "/files",
            params={"channel_id": channel_id},
            files=files,
        )
        file_infos = data.get("file_infos", [])
        if not file_infos:
            raise MattermostAPIError(500, "Empty file_infos returned by Mattermost", "/files")
        return file_infos[0]["id"]

    def build_approval_attachment(
        self,
        *,
        workflow_id: str,
        task_id: str,
        workflow_name: str,
        step_name: str,
        title: str,
        description: str | None,
        initiator_username: str,
        document_data: dict[str, Any],
        lang: str,
        include_buttons: bool = True,
        final_status_line: str | None = None,
        color: str = "#1E90FF",
    ) -> dict[str, Any]:
        """Формирует структуру Message Attachment для карточки документа."""
        fields: list[dict[str, Any]] = [
            {
                "title": self.translator.t("card.field_workflow", lang),
                "value": workflow_name,
                "short": True,
            },
            {
                "title": self.translator.t("card.field_step", lang),
                "value": step_name,
                "short": True,
            },
            {
                "title": self.translator.t("card.field_initiator", lang),
                "value": f"@{initiator_username}",
                "short": True,
            },
            {
                "title": self.translator.t("card.field_document_id", lang),
                "value": f"`{workflow_id}`",
                "short": True,
            },
        ]

        if description:
            fields.append(
                {
                    "title": self.translator.t("card.field_description", lang),
                    "value": description,
                    "short": False,
                }
            )

        if document_data:
            formatted_meta = "\n".join(f"- **{k}:** `{v}`" for k, v in document_data.items())
            fields.append(
                {
                    "title": self.translator.t("card.field_metadata", lang),
                    "value": formatted_meta,
                    "short": False,
                }
            )

        attachment: dict[str, Any] = {
            "pretext": self.translator.t("card.pretext_new", lang),
            "title": title,
            "color": color,
            "fields": fields,
        }

        if final_status_line:
            attachment["text"] = final_status_line

        if include_buttons:
            action_url = self._build_callback_url("/api/v1/mattermost/actions")
            attachment["actions"] = [
                {
                    "id": "approvebtn",
                    "name": self.translator.t("card.btn_approve", lang),
                    "type": "button",
                    "style": "good",
                    "integration": {
                        "url": action_url,
                        "context": {
                            "action": "approve",
                            "task_id": task_id,
                            "workflow_id": workflow_id,
                        },
                    },
                },
                {
                    "id": "rejectbtn",
                    "name": self.translator.t("card.btn_reject", lang),
                    "type": "button",
                    "style": "danger",
                    "integration": {
                        "url": action_url,
                        "context": {
                            "action": "reject",
                            "task_id": task_id,
                            "workflow_id": workflow_id,
                        },
                    },
                },
            ]

        return attachment

    async def send_approval_card(
        self,
        channel_id: str,
        attachment: dict[str, Any],
        file_ids: list[str] | None = None,
    ) -> str:
        """Отправляет карточку документа с интерактивными кнопками в канал (POST /api/v4/posts)."""
        payload: dict[str, Any] = {
            "channel_id": channel_id,
            "message": "",
            "props": {"attachments": [attachment]},
        }
        if file_ids:
            payload["file_ids"] = file_ids

        data = await self._request("POST", "/posts", json=payload)
        return data["id"]

    async def update_post_card(self, post_id: str, attachment: dict[str, Any]) -> None:
        """
        Обновляет исходный пост в Mattermost (PUT /api/v4/posts/{post_id}),
        заменяя интерактивные кнопки на финальный текстовый статус.
        """
        payload = {
            "id": post_id,
            "message": "",
            "props": {"attachments": [attachment]},
        }
        await self._request("PUT", f"/posts/{post_id}", json=payload)

    async def open_rejection_dialog(
        self,
        trigger_id: str,
        state_data: dict[str, Any],
        lang: str,
    ) -> None:
        """
        Открывает модальное окно (Interactive Dialog) с обязательным полем причины отклонения
        (POST /api/v4/actions/dialogs/open).
        """
        dialog_url = self._build_callback_url("/api/v1/mattermost/dialogs/reject")
        payload = {
            "trigger_id": trigger_id,
            "url": dialog_url,
            "dialog": {
                "callback_id": "reject_document_dialog",
                "title": self.translator.t("dialog.reject_title", lang),
                "introduction_text": self.translator.t("dialog.reject_intro", lang),
                "submit_label": self.translator.t("dialog.submit_label", lang),
                "notify_on_cancel": False,
                "state": json.dumps(state_data),
                "elements": [
                    {
                        "display_name": self.translator.t("dialog.reason_label", lang),
                        "name": "rejection_reason",
                        "type": "textarea",
                        "placeholder": self.translator.t("dialog.reason_placeholder", lang),
                        "optional": False,
                        "min_length": 3,
                        "max_length": 1000,
                    }
                ],
            },
        }
        await self._request("POST", "/actions/dialogs/open", json=payload)

    async def send_direct_notification(
        self,
        user_id: str,
        subject: str,
        body: str,
        color: str = "#28A745",
    ) -> str:
        """Отправляет уведомление в личные сообщения (DM) указанному пользователю."""
        channel_id = await self.get_or_create_direct_channel(user_id)
        payload = {
            "channel_id": channel_id,
            "message": "",
            "props": {
                "attachments": [
                    {
                        "title": subject,
                        "text": body,
                        "color": color,
                    }
                ]
            },
        }
        data = await self._request("POST", "/posts", json=payload)
        return data["id"]
