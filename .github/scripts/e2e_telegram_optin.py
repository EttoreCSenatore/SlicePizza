"""End to end: a customer follows their order on Telegram (ADR 0006).

Needs, already running: the API (with INTERNAL_API_TOKEN, KITCHEN_API_TOKEN, RabbitMQ and
Postgres), the worker (TELEGRAM_BOT_TOKEN set, TELEGRAM_API_URL pointing at
fake_telegram.py, TELEGRAM_PIZZERIA_CHAT_ID=-100999), and fake_telegram.py.

1. Places an order.
2. Chat 555 sends "/start <order id>"  -> the bot answers with the status.
3. Chat 666 follows too, then blocks the bot.
4. Status -> preparing   -> the pizzeria, 555 get it; 666 fails and is unlinked.
5. Chat 555 sends "/stop".
6. Status -> out_for_delivery -> only the pizzeria gets it.
7. A link that is not an order -> "I couldn't find that order".

Usage: e2e_telegram_optin.py   (API_URL, FAKE_TELEGRAM_URL; defaults for localhost)
"""

import json
import os
import sys
import time
import urllib.request

API = os.getenv("API_URL", "http://127.0.0.1:8000")
TELEGRAM = os.getenv("FAKE_TELEGRAM_URL", "http://127.0.0.1:8081")
PIZZERIA = -100999
TIMEOUT = 30


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if method == "PATCH":  # status changes are the kitchen's (ADR 0007)
        headers["Authorization"] = f"Bearer {os.environ['KITCHEN_API_TOKEN']}"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read() or b"null")


def sent():
    return call("GET", f"{TELEGRAM}/_sent")


def wait_for(description, check):
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.3)
    print(json.dumps(sent(), indent=1, ensure_ascii=False))
    sys.exit(f"FAIL: timed out waiting for {description}")


def messages_to(chat_id, containing):
    # The pizzeria's id comes from an environment variable, as text; Telegram takes both.
    return [m for m in sent() if str(m["chat_id"]) == str(chat_id) and containing in m["text"]]


def main():
    order = call(
        "POST",
        f"{API}/orders",
        {
            "customer": {"name": "Telegram Test", "phone": "+55 11 90000-0002", "address": "Rua do Bot, 3"},
            "items": [{"pizza_id": 1, "quantity": 1}],
        },
    )
    short = order["id"][:8]
    print(f"Order {short} placed")
    wait_for("the pizzeria's 'new order' message", lambda: messages_to(PIZZERIA, f"New order {short}"))

    call("POST", f"{TELEGRAM}/_inject", {"chat_id": 555, "text": f"/start {order['id']}"})
    wait_for("the bot's answer to /start", lambda: messages_to(555, f"You're following order {short}"))
    print("Chat 555 follows the order")

    call("POST", f"{TELEGRAM}/_inject", {"chat_id": 666, "text": f"/start {order['id']}"})
    wait_for("the bot's answer to chat 666", lambda: messages_to(666, f"You're following order {short}"))
    call("POST", f"{TELEGRAM}/_block", {"chat_id": 666})
    print("Chat 666 follows, then blocks the bot")

    call("PATCH", f"{API}/orders/{order['id']}/status", {"status": "preparing"})
    wait_for("the customer's 'being prepared' message", lambda: messages_to(555, "is being prepared"))
    wait_for("the pizzeria's status message", lambda: messages_to(PIZZERIA, "Received → Being prepared"))
    print("Status 'preparing' reached the pizzeria and chat 555")

    call("POST", f"{TELEGRAM}/_inject", {"chat_id": 555, "text": "/stop"})
    wait_for("the bot's answer to /stop", lambda: messages_to(555, "you won't get any more"))
    print("Chat 555 stopped")

    call("PATCH", f"{API}/orders/{order['id']}/status", {"status": "out_for_delivery"})
    wait_for("the pizzeria's 'on the way' message", lambda: messages_to(PIZZERIA, "Being prepared → On the way"))
    time.sleep(2)  # give a wrong message to 555 or 666 time to show up
    if messages_to(555, "on the way") or messages_to(666, "on the way"):
        sys.exit("FAIL: a chat that stopped (555) or blocked the bot (666) still got 'on the way'")
    print("Status 'out_for_delivery' reached only the pizzeria")

    call("POST", f"{TELEGRAM}/_inject", {"chat_id": 777, "text": "/start not-an-order"})
    wait_for("the answer to a bad link", lambda: messages_to(777, "couldn't find that order"))

    print("OK: customers follow and stop following orders on Telegram")


if __name__ == "__main__":
    main()
