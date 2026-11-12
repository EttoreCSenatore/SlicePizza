# Phase 1 — API

The Orders API is a small FastAPI application that talks to PostgreSQL through
SQLAlchemy 2.0. It serves the menu and lets customers place orders that the
kitchen moves through a fixed sequence of statuses.

This page explains **how the API behaves**. For the exact routes, request
examples, environment variables and test commands, see the
[API reference in `api/README.md`](../../../api/README.md), which lives next to
the code and is the single source for those details.

## Prices

Prices come from the `pizzas` table, never from the request, and are stored in
**cents** to avoid floating-point rounding. Each order item keeps a snapshot of
the unit price at the moment the order was placed, so changing the menu later
does not change old orders.

## Status flow

```
received ──► preparing ──► out_for_delivery ──► delivered
    │
    └──► cancelled
```

- An order can only be cancelled while it is still `received`.
- `delivered` and `cancelled` are final.
- Skipping a step, going backwards or changing a final order returns `409 Conflict`.
- Sending the current status again is a no-op and returns `200`.
- Two requests changing the same order at the same time are handled one after
  the other: the order row is locked while its status is checked and changed.

## Errors

| Code | When |
|---|---|
| `404 Not Found` | The order id or a `pizza_id` does not exist |
| `409 Conflict` | `POST /orders` with an unavailable pizza, or a status change the flow does not allow |
| `422 Unprocessable Entity` | Invalid input: malformed order id, empty fields, quantity out of range, more than 20 items or 50 pizzas, or the same pizza twice (use `quantity`) |
| `503 Service Unavailable` | The API cannot reach the database |

## Tests

The test suite runs on an in-memory SQLite database (no Docker needed), and CI
also runs it on PostgreSQL. See [Tests in `api/README.md`](../../../api/README.md#tests).
