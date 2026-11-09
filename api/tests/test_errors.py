"""Database errors: 503 only when the database is unreachable, 500 otherwise."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
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


class FailingSession:
    """A session whose every query raises the given error."""

    def __init__(self, error):
        self.error = error

    def scalars(self, *args, **kwargs):
        raise self.error


@pytest.fixture
def client_with_db_error():
    """A client whose database session raises a chosen OperationalError."""

    def use(error):
        app.dependency_overrides[get_db] = lambda: FailingSession(error)
        return TestClient(app, raise_server_exceptions=False)

    yield use
    app.dependency_overrides.pop(get_db, None)


def test_unreachable_database_returns_503(client_with_db_error, caplog):
    client = client_with_db_error(operational_error(FakePsycopgError(None)))

    response = client.get("/menu")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    # The cause is logged, so a wrong password can be diagnosed.
    assert "Database unavailable on GET /menu" in caplog.text


def test_other_database_errors_return_500(client_with_db_error):
    client = client_with_db_error(operational_error(FakePsycopgError("40P01")))

    response = client.get("/menu")

    assert response.status_code == 500
