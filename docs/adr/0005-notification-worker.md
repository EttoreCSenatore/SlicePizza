# 0005: The notification worker: one queue, retries, dead letters

- **Status:** Accepted
- **Date:** 2026-11-13
- **Phase:** 3

## Context

The API publishes `order.created` and `order.status_changed` to the `slicepizza.events` exchange ([ADR 0004](0004-order-events-outbox-rabbitmq.md)). Phase 3 needs a separate service that turns them into Telegram messages: to the pizzeria's chat for every event and, in the next step, to customers who ask for it.

The phase is done when: **if the worker is down, messages wait in the queue and are sent when it comes back.** Beyond that, the worker has to decide what to do when something fails, and the possible failures are different in kind:

- **Telegram is down or slow** (network errors, 5xx, 429 "too many requests"). It will work again; the message must wait.
- **The bot is misconfigured**: wrong token (401), bot removed from the chat (403), wrong chat id. No retry helps until a person fixes the settings, but dropping the message would lose it.
- **Telegram refuses this one message** (another 400, e.g. too long). It will never work.
- **The message is unreadable**: not JSON, or an event version this worker does not know. It will never work either.
- **The worker itself crashes on a message** (a bug). Retrying forever would block every message behind it.

## Decision

A Python service in [`worker/`](../../worker/), with the same rules as the API: hash-locked dependencies (only `pika`; Telegram is one HTTPS call made with the standard library), non-root, no capabilities.

**Queues**, declared by the worker at startup:

```
slicepizza.events ──order.#──► notifications (quorum queue, durable)
                                     │ x-delivery-limit: 20
                                     ▼
slicepizza.dead-letter ────► notifications.dead-letter (kept until a person looks)
```

- **A quorum queue.** It is RabbitMQ's queue type for messages that must not be lost. RabbitMQ 4 no longer accepts transient (non-durable) shared queues at all.
- **One message at a time** (`prefetch_count=1`), acknowledged only **after** the notification went out. A crash before that puts the message back in the queue.

**What happens on each kind of failure:**

| Failure | Action |
|---|---|
| Telegram down, 5xx, network | Keep the message, retry after 1 s, 2 s, 4 s… up to 60 s. The queue waits behind it, which keeps the order of messages |
| 429 Too Many Requests | Wait the `retry_after` Telegram gives, then retry |
| Wrong token, bot removed, wrong chat id | Keep the message, log an **error** every 60 s saying which setting to check |
| Telegram refuses the message (other 400s) | Dead-letter it and log an error |
| Unreadable message, unknown version | Dead-letter it and log an error, **without the body** (it has a customer's name) |
| Known version, unknown event type | Acknowledge and ignore it: a newer API may publish events this worker does not need |
| Duplicate event (same `event_id`) | Acknowledge it without sending again |
| The worker crashes on a message | RabbitMQ gives it back; after 20 deliveries it is dead-lettered |

**Two numbers work together:**

- RabbitMQ closes the channel of a consumer that keeps a message unacknowledged for 30 minutes (`consumer_timeout`). Each such return counts toward the delivery limit.
- So during a long Telegram outage, the worker holds a message for at most 18 minutes, then gives it back itself and takes it again.
- 20 deliveries × 18 minutes is about **6 hours of outage** before a message is set aside, while a crash loop caused by a bug is cut off after 20 quick attempts.

**Duplicates** are dropped by `event_id`, remembering the last 10 000 in memory. Delivery is at least once (ADR 0004), and duplicates are rare: they need the API to stop between publishing and marking the event published.

**Without `TELEGRAM_BOT_TOKEN`** the worker logs each message instead of sending it, so `docker compose up` and CI need no bot.

**Health**: the worker has no HTTP port. It touches `/tmp/worker-alive` every second while connected and working, and the container healthcheck checks that the file is fresh.

## Consequences

- **The phase's "done when" is tested in CI.** `.github/scripts/smoke_worker_down.py` stops the worker, places an order, sees the message waiting in `notifications`, starts the worker and sees the message handled.
- **One stuck message stops the ones behind it** while Telegram is failing. That's on purpose: messages arrive in order, and nothing is lost. Phase 5 should alert when `notifications` has messages older than a few minutes.
- **Dead-lettered messages need a person.** Look in `notifications.dead-letter` (management UI → Queues), fix the cause, then move them back to `notifications` (the UI's "Move messages" needs the `rabbitmq_shovel` and `rabbitmq_shovel_management` plugins enabled) or delete them.
- **The dedupe memory is lost on restart**, so a duplicate arriving right after a restart is sent twice. That's acceptable for a notification. Step 2b adds storage (for customers' Telegram chats), and the dedupe can move there if needed.
- **Queue arguments cannot change once the queue exists.** Changing `x-delivery-limit` in code makes the declaration fail with `PRECONDITION_FAILED`. Use a RabbitMQ policy for such changes, or recreate the queue after draining it.
