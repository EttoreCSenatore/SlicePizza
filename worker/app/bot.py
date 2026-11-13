"""The bot's commands: customers follow and stop following orders (ADR 0006).

A thread long-polls Telegram's getUpdates (no public webhook needed) and
answers:

- ``/start <order id>``: what the "Follow on Telegram" link sends. The chat
  follows the order through the API, and gets the order's current status.
- ``/start`` alone: a short welcome.
- ``/stop``: the chat stops following every order.
- anything else, in a private chat: how to use the bot. In groups (like the
  pizzeria's own chat) only commands are answered.

Only one process may poll a bot: a second one gets 409 Conflict from Telegram.
Run one worker (Phase 7 will have to keep it that way, or move to a webhook).
"""

import logging
import threading

from .api_client import ApiClient, ApiUnavailable, OrderNotFound, TooManyFollowers
from .messages import (
    REPLY_HELP,
    REPLY_STOPPED,
    REPLY_TOO_MANY,
    REPLY_UNAVAILABLE,
    REPLY_UNKNOWN_ORDER,
    REPLY_WELCOME,
    reply_following,
)
from .telegram import SendFailure, SetupFailure, TelegramSender, TemporaryFailure

logger = logging.getLogger(__name__)

POLL_SECONDS = 25
MAX_BACKOFF_SECONDS = 60.0


class BotPoller:
    def __init__(
        self,
        telegram: TelegramSender,
        api: ApiClient | None,
        stop_event: threading.Event,
        poll_seconds: int = POLL_SECONDS,
    ) -> None:
        self._telegram = telegram
        self._api = api
        self._stop = stop_event
        self._poll_seconds = poll_seconds
        self._offset: int | None = None

    def run(self) -> None:
        backoff = 1.0
        logger.info("Listening to the bot's messages")
        while not self._stop.is_set():
            try:
                updates = self._telegram.get_updates(self._offset, self._poll_seconds)
            except SetupFailure as error:
                logger.error("Cannot read the bot's messages: %s. Check TELEGRAM_BOT_TOKEN.", error)
                self._stop.wait(MAX_BACKOFF_SECONDS)
                continue
            except TemporaryFailure as error:
                wait = min(error.retry_after or backoff, MAX_BACKOFF_SECONDS)
                logger.warning("Cannot read the bot's messages: %s. Retrying in %.0fs.", error, wait)
                self._stop.wait(wait)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue
            backoff = 1.0
            for update in updates:
                if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
                    continue
                # Confirm it before handling: a message that makes the handler
                # fail must not come back forever.
                self._offset = update["update_id"] + 1
                try:
                    self.handle(update)
                except Exception:  # noqa: BLE001 - one bad update must not stop the bot
                    logger.exception("Could not handle update %s", update["update_id"])
        logger.info("Stopped listening to the bot")

    def handle(self, update: dict) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = message.get("text")
        if not isinstance(chat_id, int) or isinstance(chat_id, bool) or not isinstance(text, str):
            return
        private = chat.get("type") == "private"

        if not text.startswith("/"):
            if private:
                self._reply(chat_id, REPLY_HELP)
            return

        word, _, argument = text.strip().partition(" ")
        command = word.split("@", 1)[0].lower()  # "/start@ZesPizzeriaBot" in groups
        argument = argument.strip()

        if command == "/start":
            logger.info("Bot: /start%s", " with an order" if argument else "")
            self._reply(chat_id, self._follow(argument, chat_id) if argument else REPLY_WELCOME)
        elif command == "/stop":
            logger.info("Bot: /stop")
            self._reply(chat_id, self._unfollow(chat_id))
        elif private:
            self._reply(chat_id, REPLY_HELP)

    def _follow(self, order_id: str, chat_id: int) -> str:
        if self._api is None:
            logger.error("A customer tried to follow an order, but INTERNAL_API_TOKEN is not set")
            return REPLY_UNAVAILABLE
        try:
            status = self._api.follow(order_id, chat_id)
        except OrderNotFound:
            return REPLY_UNKNOWN_ORDER
        except TooManyFollowers:
            return REPLY_TOO_MANY
        except ApiUnavailable as error:
            logger.error("Could not link a chat to an order: %s", error)
            return REPLY_UNAVAILABLE
        return reply_following(order_id.strip().lower()[:8], status)

    def _unfollow(self, chat_id: int) -> str:
        if self._api is None:
            logger.error("A customer sent /stop, but INTERNAL_API_TOKEN is not set")
            return REPLY_UNAVAILABLE
        try:
            self._api.unfollow_all(chat_id)
        except ApiUnavailable as error:
            logger.error("Could not unlink a chat: %s", error)
            return REPLY_UNAVAILABLE
        return REPLY_STOPPED

    def _reply(self, chat_id: int, text: str) -> None:
        try:
            self._telegram.send(chat_id, text)
        except SendFailure as error:
            logger.warning("Could not answer a bot message: %s", error)
