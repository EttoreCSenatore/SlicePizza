"""Pydantic schemas for requests and responses."""

from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from .models import OrderStatus

# Postgres INTEGER is 32-bit; larger ids can never exist and would crash the query.
INT32_MAX = 2_147_483_647
MAX_ITEMS_PER_ORDER = 20
MAX_PIZZAS_PER_ORDER = 50


def _reject_nul(value: str) -> str:
    # Postgres text columns cannot store the NUL character.
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


# Trimmed, non-empty text without NUL characters. "   " is rejected.
CleanText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
    AfterValidator(_reject_nul),
]


class PizzaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    price_cents: int
    available: bool


class CustomerIn(BaseModel):
    name: CleanText = Field(max_length=120)
    phone: CleanText = Field(max_length=30)
    address: CleanText = Field(max_length=255)


class OrderItemIn(BaseModel):
    pizza_id: int = Field(ge=1, le=INT32_MAX)
    quantity: int = Field(ge=1, le=MAX_PIZZAS_PER_ORDER)


class OrderCreate(BaseModel):
    customer: CustomerIn
    items: list[OrderItemIn] = Field(min_length=1, max_length=MAX_ITEMS_PER_ORDER)

    @model_validator(mode="after")
    def check_items(self) -> "OrderCreate":
        pizza_ids = [item.pizza_id for item in self.items]
        if len(pizza_ids) != len(set(pizza_ids)):
            raise ValueError(
                "Each pizza can appear only once; use 'quantity' to order more of it."
            )

        total = sum(item.quantity for item in self.items)
        if total > MAX_PIZZAS_PER_ORDER:
            raise ValueError(
                f"An order can have at most {MAX_PIZZAS_PER_ORDER} pizzas (got {total})."
            )
        return self


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pizza_id: int
    pizza_name: str
    quantity: int
    unit_price_cents: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_name: str
    customer_phone: str
    delivery_address: str
    status: OrderStatus
    total_cents: int
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]
