"""Tests for the menu and orders routes."""

import threading
import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, select, text, update

from app import main
from app.database import engine
from app.models import Order, Pizza

ORDER_PAYLOAD = {
    "customer": {
        "name": "Zé",
        "phone": "+55 11 99999-0000",
        "address": "Rua das Pizzas, 42",
    },
    "items": [
        {"pizza_id": 1, "quantity": 2},
        {"pizza_id": 3, "quantity": 1},
    ],
}


def create_order(client, payload=None):
    return client.post("/orders", json=payload or ORDER_PAYLOAD)


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_menu_lists_seeded_pizzas(client):
    response = client.get("/menu")

    assert response.status_code == 200
    menu = response.json()
    assert len(menu) == 5
    assert menu[0]["name"] == "Margherita"
    assert menu[0]["price_cents"] == 4500
    assert menu[0]["available"] is True


def test_menu_comes_from_the_database(client, db):
    pizza = db.scalar(select(Pizza).where(Pizza.name == "Margherita"))
    pizza.price_cents = 4990
    db.commit()

    response = client.get("/menu")

    prices = {pizza["name"]: pizza["price_cents"] for pizza in response.json()}
    assert prices["Margherita"] == 4990


def test_create_order(client):
    response = create_order(client)

    assert response.status_code == 201
    order = response.json()
    assert order["id"]
    assert order["status"] == "received"
    assert order["customer_name"] == "Zé"
    assert order["total_cents"] == 4500 * 2 + 5500
    assert len(order["items"]) == 2
    assert order["items"][0]["pizza_name"] == "Margherita"
    assert order["items"][0]["quantity"] == 2
    assert order["items"][0]["unit_price_cents"] == 4500


def test_order_status_is_stored_as_its_value(client, db):
    order_id = create_order(client).json()["id"]

    stored = db.execute(
        text("SELECT status FROM orders WHERE id = :id"), {"id": order_id}
    ).scalar_one()

    assert stored == "received"


def test_create_order_rejects_unknown_pizza(client):
    payload = {
        "customer": ORDER_PAYLOAD["customer"],
        "items": [{"pizza_id": 999, "quantity": 1}],
    }

    response = create_order(client, payload)

    assert response.status_code == 404
    assert "999" in response.json()["detail"]


def test_create_order_rejects_unavailable_pizza(client, db):
    pizza = db.scalar(select(Pizza).where(Pizza.id == 2))
    pizza.available = False
    db.commit()

    payload = {
        "customer": ORDER_PAYLOAD["customer"],
        "items": [{"pizza_id": 2, "quantity": 1}],
    }

    response = create_order(client, payload)

    assert response.status_code == 409
    assert "Calabresa" in response.json()["detail"]


def test_create_order_requires_at_least_one_item(client):
    payload = {"customer": ORDER_PAYLOAD["customer"], "items": []}

    response = create_order(client, payload)

    assert response.status_code == 422


def test_create_order_rejects_invalid_quantity(client):
    payload = {
        "customer": ORDER_PAYLOAD["customer"],
        "items": [{"pizza_id": 1, "quantity": 0}],
    }

    response = create_order(client, payload)

    assert response.status_code == 422


def test_get_order(client):
    order_id = create_order(client).json()["id"]

    response = client.get(f"/orders/{order_id}")

    assert response.status_code == 200
    assert response.json()["id"] == order_id


def test_get_unknown_order(client):
    response = client.get(f"/orders/{uuid.uuid4()}")

    assert response.status_code == 404


def test_get_order_with_malformed_id(client):
    response = client.get("/orders/does-not-exist")

    assert response.status_code == 422


def test_order_items_keep_the_order_they_were_sent_in(client):
    payload = {
        "customer": ORDER_PAYLOAD["customer"],
        "items": [
            {"pizza_id": 5, "quantity": 1},
            {"pizza_id": 1, "quantity": 1},
            {"pizza_id": 3, "quantity": 1},
        ],
    }
    order_id = create_order(client, payload).json()["id"]

    response = client.get(f"/orders/{order_id}")

    assert [item["pizza_id"] for item in response.json()["items"]] == [5, 1, 3]


def test_order_follows_the_status_flow(client):
    order_id = create_order(client).json()["id"]

    for new_status in ["preparing", "out_for_delivery", "delivered"]:
        response = client.patch(
            f"/orders/{order_id}/status", json={"status": new_status}
        )
        assert response.status_code == 200
        assert response.json()["status"] == new_status


