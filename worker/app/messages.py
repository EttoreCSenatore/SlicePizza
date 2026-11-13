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
    # Customers' Telegram chats that follow this order (ADR 0006).
    telegram_chat_ids: tuple[int, ...] = ()

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
            telegram_chat_ids=_chat_ids(body.get("notify")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidEvent(f"missing or invalid field: {error}") from None


def _chat_ids(notify) -> tuple[int, ...]:
    """Chats from ``notify.telegram_chat_ids``; events without it have none."""
    if notify is None:
        return ()
    if not isinstance(notify, dict):
        raise ValueError("notify must be an object")
    ids = notify.get("telegram_chat_ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ValueError("notify.telegram_chat_ids must be a list of integers")
    return tuple(dict.fromkeys(ids))  # without duplicates, in order


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


# --- Customers ---------------------------------------------------------------

CUSTOMER_STATUS_TEXT = {
    "received": "Your order {id} was received.",
    "preparing": "Your order {id} is being prepared. 🍕",
    "out_for_delivery": "Your order {id} is on the way! 🛵",
    "delivered": "Your order {id} was delivered. Enjoy! 😋",
    "cancelled": "Your order {id} was cancelled. If you didn't expect this, please call the pizzeria.",
}
FINISHED = ("delivered", "cancelled")


def customer_status_text(short_id: str, status: str) -> str:
    template = CUSTOMER_STATUS_TEXT.get(status, "Your order {id}: " + status_label(status) + ".")
    return template.format(id=short_id)


def customer_text(event: OrderEvent) -> str:
    """The message to a customer who follows the order."""
    return "Zé's Pizzeria\n" + customer_status_text(event.short_id, event.status)


# --- Replies to the bot's commands (app/bot.py) ----------------------------------------

def reply_following(short_id: str, status: str) -> str:
    now = customer_status_text(short_id, status)
    if status in FINISHED:
        return f"{now}\nThere will be no more updates for this order."
    return (
        f"🍕 You're following order {short_id} from Zé's Pizzeria.\n"
        f"{now}\n"
        "I'll message you here when it changes. Send /stop to stop."
    )


REPLY_WELCOME = (
    "Hi! I send updates about orders from Zé's Pizzeria.\n"
    "To follow your order, tap \"Follow on Telegram\" on your order's page."
)
REPLY_UNKNOWN_ORDER = (
    "I couldn't find that order. Open the link from your order's page again."
)
REPLY_TOO_MANY = "Too many chats already follow this order."
REPLY_UNAVAILABLE = "Something went wrong on our side. Please try again in a minute."
REPLY_STOPPED = "Done: you won't get any more order updates here."
REPLY_HELP = (
    "To follow an order, tap \"Follow on Telegram\" on your order's page.\n"
    "Send /stop to stop getting updates."
)
