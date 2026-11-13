"""Smoke test for order events, against the running docker compose stack.

1. Binds a temporary queue to the events exchange (management HTTP API),
   next to the worker's own queue.
2. Creates an order through the web container and changes its status
   through the kitchen route (/kitchen/api, behind the kitchen login).
3. Expects both events, in order, as persistent JSON messages whose
   message_id is the event_id.

(The "no queue at all: the event waits in the outbox" case is covered by
api/tests/test_events.py; smoke_worker_down.py covers the worker's queue.)

Usage: smoke_order_events.py   (reads RABBITMQ_USER, RABBITMQ_PASSWORD,
KITCHEN_USERNAME and KITCHEN_PASSWORD)
Only the standard library is used.
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

WEB = os.getenv("WEB_URL", "http://127.0.0.1:8080")
MANAGEMENT = os.getenv("RABBITMQ_MANAGEMENT_URL", "http://127.0.0.1:15672")
EXCHANGE = "slicepizza.events"
QUEUE = "smoke-test-order-events"
TIMEOUT = 60

AUTH = "Basic " + base64.b64encode(
    f"{os.environ['RABBITMQ_USER']}:{os.environ['RABBITMQ_PASSWORD']}".encode()
).decode()


KITCHEN_AUTH = "Basic " + base64.b64encode(
    f"{os.getenv('KITCHEN_USERNAME') or 'kitchen'}:{os.environ['KITCHEN_PASSWORD']}".encode()
).decode()


def call(method, url, body=None, auth=False, kitchen=False):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = AUTH
    if kitchen:
        headers["Authorization"] = KITCHEN_AUTH
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def management(method, path, body=None):
    return call(method, f"{MANAGEMENT}/api{path}", body, auth=True)


def wait_for(description, check):
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(1)
    sys.exit(f"FAIL: timed out after {TIMEOUT}s waiting for {description}")


def exchange_exists():
    try:
        return management("GET", f"/exchanges/%2F/{EXCHANGE}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main():
    # The relay declares the exchange when it connects.
    wait_for("the API to declare the exchange", exchange_exists)
    # Durable: RabbitMQ 4.x refuses transient non-exclusive queues
    # (deprecated feature transient_nonexcl_queues). Deleted at the end.
    management("PUT", f"/queues/%2F/{QUEUE}", {"durable": True, "auto_delete": False})
    management("POST", f"/bindings/%2F/e/{EXCHANGE}/q/{QUEUE}", {"routing_key": "order.#"})
    print(f"Bound queue {QUEUE} to {EXCHANGE} with order.#")

    order = call(
        "POST",
        f"{WEB}/api/orders",
        {
            "customer": {"name": "CI", "phone": "+55 11 90000-0000", "address": "Rua do Teste, 1"},
            "items": [{"pizza_id": 1, "quantity": 1}],
        },
    )
    print(f"Created order {order['id']}")
    call("PATCH", f"{WEB}/kitchen/api/orders/{order['id']}/status", {"status": "preparing"}, kitchen=True)

    received = []

    def two_messages():
        # Keep only this order's events (other steps may create orders too).
        for message in management(
            "POST",
            f"/queues/%2F/{QUEUE}/get",
            {"count": 50, "ackmode": "ack_requeue_false", "encoding": "auto"},
        ):
            if json.loads(message["payload"])["order"]["id"] == order["id"]:
                received.append(message)
        return len(received) >= 2

    try:
        wait_for("both events in the queue", two_messages)
    finally:
        management("DELETE", f"/queues/%2F/{QUEUE}")

    got = []
    for message in received:
        body = json.loads(message["payload"])
        props = message["properties"]
        assert props.get("message_id") == body["event_id"], props
        assert props.get("delivery_mode") == 2, props
        assert props.get("content_type") == "application/json", props
        got.append((message["routing_key"], body["order"]["previous_status"], body["order"]["status"]))

    expected = [("order.created", None, "received"), ("order.status_changed", "received", "preparing")]
    if got != expected:
        sys.exit(f"FAIL: expected {expected}, got {got}")
    print("OK: both events arrived in order:", got)


if __name__ == "__main__":
    main()
