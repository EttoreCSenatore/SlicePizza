"""Routes for the notification worker only (ADR 0006).

They live under /internal and are:

- **off** unless INTERNAL_API_TOKEN is set: they answer 404 as if they did not
  exist;
- **protected** by that token, sent as ``Authorization: Bearer <token>``;
- **not public**: the web container (Caddy) answers 404 to /api/internal/*
  before it reaches the API, so only containers on the project network (the
  worker) can call them. The token still applies, in case the API's port is
  ever exposed.

They are left out of the OpenAPI schema (/docs).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from .auth import bearer_matches, unauthorized
from .config import settings
from .database import get_db
from .models import Order, OrderItem, TelegramSubscription

# Telegram chat ids fit in a signed 64-bit integer (they use up to 52 bits).
MIN_CHAT_ID = -(2**63)
MAX_CHAT_ID = 2**63 - 1
# A customer, a partner, a phone and a laptop... more is not a real case.
MAX_SUBSCRIPTIONS_PER_ORDER = 10


def require_worker(authorization: str | None = Header(default=None)) -> None:
    token = settings.internal_api_token
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not bearer_matches(authorization, token):
        raise unauthorized()


router = APIRouter(
    prefix="/internal",
    include_in_schema=False,
    dependencies=[Depends(require_worker)],
)


class SubscriptionOut(BaseModel):
    order_id: str
    status: str
    # False when this chat already followed the order (the call is idempotent).
    created: bool


ChatId = Annotated[int, Path(ge=MIN_CHAT_ID, le=MAX_CHAT_ID)]


@router.put("/orders/{order_id}/telegram-subscriptions/{chat_id}", response_model=SubscriptionOut)
def subscribe(
    order_id: uuid.UUID,
    chat_id: ChatId,
    db: Session = Depends(get_db),
) -> SubscriptionOut:
    """Make a Telegram chat follow an order. Returns the order's current status.

    The order row is locked, like a status change: a change that commits first
    has its event sent without this chat, so the worker tells the customer the
    status returned here; one that commits after includes the chat.
    """
    order = db.scalar(
        select(Order)
        .where(Order.id == str(order_id))
        .options(selectinload(Order.items).selectinload(OrderItem.pizza))
        .with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    existing = db.scalar(
        select(TelegramSubscription).where(
            TelegramSubscription.order_id == order.id, TelegramSubscription.chat_id == chat_id
        )
    )
    created = existing is None
    if created:
        count = db.scalar(
            select(func.count()).select_from(TelegramSubscription).where(TelegramSubscription.order_id == order.id)
        )
        if count >= MAX_SUBSCRIPTIONS_PER_ORDER:
            raise HTTPException(status_code=409, detail="Too many chats follow this order")
        db.add(TelegramSubscription(order_id=order.id, chat_id=chat_id))
    db.commit()
    return SubscriptionOut(order_id=order.id, status=order.status.value, created=created)


class UnsubscribeOut(BaseModel):
    removed: int


@router.delete("/telegram-subscriptions/{chat_id}", response_model=UnsubscribeOut)
def unsubscribe_chat(chat_id: ChatId, db: Session = Depends(get_db)) -> UnsubscribeOut:
    """Stop all updates to a chat (the customer sent /stop to the bot)."""
    result = db.execute(delete(TelegramSubscription).where(TelegramSubscription.chat_id == chat_id))
    db.commit()
    return UnsubscribeOut(removed=result.rowcount)
