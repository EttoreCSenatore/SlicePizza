"""Database engine, session factory and FastAPI dependency."""

import logging
import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings

logger = logging.getLogger(__name__)


def is_in_memory_sqlite(url: URL) -> bool:
    """True for ``sqlite://``, ``sqlite:///:memory:`` and driver variants."""
    return url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:")


engine_kwargs: dict = {"pool_pre_ping": True}
connect_args: dict = {}

if settings.database_url.get_backend_name() == "sqlite":
    # SQLite is only used for local development and tests.
    connect_args["check_same_thread"] = False
    if is_in_memory_sqlite(settings.database_url):
        # All sessions must share the same in-memory database.
        engine_kwargs["poolclass"] = StaticPool
else:
    # Recycle connections before Postgres or a proxy drops them silently.
    engine_kwargs["pool_recycle"] = 1800

engine = create_engine(settings.database_url, connect_args=connect_args, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def wait_for_database(attempts: int = 10, first_delay: float = 1.0) -> None:
    """Block until the database accepts connections, with exponential backoff.

    Even with a Compose healthcheck, the database can restart right after it
    first reports ready (e.g. on first boot), so the API retries instead of
    crashing on startup.
    """
    delay = first_delay
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError:
            if attempt == attempts:
                raise
            logger.warning(
                "Database not ready (attempt %d/%d), retrying in %.0fs",
                attempt,
                attempts,
                delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, 10)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after the request."""
    with SessionLocal() as session:
        yield session