def test_order_can_be_cancelled_while_received(client):
    order_id = create_order(client).json()["id"]

    response = client.patch(
        f"/orders/{order_id}/status", json={"status": "cancelled"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_order_cannot_skip_statuses(client):
    order_id = create_order(client).json()["id"]

    response = client.patch(
        f"/orders/{order_id}/status", json={"status": "delivered"}
    )

    assert response.status_code == 409
    assert "preparing" in response.json()["detail"]


def test_cancelled_order_is_final(client):
    order_id = create_order(client).json()["id"]
    client.patch(f"/orders/{order_id}/status", json={"status": "cancelled"})

    response = client.patch(
        f"/orders/{order_id}/status", json={"status": "preparing"}
    )

    assert response.status_code == 409


def test_repeating_status_is_a_no_op(client):
    order_id = create_order(client).json()["id"]

    response = client.patch(
        f"/orders/{order_id}/status", json={"status": "received"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_status_update_rejects_unknown_status(client):
    order_id = create_order(client).json()["id"]

    response = client.patch(
        f"/orders/{order_id}/status", json={"status": "flying"}
    )

    assert response.status_code == 422


def test_status_update_on_unknown_order(client):
    response = client.patch(
        f"/orders/{uuid.uuid4()}/status", json={"status": "preparing"}
    )

    assert response.status_code == 404


def test_status_update_changes_updated_at(client, db):
    order_id = create_order(client).json()["id"]
    # Move updated_at far into the past, so any real update is visible even on
    # SQLite, whose timestamps only have one-second resolution.
    db.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(updated_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
    )
    db.commit()

    response = client.patch(
        f"/orders/{order_id}/status", json={"status": "preparing"}
    )

    assert response.status_code == 200
    assert not response.json()["updated_at"].startswith("2000-")


def test_status_update_uses_a_single_update_statement(client):
    """The response comes from UPDATE ... RETURNING, not a SELECT afterwards."""
    order_id = create_order(client).json()["id"]
    statements = []

    def record(conn, cursor, statement, *args):
        statements.append(statement.split()[0].upper())

    event.listen(engine, "before_cursor_execute", record)
    try:
        client.patch(f"/orders/{order_id}/status", json={"status": "preparing"})
    finally:
        event.remove(engine, "before_cursor_execute", record)

    # Load (order, items, pizzas), one UPDATE, then the INSERT of its event
    # (the outbox, same transaction). No SELECT after the UPDATE.
    assert statements.count("UPDATE") == 1
    assert statements[statements.index("UPDATE") + 1 :] == ["INSERT"]


# Real concurrency needs real row locks and separate connections: Postgres only.
postgres_only = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="row locks (SELECT ... FOR UPDATE) need Postgres",
)


def patch_concurrently(client, monkeypatch, order_id, statuses):
    """Send one PATCH per status at the same time, making their reads overlap.

    Every request waits at a barrier before loading the order, then holds the
    order for a moment before writing. Without a row lock, all of them would
    read the same old status.
    """
    barrier = threading.Barrier(len(statuses))
    original_load_order = main._load_order

    def slow_load_order(*args, **kwargs):
        barrier.wait(timeout=10)
        order = original_load_order(*args, **kwargs)
        time.sleep(0.3)
        return order

    monkeypatch.setattr(main, "_load_order", slow_load_order)
    responses = [None] * len(statuses)

    def send(index, new_status):
        responses[index] = client.patch(
            f"/orders/{order_id}/status", json={"status": new_status}
        )

    threads = [
        threading.Thread(target=send, args=(i, s)) for i, s in enumerate(statuses)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    monkeypatch.undo()
    return responses


@postgres_only
def test_conflicting_concurrent_updates_one_wins(client, monkeypatch):
    order_id = create_order(client).json()["id"]

    responses = patch_concurrently(
        client, monkeypatch, order_id, ["preparing", "cancelled"]
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409]
    winner = next(r for r in responses if r.status_code == 200).json()["status"]
    assert client.get(f"/orders/{order_id}").json()["status"] == winner


@postgres_only
def test_identical_concurrent_updates_both_succeed(client, monkeypatch):
    order_id = create_order(client).json()["id"]

    responses = patch_concurrently(
        client, monkeypatch, order_id, ["preparing", "preparing"]
    )

    assert [r.status_code for r in responses] == [200, 200]
    assert client.get(f"/orders/{order_id}").json()["status"] == "preparing"
