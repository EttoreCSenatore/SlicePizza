# Phase 1 — Docker

Phase 1 runs everything with Docker Compose: the API container and a PostgreSQL
16 container. The step-by-step commands are in the
[root README](../../../README.md#running-the-system-phase-1); this page explains
what happens behind them.

## Starting the stack

```bash
cp .env.example .env
docker compose up --build -d --wait
```

Compose starts the containers in order:

1. **Postgres** starts first. Its healthcheck (`pg_isready`) reports healthy
   once it accepts connections.
2. **The API** starts only after that, because of
   `depends_on: condition: service_healthy`. On startup it creates the tables,
   seeds the menu and then opens port 8000.

Without `--wait`, `up -d` returns as soon as the API container has *started*,
while it may still be creating tables or seeding the menu, so an immediate
`curl` can fail. `--wait` returns only when the API's own healthcheck passes.

Check that the API is up and can reach the database:

```bash
curl http://localhost:8000/health
# {"status":"ok","database":"ok"}
```

## Ports

| Service | On your machine | Configurable with |
|---|---|---|
| API | `127.0.0.1:8000` | — |
| Postgres | `127.0.0.1:5432` | `POSTGRES_HOST_PORT` in `.env` |

Both are bound to `127.0.0.1` only, so they are not exposed to your network.
If you already run PostgreSQL on your machine, `docker compose up` fails with
**"port is already allocated"**: set another port in `.env`, for example
`POSTGRES_HOST_PORT=5433`.

## Persistence

Database data lives in the named volume `slicepizza_pgdata` (Compose prefixes
the `pgdata` volume with the project name, `slicepizza`). Because of that,
stopping the stack **without** `-v` keeps the orders:

```bash
docker compose down
docker compose up -d --wait
```

To inspect the volume: `docker volume inspect slicepizza_pgdata`.

`docker compose down -v` deletes the volume and with it all data. You need it
when the database schema changes: the API creates missing tables on startup,
but it never changes a table that already exists.

## Seeding

On startup the API seeds the menu only if the `pizzas` table is empty, so
restarting the stack does not duplicate pizzas.
