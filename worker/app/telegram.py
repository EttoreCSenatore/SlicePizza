"""Sending messages: to Telegram, or to the log when no bot is configured.

Telegram's Bot API is one HTTPS call, so the standard library is enough:
    POST {api}/bot{token}/sendMessage  {"chat_id": ..., "text": ...}

Every failure is sorted into one of three kinds, because the consumer treats
them differently (see app/consumer.py and ADR 0005):

- TemporaryFailure: try the same message again later (network, 5xx, 429).
- SetupFailure: the bot or the chat is misconfigured (401, 403, chat not
  found). Retrying this one message would not help, but dropping it would
  lose it: the consumer keeps it and retries slowly until someone fixes the
  settings.
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


class RejectedMessage(SendFailure):
    pass


class Sender(Protocol):
    def send(self, chat_id: str, text: str) -> None: ...


class LogSender:
    """Used when TELEGRAM_BOT_TOKEN is empty: writes the message to the log."""

    def send(self, chat_id: str, text: str) -> None:
        logger.info("Telegram is off; would send to %s:\n%s", chat_id, text)


class TelegramSender:
    def __init__(self, token: str, api_url: str = "https://api.telegram.org") -> None:
        self._url = f"{api_url}/bot{token}/sendMessage"

    def __repr__(self) -> str:
        return "TelegramSender(<token hidden>)"

    def send(self, chat_id: str, text: str) -> None:
        body = json.dumps(
            {"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}}
        ).encode()
        request = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                response.read()
        except urllib.error.HTTPError as error:
            raise _classify(error.code, _read_error(error)) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            # URLError.reason is e.g. "[Errno -2] Name or service not known":
            # safe, it never contains the URL.
            reason = getattr(error, "reason", error)
            raise TemporaryFailure(f"cannot reach Telegram: {reason}") from None


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
    if status in (401, 403, 404) or "chat not found" in description.lower():
        # 401: wrong token. 403: the bot was blocked or removed from the chat.
        # 404: wrong token too (unknown bot). 400 "chat not found": wrong chat id.
        return SetupFailure(message)
    return RejectedMessage(message)
