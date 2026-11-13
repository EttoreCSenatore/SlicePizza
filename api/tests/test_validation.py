"""Bad input must be rejected with 422, never reach the database and become a 500."""

import json

import pytest

from app.schemas import INT32_MAX, MAX_ITEMS_PER_ORDER, MAX_PIZZAS_PER_ORDER

CUSTOMER = {
    "name": "Zé",
    "phone": "+55 11 99999-0000",
    "address": "Rua das Pizzas, 42",
}


def order_with(items=None, **customer_overrides):
    return {
        "customer": {**CUSTOMER, **customer_overrides},
        "items": items if items is not None else [{"pizza_id": 1, "quantity": 1}],
    }


@pytest.mark.parametrize("pizza_id", [0, -1, INT32_MAX + 1, 2**63])
def test_pizza_id_out_of_range(client, pizza_id):
    response = client.post(
        "/orders", json=order_with([{"pizza_id": pizza_id, "quantity": 1}])
    )

    assert response.status_code == 422


def test_too_many_items(client):
    items = [{"pizza_id": i, "quantity": 1} for i in range(1, MAX_ITEMS_PER_ORDER + 2)]

    response = client.post("/orders", json=order_with(items))

    assert response.status_code == 422


def test_duplicate_pizza_is_rejected(client):
    items = [{"pizza_id": 1, "quantity": 1}, {"pizza_id": 1, "quantity": 2}]

    response = client.post("/orders", json=order_with(items))

    assert response.status_code == 422
    assert "only once" in response.text


def test_total_pizzas_are_capped(client):
    # Each item is within its own limit, but together they exceed the cap.
    items = [
        {"pizza_id": 1, "quantity": MAX_PIZZAS_PER_ORDER},
        {"pizza_id": 2, "quantity": 1},
    ]

    response = client.post("/orders", json=order_with(items))

    assert response.status_code == 422
    assert "at most" in response.text


@pytest.mark.parametrize("field", ["name", "phone", "address"])
def test_nul_character_is_rejected(client, field):
    response = client.post("/orders", json=order_with(**{field: "a\u0000b"}))

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["name", "phone", "address"])
def test_lone_surrogate_is_rejected(client, field):
    # JSON accepts "\ud800", but it is not valid Unicode and cannot be stored.
    # json.dumps escapes it as \ud800 (the test client's json= would fail to encode it).
    body = json.dumps(order_with(**{field: "a\ud800b"}))

    response = client.post(
        "/orders", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["name", "phone", "address"])
def test_whitespace_only_is_rejected(client, field):
    response = client.post("/orders", json=order_with(**{field: "   "}))

    assert response.status_code == 422


def test_customer_fields_are_trimmed(client):
    response = client.post("/orders", json=order_with(name="  Maria  "))

    assert response.status_code == 201
    assert response.json()["customer_name"] == "Maria"


def test_name_too_long_is_rejected(client):
    response = client.post("/orders", json=order_with(name="a" * 121))

    assert response.status_code == 422


def test_nul_in_order_id_is_rejected(client):
    response = client.get("/orders/%00")

    assert response.status_code == 422
