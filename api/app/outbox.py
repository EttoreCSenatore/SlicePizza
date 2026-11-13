"""Outbox relay: publishes the events in ``order_events`` to RabbitMQ (ADR 0004).

A background thread in the API process:

1. Takes the oldest unpublished events (``published_at IS NULL``), in ``id``
   order, at most ``BATCH_SIZE`` at a time.
2. Publishes each one, persistent, and waits for RabbitMQ to confirm it.
3. Marks it published.

If RabbitMQ is down, or no queue is bound for an event (RabbitMQ would drop
it), the relay stops at that event and tries again later, with a growing
pause. Nothing is lost, and the order of events is kept: an event is never
published before an older one.

Delivery is **at least once**: if the API stops between "RabbitMQ confirmed"
and "marked published", the event is sent again on restart. Consumers drop
duplicates by ``message_id`` (the event's ``event_id``).

Only one relay publishes at a time, even with several API processes: on
Postgres each round takes a transaction-level advisory lock, and a process
that does not get it skips the round.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .events import EXCHANGE, message_body
from .models import OrderEvent

logger = logging.getLogger(__name__)

# The relay logs one line per failure (see OutboxRelay._run). pika's own logs
# would repeat it as several ERRORs with a traceback on every retry while
# RabbitMQ is down, and its warning for a returned (unroutable) message
# includes the start of the body, which has the customer's name.
logging.getLogger("pika").setLevel(logging.CRITICAL)

BATCH_SIZE = 100
# How often the relay looks for new events when nobody wakes it up. After a
# commit the API wakes it at once (OutboxRelay.wake), so this is a fallback.
POLL_SECONDS = 1.0
# Pause after a failure: 1 s, then doubling, up to MAX_BACKOFF_SECONDS.
MAX_BACKOFF_SECONDS = 30.0
# Any constant works, as long as nothing else in the database uses it.
ADVISORY_LOCK_ID = 0x51ACE_0B0  # "slice outbox"


class PublishError(Exception):
    """The event could not be published; it stays in the outbox."""


class Publisher(Protocol):
    def publish(self, event: OrderEvent) -> None:
        """Publish ``event`` and return once the broker has accepted it.

        Raise ``PublishError`` (or any exception) otherwise.
        """

    def close(self) -> None: ...


def publish_pending(db: Session, publisher: Publisher, batch_size: int = BATCH_SIZE) -> int:
    """Publish up to ``batch_size`` pending events, oldest first.

    Returns how many were published. Stops at the first failure and re-raises
    it, after committing the ones already published, so they are not sent again.
    """
    if db.get_bind().dialect.name == "postgresql":
        got_lock = db.scalar(text("SELECT pg_try_advisory_xact_lock(:id)"), {"id": ADVISORY_LOCK_ID})
        if not got_lock:
            db.rollback()
            return 0

    events = db.scalars(
        select(OrderEvent)
        .where(OrderEvent.published_at.is_(None))
        .order_by(OrderEvent.id)
        .limit(batch_size)
    ).all()

    published = 0
    try:
        for event in events:
            publisher.publish(event)
            event.published_at = datetime.now(UTC)
            published += 1
    finally:
        # Also on failure: keep the ones RabbitMQ already confirmed.
        db.commit()
    return published


class RabbitMQPublisher:
    """Publishes events to the ``slicepizza.events`` topic exchange with pika.

    - Declares the exchange (durable), so the API can publish before any
      consumer exists. Queues are declared by the consumers.
    - Publisher confirms: ``publish`` returns only after RabbitMQ accepted the
      message.
    - ``mandatory``: if no queue is bound for the routing key, RabbitMQ returns
      the message instead of dropping it, and ``publish`` fails. The event
      stays in the outbox until a consumer has declared its queue.
    - Persistent messages (delivery_mode 2): they survive a broker restart in
      a durable queue.
    """

    def __init__(self, settings) -> None:
        import pika  # imported here so the API starts without it when RabbitMQ is off

        self._pika = pika
        params = pika.ConnectionParameters(
            host=settings.host,
            port=settings.port,
            virtual_host=settings.vhost,
            credentials=pika.PlainCredentials(settings.user, settings.password),
            heartbeat=60,
            blocked_connection_timeout=30,
            connection_attempts=1,
            socket_timeout=5,
            client_properties={"connection_name": "slicepizza-api outbox relay"},
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        self._channel.confirm_delivery()

    def publish(self, event: OrderEvent) -> None:
        pika = self._pika
        try:
            self._channel.basic_publish(
                exchange=EXCHANGE,
                routing_key=event.type,
                body=json.dumps(message_body(event)).encode(),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent,
                    message_id=event.event_id,
                    type=event.type,
                    app_id="slicepizza-api",
                    timestamp=int(event.created_at.timestamp()) if event.created_at else None,
                ),
                mandatory=True,
            )
        except pika.exceptions.UnroutableError as error:
            raise PublishError(
                f"No queue is bound to {EXCHANGE!r} for {event.type!r}; "
                "start a consumer (the worker) to create one"
            ) from error
        except pika.exceptions.NackError as error:
            raise PublishError(f"RabbitMQ refused event {event.event_id}") from error

    def keep_alive(self) -> None:
        """Answer heartbeats while idle, so RabbitMQ keeps the connection."""
        self._connection.process_data_events(time_limit=0)

    def close(self) -> None:
        try:
            if self._connection.is_open:
                self._connection.close()
        except Exception:  # noqa: BLE001 - closing a broken connection
            pass


def _describe(error: BaseException) -> str:
    """Error name and message; pika's connection errors often have no message."""
    message = str(error).strip()
    if not message and error.__cause__ is not None:
        message = str(error.__cause__).strip()
    if not message and error.args:
        message = repr(error.args)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


class OutboxRelay:
    """Runs ``publish_pending`` in a background thread until ``stop()``."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        publisher_factory: Callable[[], Publisher],
        poll_seconds: float = POLL_SECONDS,
        max_backoff_seconds: float = MAX_BACKOFF_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._publisher_factory = publisher_factory
        self._poll_seconds = poll_seconds
        self._max_backoff = max_backoff_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="outbox-relay", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def wake(self) -> None:
        """Publish now instead of at the next poll (called after a commit)."""
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout)

    def _run(self) -> None:
        publisher: Publisher | None = None
        backoff = 1.0
        while not self._stop.is_set():
            try:
                if publisher is None:
                    publisher = self._publisher_factory()
                    logger.info("Outbox relay connected to RabbitMQ")
                with self._session_factory() as db:
                    count = publish_pending(db, publisher)
                if count:
                    logger.info("Published %d order event(s)", count)
                backoff = 1.0
                if count == BATCH_SIZE:
                    continue  # more may be waiting
                if hasattr(publisher, "keep_alive"):
                    publisher.keep_alive()
                self._wake.wait(self._poll_seconds)
                self._wake.clear()
            except Exception as error:  # noqa: BLE001 - the relay must keep running
                logger.warning(
                    "Outbox relay: %s. Retrying in %.0fs; events wait in order_events.",
                    _describe(error),
                    backoff,
                )
                # A refused event or a database error leaves the RabbitMQ
                # connection usable; anything else (connection lost) starts
                # over with a new one.
                if publisher is not None and not isinstance(error, (PublishError, SQLAlchemyError)):
                    publisher.close()
                    publisher = None
                self._stop.wait(backoff)
                backoff = min(backoff * 2, self._max_backoff)
        if publisher is not None:
            publisher.close()
