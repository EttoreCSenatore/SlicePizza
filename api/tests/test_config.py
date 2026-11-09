"""Database settings from environment variables."""

import pytest
from sqlalchemy.engine import make_url

from app.config import ConfigError, database_url_from_env
from app.database import is_in_memory_sqlite

DB_VARS = [
    "DATABASE_URL",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
]


@pytest.fixture
def env(monkeypatch):
    for name in DB_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_password_with_special_characters_needs_no_encoding(env):
    password = "p@ss:w/rd?#%1"
    env.setenv("POSTGRES_HOST", "db")
    env.setenv("POSTGRES_USER", "slicepizza")
    env.setenv("POSTGRES_PASSWORD", password)
    env.setenv("POSTGRES_DB", "slicepizza")

    url = database_url_from_env()

    assert url.password == password
    assert url.host == "db"
    assert url.port == 5432
    assert url.drivername == "postgresql+psycopg"
    # The URL survives a round trip through its string form.
    assert make_url(url.render_as_string(hide_password=False)).password == password


def test_postgres_host_requires_the_other_variables(env):
    env.setenv("POSTGRES_HOST", "db")

    with pytest.raises(ConfigError, match="POSTGRES_USER"):
        database_url_from_env()


def test_database_url_takes_precedence(env):
    env.setenv("DATABASE_URL", "sqlite:///./local.db")
    env.setenv("POSTGRES_HOST", "db")

    assert database_url_from_env().get_backend_name() == "sqlite"


@pytest.mark.parametrize("scheme", ["postgresql", "postgres"])
def test_plain_postgres_url_uses_psycopg3(env, scheme):
    env.setenv("DATABASE_URL", f"{scheme}://user:secret@localhost:5432/slicepizza")

    assert database_url_from_env().drivername == "postgresql+psycopg"


def test_missing_configuration_fails_fast(env):
    with pytest.raises(ConfigError, match="No database configured"):
        database_url_from_env()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite://", True),
        ("sqlite:///:memory:", True),
        ("sqlite+pysqlite:///:memory:", True),
        ("sqlite:///./slicepizza.db", False),
        ("postgresql+psycopg://u:p@db/slicepizza", False),
    ],
)
def test_in_memory_sqlite_detection(url, expected):
    assert is_in_memory_sqlite(make_url(url)) is expected
