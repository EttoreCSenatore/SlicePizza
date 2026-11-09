"""Orders API: menu, orders and order status updates."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from .database import Base, SessionLocal, engine, get_db
from .models import ALLOWED_TRANSITIONS, Order, OrderItem, OrderStatus, Pizza
from .schemas import OrderCreate, OrderOut, OrderStatusUpdate, PizzaOut
from .seed import seed_menu


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1 keeps the schema simple: create the tables on startup and seed
    # the menu. Migrations (Alembic) arrive when the schema starts to evolve.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_menu(db)
    yield


app = FastAPI(
    title="SlicePizza Orders API",
    description="Menu and orders for Zé's Pizzeria.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(OperationalError)
async def database_unavailable(
    request: Request, exc: OperationalError
) -> JSONResponse:
    """Return 503 instead of 500 when the database cannot be reached."""
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


def _load_order(db: Session, order_id: str) -> Order:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).selectinload(OrderItem.pizza))
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    """Report whether the API can reach the database."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ok", "database": "ok"}


@app.get("/menu", response_model=list[PizzaOut])
def get_menu(db: Session = Depends(get_db)) -> list[Pizza]:
    """List the pizzas on the menu."""
    return list(db.scalars(select(Pizza).order_by(Pizza.id)))


@app.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)) -> Order:
    """Create an order, pricing it from the menu in the database."""
    pizza_ids = {item.pizza_id for item in payload.items}
    pizzas = {
        pizza.id: pizza
        for pizza in db.scalars(select(Pizza).where(Pizza.id.in_(pizza_ids)))
    }

    missing = sorted(pizza_ids - pizzas.keys())
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Pizza(s) not found: {missing}",
        )

    unavailable = sorted(
        pizza.name for pizza in pizzas.values() if not pizza.available
    )
    if unavailable:
        raise HTTPException(
            status_code=409,
            detail=f"Pizza(s) unavailable: {unavailable}",
        )

    order = Order(
        customer_name=payload.customer.name,
        customer_phone=payload.customer.phone,
        delivery_address=payload.customer.address,
        status=OrderStatus.RECEIVED,
        total_cents=sum(
            pizzas[item.pizza_id].price_cents * item.quantity
            for item in payload.items
        ),
    )
    for item in payload.items:
        pizza = pizzas[item.pizza_id]
        order.items.append(
            OrderItem(
                pizza=pizza,
                quantity=item.quantity,
                unit_price_cents=pizza.price_cents,
            )
        )

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: Session = Depends(get_db)) -> Order:
    """Get a single order and its items."""
    return _load_order(db, order_id)


@app.patch("/orders/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
) -> Order:
    """Move an order to the next status.

    Allowed path: received -> preparing -> out_for_delivery -> delivered,
    and received -> cancelled. Repeating the current status is a no-op.
    """
    order = _load_order(db, order_id)

    if payload.status == order.status:
        return order

    allowed = ALLOWED_TRANSITIONS[order.status]
    if payload.status not in allowed:
        allowed_names = ", ".join(sorted(s.value for s in allowed)) or "none"
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot change status from '{order.status.value}' "
                f"to '{payload.status.value}'. Allowed: {allowed_names}"
            ),
        )

    order.status = payload.status
    db.commit()
    db.refresh(order)
    return order
