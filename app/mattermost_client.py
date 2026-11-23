# Author: Oleh Riabtsev
# File: app/mattermost_client.py
# Created: 2026-11-23
# Version: 1.2.0

"""
Asynchronous client for Mattermost REST API v4 built on httpx.
Handles Bot Token authentication, user search, Direct Message channels, file uploads,
interactive approval cards (including escalation banners), post updates, and dialogs.
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
    """Raised when Mattermost REST API v4 returns an HTTP error response."""

    def __init__(self, status_code: int, message: str, endpoint: str) -> None:
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"Mattermost API error ({status_code}) on {endpoint}: {message}")


class MattermostClient:
    """Asynchronous Mattermost REST API v4 client."""

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
        """Closes the underlying HTTP connection pool."""
        await self._client.aclose()

    def _build_callback_url(self, path: str) -> str:
        """Constructs a public callback URL with an optional webhook secret token."""
        base = f"{self.settings.PUBLIC_BASE_URL.rstrip('/')}{path}"
        if self.settings.MATTERMOST_WEBHOOK_SECRET:
            query = urlencode({"token": self.settings.MATTERMOST_WEBHOOK_SECRET})
            return f"{base}?{query}"
        return base

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        """Executes an HTTP request against Mattermost API v4 with unified error handling."""
        response = await self._client.request(method, endpoint, **kwargs)
        if response.status_code >= 400:
            try:
                error_data = response.json()
                detail = error_data.get("message", response.text)
            except Exception:
                detail = response.text

            logger.error(
                self.translator.t_log(
                    "mm_api_error",
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
        """Retrieves and caches the bot account user ID (GET /api/v4/users/me)."""
        if self._bot_user_id is None:
            data = await self._request("GET", "/users/me")
            self._bot_user_id = data["id"]
        return self._bot_user_id

    async def get_username(self, user_id: str) -> str:
        """Retrieves a Mattermost username by user ID (GET /api/v4/users/{user_id})."""
        try:
            data = await self._request("GET", f"/users/{user_id}")
            return data.get("username", user_id)
        except MattermostAPIError:
            return user_id

    async def search_users(self, term: str = "", limit: int = 25) -> list[dict[str, Any]]:
        """
        Searches active non-bot Mattermost users for the visual workflow builder UI.
        Falls back to listing active users when the search term is empty.
        """
        bot_id = await self.get_bot_user_id()
        clean_term = term.strip()

        if clean_term:
            raw_users = await self._request(
                "POST",
                "/users/search",
                json={"term": clean_term, "limit": limit, "allow_inactive": False},
            )
        else:
            raw_users = await self._request(
                "GET",
                "/users",
                params={"per_page": limit, "active": "true"},
            )

        results: list[dict[str, Any]] = []
        for user in raw_users:
            if user.get("id") == bot_id or user.get("is_bot") or user.get("delete_at", 0) > 0:
                continue
            full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            results.append(
                {
                    "id": user["id"],
                    "username": user.get("username", ""),
                    "full_name": full_name or user.get("username", ""),
                    "email": user.get("email", ""),
                }
            )
        return results

    async def get_or_create_direct_channel(self, target_user_id: str) -> str:
        """
        Creates or retrieves an existing Direct Message channel
        between the bot and the target user (POST /api/v4/channels/direct).
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
        Uploads a file to the specified Mattermost channel (POST /api/v4/files)
        and returns the generated file_id for post attachment.
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
        escalation_banner: str | None = None,
        color: str = "#1E90FF",
    ) -> dict[str, Any]:
        """Builds a Mattermost Message Attachment payload for an approval card."""
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

        # Render custom typed fields or legacy key-value metadata cleanly
        formatted_lines: list[str] = []
        custom_fields = document_data.get("_custom_fields") if isinstance(document_data, dict) else None
        if isinstance(custom_fields, list) and custom_fields:
            for item in custom_fields:
                f_name = item.get("name", "")
                f_val = item.get("value", "")
                if f_name:
                    formatted_lines.append(f"- **{f_name}:** `{f_val}`")
        elif isinstance(document_data, dict):
            for k, v in document_data.items():
                if not str(k).startswith("_"):
                    formatted_lines.append(f"- **{k}:** `{v}`")

        if formatted_lines:
            fields.append(
                {
                    "title": self.translator.t("card.field_metadata", lang),
                    "value": "\n".join(formatted_lines),
                    "short": False,
                }
            )

        pretext_key = "card.pretext_escalated" if escalation_banner else "card.pretext_new"
        attachment: dict[str, Any] = {
            "pretext": self.translator.t(pretext_key, lang),
            "title": title,
            "color": "#F59E0B" if (escalation_banner and include_buttons) else color,
            "fields": fields,
        }

        if final_status_line:
            attachment["text"] = final_status_line
        elif escalation_banner:
            attachment["text"] = escalation_banner

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
        """Posts an interactive approval card to a channel (POST /api/v4/posts)."""
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
        Updates an existing Mattermost post (PUT /api/v4/posts/{post_id}),
        replacing interactive action buttons with a final status summary.
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
        Opens an Interactive Dialog with a required rejection reason textarea
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
        """Sends a Direct Message notification card to the specified user."""
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
