"""Worker settings, read from environment variables once at startup."""

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """A setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str
    rabbitmq_vhost: str
    # Empty: no bot configured. The worker then logs each message instead of
    # sending it (local development, CI).
    telegram_bot_token: str
    # Chat (or group) that gets every order event. Empty: none.
    telegram_pizzeria_chat_id: str
    telegram_api_url: str
    # The worker touches this file while it is connected and working; the
    # container healthcheck looks at its age.
    heartbeat_file: str

    def __repr__(self) -> str:
        # Never print the bot token or the password, e.g. in a traceback.
        return (
            f"Settings(rabbitmq={self.rabbitmq_user}@{self.rabbitmq_host}:{self.rabbitmq_port}"
            f"{self.rabbitmq_vhost}, telegram={'on' if self.telegram_bot_token else 'off'}, "
            f"pizzeria_chat={'set' if self.telegram_pizzeria_chat_id else 'unset'})"
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"{name} is required.")
    return value


def load_settings() -> Settings:
    raw_port = os.getenv("RABBITMQ_PORT") or "5672"
    try:
        port = int(raw_port)
    except ValueError:
        raise ConfigError(f"RABBITMQ_PORT must be a number, got {raw_port!r}.") from None

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_PIZZERIA_CHAT_ID") or "").strip()
    if chat_id and not chat_id.lstrip("-").isdigit() and not chat_id.startswith("@"):
        raise ConfigError(
            "TELEGRAM_PIZZERIA_CHAT_ID must be a numeric chat id (e.g. -1001234567890) "
            f"or a public @channelname, got {chat_id!r}."
        )

    return Settings(
        rabbitmq_host=_required("RABBITMQ_HOST"),
        rabbitmq_port=port,
        rabbitmq_user=_required("RABBITMQ_USER"),
        rabbitmq_password=_required("RABBITMQ_PASSWORD"),
        rabbitmq_vhost=os.getenv("RABBITMQ_VHOST") or "/",
        telegram_bot_token=token,
        telegram_pizzeria_chat_id=chat_id,
        telegram_api_url=(os.getenv("TELEGRAM_API_URL") or "https://api.telegram.org").rstrip("/"),
        heartbeat_file=os.getenv("WORKER_HEARTBEAT_FILE") or "/tmp/worker-alive",
    )
