"""Pytest fixtures.

The tests use an in-memory SQLite database by default, so they need neither
Docker nor Postgres. To run them against Postgres (CI does this), set
TEST_DATABASE_URL, for example:

    TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/slicepizza_test pytest

The tests drop all tables, so this file makes sure they never touch a real
database:

- a dedicated variable is used, never DATABASE_URL or POSTGRES_*;
- an empty TEST_DATABASE_URL means "not set" (SQLite);
- a non-SQLite database must have "test" in its name.
"""

import os

import pytest
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or "sqlite+pysqlite:///:memory:"

_test_url = make_url(TEST_DATABASE_URL)
if _test_url.get_backend_name() != "sqlite" and "test" not in (_test_url.database or ""):
    pytest.exit(
        f"Refusing to run the tests against database {_test_url.database!r}: they "
        "drop all tables. Use a database whose name contains 'test', e.g. "
        "slicepizza_test.",
        returncode=2,
    )

# Make sure no Postgres settings from the shell (e.g. a sourced .env) are used.
for _name in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
    os.environ.pop(_name, None)
# Never publish to a real broker from the tests: events stay in the outbox,
# and test_events.py drives the relay with a fake publisher.
for _name in ("RABBITMQ_HOST", "RABBITMQ_PORT", "RABBITMQ_USER", "RABBITMQ_PASSWORD", "RABBITMQ_VHOST"):
    os.environ.pop(_name, None)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Turns on the worker's /internal routes (test_internal.py).
os.environ["INTERNAL_API_TOKEN"] = "test-internal-token-0123456789abcdef"
# Turns on the kitchen's routes: the order list and status changes (ADR 0007).
os.environ["KITCHEN_API_TOKEN"] = "test-kitchen-token-0123456789abcdef0"
# The origin the CORS tests treat as "the frontend" (see test_cors.py).
os.environ["CORS_ORIGINS"] = "https://menu.slicepizza.test"

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
    """The public: no credentials, like the menu site."""
    # Not used as a context manager, so the app lifespan does not run: the
    # fixture above owns the database setup. test_startup.py covers the lifespan.
    return TestClient(app)


@pytest.fixture
def kitchen():
    """The kitchen dashboard: sends the kitchen token, as Caddy does for it."""
    return TestClient(
        app, headers={"Authorization": f"Bearer {os.environ['KITCHEN_API_TOKEN']}"}
    )


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
