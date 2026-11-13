"""Consumes order events from RabbitMQ and sends the notifications (ADR 0005).

Two parts:

- ``Notifier`` decides what to do with one message: send it, skip it, or set
  it aside. It knows nothing about RabbitMQ, so the tests drive it directly.
- ``Consumer`` owns the RabbitMQ connection: declares the queues, takes one
  message at a time, acknowledges it only after the notification went out,
  and retries when Telegram fails.

Queues (declared here, by the consumer, as ADR 0004 says):

    slicepizza.events --order.#--> notifications  (quorum, durable)
                                       │ after DELIVERY_LIMIT failed deliveries
                                       ▼
    slicepizza.dead-letter -------> notifications.dead-letter  (kept for a human)
"""

from __future__ import annotations

import enum
import json
import logging
import os
import threading
import time
from collections import OrderedDict

from .messages import InvalidEvent, parse_event, pizzeria_text
from .telegram import RejectedMessage, Sender, SetupFailure, TemporaryFailure

logger = logging.getLogger(__name__)

EXCHANGE = "slicepizza.events"
QUEUE = "notifications"
BINDING_KEY = "order.#"
DEAD_LETTER_EXCHANGE = "slicepizza.dead-letter"
DEAD_LETTER_QUEUE = "notifications.dead-letter"

# A message whose delivery fails this many times (the worker crashed or lost
# its connection while holding it) goes to the dead-letter queue instead of
# blocking the queue forever: a bug that crashes the worker on one message
# cannot stop all the others.
DELIVERY_LIMIT = 20
# Hold a message for at most this long while Telegram is failing, then give it
# back (basic.nack with requeue) and take it again. RabbitMQ would otherwise
# return it after its 30-minute consumer_timeout by closing the channel.
# Since RabbitMQ 4.3, a nack is not a failed delivery: it does not count
# toward DELIVERY_LIMIT, and the message keeps its place in the queue. So a
# Telegram outage, however long, never dead-letters a message.
MAX_HOLD_SECONDS = 18 * 60
# Pauses between retries: temporary failures start at 1 s and double; a setup
# problem (wrong token or chat) waits SETUP_RETRY_SECONDS each time.
MAX_RETRY_SECONDS = 60.0
SETUP_RETRY_SECONDS = 60.0
# Telegram's own retry_after (429) is followed up to this long.
MAX_RETRY_AFTER_SECONDS = 10 * 60.0
# Remember this many recent event ids to drop duplicates (ADR 0004: delivery
# is at least once). In memory: a duplicate right after a restart can still
# get through, which costs one repeated message, nothing more.
SEEN_EVENTS = 10_000


class Decision(enum.Enum):
    ACK = "ack"  # done (sent, a duplicate, or not for us)
    DEAD_LETTER = "dead-letter"  # can never be processed: set aside


class Notifier:
    def __init__(self, sender: Sender, pizzeria_chat_id: str = "") -> None:
        self._sender = sender
        self._pizzeria_chat_id = pizzeria_chat_id
        self._seen: OrderedDict[str, None] = OrderedDict()

    def handle(self, body: bytes) -> Decision:
        """Process one message. Raises TemporaryFailure/SetupFailure to retry it."""
        try:
            event = parse_event(json.loads(body))
        except (ValueError, InvalidEvent) as error:
            # Log the reason, not the body: it may contain a customer's name.
            logger.error("Unreadable message, moving it to %s: %s", DEAD_LETTER_QUEUE, error)
            return Decision.DEAD_LETTER

        if event is None:
            logger.info("Ignoring an event type this worker does not handle")
            return Decision.ACK
        if event.event_id in self._seen:
            logger.info("Duplicate event %s, already handled", event.event_id)
            return Decision.ACK

        if self._pizzeria_chat_id:
            try:
                self._sender.send(self._pizzeria_chat_id, pizzeria_text(event))
            except RejectedMessage as error:
                logger.error(
                    "Telegram refused the message for event %s, moving it to %s: %s",
                    event.event_id,
                    DEAD_LETTER_QUEUE,
                    error,
                )
                return Decision.DEAD_LETTER

        self._remember(event.event_id)
        logger.info("Handled %s for order %s", event.type, event.short_id)
        return Decision.ACK

    def _remember(self, event_id: str) -> None:
        self._seen[event_id] = None
        if len(self._seen) > SEEN_EVENTS:
            self._seen.popitem(last=False)


def declare_topology(channel) -> None:
    """Exchanges, queues and bindings. Idempotent: safe on every start.

    Queue arguments cannot change once a queue exists: changing one below makes
    the declaration fail with PRECONDITION_FAILED until the queue is deleted
    (after moving its messages) or the change is made with a policy instead.
    """
    channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(DEAD_LETTER_EXCHANGE, exchange_type="fanout", durable=True)
    channel.queue_declare(DEAD_LETTER_QUEUE, durable=True, arguments={"x-queue-type": "quorum"})
    channel.queue_bind(DEAD_LETTER_QUEUE, DEAD_LETTER_EXCHANGE)
    channel.queue_declare(
        QUEUE,
        durable=True,
        arguments={
            # Quorum queue: RabbitMQ's durable queue type, the one meant for
            # messages that must not be lost.
            "x-queue-type": "quorum",
            "x-delivery-limit": DELIVERY_LIMIT,
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
        },
    )
    channel.queue_bind(QUEUE, EXCHANGE, routing_key=BINDING_KEY)


