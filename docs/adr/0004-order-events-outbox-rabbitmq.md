# 0004: Order events through a transactional outbox and RabbitMQ

- **Status:** Accepted
- **Date:** 2026-11-13
- **Phase:** 3

## Context

Phase 3: "Customers want to know when their pizza is on the way." Every time an order changes, someone must be told: the customer on Telegram (if they asked for it), and the pizzeria's own Telegram chat. Sending a Telegram message from inside the API request would make the API as slow and as fragile as Telegram, so the roadmap puts a queue (RabbitMQ) between the API and a separate notification worker.

The phase is done when: **if the worker is down, messages wait in the queue and are sent when it comes back.**

That leaves one gap the roadmap does not mention: the API saves the change in Postgres and publishes to RabbitMQ, two different systems. Whatever order it does them in, a crash or an outage between the two loses something:

- Commit, then publish: if RabbitMQ is down, or the API stops right after the commit, the event is lost. The customer never hears about it.
- Publish, then commit: if the commit fails, the customer is told about a change that never happened.

## Options considered

1. **Publish right after the commit**, and log when it fails. Simple, and it loses events whenever RabbitMQ is restarting, which is exactly when the "messages wait" promise matters.
2. **Transactional outbox.** The API writes the event to an `order_events` table **in the same transaction** as the order change. A relay reads that table and publishes to RabbitMQ, then marks the row published. Saving the change and the event becomes one atomic step; publishing becomes a retryable job.
3. **Change data capture** (e.g. Debezium reading Postgres' write-ahead log). The same guarantee without touching the API's code, but another heavy service to run, far beyond a one-server pizzeria.

## Decision

Option 2, the transactional outbox.

```
PATCH /orders/{id}/status
  └─ one transaction: UPDATE orders + INSERT order_events
                                         │
          outbox relay (thread in the API) │  oldest first, waits for RabbitMQ's confirm,
                                         ▼  then sets published_at
               RabbitMQ: topic exchange "slicepizza.events"
                    routing key = event type: order.created, order.status_changed
                                         │
                                         ▼
               queues declared by each consumer (the worker, next PR)
```

- **Events**: `order.created` and `order.status_changed`, JSON, versioned (`"version": 1`). The format is in [`api/app/events.py`](../../api/app/events.py). They carry the order's id, status, previous status, customer name, total and items, but **not the phone or the address**: no consumer needs them, and every copy of personal data is one more place it can leak from.
- **Relay**: a background thread in the API ([`api/app/outbox.py`](../../api/app/outbox.py)). The API wakes it right after each commit; it also checks every second. On Postgres it takes an advisory lock per round, so only one API process publishes at a time, even after scaling out (Phase 7).
- **Publishing**: persistent messages, publisher confirms, and `mandatory`. If no queue is bound for an event, RabbitMQ returns it instead of silently dropping it. The relay then leaves it in the outbox and retries: events published before the worker ever ran are not lost.
- **Order**: the relay stops at the first event it cannot publish and never skips ahead, so a consumer never sees `out_for_delivery` before `preparing`.
- **Queues belong to consumers.** The API only declares the exchange. Each consumer declares its own durable queue and binding. Once declared, the queue keeps collecting messages while the consumer is down: that is the phase's "done when".
- **RabbitMQ is optional for the API.** Without `RABBITMQ_HOST`, or with RabbitMQ down, orders still work and their events wait in `order_events`.
- **Schema**: `order_events` is a new table, so `create_all()` creates it on the server's existing database. No migration is needed (see ADR 0002).

## Consequences

- **At-least-once delivery.** If the API stops between RabbitMQ's confirm and marking the row published, the event is published again on restart. Consumers must ignore duplicates by `message_id` (the event's `event_id`). The worker will.
- **One more table that grows forever.** Published rows are kept. That is useful history for now; a cleanup (e.g. delete published rows after 30 days) belongs with the backups and retention work of Phase 6.
- **One more service to run**: RabbitMQ, with a volume for its queues. Its data directory depends on its hostname, so the hostname is fixed in `docker-compose.yml`.
- **A stuck event blocks the ones after it**: for example, if no consumer exists. That is on purpose (order matters), and the relay logs a warning on every retry, so it does not go unnoticed. Phase 5 will turn "events waiting for more than N minutes" into an alert.
- The relay runs inside the API process: no extra container. If publishing ever needs to scale on its own, the same code can run as a separate service.
