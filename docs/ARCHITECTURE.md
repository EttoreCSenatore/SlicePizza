# Architecture

This document describes **where the system is headed**. Not everything exists yet: check the "Phase" column to see when each part is introduced.

## Overview

```
Customer ──► www.yourdomain.com ──► Menu website (static, CDN)
                                          │ calls the API
                                          ▼
         api.yourdomain.com ──► Proxy (Caddy) ──► Orders API ──► Postgres
                                                      │      └────► Redis (cache)
                                                      ▼
                                               Queue (RabbitMQ)
                                                      │
                                                      ▼
                                             Notification worker ──► Telegram

Kitchen ──► admin.yourdomain.com ──► Kitchen dashboard ──► API
```

## Components

| Component | Folder | Responsibility | Phase |
|---|---|---|---|
| Orders API | `api/` | Menu, create orders, get and update order status | 1 |
| Postgres | (official image) | Stores pizzas, orders and customers | 1 |
| Menu website | `frontend/` | Public page where customers place orders | 2 |
| Reverse proxy (Caddy) | `infra/` | Receives HTTPS traffic and forwards it to the API | 2 |
| RabbitMQ | (official image) | Queue for order events | 3 |
| Notification worker | `worker/` | Reads the queue and notifies the customer on Telegram | 3 |
| Kitchen dashboard | `frontend/` | The kitchen sees orders and updates their status | 3 |
| Redis | (official image) | Menu cache | 7 |

## Order flow

1. The customer opens `www.yourdomain.com` and picks their pizzas.
2. The site calls `POST /orders` on the API. The order is saved in Postgres with status `received`.
3. The kitchen sees the order on the dashboard and changes its status to `preparing`.
4. The API saves the new status and publishes an `order.status_changed` event to the queue.
5. The worker reads the event and sends the customer a Telegram message.
6. The same happens for `out_for_delivery` and `delivered`.

Why use a queue in step 4, instead of having the API call Telegram directly? If Telegram is slow or down, the API keeps responding quickly, and the messages wait in the queue until the worker can send them.

## Order status

```
received ──► preparing ──► out_for_delivery ──► delivered
    │
    └──► cancelled
```

## Planned DNS (Phase 2)

| Record | Type | Points to |
|---|---|---|
| `www.yourdomain.com` | CNAME | CDN for the static site |
| `api.yourdomain.com` | A | Virtual machine IP |
| `admin.yourdomain.com` | A | Virtual machine IP |
| `staging.yourdomain.com` | A | Staging virtual machine IP (Phase 4) |

## Planned local ports (Docker Compose)

| Service | Port |
|---|---|
| API | 8000 |
| Postgres | 5432 |
| RabbitMQ (Phase 3) | 5672, management UI on 15672 |
| Grafana (Phase 5) | 3000 |
