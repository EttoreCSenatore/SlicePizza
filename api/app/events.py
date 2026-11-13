"""Order events: what the API tells the rest of the system (ADR 0004).

Every change to an order adds an event to the outbox (the ``order_events``
table) in the same transaction as the change itself. ``app/outbox.py`` then
publishes it to RabbitMQ.

Message format, version 1. The routing key is the event type, the body is JSON:

    {
      "version": 1,
      "event_id": "4f1c...",            # also the AMQP message_id
      "type": "order.status_changed",   # or "order.created"
      "occurred_at": "2026-11-13T18:30:00+00:00",
      "order": {
        "id": "9b2e...",
        "status": "preparing",
        "previous_status": "received",  # null for order.created
        "customer_name": "Maria",
        "total_cents": 9800,
        "items": [{"pizza_name": "Margherita", "quantity": 2}]
      }
    }

Phone and delivery address stay out on purpose: the consumers (Telegram
notifications) do not need them, and every copy of personal data is one more
place it can leak from.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .models import Order, OrderEvent, OrderStatus

# Topic exchange that carries every event. Consumers bind their own queues to
# it, e.g. "order.#" for everything about orders.
EXCHANGE = "slicepizza.events"

ORDER_CREATED = "order.created"
ORDER_STATUS_CHANGED = "order.status_changed"

SCHEMA_VERSION = 1


def record_event(
    db: Session,
    order: Order,
    event_type: str,
    previous_status: OrderStatus | None = None,
) -> OrderEvent:
    """Add an event about ``order`` to the session, to be committed with it.

    Call it before ``db.commit()``: the event is saved if and only if the
    order change is.
    """
    if order.id is None:
        # A new order gets its id on INSERT: flush it first (same transaction,
        # nothing is committed yet).
        db.flush()

    payload = {
        "version": SCHEMA_VERSION,
        "type": event_type,
        "occurred_at": datetime.now(UTC).isoformat(),
        "order": {
            "id": order.id,
            "status": order.status.value,
            "previous_status": previous_status.value if previous_status else None,
            "customer_name": order.customer_name,
            "total_cents": order.total_cents,
            "items": [
                {"pizza_name": item.pizza.name, "quantity": item.quantity}
                for item in order.items
            ],
        },
    }
    event = OrderEvent(
        event_id=str(uuid.uuid4()), order_id=order.id, type=event_type, payload=payload
    )
    db.add(event)
    return event


def message_body(event: OrderEvent) -> dict:
    """The JSON body published for ``event``: its payload plus its id."""
    return {**event.payload, "event_id": event.event_id}