class Consumer:
    def __init__(self, settings, notifier: Notifier, connect=None) -> None:
        self._settings = settings
        self._notifier = notifier
        self._connect = connect or self._pika_connect
        self.stop_event = threading.Event()

    def _pika_connect(self):
        import pika

        s = self._settings
        return pika.BlockingConnection(
            pika.ConnectionParameters(
                host=s.rabbitmq_host,
                port=s.rabbitmq_port,
                virtual_host=s.rabbitmq_vhost,
                credentials=pika.PlainCredentials(s.rabbitmq_user, s.rabbitmq_password),
                heartbeat=60,
                blocked_connection_timeout=30,
                connection_attempts=1,
                socket_timeout=5,
                client_properties={"connection_name": "slicepizza-worker"},
            )
        )

    def stop(self) -> None:
        self.stop_event.set()

    def heartbeat(self) -> None:
        """Mark the worker alive for the container healthcheck."""
        try:
            with open(self._settings.heartbeat_file, "a"):
                os.utime(self._settings.heartbeat_file)
        except OSError:
            pass

    def run(self) -> None:
        """Consume until stop(), reconnecting with a growing pause on errors."""
        backoff = 1.0
        while not self.stop_event.is_set():
            connection = None
            try:
                connection = self._connect()
                channel = connection.channel()
                declare_topology(channel)
                channel.basic_qos(prefetch_count=1)
                logger.info("Connected to RabbitMQ, consuming %r", QUEUE)
                backoff = 1.0
                self._consume(connection, channel)
            except Exception as error:  # noqa: BLE001 - keep the worker alive
                if self.stop_event.is_set():
                    break
                logger.warning(
                    "RabbitMQ connection lost or failed (%s: %s); reconnecting in %.0fs",
                    type(error).__name__,
                    error,
                    backoff,
                )
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                if connection is not None and connection.is_open:
                    try:
                        connection.close()
                    except Exception:  # noqa: BLE001
                        pass
        logger.info("Worker stopped")

    def _consume(self, connection, channel) -> None:
        # inactivity_timeout: wake up every second even with no messages, to
        # notice stop() and refresh the heartbeat.
        for method, _properties, body in channel.consume(QUEUE, inactivity_timeout=1):
            self.heartbeat()
            if self.stop_event.is_set():
                channel.cancel()  # unacked messages go back to the queue
                return
            if method is None:
                continue
            self._process(connection, channel, method.delivery_tag, body)

    def _process(self, connection, channel, delivery_tag, body: bytes) -> None:
        delay = 1.0
        held_since = time.monotonic()
        while True:
            try:
                decision = self._notifier.handle(body)
            except (TemporaryFailure, SetupFailure) as error:
                if isinstance(error, SetupFailure):
                    wait = SETUP_RETRY_SECONDS
                    logger.error(
                        "Telegram setup problem: %s. Check TELEGRAM_BOT_TOKEN and "
                        "TELEGRAM_PIZZERIA_CHAT_ID; retrying in %.0fs, the message waits.",
                        error,
                        wait,
                    )
                elif error.retry_after:
                    # 429: Telegram says how long to wait. Retrying sooner only
                    # earns another 429, so honour it (within the hold limit).
                    wait = min(max(error.retry_after, 1.0), MAX_RETRY_AFTER_SECONDS)
                    logger.warning("Sending failed: %s. Retrying in %.0fs.", error, wait)
                else:
                    wait = delay
                    delay = min(delay * 2, MAX_RETRY_SECONDS)
                    logger.warning("Sending failed: %s. Retrying in %.0fs.", error, wait)

                if time.monotonic() - held_since + wait > MAX_HOLD_SECONDS:
                    logger.warning("Giving the message back to the queue after holding it too long")
                    channel.basic_nack(delivery_tag, requeue=True)
                    return
                if not self._sleep(connection, wait):
                    return  # stopping: the unacked message goes back to the queue
                continue

            if decision is Decision.ACK:
                channel.basic_ack(delivery_tag)
            else:
                channel.basic_nack(delivery_tag, requeue=False)  # to the dead-letter queue
            return

    def _sleep(self, connection, seconds: float) -> bool:
        """Wait while answering RabbitMQ heartbeats. False if stop() was called."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.stop_event.is_set():
                return False
            connection.sleep(min(1.0, max(deadline - time.monotonic(), 0)))
            self.heartbeat()
        return not self.stop_event.is_set()
