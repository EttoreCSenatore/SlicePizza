"""Database errors: 503 only when the database is unreachable, 500 otherwise."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import Base, engine
from app.main import app, is_database_unavailable


class FakePsycopgError(Exception):
    """Stands in for a psycopg error, which carries a SQLSTATE code."""

    def __init__(self, sqlstate):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class FakeSqliteError(Exception):
    """sqlite3 errors have no SQLSTATE."""


def operational_error(orig, connection_invalidated=False):
    return OperationalError(
        "SELECT 1", {}, orig, connection_invalidated=connection_invalidated
    )


@pytest.mark.parametrize(
    "sqlstate",
    [
        None,  # connection refused, DNS failure, timeout
        "08006",  # connection failure
        "57P01",  # admin shutdown
        "57P03",  # the database system is starting up
    ],
)
def test_unreachable_database_is_unavailable(sqlstate):
    assert is_database_unavailable(operational_error(FakePsycopgError(sqlstate)))


@pytest.mark.parametrize(
    "sqlstate",
    [
        "40P01",  # deadlock
        "40001",  # serialization failure
        "57014",  # query cancelled / statement timeout
    ],
)
def test_other_operational_errors_are_not_unavailable(sqlstate):
    assert not is_database_unavailable(operational_error(FakePsycopgError(sqlstate)))


def test_invalidated_connection_is_unavailable():
    error = operational_error(FakeSqliteError(), connection_invalidated=True)

    assert is_database_unavailable(error)


def test_sqlite_error_is_not_unavailable():
    assert not is_database_unavailable(operational_error(FakeSqliteError()))


def test_missing_table_returns_500_not_503():
    Base.metadata.drop_all(bind=engine)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/menu")

    assert response.status_code == 500
