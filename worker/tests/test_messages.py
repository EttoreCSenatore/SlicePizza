import pytest

from app.messages import (
    InvalidEvent,
    customer_text,
    format_brl,
    parse_event,
    pizzeria_text,
    reply_following,
    status_label,
)


def event_body(**changes):
    body = {
        "version": 1,
        "event_id": "4f1c0000-0000-0000-0000-000000000001",
        "type": "order.created",
        "occurred_at": "2026-11-13T18:30:00+00:00",
        "order": {
            "id": "9b2e1c4a-0000-0000-0000-000000000000",
            "status": "received",
            "previous_status": None,
            "customer_name": "Maria",
            "total_cents": 9800,
            "items": [
                {"pizza_name": "Margherita", "quantity": 2},
                {"pizza_name": "Calabresa", "quantity": 1},
            ],
        },
    }
    body.update(changes)
    return body


def test_parse_order_created():
    event = parse_event(event_body())

    assert event.type == "order.created"
    assert event.short_id == "9b2e1c4a"
    assert event.items == (("Margherita", 2), ("Calabresa", 1))
    assert event.previous_status is None


def test_unknown_event_type_is_ignored_not_an_error():
    assert parse_event(event_body(type="order.refunded")) is None


@pytest.mark.parametrize("version", [None, 2, "1"])
def test_unknown_version_is_invalid(version):
    with pytest.raises(InvalidEvent, match="version"):
        parse_event(event_body(version=version))


@pytest.mark.parametrize(
    "body",
    [
        [],
        "text",
        event_body(order={}),
        event_body(order={**event_body()["order"], "total_cents": "lots"}),
        event_body(order={**event_body()["order"], "items": [{"pizza_name": "X"}]}),
        event_body(order={**event_body()["order"], "previous_status": ["received"]}),
        {k: v for k, v in event_body().items() if k != "event_id"},
    ],
)
def test_malformed_events_are_invalid(body):
    with pytest.raises(InvalidEvent):
        parse_event(body)


@pytest.mark.parametrize(
    ("cents", "text"),
    [(0, "R$ 0,00"), (5, "R$ 0,05"), (9800, "R$ 98,00"), (123456, "R$ 1.234,56"), (100000000, "R$ 1.000.000,00")],
)
def test_format_brl(cents, text):
    assert format_brl(cents) == text


def test_pizzeria_text_for_a_new_order():
    assert pizzeria_text(parse_event(event_body())) == (
        "🍕 New order 9b2e1c4a\n"
        "Customer: Maria\n"
        "2 × Margherita\n"
        "1 × Calabresa\n"
        "Total: R$ 98,00"
    )


def test_pizzeria_text_for_a_status_change():
    order = {**event_body()["order"], "status": "out_for_delivery", "previous_status": "preparing"}
    event = parse_event(event_body(type="order.status_changed", order=order))

    assert pizzeria_text(event) == "Order 9b2e1c4a (Maria): Being prepared → On the way"


def test_unknown_status_is_shown_as_is():
    assert status_label("baking") == "baking"


# --- Customers (ADR 0006) -------------------------------------------------------


def test_events_without_notify_have_no_customer_chats():
    assert parse_event(event_body()).telegram_chat_ids == ()


def test_customer_chats_are_read_without_duplicates():
    event = parse_event(event_body(notify={"telegram_chat_ids": [111, -222, 111]}))

    assert event.telegram_chat_ids == (111, -222)


@pytest.mark.parametrize(
    "notify",
    ["chats", {"telegram_chat_ids": "111"}, {"telegram_chat_ids": ["111"]}, {"telegram_chat_ids": [True]}, {"telegram_chat_ids": [1.5]}],
)
def test_malformed_customer_chats_are_invalid(notify):
    with pytest.raises(InvalidEvent):
        parse_event(event_body(notify=notify))


@pytest.mark.parametrize(
    ("status", "words"),
    [
        ("preparing", "is being prepared"),
        ("out_for_delivery", "is on the way"),
        ("delivered", "was delivered"),
        ("cancelled", "was cancelled"),
        ("baking", "Your order 9b2e1c4a: baking."),
    ],
)
def test_customer_text(status, words):
    order = {**event_body()["order"], "status": status, "previous_status": "received"}
    text = customer_text(parse_event(event_body(type="order.status_changed", order=order)))

    assert text.startswith("Zé's Pizzeria\n")
    assert words in text
    assert "9b2e1c4a" in text
    assert "Maria" not in text  # the customer knows their own name


def test_reply_following_an_open_order():
    text = reply_following("9b2e1c4a", "preparing")

    assert "You're following order 9b2e1c4a" in text
    assert "is being prepared" in text
    assert "/stop" in text


def test_reply_following_a_finished_order():
    text = reply_following("9b2e1c4a", "delivered")

    assert "was delivered" in text
    assert "no more updates" in text
