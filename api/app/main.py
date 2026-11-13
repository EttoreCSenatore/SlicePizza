"""Orders API: menu, orders and order status updates."""

import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .database import Base, SessionLocal, engine, get_db, wait_for_database
from .models import ALLOWED_TRANSITIONS, Order, OrderItem, OrderStatus, Pizza
from .schemas import OrderCreate, OrderOut, OrderStatusUpdate, PizzaOut
from .seed import seed_menu

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1 keeps the schema simple: create the tables on startup and seed
    # the menu. Migrations (Alembic) arrive when the schema starts to evolve.
    await wait_for_database()
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


class UnhandledErrorAsJSON:
    """Turn an unhandled exception into a JSON 500 *inside* CORSMiddleware.

    Starlette answers unhandled exceptions in ServerErrorMiddleware, which sits
    outside every middleware added here, so its 500 would carry no CORS
    header and the browser would report a CORS error instead of the 500.
    Added before CORSMiddleware, this one runs inside it.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_and_track(message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_and_track)
        except Exception:
            if response_started:
                raise  # too late to send another response
            logger.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
            await response(scope, receive, send)


if settings.cors_origins:
    # Off by default: in production the site and the API share one origin
    # (ADR 0003), so browsers need no CORS. CORS_ORIGINS is for a site served
    # from another origin, e.g. a local `python3 -m http.server 8080` against
    # the API on port 8000. Browsers then send an OPTIONS preflight before
    # every POST and PATCH that carries JSON, and only the configured origins
    # get an answer. No cookies are used, so credentials stay disabled.
    #
    # Middleware added last runs first: CORSMiddleware wraps
    # UnhandledErrorAsJSON, so even a 500 carries the CORS header.
    app.add_middleware(UnhandledErrorAsJSON)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        # Starlette always allows the CORS-safelisted Accept, Accept-Language,
        # Content-Language and Content-Type; listed here to make the intent
        # explicit, since every POST and PATCH sends application/json.
        allow_headers=["Content-Type"],
        max_age=600,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> Response:
    """Same 422 body as FastAPI's default handler, but JSON-escaped as ASCII.

    The error echoes the invalid input back. If that input is not valid
    Unicode (e.g. a lone surrogate "\\ud800"), the default handler crashes
    while encoding its own response and returns 500. ASCII-escaped JSON
    ("\\u00e9" instead of "é") is equivalent for any JSON client.
    """
    body = json.dumps({"detail": jsonable_encoder(exc.errors())}, ensure_ascii=True)
    return Response(content=body, status_code=422, media_type="application/json")


# SQLSTATE codes that mean "cannot talk to the server", as opposed to a bug,
# a deadlock or a timeout: class 08 (connection exception), admin shutdown,
# crash shutdown and "the database system is starting up".
# Note: errors raised while *connecting* (refused, timeout, DNS, wrong password,
# unknown database, too many connections) carry no SQLSTATE at all.
_UNAVAILABLE_SQLSTATES = ("08", "57P01", "57P02", "57P03")


def is_database_unavailable(exc: OperationalError) -> bool:
    """True only when the error means the database cannot be reached."""
    if exc.connection_invalidated:
        return True
    if not hasattr(exc.orig, "sqlstate"):
        # Not a psycopg error (e.g. SQLite in the tests): a real error.
        return False
    sqlstate = exc.orig.sqlstate
    # No SQLSTATE: the connection could not be established (see above).
    return sqlstate is None or sqlstate.startswith(_UNAVAILABLE_SQLSTATES)


@app.exception_handler(OperationalError)
async def database_error(request: Request, exc: OperationalError) -> JSONResponse:
    """Return 503 when the database is unreachable, 500 for anything else."""
    if is_database_unavailable(exc):
        # Log the cause: "unavailable" can also mean a wrong password or an
        # unknown database, which nobody could diagnose from the 503 alone.
        logger.warning(
            "Database unavailable on %s %s: %s",
            request.method,
            request.url.path,
            exc.orig,
        )
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


def _load_order(db: Session, order_id: uuid.UUID, for_update: bool = False) -> Order:
    query = (
        select(Order)
        .where(Order.id == str(order_id))
        .options(selectinload(Order.items).selectinload(OrderItem.pizza))
    )
    if for_update:
        # SELECT ... FOR UPDATE: lock the order row until this transaction
        # ends. (SQLite has no row locks; it is only used for dev and tests.)
        query = query.with_for_update()
    order = db.scalar(query)
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

    The order row is locked while we check and change it, so concurrent
    requests for the same order run one after the other: each one sees the
    status the previous one committed. Two identical requests both get 200,
    and two conflicting ones get 200 and 409.
    """
    order = _load_order(db, order_id, for_update=True)

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
    # The UPDATE returns the new updated_at (eager_defaults on Order), so the
    # response shows exactly what this request wrote, with no extra SELECT.
    db.commit()
    return order
