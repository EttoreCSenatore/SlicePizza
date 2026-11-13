"""Turns order events into Telegram message texts.

Events are produced by the API (api/app/events.py, ADR 0004). This module only
reads them: an event it does not understand is reported as such, never guessed.
"""

from dataclasses import dataclass

SUPPORTED_VERSION = 1
ORDER_CREATED = "order.created"
ORDER_STATUS_CHANGED = "order.status_changed"
KNOWN_TYPES = (ORDER_CREATED, ORDER_STATUS_CHANGED)

STATUS_LABELS = {
    "received": "Received",
    "preparing": "Being prepared",
    "out_for_delivery": "On the way",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


class InvalidEvent(ValueError):
    """The message is not an order event this worker can read."""


@dataclass(frozen=True)
class OrderEvent:
    event_id: str
    type: str
    order_id: str
    status: str
    previous_status: str | None
    customer_name: str
    total_cents: int
    items: tuple[tuple[str, int], ...]

    @property
    def short_id(self) -> str:
        """The first 8 characters of the order id, as the menu site shows it."""
        return self.order_id[:8]


def parse_event(body: dict) -> OrderEvent | None:
    """Read an event body. None for a valid event of a type this worker ignores.

    Raises InvalidEvent for anything malformed or of an unknown version.
    """
    if not isinstance(body, dict):
        raise InvalidEvent("the body is not a JSON object")
    if body.get("version") != SUPPORTED_VERSION:
        raise InvalidEvent(f"unsupported event version {body.get('version')!r}")
    if body.get("type") not in KNOWN_TYPES:
        # A newer API may publish new event types: not an error, just not ours.
        return None
    try:
        order = body["order"]
        previous = order["previous_status"]
        if previous is not None and not isinstance(previous, str):
            raise ValueError("previous_status must be a string or null")
        return OrderEvent(
            event_id=str(body["event_id"]),
            type=body["type"],
            order_id=str(order["id"]),
            status=str(order["status"]),
            previous_status=previous,
            customer_name=str(order["customer_name"]),
            total_cents=int(order["total_cents"]),
            items=tuple((str(i["pizza_name"]), int(i["quantity"])) for i in order["items"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidEvent(f"missing or invalid field: {error}") from None


def format_brl(cents: int) -> str:
    """9800 -> 'R$ 98,00'; 123456 -> 'R$ 1.234,56' (Brazilian format)."""
    reais, centavos = divmod(cents, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status or "", status or "?")


def pizzeria_text(event: OrderEvent) -> str:
    """The message for the pizzeria's own chat: one per event."""
    if event.type == ORDER_CREATED:
        lines = [f"🍕 New order {event.short_id}", f"Customer: {event.customer_name}"]
        lines += [f"{quantity} × {name}" for name, quantity in event.items]
        lines.append(f"Total: {format_brl(event.total_cents)}")
        return "\n".join(lines)
    return (
        f"Order {event.short_id} ({event.customer_name}): "
        f"{status_label(event.previous_status)} → {status_label(event.status)}"
    )
