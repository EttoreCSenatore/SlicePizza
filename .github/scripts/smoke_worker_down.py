"""Phase 3's "done when", against the running docker compose stack:

    if you take the worker down, messages wait in the queue
    and are sent when it comes back.

1. Waits for the worker to have declared its queue (notifications).
2. Stops the worker container.
3. Places an order through the web container.
4. Expects its event to wait in the queue.
5. Starts the worker again.
6. Expects the queue to drain and the worker's log to show the message for
   that order (without TELEGRAM_BOT_TOKEN the worker logs instead of sending).

Usage: smoke_worker_down.py   (reads RABBITMQ_USER and RABBITMQ_PASSWORD)
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

WEB = os.getenv("WEB_URL", "http://127.0.0.1:8080")
MANAGEMENT = os.getenv("RABBITMQ_MANAGEMENT_URL", "http://127.0.0.1:15672")
QUEUE = "notifications"
TIMEOUT = 90

AUTH = "Basic " + base64.b64encode(
    f"{os.environ['RABBITMQ_USER']}:{os.environ['RABBITMQ_PASSWORD']}".encode()
).decode()


def call(method, url, body=None, auth=False):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = AUTH
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def queue_messages():
    """Messages in the queue (ready + unacknowledged), or None if it does not exist."""
    try:
        queue = call("GET", f"{MANAGEMENT}/api/queues/%2F/{QUEUE}", auth=True)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    return queue.get("messages")


def compose(*args):
    return subprocess.run(["docker", "compose", *args], check=True, capture_output=True, text=True).stdout


def wait_for(description, check):
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(1)
    sys.exit(f"FAIL: timed out after {TIMEOUT}s waiting for {description}")


def main():
    wait_for(f"the worker to declare the {QUEUE!r} queue", lambda: queue_messages() is not None)
    # Let it handle whatever the earlier steps produced.
    wait_for(f"the {QUEUE!r} queue to be empty", lambda: queue_messages() == 0)

    compose("stop", "worker")
    print("Worker stopped")

    order = call(
        "POST",
        f"{WEB}/api/orders",
        {
            "customer": {"name": "Queue Test", "phone": "+55 11 90000-0001", "address": "Rua da Fila, 2"},
            "items": [{"pizza_id": 2, "quantity": 3}],
        },
    )
    short_id = order["id"][:8]
    print(f"Created order {short_id} while the worker is down")

    # The management API refreshes queue counts every few seconds.
    wait_for("the event to wait in the queue", lambda: (queue_messages() or 0) >= 1)
    print(f"Its event is waiting in {QUEUE!r}: {queue_messages()} message(s)")

    compose("start", "worker")
    print("Worker started")

    wait_for(f"the worker to empty {QUEUE!r}", lambda: queue_messages() == 0)

    def logged():
        return f"New order {short_id}" in compose("logs", "--no-color", "worker")

    wait_for("the worker's log to show the order", logged)
    print(f"OK: the worker handled order {short_id} after coming back")


if __name__ == "__main__":
    main()
