"""Application settings, read from environment variables."""

import os

from sqlalchemy.engine import URL, make_url


class ConfigError(RuntimeError):
    """Raised when the database settings are missing or incomplete."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"{name} is required when POSTGRES_HOST is set.")
    return value


def database_url_from_env() -> URL:
    """Build the database URL from the environment.

    1. ``DATABASE_URL``, if set: an explicit, complete URL, e.g.
       ``sqlite:///./slicepizza.db`` for a quick local run. A plain
       ``postgresql://`` URL is switched to the psycopg 3 driver that the
       project installs.
    2. Otherwise ``POSTGRES_HOST`` plus ``POSTGRES_USER``, ``POSTGRES_PASSWORD``,
       ``POSTGRES_DB`` and optionally ``POSTGRES_PORT``. Docker Compose uses
       this. The parts are passed separately, never pasted into a URL string,
       so the password can contain any character without URL-encoding.

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
            password=_require("POSTGRES_PASSWORD"),
            host=os.environ["POSTGRES_HOST"],
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=_require("POSTGRES_DB"),
        )

    raise ConfigError(
        "No database configured. Set POSTGRES_HOST, POSTGRES_USER, "
        "POSTGRES_PASSWORD and POSTGRES_DB (Docker Compose does this), or set "
        "DATABASE_URL, e.g. DATABASE_URL=sqlite:///./slicepizza.db for a quick "
        "local run without Postgres."
    )


class Settings:
    """Runtime configuration, resolved once at import time."""

    def __init__(self) -> None:
        self.database_url: URL = database_url_from_env()


settings = Settings()
