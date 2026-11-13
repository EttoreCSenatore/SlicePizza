# Architecture

This document describes **where the system is headed**. Not everything exists yet: check the "Phase" column to see when each part is introduced.

## Overview

```
                                       ┌─ /       ► Menu website (static files)
Customer ──► slicepizza.senatore.tech ─┤
             (HTTPS at the server's    └─ /api/*  ► Orders API ──► Postgres
              proxy, then Caddy)                       │      └────► Redis (cache)
                                                       ▼
                                                Queue (RabbitMQ)
                                                       │
                                                       ▼
                                              Notification worker ──► Telegram

Kitchen ──► Kitchen dashboard (Phase 3, address to be decided) ──► API
```

One domain serves both the site and the API, so the browser never calls another origin. Why: [ADR 0003](adr/0003-one-domain-caddy-in-front.md). Documentation: `slicepizza-docs.senatore.tech` (GitHub Pages).

## Components

| Component | Folder | Responsibility | Phase |
|---|---|---|---|
| Orders API | `api/` | Menu, create orders, get and update order status | 1 |
| Postgres | (official image) | Stores pizzas, orders and customers | 1 |
| Menu website | `frontend/menu/` | Public page where customers place orders | 2 |
| Web container (Caddy) | `infra/caddy/` | Serves the site at `/` and forwards `/api/*` to the API. HTTPS is terminated before it, by the server's proxy | 2 |
| RabbitMQ | (official image) | Queue for order events | 3 |
| Notification worker | `worker/` | Reads the queue and notifies the customer on Telegram | 3 |
| Kitchen dashboard | `frontend/` | The kitchen sees orders and updates their status | 3 |
| Redis | (official image) | Menu cache | 7 |

## Order flow

1. The customer opens `slicepizza.senatore.tech` and picks their pizzas.
2. The site calls `POST /api/orders`, which Caddy forwards to the API as `POST /orders`. The order is saved in Postgres with status `received`.
3. The kitchen sees the order on the dashboard and changes its status to `preparing`.
4. The API saves the new status **and** an `order.status_changed` event in the same transaction (the outbox). A background relay publishes the event to RabbitMQ ([ADR 0004](adr/0004-order-events-outbox-rabbitmq.md)).
5. The worker reads the event and sends the customer a Telegram message.
6. The same happens for `out_for_delivery` and `delivered`.

Why use a queue in step 4, instead of having the API call Telegram directly? If Telegram is slow or down, the API keeps responding quickly, and the messages wait in the queue until the worker can send them.

Why the outbox, instead of publishing right after saving? Saving to Postgres and publishing to RabbitMQ are two systems: a crash or a RabbitMQ restart between them would lose the event. With the outbox, the event is saved with the change, and publishing is retried until RabbitMQ confirms it.

### Events

| Routing key | When | Body |
|---|---|---|
| `order.created` | An order is placed | `order` with `status: "received"`, `previous_status: null` |
| `order.status_changed` | The status changes (not on a no-op or a refused change) | `order` with the new `status` and the `previous_status` |

All go to the `slicepizza.events` topic exchange, as persistent JSON with `message_id` = `event_id`. The format is documented in [`api/app/events.py`](../api/app/events.py). Consumers bind their own durable queue (e.g. `order.#`) and must ignore duplicates by `message_id`.

## Order status

```
received ──► preparing ──► out_for_delivery ──► delivered
    │
    └──► cancelled
```

## DNS

| Record | Type | Points to |
|---|---|---|
| `slicepizza.senatore.tech` | A | The shared server (site and API, see [DEPLOY.md](DEPLOY.md)) |
| `slicepizza-docs.senatore.tech` | CNAME | `senatoreteam.github.io` (docs site) |
| `staging…` | | To be decided in Phase 4 |

## Planned local ports (Docker Compose)

| Service | Port |
|---|---|
| Web (Caddy: site + `/api`) | 8080 |
| API | 8000 |
| Postgres | 5432 |
| RabbitMQ (Phase 3) | 5672, management UI on 15672 |
| Grafana (Phase 5) | 3000 |
