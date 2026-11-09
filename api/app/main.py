"""Orders API: menu, orders and order status updates."""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from .database import Base, SessionLocal, engine, get_db, wait_for_database
from .models import ALLOWED_TRANSITIONS, Order, OrderItem, OrderStatus, Pizza
from .schemas import OrderCreate, OrderOut, OrderStatusUpdate, PizzaOut
from .seed import seed_menu

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1 keeps the schema simple: create the tables on startup and seed
    # the menu. Migrations (Alembic) arrive when the schema starts to evolve.
    wait_for_database()
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


# SQLSTATE codes that mean "cannot talk to the server", as opposed to a bug,
# a deadlock or a timeout: class 08 (connection exception), admin shutdown,
# crash shutdown and "the database system is starting up".
_UNAVAILABLE_SQLSTATES = ("08", "57P01", "57P02", "57P03")


def is_database_unavailable(exc: OperationalError) -> bool:
    """True only when the error means the database cannot be reached."""
    if exc.connection_invalidated:
        return True
    if not hasattr(exc.orig, "sqlstate"):
        # Not a psycopg error (e.g. SQLite in the tests): a real error.
        return False
    sqlstate = exc.orig.sqlstate
    # No SQLSTATE: the server never answered (refused, DNS, timeout).
    return sqlstate is None or sqlstate.startswith(_UNAVAILABLE_SQLSTATES)


@app.exception_handler(OperationalError)
async def database_error(request: Request, exc: OperationalError) -> JSONResponse:
    """Return 503 when the database is unreachable, 500 for anything else."""
    if is_database_unavailable(exc):
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


def _load_order(db: Session, order_id: uuid.UUID) -> Order:
    order = db.scalar(
        select(Order)
        .where(Order.id == str(order_id))
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
    # The INSERT ... RETURNING already fills created_at/updated_at, and the
    # items and pizzas are in memory, so no refresh is needed.
    db.commit()
    return order


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)) -> Order:
    """Get a single order and its items."""
    return _load_order(db, order_id)


@app.patch("/orders/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: uuid.UUID,
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

    # Compare-and-set: only write if the status is still the one we checked.
    # Two simultaneous requests cannot both pass, because the second UPDATE
    # matches zero rows once the first has committed.
    result = db.execute(
        update(Order)
        .where(Order.id == order.id, Order.status == order.status)
        .values(status=payload.status)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The order status was changed by another request. "
            "Fetch the order and try again.",
        )
    db.commit()
    db.refresh(order, attribute_names=["status", "updated_at"])
    return order
