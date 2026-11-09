"""Database engine, session factory and FastAPI dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings

engine_kwargs: dict = {}
connect_args: dict = {}

if settings.database_url.startswith("sqlite"):
    # SQLite is only used for local development and tests.
    connect_args["check_same_thread"] = False
    if ":memory:" in settings.database_url:
        # All sessions must share the same in-memory database.
        engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.database_url, connect_args=connect_args, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after the request."""
    with SessionLocal() as session:
        yield session
