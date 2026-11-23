# Author: Oleh Riabtsev
# File: app/bot_listener.py
# Created: 2026-11-23
# Version: 1.0.0

"""
Background Mattermost WebSocket listener for the bot account.
Allows any user to send a Direct Message to the bot (e.g., 'start', 'старт',
'хочу начать согласование', 'neu') and immediately receive a signed magic link
opening the Visual Workflow Studio authenticated as that user.
"""

import asyncio
import json
import logging
import websockets

from app.auth_tokens import create_studio_session_token
from app.config import Settings
from app.i18n import Translator
from app.mattermost_client import MattermostClient

logger = logging.getLogger("workflow_engine.bot_ws")

TRIGGER_KEYWORDS = {
    "start",
    "старт",
    "начать",
    "согласование",
    "хочу начать согласование",
    "запуск",
    "neu",
    "genehmigung",
    "studio",
    "help",
    "помощь",
    "hilfe",
}


class BotWebSocketListener:
    """Listens to Mattermost WebSocket events for Direct Messages addressed to the bot."""

    def __init__(
        self,
        settings: Settings,
        mm_client: MattermostClient,
        translator: Translator,
    ) -> None:
        self.settings = settings
        self.mm_client = mm_client
        self.translator = translator
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def _build_ws_url(self) -> str:
        """Converts HTTP(S) Mattermost URL to WS(S) WebSocket endpoint."""
        base = self.settings.MATTERMOST_URL.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://") :]
        else:
            ws_base = f"ws://{base}"
        return f"{ws_base}/api/v4/websocket"

    def start(self) -> None:
        """Starts the background WebSocket listener task."""
        if not self.settings.ENABLE_BOT_WS_LISTENER:
            return
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Signals the background listener to stop and waits for clean shutdown."""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        """Maintains a persistent WebSocket connection with exponential backoff."""
        backoff = 3
        while not self._stop_event.is_set():
            try:
                bot_id = await self.mm_client.get_bot_user_id()
                ws_url = self._build_ws_url()

                async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                    # Authenticate over WebSocket using the Bot Account Token
                    auth_challenge = {
                        "seq": 1,
                        "action": "authentication_challenge",
                        "data": {"token": self.settings.MATTERMOST_BOT_TOKEN},
                    }
                    await ws.send(json.dumps(auth_challenge))
                    logger.info(self.translator.t_log("ws_connected"))
                    backoff = 3

                    async for raw_message in ws:
                        if self._stop_event.is_set():
                            break
                        await self._handle_event(raw_message, bot_id)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    self.translator.t_log("ws_disconnected", detail=str(exc), delay=backoff)
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _handle_event(self, raw_message: str, bot_id: str) -> None:
        """Processes incoming Mattermost 'posted' events in Direct Message channels."""
        try:
            event = json.loads(raw_message)
        except json.JSONDecodeError:
            return

        if event.get("event") != "posted":
            return

        data = event.get("data", {})
        if data.get("channel_type") != "D":
            return

        post_raw = data.get("post")
        if not post_raw:
            return

        try:
            post = json.loads(post_raw) if isinstance(post_raw, str) else post_raw
        except json.JSONDecodeError:
            return

        sender_id = post.get("user_id")
        if not sender_id or sender_id == bot_id:
            return

        message_text = str(post.get("message", "")).strip().lower()
        if not message_text:
            return

        # Match direct keywords or phrases like 'хочу начать согласование'
        is_trigger = message_text in TRIGGER_KEYWORDS or any(
            kw in message_text for kw in ("согласован", "start", "старт", "genehmig")
        )
        if not is_trigger:
            return

        # Infer preferred reply language from the user's message
        reply_lang = "de" if any(w in message_text for w in ("neu", "genehmig", "hilfe")) else "en"

        username = await self.mm_client.get_username(sender_id)
        session_token = create_studio_session_token(
            self.settings,
            user_id=sender_id,
            username=username,
        )
        studio_url = f"{self.settings.STUDIO_PUBLIC_URL.rstrip('/')}/studio?token={session_token}"

        subject = self.translator.t("dm.bot_studio_subject", reply_lang)
        body = self.translator.t(
            "dm.bot_studio_body",
            reply_lang,
            username=username,
            studio_url=studio_url,
        )
        await self.mm_client.send_direct_notification(
            user_id=sender_id,
            subject=subject,
            body=body,
            color="#2563EB",
        )
        logger.info(
            self.translator.t_log("ws_trigger_sent", username=username, user_id=sender_id)
        )
