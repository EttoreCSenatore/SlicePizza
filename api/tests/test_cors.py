"""CORS for the menu site, and the Content-Type rule for JSON bodies.

CORS is off by default: in production the site and the API share one origin
(ADR 0003). A site served from another origin can only call the API when the
API answers with the right CORS headers. conftest.py sets CORS_ORIGINS to
ALLOWED_ORIGIN before the app is imported; test_cors_is_off_by_default starts
the app in a separate process without it.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, cors_origins_from_env
from app.database import get_db
from app.main import app

ALLOWED_ORIGIN = os.environ["CORS_ORIGINS"]  # set by conftest.py

OTHER_ORIGIN = "https://evil.example.com"

ORDER = {
    "customer": {"name": "Maria", "phone": "+55 11 98888-7777", "address": "Av. Paulista, 100"},
    "items": [{"pizza_id": 1, "quantity": 1}],
}


def preflight(client, origin: str, method: str, path: str = "/orders"):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )


# --- Preflight -------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), [("POST", "/orders"), ("PATCH", "/orders/x/status")])
def test_preflight_from_the_frontend_is_allowed(client, method, path):
    response = preflight(client, ALLOWED_ORIGIN, method, path)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert method in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    # No cookies or auth headers: the browser must not send credentials.
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_from_another_origin_is_refused(client):
    response = preflight(client, OTHER_ORIGIN, "POST")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("method", ["DELETE", "PUT"])
def test_preflight_for_a_method_the_api_does_not_use_is_refused(client, method):
    response = preflight(client, ALLOWED_ORIGIN, method)

    assert response.status_code == 400


# --- Actual requests -------------------------------------------------------


def test_response_to_the_frontend_carries_the_cors_header(client):
    response = client.get("/menu", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_error_responses_also_carry_the_cors_header(client):
    # Otherwise the browser hides the API's error message from the site.
    response = client.post(
        "/orders",
        json={**ORDER, "items": []},
        headers={"Origin": ALLOWED_ORIGIN},
    )

    assert response.status_code == 422
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


class BrokenSession:
    """A session whose every query fails with an error no handler expects."""

    def scalars(self, *args, **kwargs):
        raise RuntimeError("boom")


def test_unexpected_500_also_carries_the_cors_header(caplog):
    # Starlette answers unhandled errors outside CORSMiddleware; without
    # UnhandledErrorAsJSON the browser would see a CORS error, not the 500.
    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = TestClient(app).get("/menu", headers={"Origin": ALLOWED_ORIGIN})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "Unhandled error on GET /menu" in caplog.text


def test_cors_is_off_by_default():
    # The app reads CORS_ORIGINS once at import, and conftest.py sets it for
    # this process, so check the default in a fresh interpreter.
    script = """
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
get = client.get("/health", headers={"Origin": "http://localhost:8080"})
preflight = client.options(
    "/orders",
    headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST"},
)
assert get.status_code == 200, get.status_code
assert "access-control-allow-origin" not in get.headers, get.headers
assert preflight.status_code == 405, preflight.status_code
assert "access-control-allow-origin" not in preflight.headers, preflight.headers
"""
    env = {k: v for k, v in os.environ.items() if k != "CORS_ORIGINS"}
    env["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],  # api/, where the app package is
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,  # the assert below shows stderr
    )
    assert result.returncode == 0, result.stderr


def test_response_to_another_origin_has_no_cors_header(client):
    response = client.get("/menu", headers={"Origin": OTHER_ORIGIN})

    # The API still answers (CORS is enforced by the browser, not the server),
    # but without the header the browser will not hand the response to the page.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


# --- Content-Type ----------------------------------------------------------


def test_order_with_json_content_type_is_created(client):
    response = client.post("/orders", json=ORDER)

    assert response.status_code == 201


@pytest.mark.parametrize("content_type", [None, "text/plain"])
def test_json_body_without_json_content_type_is_rejected(client, content_type):
    # A browser fetch() with a string body and no header sends text/plain.
    # Since FastAPI 0.132 that body is not parsed as JSON (issue #25).
    headers = {"Content-Type": content_type} if content_type else {}
    response = client.post("/orders", content=json.dumps(ORDER), headers=headers)

    assert response.status_code == 422


# --- Settings --------------------------------------------------------------


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    return monkeypatch


def test_no_origins_by_default(env):
    assert cors_origins_from_env() == []


def test_empty_value_means_no_origins(env):
    env.setenv("CORS_ORIGINS", " , ")
    assert cors_origins_from_env() == []


def test_several_origins_are_trimmed_lowercased_and_deduplicated(env):
    env.setenv(
        "CORS_ORIGINS",
        " https://WWW.Example.com , http://localhost:8080,https://www.example.com",
    )
    assert cors_origins_from_env() == ["https://www.example.com", "http://localhost:8080"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Browsers never send the scheme's default port.
        ("https://www.example.com:443", "https://www.example.com"),
        ("http://localhost:80", "http://localhost"),
        ("HTTP://LocalHost:8080", "http://localhost:8080"),
        ("https://www.example.com:8443", "https://www.example.com:8443"),
        # Browsers send a non-ASCII domain in punycode.
        ("https://Bücher.de", "https://xn--bcher-kva.de"),
        ("http://[::1]:8080", "http://[::1]:8080"),
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
    ],
)
def test_origins_are_written_the_way_browsers_send_them(env, value, expected):
    env.setenv("CORS_ORIGINS", value)
    assert cors_origins_from_env() == [expected]


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "https://www.example.com/",  # trailing slash never matches the Origin header
        "https://www.example.com/menu",
        "www.example.com",  # no scheme
        "ftp://www.example.com",
        "https://user:pass@www.example.com",
        "https://www.example.com:99999",
        "https://www.example.com?x=1",
        # Leftover characters that urlsplit reports as empty parts.
        "https://www.example.com:",
        "https://www.example.com?",
        "https://www.example.com#",
        "https://@www.example.com",
    ],
)
def test_invalid_origins_are_refused(env, value):
    env.setenv("CORS_ORIGINS", value)
    with pytest.raises(ConfigError):
        cors_origins_from_env()
