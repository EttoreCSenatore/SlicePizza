"""Database engine, session factory and FastAPI dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings

engine_kwargs: dict = {"pool_pre_ping": True}
connect_args: dict = {}

if settings.database_url.startswith("sqlite"):
    # SQLite is only used for local development and tests.
    connect_args["check_same_thread"] = False
    if ":memory:" in settings.database_url:
        # All sessions must share the same in-memory database.
        engine_kwargs["poolclass"] = StaticPool
else:
    # Recycle connections before Postgres or a proxy drops them silently.
    engine_kwargs["pool_recycle"] = 1800

engine = create_engine(settings.database_url, connect_args=connect_args, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after the request."""
    with SessionLocal() as session:
        yield session
