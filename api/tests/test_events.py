"""Order events: the outbox (order_events) and the relay that publishes it (ADR 0004).

RabbitMQ itself is not needed here: the relay is driven with a fake publisher.
CI's docker compose smoke test checks the real broker end to end.
"""

import threading
import time

import pytest
from sqlalchemy import func, select, text

from app import main
from app.config import ConfigError, rabbitmq_from_env
from app.database import SessionLocal, engine
from app.events import ORDER_CREATED, ORDER_STATUS_CHANGED, message_body
from app.models import Order, OrderEvent
from app.outbox import ADVISORY_LOCK_ID, OutboxRelay, PublishError, publish_pending

ORDER_PAYLOAD = {
    "customer": {"name": "Zé", "phone": "+55 11 99999-0000", "address": "Rua das Pizzas, 42"},
    "items": [{"pizza_id": 1, "quantity": 2}, {"pizza_id": 3, "quantity": 1}],
}


def create_order(client, payload=None):
    return client.post("/orders", json=payload or ORDER_PAYLOAD)


def events(db, order_id=None):
    query = select(OrderEvent).order_by(OrderEvent.id)
    if order_id:
        query = query.where(OrderEvent.order_id == order_id)
    return db.scalars(query).all()


class FakePublisher:
    """Records what would be published; can be told to fail on some events."""

    def __init__(self, fail_on=()):
        self.published = []
        self.fail_on = set(fail_on)
        self.closed = False

    def publish(self, event):
        if event.id in self.fail_on:
            raise PublishError("no queue bound")
        self.published.append(message_body(event))

    def close(self):
        self.closed = True


# --- Writing events --------------------------------------------------------------


def test_creating_an_order_records_an_order_created_event(client, db):
    order = create_order(client).json()

    [event] = events(db, order["id"])
    assert event.type == ORDER_CREATED
    assert event.published_at is None
    assert event.payload["version"] == 1
    assert event.payload["order"] == {
        "id": order["id"],
        "status": "received",
        "previous_status": None,
        "customer_name": "Zé",
        "total_cents": order["total_cents"],
        "items": [
            {"pizza_name": item["pizza_name"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    }


def test_event_leaves_out_phone_and_address(client, db):
    create_order(client)

    [event] = events(db)
    text = str(event.payload)
    assert ORDER_PAYLOAD["customer"]["phone"] not in text
    assert ORDER_PAYLOAD["customer"]["address"] not in text


def test_status_change_records_an_event_with_the_previous_status(client, kitchen, db):
    order_id = create_order(client).json()["id"]
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})

    created, changed = events(db, order_id)
    assert created.type == ORDER_CREATED
    assert changed.type == ORDER_STATUS_CHANGED
    assert changed.payload["order"]["status"] == "preparing"
    assert changed.payload["order"]["previous_status"] == "received"
    assert changed.id > created.id


def test_every_step_of_an_order_records_one_event(client, kitchen, db):
    order_id = create_order(client).json()["id"]
    for status in ("preparing", "out_for_delivery", "delivered"):
        assert kitchen.patch(f"/orders/{order_id}/status", json={"status": status}).status_code == 200

    assert [(e.payload["order"]["previous_status"], e.payload["order"]["status"]) for e in events(db)] == [
        (None, "received"),
        ("received", "preparing"),
        ("preparing", "out_for_delivery"),
        ("out_for_delivery", "delivered"),
    ]


def test_repeating_the_current_status_records_no_event(client, kitchen, db):
    order_id = create_order(client).json()["id"]
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "received"})

    assert [e.type for e in events(db)] == [ORDER_CREATED]


def test_refused_status_change_records_no_event(client, kitchen, db):
    order_id = create_order(client).json()["id"]
    response = kitchen.patch(f"/orders/{order_id}/status", json={"status": "delivered"})

    assert response.status_code == 409
    assert [e.type for e in events(db)] == [ORDER_CREATED]


def test_refused_order_records_no_event(client, db):
    response = client.post("/orders", json={**ORDER_PAYLOAD, "items": [{"pizza_id": 999, "quantity": 1}]})

    assert response.status_code == 404
    assert events(db) == []


