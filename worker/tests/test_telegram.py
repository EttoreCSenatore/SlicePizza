"""The Telegram client, against a fake Bot API on localhost."""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.telegram import (
    ChatUnavailable,
    LogSender,
    RejectedMessage,
    SetupFailure,
    TelegramSender,
    TemporaryFailure,
)

TOKEN = "123456:SECRET-token-that-must-never-be-logged"


@pytest.fixture
def fake_telegram():
    """A tiny HTTP server; set ``.reply`` to (status, json) to choose the answer."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            server.requests.append(
                {"path": self.path, "json": json.loads(self.rfile.read(length)), "type": self.headers["Content-Type"]}
            )
            status, payload = server.reply
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.reply = (200, {"ok": True, "result": {}})
    server.url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_sends_the_message(fake_telegram):
    TelegramSender(TOKEN, fake_telegram.url).send("-100123", "Hello")

    [request] = fake_telegram.requests
    assert request["path"] == f"/bot{TOKEN}/sendMessage"
    assert request["type"] == "application/json"
    assert request["json"]["chat_id"] == "-100123"
    assert request["json"]["text"] == "Hello"


@pytest.mark.parametrize(
    ("status", "payload", "kind"),
    [
        (429, {"ok": False, "description": "Too Many Requests: retry after 7", "parameters": {"retry_after": 7}}, TemporaryFailure),
        (500, {"ok": False, "description": "Internal Server Error"}, TemporaryFailure),
        (502, {}, TemporaryFailure),
        (401, {"ok": False, "description": "Unauthorized"}, SetupFailure),
        (403, {"ok": False, "description": "Forbidden: bot was blocked by the user"}, ChatUnavailable),
        (404, {"ok": False, "description": "Not Found"}, SetupFailure),
        (400, {"ok": False, "description": "Bad Request: chat not found"}, ChatUnavailable),
        (409, {"ok": False, "description": "Conflict: terminated by other getUpdates request"}, TemporaryFailure),
        (400, {"ok": False, "description": "Bad Request: message is too long"}, RejectedMessage),
    ],
)
def test_failures_are_classified(fake_telegram, status, payload, kind):
    fake_telegram.reply = (status, payload)

    with pytest.raises(kind) as raised:
        TelegramSender(TOKEN, fake_telegram.url).send("1", "x")

    assert type(raised.value) is kind
    assert str(status) in str(raised.value)


def test_retry_after_is_read_from_a_429(fake_telegram):
    fake_telegram.reply = (429, {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 7}})

    with pytest.raises(TemporaryFailure) as raised:
        TelegramSender(TOKEN, fake_telegram.url).send("1", "x")

    assert raised.value.retry_after == 7


def test_unreachable_telegram_is_temporary():
    # Port 9 on localhost: nothing listens, the connection is refused at once.
    with pytest.raises(TemporaryFailure, match="cannot reach Telegram"):
        TelegramSender(TOKEN, "http://127.0.0.1:9").send("1", "x")


@pytest.mark.parametrize("status", [400, 401, 500])
def test_the_token_never_appears_in_errors(fake_telegram, status):
    fake_telegram.reply = (status, {"ok": False, "description": "nope"})
    sender = TelegramSender(TOKEN, fake_telegram.url)

    with pytest.raises(Exception) as raised:
        sender.send("1", "x")

    assert "SECRET" not in str(raised.value)
    assert "SECRET" not in repr(raised.value)
    assert raised.value.__cause__ is None  # "from None": no HTTPError carrying the URL
    assert "SECRET" not in repr(sender)


def test_the_token_never_appears_in_network_errors():
    with pytest.raises(TemporaryFailure) as raised:
        TelegramSender(TOKEN, "http://127.0.0.1:9").send("1", "x")

    assert "SECRET" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_log_sender_writes_the_message(caplog):
    caplog.set_level(logging.INFO)

    LogSender().send("<pizzeria chat>", "🍕 New order 9b2e1c4a")

    assert "would send to <pizzeria chat>" in caplog.text
    assert "🍕 New order 9b2e1c4a" in caplog.text
