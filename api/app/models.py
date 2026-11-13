"""SQLAlchemy models and the order status state machine."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class OrderStatus(str, enum.Enum):
    RECEIVED = "received"
    PREPARING = "preparing"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# An order can only move along these paths. Anything else is a conflict.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.RECEIVED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


class Pizza(Base):
    __tablename__ = "pizzas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    price_cents: Mapped[int] = mapped_column(nullable=False)
    available: Mapped[bool] = mapped_column(default=True, nullable=False)

    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="pizza")


class Order(Base):
    __tablename__ = "orders"
    # Fetch server-generated values (created_at, updated_at) with RETURNING in
    # the same INSERT/UPDATE, instead of a separate SELECT afterwards.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    delivery_address: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(
            OrderStatus,
            name="order_status",
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            create_constraint=True,
            length=20,
        ),
        default=OrderStatus.RECEIVED,
        nullable=False,
    )
    # BIGINT: a large order must not overflow Postgres' 32-bit INTEGER.
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Loading strategy is chosen per query (see _load_order in main.py).
    # order_by keeps the items in the order the customer sent them.
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Postgres does not index foreign keys automatically.
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pizza_id: Mapped[int] = mapped_column(
        ForeignKey("pizzas.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    # Snapshot of the price at the moment the order was placed.
    unit_price_cents: Mapped[int] = mapped_column(nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")
    pizza: Mapped[Pizza] = relationship(back_populates="order_items")

    @property
    def pizza_name(self) -> str:
        return self.pizza.name


class OrderEvent(Base):
    """An event about an order, waiting to be (or already) sent to RabbitMQ.

    This table is the transactional outbox (ADR 0004): the API inserts the
    event in the same transaction that changes the order, so either both are
    saved or neither is. A background relay (app/outbox.py) publishes the rows
    that have no ``published_at`` yet, in ``id`` order, and then fills it in.
    If RabbitMQ is down, the rows wait here.
    """

    __tablename__ = "order_events"

    # BIGINT on Postgres; SQLite only auto-increments an INTEGER primary key.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    # Sent as the AMQP message_id: consumers use it to drop duplicates, since
    # a message can be delivered more than once (at-least-once delivery).
    event_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Also the RabbitMQ routing key: order.created, order.status_changed.
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # The relay only ever looks for unpublished rows: keep that index
        # small by leaving the published ones out of it.
        Index(
            "ix_order_events_unpublished",
            "id",
            postgresql_where=text("published_at IS NULL"),
            sqlite_where=text("published_at IS NULL"),
        ),
    )


class TelegramSubscription(Base):
    """A Telegram chat that asked for updates about one order (ADR 0006).

    The worker creates it when a customer taps "Follow on Telegram" and starts
    the bot. Every later event about the order carries the subscribed chat
    ids, so the worker can message them without a database of its own.
    """

    __tablename__ = "telegram_subscriptions"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Telegram chat ids can exceed 32 bits.
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("order_id", "chat_id", name="uq_telegram_subscription"),)