def test_order_and_event_are_saved_together_or_not_at_all(client, db, monkeypatch):
    """If the event cannot be saved, the order is not saved either."""

    def broken_record_event(db, order, event_type, previous_status=None):
        db.flush()
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(main, "record_event", broken_record_event)

    assert create_order(client).status_code == 500

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Order)) == 0
    assert events(db) == []


def test_every_event_gets_its_own_id(client, kitchen, db):
    order_id = create_order(client).json()["id"]
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})

    ids = [e.event_id for e in events(db)]
    assert len(set(ids)) == 2
    assert all(len(i) == 36 for i in ids)


# --- Publishing ---------------------------------------------------------------


def test_publish_pending_sends_events_in_order_and_marks_them(client, kitchen, db):
    order_id = create_order(client).json()["id"]
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})
    publisher = FakePublisher()

    with SessionLocal() as session:
        assert publish_pending(session, publisher) == 2

    assert [m["type"] for m in publisher.published] == [ORDER_CREATED, ORDER_STATUS_CHANGED]
    assert [m["event_id"] for m in publisher.published] == [e.event_id for e in events(db)]
    db.expire_all()
    assert all(e.published_at is not None for e in events(db))

    # Nothing left: a second round publishes nothing.
    with SessionLocal() as session:
        assert publish_pending(session, publisher) == 0
    assert len(publisher.published) == 2


def test_message_body_is_the_payload_plus_the_event_id(client, db):
    create_order(client)
    [event] = events(db)

    body = message_body(event)

    assert body == {**event.payload, "event_id": event.event_id}


def test_a_failure_stops_the_round_and_keeps_the_rest_in_order(client, kitchen, db):
    """Events after a failed one wait, so consumers never see them out of order."""
    order_id = create_order(client).json()["id"]
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "out_for_delivery"})
    first, second, third = events(db)
    publisher = FakePublisher(fail_on={second.id})

    with SessionLocal() as session, pytest.raises(PublishError):
        publish_pending(session, publisher)

    # The first one was confirmed and stays published; the others wait.
    db.expire_all()
    assert [e.published_at is not None for e in events(db)] == [True, False, False]
    assert [m["event_id"] for m in publisher.published] == [first.event_id]

    # Once the problem is gone, the next round continues where it stopped.
    publisher.fail_on.clear()
    with SessionLocal() as session:
        assert publish_pending(session, publisher) == 2
    assert [m["event_id"] for m in publisher.published] == [first.event_id, second.event_id, third.event_id]


def test_publish_pending_respects_the_batch_size(client, kitchen, db):
    order_id = create_order(client).json()["id"]
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "preparing"})
    kitchen.patch(f"/orders/{order_id}/status", json={"status": "out_for_delivery"})
    publisher = FakePublisher()

    with SessionLocal() as session:
        assert publish_pending(session, publisher, batch_size=2) == 2
    with SessionLocal() as session:
        assert publish_pending(session, publisher, batch_size=2) == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="advisory locks are Postgres-only")
def test_only_one_relay_publishes_at_a_time(client):
    """A second API process skips the round while another one is publishing."""
    create_order(client)

    with SessionLocal() as busy_relay:
        busy_relay.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": ADVISORY_LOCK_ID})
        with SessionLocal() as other_relay:
            assert publish_pending(other_relay, FakePublisher()) == 0
        busy_relay.rollback()  # ends the transaction, releasing the lock

    with SessionLocal() as relay_session:
        assert publish_pending(relay_session, FakePublisher()) == 1


# --- The relay thread ----------------------------------------------------------


def wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_relay_publishes_new_events_in_the_background(client):
    publisher = FakePublisher()
    relay = OutboxRelay(SessionLocal, lambda: publisher, poll_seconds=0.05)
    relay.start()
    try:
        create_order(client)
        assert wait_until(lambda: len(publisher.published) == 1)
    finally:
        relay.stop()
    assert publisher.closed


