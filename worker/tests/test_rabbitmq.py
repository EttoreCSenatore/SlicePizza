"""The consumer against a real RabbitMQ (CI runs one; locally, see README.md).

Skipped unless RABBITMQ_TEST_HOST is set. A dedicated variable, never
RABBITMQ_HOST, because these tests delete the worker's queues.
"""

import json
import os
import threading
import time

import pytest

from app import consumer as consumer_module
from app.config import Settings
from app.consumer import (
    DEAD_LETTER_QUEUE,
    EXCHANGE,
    QUEUE,
    Consumer,
    Notifier,
    declare_topology,
)
from app.telegram import TemporaryFailure

from test_messages import event_body

HOST = os.getenv("RABBITMQ_TEST_HOST")
pytestmark = pytest.mark.skipif(not HOST, reason="set RABBITMQ_TEST_HOST to run against RabbitMQ")

pika = pytest.importorskip("pika")


def settings(tmp_path):
    return Settings(
        rabbitmq_host=HOST or "",
        rabbitmq_port=int(os.getenv("RABBITMQ_TEST_PORT") or 5672),
        rabbitmq_user=os.getenv("RABBITMQ_TEST_USER") or "guest",
        rabbitmq_password=os.getenv("RABBITMQ_TEST_PASSWORD") or "guest",
        rabbitmq_vhost="/",
        telegram_bot_token="",
        telegram_pizzeria_chat_id="",
        telegram_api_url="",
        heartbeat_file=str(tmp_path / "alive"),
    )


class FakeSender:
    def __init__(self, failures=0):
        self.sent = []
        self.attempts = 0
        self.failures = failures

    def send(self, chat_id, text):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise TemporaryFailure("Telegram is down")
        self.sent.append(text)


@pytest.fixture
def broker(tmp_path):
    s = settings(tmp_path)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(s.rabbitmq_host, s.rabbitmq_port, credentials=pika.PlainCredentials(s.rabbitmq_user, s.rabbitmq_password))
    )
    channel = connection.channel()
    for queue in (QUEUE, DEAD_LETTER_QUEUE):
        channel.queue_delete(queue)
    declare_topology(channel)
    channel.confirm_delivery()
    yield s, channel
    for queue in (QUEUE, DEAD_LETTER_QUEUE):
        channel.queue_delete(queue)
    connection.close()


def publish(channel, body):
    channel.basic_publish(
        EXCHANGE,
        body["type"] if isinstance(body, dict) else "order.created",
        json.dumps(body).encode() if isinstance(body, dict) else body,
        pika.BasicProperties(delivery_mode=2, content_type="application/json"),
        mandatory=True,
    )


def depth(channel, queue):
    return channel.queue_declare(queue, passive=True).method.message_count


def wait_until(condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


class Running:
    """A consumer in a background thread."""

    def __init__(self, s, sender):
        self.consumer = Consumer(s, Notifier(sender, "-100123"))
        self.thread = threading.Thread(target=self.consumer.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.consumer

    def __exit__(self, *exc):
        self.consumer.stop()
        self.thread.join(10)
        assert not self.thread.is_alive()


def created(n):
    return event_body(event_id=f"00000000-0000-0000-0000-00000000000{n}")


def test_messages_wait_while_the_worker_is_down_and_go_out_in_order(broker):
    """The phase's "done when", in miniature."""
    s, channel = broker
    publish(channel, created(1))
    order = {**created(2)["order"], "status": "preparing", "previous_status": "received"}
    publish(channel, event_body(event_id="00000000-0000-0000-0000-000000000002", type="order.status_changed", order=order))
    assert wait_until(lambda: depth(channel, QUEUE) == 2)

    sender = FakeSender()
    with Running(s, sender):
        assert wait_until(lambda: len(sender.sent) == 2)
        assert wait_until(lambda: depth(channel, QUEUE) == 0)

    assert sender.sent[0].startswith("🍕 New order")
    assert "Received → Being prepared" in sender.sent[1]


def test_unreadable_message_goes_to_the_dead_letter_queue(broker):
    s, channel = broker
    publish(channel, b"not json")

    with Running(s, FakeSender()):
        assert wait_until(lambda: depth(channel, DEAD_LETTER_QUEUE) == 1)
    assert depth(channel, QUEUE) == 0


def test_temporary_failures_are_retried_and_the_message_is_sent_once(broker):
    s, channel = broker
    sender = FakeSender(failures=2)  # retries after 1 s and 2 s
    publish(channel, created(1))

    with Running(s, sender):
        assert wait_until(lambda: len(sender.sent) == 1, timeout=10)
        assert wait_until(lambda: depth(channel, QUEUE) == 0)

    assert sender.attempts == 3
    assert depth(channel, DEAD_LETTER_QUEUE) == 0


def test_stopping_during_retries_keeps_the_message(broker):
    s, channel = broker
    sender = FakeSender(failures=1000)
    publish(channel, created(1))

    with Running(s, sender):
        assert wait_until(lambda: sender.attempts >= 1)
    # The unacknowledged message went back to the queue, not lost or dead-lettered.
    assert wait_until(lambda: depth(channel, QUEUE) == 1)
    assert depth(channel, DEAD_LETTER_QUEUE) == 0


def test_a_message_held_too_long_is_given_back_and_retried(broker, monkeypatch):
    """Instead of RabbitMQ's consumer timeout closing the channel."""
    monkeypatch.setattr(consumer_module, "MAX_HOLD_SECONDS", 2)
    s, channel = broker
    sender = FakeSender(failures=3)  # fails at 0 s, 1 s; given back; then works
    publish(channel, created(1))

    with Running(s, sender):
        assert wait_until(lambda: len(sender.sent) == 1, timeout=15)
        assert wait_until(lambda: depth(channel, QUEUE) == 0)

    assert depth(channel, DEAD_LETTER_QUEUE) == 0


def test_the_worker_marks_itself_alive(broker, tmp_path):
    s, _channel = broker
    with Running(s, FakeSender()):
        assert wait_until(lambda: os.path.exists(s.heartbeat_file))
        first = os.path.getmtime(s.heartbeat_file)
        assert wait_until(lambda: os.path.getmtime(s.heartbeat_file) > first, timeout=5)


class RateLimitedSender(FakeSender):
    """Fails once with Telegram's 429 and a retry_after, then works."""

    def __init__(self, retry_after):
        super().__init__()
        self.retry_after = retry_after
        self.times = []

    def send(self, chat_id, text):
        self.times.append(time.monotonic())
        self.attempts += 1
        if self.attempts == 1:
            raise TemporaryFailure("Telegram answered 429", retry_after=self.retry_after)
        self.sent.append(text)


def test_telegrams_retry_after_is_honoured(broker):
    s, channel = broker
    sender = RateLimitedSender(retry_after=3)
    publish(channel, created(1))

    with Running(s, sender):
        assert wait_until(lambda: len(sender.sent) == 1, timeout=10)

    # Not the 1 s of the normal first retry: the 3 s Telegram asked for.
    assert sender.times[1] - sender.times[0] >= 2.9
