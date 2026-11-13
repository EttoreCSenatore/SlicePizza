"""Sending messages: to Telegram, or to the log when no bot is configured.

Telegram's Bot API is one HTTPS call, so the standard library is enough:
    POST {api}/bot{token}/sendMessage  {"chat_id": ..., "text": ...}

Every failure is sorted into one of three kinds, because the consumer treats
them differently (see app/consumer.py and ADR 0005):

- TemporaryFailure: try the same message again later (network, 5xx, 429).
- SetupFailure: the bot is misconfigured (401, 404: wrong token). Retrying
  this one message would not help, but dropping it would lose it: the
  consumer keeps it and retries slowly until someone fixes the settings.
  - ChatUnavailable (a SetupFailure): one chat cannot be reached (403: the bot
    was blocked or removed; 400 "chat not found"). A setup problem for the
    pizzeria's chat; for a customer it just means they left.
- RejectedMessage: Telegram refuses this one message (other 400s). Retrying
  will never work: it goes to the dead-letter queue.

The bot token is part of the URL. It must never reach a log line or an error
message, so errors are built from the status code and Telegram's description
only, never from the request or the URL.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Protocol

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10


class SendFailure(Exception):
    """Base class. ``retry_after`` is a hint in seconds, when Telegram gives one."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TemporaryFailure(SendFailure):
    pass


class SetupFailure(SendFailure):
    pass


class ChatUnavailable(SetupFailure):
    """This one chat cannot be reached (bot blocked, removed, wrong id).

    For the pizzeria's chat it is a setup problem like any other: keep the
    message and fix the settings. For a customer, it only means this customer
    left: skip them (ADR 0006).
    """


class RejectedMessage(SendFailure):
    pass


class Sender(Protocol):
    def send(self, chat_id: str | int, text: str) -> None: ...


class LogSender:
    """Used when TELEGRAM_BOT_TOKEN is empty: writes the message to the log."""

    def send(self, chat_id: str | int, text: str) -> None:
        logger.info("Telegram is off; would send to %s:\n%s", chat_id, text)


class TelegramSender:
    """Talks to the Bot API: sendMessage, and getUpdates for the bot's commands."""

    def __init__(self, token: str, api_url: str = "https://api.telegram.org") -> None:
        self._base = f"{api_url}/bot{token}"

    def __repr__(self) -> str:
        return "TelegramSender(<token hidden>)"

    def send(self, chat_id: str | int, text: str) -> None:
        self._call(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}},
        )

    def get_me(self) -> dict:
        """The bot's own account, e.g. {"username": "ZesPizzeriaBot", ...}."""
        result = self._call("getMe", {})
        return result if isinstance(result, dict) else {}

    def get_updates(self, offset: int | None, timeout: int) -> list[dict]:
        """Long polling: waits up to ``timeout`` seconds for new messages to the bot.

        Updates up to ``offset - 1`` are confirmed and never sent again.
        """
        payload = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        result = self._call("getUpdates", payload, http_timeout=timeout + TIMEOUT_SECONDS)
        return result if isinstance(result, list) else []

    def _call(self, method: str, payload: dict, http_timeout: float = TIMEOUT_SECONDS):
        request = urllib.request.Request(
            f"{self._base}/{method}",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=http_timeout) as response:
                answer = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            raise _classify(error.code, _read_error(error)) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            # URLError.reason is e.g. "[Errno -2] Name or service not known":
            # safe, it never contains the URL.
            reason = getattr(error, "reason", error)
            raise TemporaryFailure(f"cannot reach Telegram: {reason}") from None
        except ValueError:
            raise TemporaryFailure("Telegram sent an answer that is not JSON") from None
        return answer.get("result")


def _read_error(error: urllib.error.HTTPError) -> dict:
    try:
        return json.loads(error.read() or b"{}")
    except (ValueError, OSError):
        return {}
    finally:
        error.close()


def _classify(status: int, payload: dict) -> SendFailure:
    description = str(payload.get("description") or "no description")[:200]
    message = f"Telegram answered {status}: {description}"
    if status == 429:
        retry_after = (payload.get("parameters") or {}).get("retry_after")
        return TemporaryFailure(message, retry_after=float(retry_after) if retry_after else None)
    if status >= 500:
        return TemporaryFailure(message)
    if status in (401, 404):
        # 401: wrong token. 404: wrong token too (unknown bot).
        return SetupFailure(message)
    if status == 403 or "chat not found" in description.lower():
        # 403: the bot was blocked by the user or removed from the group.
        # 400 "chat not found": wrong chat id, or a chat the bot never saw.
        return ChatUnavailable(message)
    if status == 409:
        # getUpdates: another process is polling the same bot, or a webhook is set.
        return TemporaryFailure(message)
    return RejectedMessage(message)
