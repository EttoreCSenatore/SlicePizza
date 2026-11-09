---
sidebar_position: 2
---

# Phase 1 — API

The Orders API is a small FastAPI application that talks to PostgreSQL through
SQLAlchemy 2.0.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Health check that also pings the database |
| `GET` | `/menu` | Returns the seeded pizzas |
| `POST` | `/orders` | Creates an order, pricing items from the database |
| `GET` | `/orders/{id}` | Fetches a single order |
| `PATCH` | `/orders/{id}/status` | Advances the order status |

## Creating an order

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
      { "pizza_id": 1, "quantity": 2 }
    ]
  }'
```

Prices are stored in cents, and each order item keeps a snapshot of the unit
price at the time the order was created.

## Status flow

`received` → `preparing` → `out_for_delivery` → `delivered`

Skipping a step returns `409 Conflict`.

## Tests

```bash
cd api
pip install -r requirements-dev.txt
pytest
```

The suite runs against an in-memory SQLite database, so no Docker is needed.
