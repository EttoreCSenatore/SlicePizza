"""Application settings, read from environment variables."""

import os
from urllib.parse import urlsplit

from sqlalchemy.engine import URL, make_url


class ConfigError(RuntimeError):
    """Raised when the database settings are missing or incomplete."""


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
    silently failing.
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
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ConfigError(
                f"CORS_ORIGINS entry {origin!r} is not an origin. Use "
                "scheme://host[:port] with no path or trailing slash, e.g. "
                "https://www.example.com."
            )
        try:
            parsed.port  # noqa: B018 - raises ValueError on a bad port
        except ValueError:
            raise ConfigError(f"CORS_ORIGINS entry {origin!r} has an invalid port.") from None
        # Browsers send the scheme and host in lowercase.
        origin = origin.lower()
        if origin not in origins:
            origins.append(origin)
    return origins


class Settings:
    """Runtime configuration, resolved once at import time."""

    def __init__(self) -> None:
        self.database_url: URL = database_url_from_env()
        self.cors_origins: list[str] = cors_origins_from_env()


settings = Settings()