def test_relay_is_woken_up_by_the_api_after_a_commit(client, monkeypatch):
    """With a long poll interval, only the wake-up can publish in time."""
    publisher = FakePublisher()
    relay = OutboxRelay(SessionLocal, lambda: publisher, poll_seconds=60)
    monkeypatch.setattr(main, "relay", relay)
    relay.start()
    try:
        # Let the relay finish its first (empty) round and start waiting.
        time.sleep(0.2)
        create_order(client)
        assert wait_until(lambda: len(publisher.published) == 1, timeout=2)
    finally:
        relay.stop()


def test_relay_keeps_trying_when_rabbitmq_is_down(client):
    """Connection errors are retried; the events wait and go out afterwards."""
    publisher = FakePublisher()
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("RabbitMQ is down")
        return publisher

    create_order(client)
    relay = OutboxRelay(SessionLocal, factory, poll_seconds=0.05)
    relay.start()
    try:
        # The first attempt fails; the retry comes after a 1 s pause.
        assert wait_until(lambda: len(publisher.published) == 1, timeout=4)
    finally:
        relay.stop()
    assert len(attempts) == 2


def test_relay_keeps_the_rabbitmq_connection_when_the_database_fails(client, monkeypatch):
    """A database error is retried without dropping a healthy RabbitMQ connection."""
    from sqlalchemy.exc import OperationalError

    from app import outbox

    publisher = FakePublisher()
    connections = []
    real_publish_pending = outbox.publish_pending
    calls = []

    def flaky_publish_pending(db, pub, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("SELECT", {}, Exception("database restarting"))
        return real_publish_pending(db, pub, *args, **kwargs)

    monkeypatch.setattr(outbox, "publish_pending", flaky_publish_pending)
    create_order(client)

    def factory():
        connections.append(1)
        return publisher

    relay = OutboxRelay(SessionLocal, factory, poll_seconds=0.05)
    relay.start()
    try:
        assert wait_until(lambda: len(publisher.published) == 1, timeout=4)
    finally:
        relay.stop()
    assert len(connections) == 1


def test_relay_stops_promptly(client):
    relay = OutboxRelay(SessionLocal, FakePublisher, poll_seconds=60)
    relay.start()
    started = time.monotonic()
    relay.stop()
    assert time.monotonic() - started < 2
    assert not any(t.name == "outbox-relay" and t.is_alive() for t in threading.enumerate())


# --- Settings ----------------------------------------------------------------------


@pytest.fixture
def rabbit_env(monkeypatch):
    for name in ("RABBITMQ_HOST", "RABBITMQ_PORT", "RABBITMQ_USER", "RABBITMQ_PASSWORD", "RABBITMQ_VHOST"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_rabbitmq_is_off_without_a_host(rabbit_env):
    assert rabbitmq_from_env() is None


def test_rabbitmq_settings_with_defaults(rabbit_env):
    rabbit_env.setenv("RABBITMQ_HOST", "rabbitmq")
    rabbit_env.setenv("RABBITMQ_USER", "slicepizza")
    rabbit_env.setenv("RABBITMQ_PASSWORD", "p@ss:w/rd")

    settings = rabbitmq_from_env()

    assert (settings.host, settings.port, settings.user, settings.password, settings.vhost) == (
        "rabbitmq",
        5672,
        "slicepizza",
        "p@ss:w/rd",
        "/",
    )


@pytest.mark.parametrize("missing", ["RABBITMQ_USER", "RABBITMQ_PASSWORD"])
def test_rabbitmq_host_requires_credentials(rabbit_env, missing):
    rabbit_env.setenv("RABBITMQ_HOST", "rabbitmq")
    rabbit_env.setenv("RABBITMQ_USER", "slicepizza")
    rabbit_env.setenv("RABBITMQ_PASSWORD", "secret")
    rabbit_env.delenv(missing)

    with pytest.raises(ConfigError, match=missing):
        rabbitmq_from_env()


def test_rabbitmq_port_must_be_a_number(rabbit_env):
    rabbit_env.setenv("RABBITMQ_HOST", "rabbitmq")
    rabbit_env.setenv("RABBITMQ_USER", "u")
    rabbit_env.setenv("RABBITMQ_PASSWORD", "p")
    rabbit_env.setenv("RABBITMQ_PORT", "amqp")

    with pytest.raises(ConfigError, match="RABBITMQ_PORT"):
        rabbitmq_from_env()
