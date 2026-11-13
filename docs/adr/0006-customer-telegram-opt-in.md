# 0006: Customers follow their order on Telegram, linked through the API

- **Status:** Accepted
- **Date:** 2026-11-13
- **Phase:** 3

## Context

Phase 3 sends Telegram messages about orders. The pizzeria's chat gets every event ([ADR 0005](0005-notification-worker.md)). Customers should also get their own order's updates, if they want them.

Two facts shape this:

- **A Telegram bot cannot message someone first.** The person must open the bot and press *Start*. The menu site only knows a name, a phone number and an address, and none of those lets the bot reach anyone.
- **Telegram's "deep links" carry a parameter.** `https://t.me/<bot>?start=<value>` opens the bot, and pressing *Start* sends `/start <value>` to it. Up to 64 characters from `A–Z a–z 0–9 _ -`; an order id (a UUID) fits.

So the flow is: the order page shows a "Follow on Telegram" link with the order id; the customer starts the bot; the bot learns which chat wants which order. Something must **store** that link, and every later event must reach **those** chats.

## Options considered

Where to keep "chat X follows order Y":

1. **The worker keeps it**, in its own database or file. The worker would gain state, a volume, and maybe a second database to back up.
2. **The API keeps it**, in its Postgres, next to the order. The worker asks the API to save a link; every event about an order carries the chats that follow it.
3. **Through RabbitMQ**: the worker publishes "chat X follows order Y" and the API consumes it. Asynchronous both ways, and the bot could not reply with the order's status right away.

## Decision

Option 2. The API owns the data; the worker stays stateless.

```
customer ──taps──► t.me/<bot>?start=<order id> ──Start──► bot (worker)
worker ──PUT /internal/orders/{id}/telegram-subscriptions/{chat}──► API
                                       ◄── {"status": "preparing", ...}
worker ──► customer: "You're following order 9b2e1c4a. Now: Being prepared."

PATCH /orders/{id}/status ──► event with "notify": {"telegram_chat_ids": [chat]}
                                         ──► worker ──► customer's chat
```

- **`telegram_subscriptions` table**: order id + chat id, unique together, at most 10 chats per order. It is a new table, so it is created on the existing server database without a migration (ADR 0002).
- **Events carry the chats**: `"notify": {"telegram_chat_ids": [...]}` in every event, read at the moment of the change. The worker needs nothing but the event, so a message waiting in the queue already says who gets it.
- **Linking locks the order row**, like a status change. A change either commits first (its event goes without the new chat, and the API's answer tells the worker the current status, which it sends) or after (its event includes the chat). No update falls in between.
- **`/stop`** in the bot removes the chat from every order.
- **The `/internal` routes**:
  - They are for the worker only. They are **off** unless `INTERNAL_API_TOKEN` is set (at least 32 characters), and they then require it as a Bearer token, compared in constant time.
  - **Caddy answers 404** to `/api/internal/*`, so they are never reachable from the internet, whatever the token. Tested through Caddy with a valid token, including `%69nternal`, `//`, `/./` and `..`.
  - They are left out of `/api/docs`.

## Consequences

- **The order id is the key.** Anyone with the link can follow the order, which is the same exposure as today: the same id already opens the order's page, with the name and address. The link is shown only to the customer, on their order page.
- **A Telegram chat id is now in the events and in `order_events`.** It's internal data, stays on the project network, and identifies a Telegram account, not a person by name. The customer gave it to us by starting the bot, and `/stop` removes it from new events.
- **The worker calls the API synchronously** when someone starts the bot. If the API is down, the worker answers "try again in a moment"; nothing else depends on it.
- **One more secret** (`INTERNAL_API_TOKEN`), shared by the API and the worker, set on the server only.
- **Delivered in three PRs**: the API side (#33); the worker's `/start` and `/stop` handling and its messages to customers (#34); and the "Follow on Telegram" button on the order page, whose bot username Caddy fills into the site's `config.js` from the `web` container's `TELEGRAM_BOT_USERNAME` (no setting: no button).
- **The worker reads the bot's messages by long polling** (`getUpdates`), so no public webhook endpoint is needed. Only one process may poll a bot (Telegram answers 409 to a second one), so there is **one worker**. Scaling it out later means moving to a webhook.
- **A customer who blocks the bot is unlinked** the first time a message to them fails with 403, and skipped meanwhile. Unlike the pizzeria's chat, an unreachable customer is not a setup problem and never holds up the queue.
