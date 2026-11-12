# Orders API

A **Python + FastAPI** API that serves the menu and receives the pizzeria's orders. It stores everything in **PostgreSQL** (SQLite is used only by the tests and, if you ask for it explicitly, for a quick local run).

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

To run only the API on your machine (with auto-reload), against the Postgres from Docker Compose:

```bash
docker compose up -d db          # from the repository root: only the database
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

set -a; source ../.env; set +a   # load POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
export POSTGRES_HOST=localhost   # Compose publishes Postgres on 127.0.0.1
export POSTGRES_PORT=${POSTGRES_HOST_PORT:-5432}
uvicorn app.main:app --reload
```

If you already run Postgres on port 5432, `docker compose up` fails with "port is already allocated". Set another port in `.env`, for example `POSTGRES_HOST_PORT=5433`.

For a quick run without Postgres, use SQLite explicitly:

```bash
DATABASE_URL=sqlite:///./slicepizza.db uvicorn app.main:app --reload
```

The API refuses to start if no database is configured, instead of silently writing somewhere unexpected.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use an in-memory SQLite database (see `tests/conftest.py`), so they need neither Docker nor Postgres.

To run the same tests against Postgres (CI does both):

```bash
docker run -d --name slicepizza-test-db -p 127.0.0.1:5433:5432 \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=slicepizza_test \
  postgres:16-alpine
TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:5433/slicepizza_test pytest
docker rm -f slicepizza-test-db
```

The tests drop all tables, so `tests/conftest.py` protects your data:

- they read only `TEST_DATABASE_URL`, never `DATABASE_URL` or the `POSTGRES_*` variables (it clears them);
- an empty `TEST_DATABASE_URL` means SQLite;
- a Postgres database must have `test` in its name, or the tests refuse to run.

The concurrency tests (two requests changing the same order at once) need Postgres row locks, so they only run against Postgres.

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
│   ├── conftest.py        # test database setup and safety checks
│   ├── test_api.py        # routes, status flow, concurrency
│   ├── test_validation.py # invalid input → 422
│   ├── test_errors.py     # database errors → 503 or 500
│   ├── test_config.py     # environment variables
│   └── test_startup.py    # schema creation and menu seed
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```

## Environment variables

| Variable | Purpose | Example |
|---|---|---|
| `POSTGRES_HOST` | Postgres host | `db` (Compose) or `localhost` |
| `POSTGRES_PORT` | Postgres port (optional, default `5432`) | `5432` |
| `POSTGRES_USER` | Database user | `slicepizza` |
| `POSTGRES_PASSWORD` | Database password (optional), any characters, no encoding needed | `p@ss:w/rd` |
| `POSTGRES_DB` | Database name | `slicepizza` |
| `DATABASE_URL` | Optional full URL; takes precedence over the variables above | `sqlite:///./slicepizza.db` |

Docker Compose sets the `POSTGRES_*` variables from the root `.env`. The parts are passed separately, never pasted into a URL, so the password needs no URL-encoding.

`DATABASE_URL` and `TEST_DATABASE_URL` **are** URLs: special characters in their password must be percent-encoded (`@` → `%40`, `:` → `%3A`, `/` → `%2F`, `#` → `%23`, `%` → `%25`). Prefer the `POSTGRES_*` variables when the password has such characters.

Compose-only variable (root `.env`): `POSTGRES_HOST_PORT`, the port on your machine where Postgres is published (default `5432`).

## Schema note

The tables are created on startup with `Base.metadata.create_all()` and the menu is seeded if the `pizzas` table is empty. This is deliberate for Phase 1; see [ADR 0002](../docs/adr/0002-sqlalchemy-and-schema-creation.md). Migrations (Alembic) arrive when the schema starts to change in production.

`create_all()` only creates **missing** tables: it never changes a table that already exists. If you pull a change to `models.py` (a new column, index or type) and your database volume is older, the change is not applied. Until Alembic arrives, recreate the local database (this deletes its data):

```bash
docker compose down -v
docker compose up --build -d --wait
```
