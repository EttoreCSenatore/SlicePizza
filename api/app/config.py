"""Application settings, read from environment variables."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy.engine import URL, make_url


class ConfigError(RuntimeError):
    """Raised when a setting is missing, incomplete or invalid."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"{name} is required when POSTGRES_HOST is set.")
    return value


def _port() -> int:
    value = os.getenv("POSTGRES_PORT") or "5432"  # empty means "use the default"
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"POSTGRES_PORT must be a number, got {value!r}.") from None


def database_url_from_env() -> URL:
    """Build the database URL from the environment.

    1. ``DATABASE_URL``, if set: an explicit, complete URL, e.g.
       ``sqlite:///./slicepizza.db`` for a quick local run. A plain
       ``postgresql://`` URL is switched to the psycopg 3 driver that the
       project installs.
       Being a URL, special characters in its password must be percent-encoded
       (``@`` becomes ``%40``).
    2. Otherwise ``POSTGRES_HOST`` plus ``POSTGRES_USER`` and ``POSTGRES_DB``,
       and optionally ``POSTGRES_PASSWORD`` and ``POSTGRES_PORT``. Docker
       Compose uses this. The parts are passed separately, never pasted into a
       URL string, so the password can contain any character without
       URL-encoding. Without a password, psycopg falls back to PGPASSWORD,
       ~/.pgpass or trust authentication.

    With neither set, the API refuses to start. Silently falling back to a
    local file would hide a broken deployment and lose orders on redeploy.
    """
    raw_url = os.getenv("DATABASE_URL")
    if raw_url:
        url = make_url(raw_url)
        if url.drivername in ("postgres", "postgresql"):
            url = url.set(drivername="postgresql+psycopg")
        return url

    if os.getenv("POSTGRES_HOST"):
        return URL.create(
            drivername="postgresql+psycopg",
            username=_require("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD") or None,
            host=os.environ["POSTGRES_HOST"],
            port=_port(),
            database=_require("POSTGRES_DB"),
        )

    raise ConfigError(
        "No database configured. Set POSTGRES_HOST, POSTGRES_USER, "
        "POSTGRES_PASSWORD and POSTGRES_DB (Docker Compose does this), or set "
        "DATABASE_URL, e.g. DATABASE_URL=sqlite:///./slicepizza.db for a quick "
        "local run without Postgres."
    )


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _normalize_origin(origin: str) -> str:
    """Return the origin exactly as a browser writes it in the Origin header.

    Starlette compares the header with the configured origins as plain
    strings, so an entry that is written differently (``HTTPS://X.com``,
    ``https://x.com:443``, ``https://bücher.de``) would never match. Instead of
    lowercasing the raw text, the origin is rebuilt from its parts: lowercase
    scheme and host, the host in its ASCII (punycode) form, and the port only
    when it is not the scheme's default. Anything that is not an origin raises
    ConfigError.
    """
    error = ConfigError(
        f"CORS_ORIGINS entry {origin!r} is not an origin. Use "
        "scheme://host[:port] with no path or trailing slash, e.g. "
        "https://www.example.com."
    )
    # urlsplit returns an empty query/fragment for a bare "?" or "#", so look
    # for the characters themselves.
    if "?" in origin or "#" in origin:
        raise error
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in _DEFAULT_PORTS
        or not parsed.hostname
        or parsed.path
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise error
    try:
        port = parsed.port
    except ValueError:
        raise ConfigError(f"CORS_ORIGINS entry {origin!r} has an invalid port.") from None
    if parsed.netloc.endswith(":"):
        # "https://a.com:" has no port; browsers never send the bare colon.
        raise ConfigError(f"CORS_ORIGINS entry {origin!r} has an empty port.")

    host = parsed.hostname  # already lowercase, without IPv6 brackets
    if ":" in host:
        host = f"[{host}]"  # IPv6 address
    else:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise ConfigError(f"CORS_ORIGINS entry {origin!r} has an invalid host.") from None

    if port is None or port == _DEFAULT_PORTS[parsed.scheme]:
        return f"{parsed.scheme}://{host}"
    return f"{parsed.scheme}://{host}:{port}"


