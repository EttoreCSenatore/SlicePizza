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

Behind the `web` container (Caddy, see [ADR 0003](../docs/adr/0003-one-domain-caddy-in-front.md)) every route is also served under **`/api`**: `https://slicepizza.senatore.tech/api/menu`, or `http://localhost:8080/api/menu` with Docker Compose. Caddy removes the prefix, so the API itself keeps the routes above.

Interactive docs: `http://localhost:8080/api/docs` with Docker Compose. The API runs there with `UVICORN_ROOT_PATH=/api`, so the docs page asks for its schema at `/api/openapi.json`; that is why `http://localhost:8000/docs` cannot load it. When you run Uvicorn yourself (below), without that variable, the docs are at `http://localhost:8000/docs`.

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

**Always send `Content-Type: application/json`** with a JSON body (`POST` and `PATCH`). Without it the API does not read the body as JSON and answers `422 Input should be a valid dictionary or object`. A browser `fetch()` with `body: JSON.stringify(...)` and no header sends `text/plain`, so the header must be set explicitly.

Prices come from the `pizzas` table, never from the request, and are stored in **cents** (`price_cents`, `total_cents`) to avoid floating-point rounding. Each order item keeps a snapshot of the price at the time of the order.

### Order status

```
received ──► preparing ──► out_for_delivery ──► delivered
    │
    └──► cancelled
```

Skipping a step returns `409 Conflict`. Repeating the current status is a no-op.

### Calling the API from a browser (CORS)

A browser only lets a page call an API on **another origin** (another domain, or another port) if the API says that origin is allowed. When the page and the API share an origin, nothing is needed. Otherwise, list the allowed origins in **`CORS_ORIGINS`**, comma-separated:

```bash
CORS_ORIGINS=https://www.yourdomain.com,http://localhost:8080
```

- Each entry is `scheme://host[:port]`, with **no path and no trailing slash** (`https://www.yourdomain.com/` never matches what the browser sends, so the API refuses to start with it).
- `*` is refused: the API stores customers' names, phones and addresses, so only the project's own sites may call it.
- Unset or empty means no browser on another domain can call the API. `curl`, scripts and other servers are not affected: CORS is enforced by browsers only.
- Each entry is rewritten the way browsers send it: lowercase, without the default port (`https://x.com:443` becomes `https://x.com`) and with a non-ASCII domain in punycode (`bücher.de` becomes `xn--bcher-kva.de`).
- Allowed methods: `GET`, `POST`, `PATCH`. Allowed request headers: `Content-Type`, plus `Accept`, `Accept-Language` and `Content-Language`, which Starlette always allows. No cookies.
- Error responses, including an unexpected `500`, carry the CORS header too, so the page can read the API's status and message.

For example, to serve the site with `python3 -m http.server 8080` while the API runs on port 8000, start the API with `CORS_ORIGINS=http://localhost:8080`. With Docker Compose, put the line in `.env`; `docker-compose.yml` passes it to the `api` container.

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
pip install --require-hashes -r requirements-dev.txt

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
pip install --require-hashes -r requirements-dev.txt
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
├── scripts/
│   └── compile-requirements.sh  # regenerates the lock files
├── Dockerfile
├── requirements.in        # direct dependencies, as version ranges (edit this)
├── requirements.txt       # lock file generated from it (never edit by hand)
├── requirements-dev.in    # test dependencies (edit this)
└── requirements-dev.txt   # lock file generated from it (never edit by hand)
```

## Dependencies

Two kinds of files:

| File | What it has | Who edits it |
|---|---|---|
| `requirements.in`, `requirements-dev.in` | The packages the API and the tests use **directly**, as version ranges (`fastapi>=0.162.2,<1.0`) | You, or Dependabot |
| `requirements.txt`, `requirements-dev.txt` | **Every** package, direct or not, pinned to **one version**, with the sha256 **hashes** of its files | Generated by [pip-compile](https://pip-tools.readthedocs.io/) |

The image and CI install with `pip install --require-hashes --only-binary=:all:`:

- **Same versions on every build.** Without a lock file, every build installed the newest version inside each range, so a package released minutes earlier reached production on the next merge, with no PR and no review ([issue #23](https://github.com/SenatoreTeam/SlicePizza/issues/23)). Now a new version only arrives through a PR that changes the lock file, after Dependabot's 7-day cooldown.
- **`--require-hashes`**: if a downloaded file does not match a hash in the lock file (a replaced release, a compromised mirror), or a package is not in the lock file at all, the install fails.
- **`--only-binary=:all:`**: only prebuilt wheels, nothing compiled from source. Compiling would download build tools (setuptools, Cython…) that pip does **not** hash-check. If a future version has no wheel for the image's Python, the build fails and says so: then decide in a PR whether to wait for the wheel or allow that one package.

The lock files are generated with the image's Python (3.15), on Linux. On Windows, `uvloop` is skipped (it does not exist there); everything else is the same.

### Adding, removing or updating a package

Edit the `.in` file, then regenerate the lock files **with the image's Python**. From `api/`:

```bash
# After editing requirements.in or requirements-dev.in:
docker run --rm -v "$PWD":/api -w /api python:3.15-slim scripts/compile-requirements.sh

# Update one package to the newest version its range allows:
docker run --rm -v "$PWD":/api -w /api python:3.15-slim scripts/compile-requirements.sh --upgrade-package fastapi
```

Commit the `.in` and the `.txt` files together. pip-compile keeps every version already in the lock files and only resolves what changed, so the diff shows exactly what moved. CI regenerates the lock files and fails if they differ from the committed ones.

Usually you don't do this by hand: **Dependabot** reads the `.in` files, proposes new versions once a week (each at least 7 days old), and its PRs regenerate the lock files.

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
