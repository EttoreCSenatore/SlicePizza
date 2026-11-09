"""Pytest fixtures.

The environment variable is set before importing the app so the tests use an
in-memory SQLite database instead of Postgres. Docker Compose still runs the
real thing against Postgres.
"""

import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_menu  # noqa: E402


@pytest.fixture(autouse=True)
def database():
    """Give every test a fresh schema and menu."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_menu(db)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    # Not used as a context manager, so the app lifespan does not run: the
    # fixture above owns the database setup.
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