def cors_origins_from_env() -> list[str]:
    """Read the origins allowed to call the API from a browser.

    ``CORS_ORIGINS`` is a comma-separated list of origins, e.g.
    ``https://www.example.com,http://localhost:8080``. Unset or empty means no
    cross-origin browser access at all; curl and server-to-server calls are
    not affected, since CORS is enforced only by browsers.

    ``*`` is refused: the API takes customers' names, phones and addresses,
    so only the project's own frontends may call it. An origin is a scheme,
    a host and an optional port; a path (even a trailing ``/``) would never
    match the browser's ``Origin`` header, so it is rejected instead of
    silently failing. Each origin is rewritten the way browsers send it
    (see _normalize_origin).
    """
    raw = os.getenv("CORS_ORIGINS") or ""
    origins: list[str] = []
    for entry in raw.split(","):
        origin = entry.strip()
        if not origin:
            continue
        if origin == "*":
            raise ConfigError(
                "CORS_ORIGINS must list the frontend's origins; '*' is not allowed."
            )
        origin = _normalize_origin(origin)
        if origin not in origins:
            origins.append(origin)
    return origins


@dataclass(frozen=True)
class RabbitMQSettings:
    host: str
    port: int
    user: str
    password: str
    vhost: str


def rabbitmq_from_env() -> RabbitMQSettings | None:
    """Where the API publishes order events, or None to keep them in the outbox.

    ``RABBITMQ_HOST`` turns publishing on; ``RABBITMQ_USER`` and
    ``RABBITMQ_PASSWORD`` are then required, ``RABBITMQ_PORT`` (5672) and
    ``RABBITMQ_VHOST`` (``/``) are optional. As with Postgres, the parts are
    separate variables, so the password needs no URL-encoding.

    Without ``RABBITMQ_HOST`` the API still records every event in the
    ``order_events`` table (the outbox); they are published once a broker is
    configured. The tests run this way.
    """
    host = os.getenv("RABBITMQ_HOST")
    if not host:
        return None

    def required(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise ConfigError(f"{name} is required when RABBITMQ_HOST is set.")
        return value

    raw_port = os.getenv("RABBITMQ_PORT") or "5672"
    try:
        port = int(raw_port)
    except ValueError:
        raise ConfigError(f"RABBITMQ_PORT must be a number, got {raw_port!r}.") from None

    return RabbitMQSettings(
        host=host,
        port=port,
        user=required("RABBITMQ_USER"),
        password=required("RABBITMQ_PASSWORD"),
        vhost=os.getenv("RABBITMQ_VHOST") or "/",
    )


# A shared secret must not be guessable: 32 characters from a password
# generator or `openssl rand -hex 32` (64) is plenty.
MIN_TOKEN_LENGTH = 32
MIN_INTERNAL_TOKEN_LENGTH = MIN_TOKEN_LENGTH


def _token_from_env(name: str) -> str | None:
    """A shared secret from the environment: unset/empty is None, short is an error.

    The value never appears in an error message.
    """
    token = (os.getenv(name) or "").strip()
    if not token:
        return None
    if len(token) < MIN_TOKEN_LENGTH:
        raise ConfigError(
            f"{name} must be at least {MIN_TOKEN_LENGTH} characters "
            "long; generate one with `openssl rand -hex 32`."
        )
    return token


def internal_api_token_from_env() -> str | None:
    """The secret the worker sends to the /internal routes (ADR 0006).

    Unset or empty: those routes are off and answer 404, as if they did not
    exist.
    """
    return _token_from_env("INTERNAL_API_TOKEN")


def kitchen_api_token_from_env() -> str | None:
    """The secret the kitchen dashboard's requests carry (ADR 0007).

    Caddy adds it to the requests it forwards from /kitchen/api/*, after the
    kitchen login; browsers never see it. Unset or empty: listing orders and
    changing their status are off (503), for everyone.
    """
    return _token_from_env("KITCHEN_API_TOKEN")


class Settings:
    """Runtime configuration, resolved once at import time."""

    def __init__(self) -> None:
        self.database_url: URL = database_url_from_env()
        self.cors_origins: list[str] = cors_origins_from_env()
        self.rabbitmq: RabbitMQSettings | None = rabbitmq_from_env()
        self.internal_api_token: str | None = internal_api_token_from_env()
        self.kitchen_api_token: str | None = kitchen_api_token_from_env()


settings = Settings()
