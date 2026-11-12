"""SQLAlchemy models and the order status state machine."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, String, func
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
