"""Pytest fixtures.

The tests use an in-memory SQLite database by default, so they need neither
Docker nor Postgres. To run them against Postgres (CI does this), set
TEST_DATABASE_URL, for example:

    TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/slicepizza_test pytest

A dedicated variable is used on purpose: the tests drop all tables, so they
must never pick up a DATABASE_URL that points at your development database.
"""

import os

os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:"
)

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
    # fixture above owns the database setup. test_startup.py covers the lifespan.
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
