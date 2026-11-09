"""Pydantic schemas for requests and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import OrderStatus


class PizzaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    price_cents: int
    available: bool


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=30)
    address: str = Field(min_length=1, max_length=255)


class OrderItemIn(BaseModel):
    pizza_id: int
    quantity: int = Field(ge=1, le=50)


class OrderCreate(BaseModel):
    customer: CustomerIn
    items: list[OrderItemIn] = Field(min_length=1)


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
