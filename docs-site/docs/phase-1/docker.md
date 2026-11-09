---
sidebar_position: 3
---

# Phase 1 — Docker

Phase 1 runs everything with Docker Compose: the API container and a PostgreSQL
16 container.

## Starting the stack

```bash
cp .env.example .env
docker compose up --build -d
```

Check that the API is up and can reach the database:

```bash
curl http://localhost:8000/health
# {"status":"ok","database":"ok"}
```

## Persistence

Database data lives in the named volume `pgdata`. Because of that, stopping the
stack **without** `-v` keeps the orders:

```bash
docker compose down
docker compose up -d
```

The order you created before `down` is still available afterwards. Using
`docker compose down -v` deletes the volume and with it all data.

## Seeding

On startup the API creates the schema and seeds the menu if it is empty, so
restarting the stack does not duplicate pizzas.
