# Orders API

A **Python + FastAPI** API that serves the menu and receives the pizzeria's orders. It stores everything in **PostgreSQL** (SQLite is used only for local development without Docker and for the tests).

## Routes

| Method | Route | What it does |
|---|---|---|
| GET | `/health` | Checks the API and the database connection |
| GET | `/menu` | Lists the pizzas |
| POST | `/orders` | Creates an order |
| GET | `/orders/{id}` | Gets an order |
| PATCH | `/orders/{id}/status` | Changes an order's status |

Interactive docs are available at `http://localhost:8000/docs`.

### Creating an order

```bash
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer": {
      "name": "Maria",
      "phone": "+55 11 98888-7777",
      "address": "Av. Paulista, 100"
    },
    "items": [
      { "pizza_id": 1, "quantity": 2 },
      { "pizza_id": 4, "quantity": 1 }
    ]
  }'
```

Prices come from the `pizzas` table, never from the request, and are stored in **cents** (`price_cents`, `total_cents`) to avoid floating-point rounding. Each order item keeps a snapshot of the price at the time of the order.

### Order status

```
received ──► preparing ──► out_for_delivery ──► delivered
    │
    └──► cancelled
```

Skipping a step returns `409 Conflict`. Repeating the current status is a no-op.

## Running

The recommended way is Docker Compose, from the repository root:

```bash
cp .env.example .env
docker compose up --build
```

See the [root README](../README.md#getting-started).

To run only the API locally (SQLite fallback):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Set `DATABASE_URL` to point at Postgres when running locally, for example:

```bash
export DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/slicepizza
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use an in-memory SQLite database (see `tests/conftest.py`), so they need neither Docker nor Postgres.

## Structure

```
api/
├── app/
│   ├── main.py        # FastAPI app and routes
│   ├── config.py      # settings from environment variables
│   ├── database.py    # engine, session and get_db dependency
│   ├── models.py      # SQLAlchemy models and status transitions
│   ├── schemas.py     # Pydantic request/response schemas
│   └── seed.py        # default menu
├── tests/
│   ├── conftest.py
│   └── test_api.py
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```

## Environment variables

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | Database connection | `postgresql+psycopg://user:password@db:5432/slicepizza` |

When running through Docker Compose, `DATABASE_URL` is built from `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` in the root `.env`.

## Schema note

The tables are created on startup with `Base.metadata.create_all()` and the menu is seeded if the `pizzas` table is empty. This is deliberate for Phase 1; see [ADR 0002](../docs/adr/0002-sqlalchemy-and-schema-creation.md). Migrations (Alembic) arrive when the schema starts to change in production.
