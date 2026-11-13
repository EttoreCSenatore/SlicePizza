"""The worker's /internal routes and the chat ids in events (ADR 0006)."""

import os
import threading
import time
import uuid

import pytest
from sqlalchemy import select, text

from app import internal
from app.config import ConfigError, internal_api_token_from_env, settings
from app.database import SessionLocal, engine
from app.models import OrderEvent, TelegramSubscription

TOKEN = os.environ["INTERNAL_API_TOKEN"]  # set by conftest.py
AUTH = {"Authorization": f"Bearer {TOKEN}"}
CHAT = 123456789

ORDER_PAYLOAD = {
    "customer": {"name": "Zé", "phone": "+55 11 99999-0000", "address": "Rua das Pizzas, 42"},
    "items": [{"pizza_id": 1, "quantity": 2}],
}


def new_order(client):
    return client.post("/orders", json=ORDER_PAYLOAD).json()["id"]


def subscribe(client, order_id, chat_id=CHAT, headers=AUTH):
    return client.put(f"/internal/orders/{order_id}/telegram-subscriptions/{chat_id}", headers=headers)


def last_event(db):
    return db.scalars(select(OrderEvent).order_by(OrderEvent.id.desc())).first()


# --- Access -------------------------------------------------------------------


def test_routes_are_off_without_a_token(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_token", None)
    order_id = new_order(client)

    response = subscribe(client, order_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": TOKEN},
        {"Authorization": f"Bearer {TOKEN}x"},
    ],
)
def test_a_wrong_or_missing_token_is_refused(client, db, headers):
    order_id = new_order(client)

    response = subscribe(client, order_id, headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert db.scalars(select(TelegramSubscription)).all() == []


def test_internal_routes_are_not_in_the_public_docs(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert not any(path.startswith("/internal") for path in paths)


# --- Subscribing --------------------------------------------------------------


def test_subscribe_returns_the_current_status(client, kitchen, db):
    order_id = new_order(client)
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})

    response = subscribe(client, order_id)

    assert response.status_code == 200
    assert response.json() == {"order_id": order_id, "status": "preparing", "created": True}
    [row] = db.scalars(select(TelegramSubscription)).all()
    assert (row.order_id, row.chat_id) == (order_id, CHAT)


def test_subscribing_twice_is_harmless(client, db):
    order_id = new_order(client)
    subscribe(client, order_id)

    response = subscribe(client, order_id)

    assert response.json()["created"] is False
    assert len(db.scalars(select(TelegramSubscription)).all()) == 1


def test_unknown_order(client):
    assert subscribe(client, uuid.uuid4()).status_code == 404


@pytest.mark.parametrize(
    ("order_id", "chat_id"),
    [("not-a-uuid", CHAT), (None, "abc"), (None, 2**63), (None, -(2**63) - 1)],
)
def test_invalid_ids_are_refused(client, order_id, chat_id):
    response = subscribe(client, order_id or new_order(client), chat_id)

    assert response.status_code == 422


def test_negative_chat_ids_are_fine(client):
    """Groups have negative ids."""
    order_id = new_order(client)

    assert subscribe(client, order_id, chat_id=-1001234567890).status_code == 200


def test_one_order_has_a_limited_number_of_chats(client, monkeypatch):
    monkeypatch.setattr(internal, "MAX_SUBSCRIPTIONS_PER_ORDER", 2)
    order_id = new_order(client)
    subscribe(client, order_id, chat_id=1)
    subscribe(client, order_id, chat_id=2)

    assert subscribe(client, order_id, chat_id=3).status_code == 409
    # A chat that already follows it is still fine.
    assert subscribe(client, order_id, chat_id=2).status_code == 200


def test_unsubscribe_removes_the_chat_from_every_order(client, db):
    first, second = new_order(client), new_order(client)
    subscribe(client, first)
    subscribe(client, second)
    subscribe(client, second, chat_id=555)

    response = client.delete(f"/internal/telegram-subscriptions/{CHAT}", headers=AUTH)

    assert response.json() == {"removed": 2}
    assert [s.chat_id for s in db.scalars(select(TelegramSubscription))] == [555]


def test_unsubscribe_needs_the_token(client):
    assert client.delete(f"/internal/telegram-subscriptions/{CHAT}").status_code == 401


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="row locks need Postgres")
def test_subscribing_waits_for_a_status_change_in_progress(client):
    """Linking locks the order row like PATCH does (ADR 0006), so a link and a
    status change never interleave."""
    order_id = new_order(client)
    results = {}

    with SessionLocal() as status_change:
        # A status change in progress holds the order row. FOR NO KEY UPDATE
        # (what an UPDATE of the status takes) and not FOR UPDATE: inserting
        # the subscription checks its foreign key with a KEY SHARE lock, which
        # FOR UPDATE would also block, so the test would pass even without the
        # route's own lock. FOR NO KEY UPDATE only blocks the route's FOR UPDATE.
        status_change.execute(
            text("SELECT id FROM orders WHERE id = :id FOR NO KEY UPDATE"), {"id": order_id}
        )

        def link():
            results["response"] = subscribe(client, order_id)
            results["at"] = time.monotonic()

        thread = threading.Thread(target=link)
        thread.start()
        time.sleep(0.5)
        assert "response" not in results  # still waiting for the lock
        released = time.monotonic()
        status_change.rollback()  # releases the row lock

    thread.join(5)
    assert results["response"].status_code == 200
    assert results["at"] >= released


# --- Chat ids in events -----------------------------------------------------------


def test_a_new_order_has_no_chats_to_notify(client, db):
    new_order(client)

    assert last_event(db).payload["notify"] == {"telegram_chat_ids": []}


def test_status_changes_carry_the_chats_that_follow_the_order(client, kitchen, db):
    order_id = new_order(client)
    subscribe(client, order_id, chat_id=111)
    subscribe(client, order_id, chat_id=-222)

    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})

    assert last_event(db).payload["notify"] == {"telegram_chat_ids": [111, -222]}


def test_only_this_orders_chats_are_included(client, kitchen, db):
    order_id, other = new_order(client), new_order(client)
    subscribe(client, other, chat_id=999)

    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})

    assert last_event(db).payload["notify"]["telegram_chat_ids"] == []


def test_after_unsubscribing_the_chat_is_no_longer_notified(client, kitchen, db):
    order_id = new_order(client)
    subscribe(client, order_id)
    client.delete(f"/internal/telegram-subscriptions/{CHAT}", headers=AUTH)

    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})

    assert last_event(db).payload["notify"]["telegram_chat_ids"] == []


# --- Setting ------------------------------------------------------------------------


def test_token_is_optional(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    assert internal_api_token_from_env() is None


def test_short_tokens_are_refused_without_echoing_them(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "short-secret")

    with pytest.raises(ConfigError) as raised:
        internal_api_token_from_env()

    assert "short-secret" not in str(raised.value)
