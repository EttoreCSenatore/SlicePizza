"""The kitchen's routes: the order list and status changes (ADR 0007)."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.config import ConfigError, kitchen_api_token_from_env, settings
from app.models import Order, OrderEvent

TOKEN = os.environ["KITCHEN_API_TOKEN"]  # set by conftest.py

ORDER_PAYLOAD = {
    "customer": {"name": "Zé", "phone": "+55 11 99999-0000", "address": "Rua das Pizzas, 42"},
    "items": [{"pizza_id": 1, "quantity": 2}],
}


def new_order(client, name="Zé"):
    payload = {**ORDER_PAYLOAD, "customer": {**ORDER_PAYLOAD["customer"], "name": name}}
    return client.post("/orders", json=payload).json()["id"]


def set_created_at(db, order_id, minutes_ago):
    db.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
    )
    db.commit()


# --- Access -------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": TOKEN},
        {"Authorization": f"Bearer {TOKEN}x"},
        # The worker's token opens the worker's routes, not the kitchen's.
        {"Authorization": f"Bearer {os.environ['INTERNAL_API_TOKEN']}"},
    ],
)
def test_the_public_cannot_change_a_status(client, db, headers):
    order_id = new_order(client)

    response = client.patch(f"/orders/{order_id}/status", json={"status": "preparing"}, headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert client.get(f"/orders/{order_id}").json()["status"] == "received"
    # Refused before anything is written: no status_changed event either.
    assert [e.type for e in db.scalars(select(OrderEvent))] == ["order.created"]


def test_the_public_cannot_list_orders(client):
    new_order(client)

    response = client.get("/orders")

    assert response.status_code == 401
    assert "Zé" not in response.text


def test_customers_still_see_their_own_order(client, kitchen):
    order_id = new_order(client)
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})

    response = client.get(f"/orders/{order_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "preparing"


def test_without_a_token_on_the_server_the_kitchen_routes_are_off(client, kitchen, monkeypatch):
    order_id = new_order(client)
    monkeypatch.setattr(settings, "kitchen_api_token", None)

    patched = kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})
    listed = kitchen.get("/orders")

    for response in (patched, listed):
        assert response.status_code == 503
        assert "KITCHEN_API_TOKEN" in response.json()["detail"]
    assert client.get(f"/orders/{order_id}").json()["status"] == "received"


def test_the_token_check_comes_before_validation(client):
    """Without the token, a caller learns nothing about valid bodies or ids."""
    response = client.patch("/orders/not-an-id/status", json={"status": "flying"})

    assert response.status_code == 401


# --- Listing ------------------------------------------------------------------


def test_lists_the_open_orders_oldest_first(client, kitchen, db):
    newest = new_order(client, "Newest")
    oldest = new_order(client, "Oldest")
    middle = new_order(client, "Middle")
    set_created_at(db, newest, 1)
    set_created_at(db, oldest, 30)
    set_created_at(db, middle, 10)
    kitchen.patch(f"/orders/{middle}/status", json={"status": "preparing"})

    response = kitchen.get("/orders")

    assert response.status_code == 200
    assert [o["id"] for o in response.json()] == [oldest, middle, newest]


def test_the_list_has_what_the_kitchen_needs(client, kitchen):
    order_id = new_order(client)

    (order,) = kitchen.get("/orders").json()

    assert order["id"] == order_id
    assert order["customer_name"] == "Zé"
    assert order["customer_phone"] == "+55 11 99999-0000"
    assert order["delivery_address"] == "Rua das Pizzas, 42"
    assert order["status"] == "received"
    assert order["items"][0]["pizza_name"]
    assert order["items"][0]["quantity"] == 2
    assert order["total_cents"] == order["items"][0]["unit_price_cents"] * 2


def test_finished_orders_are_left_out_by_default(client, kitchen):
    delivered = new_order(client)
    for status in ("preparing", "out_for_delivery", "delivered"):
        kitchen.patch(f"/orders/{delivered}/status", json={"status": status})
    cancelled = new_order(client)
    kitchen.patch(f"/orders/{cancelled}/status", json={"status": "cancelled"})
    open_order = new_order(client)

    assert [o["id"] for o in kitchen.get("/orders").json()] == [open_order]


def test_filters_by_status(client, kitchen):
    received = new_order(client)
    preparing = new_order(client)
    kitchen.patch(f"/orders/{preparing}/status", json={"status": "preparing"})
    cancelled = new_order(client)
    kitchen.patch(f"/orders/{cancelled}/status", json={"status": "cancelled"})

    only_cancelled = kitchen.get("/orders", params={"status": "cancelled"}).json()
    two = kitchen.get("/orders", params=[("status", "received"), ("status", "cancelled")]).json()

    assert [o["id"] for o in only_cancelled] == [cancelled]
    assert {o["id"] for o in two} == {received, cancelled}


def test_an_unknown_status_filter_is_a_validation_error(kitchen):
    assert kitchen.get("/orders", params={"status": "flying"}).status_code == 422


def test_limit(client, kitchen, db):
    ids = [new_order(client) for _ in range(3)]
    for minutes, order_id in zip((30, 20, 10), ids):
        set_created_at(db, order_id, minutes)

    response = kitchen.get("/orders", params={"limit": 2})

    assert [o["id"] for o in response.json()] == ids[:2]
    assert kitchen.get("/orders", params={"limit": 0}).status_code == 422
    assert kitchen.get("/orders", params={"limit": 501}).status_code == 422


def test_an_empty_kitchen(kitchen):
    response = kitchen.get("/orders")

    assert response.status_code == 200
    assert response.json() == []


# --- Configuration ------------------------------------------------------------


def test_an_empty_token_means_off(monkeypatch):
    monkeypatch.setenv("KITCHEN_API_TOKEN", "  ")
    assert kitchen_api_token_from_env() is None


def test_short_tokens_are_refused_without_echoing_them(monkeypatch):
    monkeypatch.setenv("KITCHEN_API_TOKEN", "short-secret")

    with pytest.raises(ConfigError) as raised:
        kitchen_api_token_from_env()

    assert "short-secret" not in str(raised.value)
    assert "KITCHEN_API_TOKEN" in str(raised.value)
