# Notification worker

> 🚧 **Phase 3.** The pizzeria's Telegram chat gets a message for every new order and every status change, and customers who follow their order get its updates. Next: the "Follow on Telegram" button on the order page. See the [ROADMAP](../docs/ROADMAP.md#phase-3-customers-want-to-know-when-their-pizza-is-on-the-way).

A Python service that reads order events from its RabbitMQ queue and sends Telegram messages, and that runs the bot customers talk to. It never touches the database: everything it needs to send is in the event, and the API links customers' chats to their orders ([ADR 0006](../docs/adr/0006-customer-telegram-opt-in.md)).

Why a separate service? If Telegram is slow or down, the API keeps answering, and the messages wait in the queue until the worker can send them. How it handles each kind of failure: [ADR 0005](../docs/adr/0005-notification-worker.md).

```
slicepizza.events ──order.#──► notifications ──► worker ──► Telegram (pizzeria chat + customers)
                                     │
                       unreadable / refused / crashed 20×
                                     ▼
                         notifications.dead-letter

customer ──/start <order id>──► bot (worker) ──PUT /internal/...──► API
```

## What the pizzeria chat receives

```
🍕 New order 9b2e1c4a
Customer: Maria
2 × Margherita
1 × Calabresa
Total: R$ 98,00
```

```
Order 9b2e1c4a (Maria): Received → Being prepared
```

`9b2e1c4a` is the start of the order id, as the menu site shows it.

## What customers receive

A customer taps "Follow on Telegram" on their order page (`https://t.me/<bot>?start=<order id>`) and presses **Start**:

```
🍕 You're following order 9b2e1c4a from Zé's Pizzeria.
Your order 9b2e1c4a is being prepared. 🍕
I'll message you here when it changes. Send /stop to stop.
```

Then, on each change:

```
Zé's Pizzeria
Your order 9b2e1c4a is on the way! 🛵
```

| They send | The bot |
|---|---|
| `/start <order id>` | Follows the order (through the API) and answers with its status |
| `/start` | Says hello and how to follow an order |
| `/stop` | Stops every order's updates to this chat |
| Anything else (private chat) | Explains how to use it. In groups, only commands are answered |

A customer who blocks the bot is skipped and unlinked; the pizzeria's chat and the other customers are not affected.

## Running

With the rest of the stack, from the repository root:

```bash
docker compose up --build
docker compose logs -f worker
```

Without `TELEGRAM_BOT_TOKEN` in `.env`, the worker **writes each message to its log** instead of sending it. Place an order at <http://localhost:8080> and watch it appear. (Meant for development: the messages include customers' names, so on the server set the token.)

To see the queue: the RabbitMQ management UI at <http://localhost:15672> → Queues → `notifications`.

To see it wait while the worker is down (the phase's "done when"):

```bash
docker compose stop worker
# place an order at http://localhost:8080: the message waits in "notifications"
docker compose start worker
# the worker sends it as soon as it is back
```

## Setting up Telegram

1. In Telegram, talk to **@BotFather**, send `/newbot` and follow the steps. It gives you the **token** (`123456789:AA...`). Treat it like a password.
2. Create a group for the pizzeria (or use an existing one) and **add the bot** to it.
3. Send any message in the group, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser. In the answer, `"chat":{"id":-100...}` is the **chat id**. Groups have negative ids.
4. Put both in `.env` (never in Git) and restart the worker:
   ```bash
   TELEGRAM_BOT_TOKEN=123456789:AA...
   TELEGRAM_PIZZERIA_CHAT_ID=-1001234567890
   ```
   ```bash
   docker compose up -d worker
   ```

If the token or the chat id is wrong, the worker logs an **error** every minute saying which setting to check, and keeps the message until it can send it.

5. For customers to follow their orders, set the same `INTERNAL_API_TOKEN` for the API and the worker (`openssl rand -hex 32`) in `.env`, and restart both: `docker compose up -d api worker`. Then open `https://t.me/<your bot's username>?start=<an order id>` on your phone.

Only **one** worker may run per bot: it reads the bot's messages by long polling, and Telegram refuses a second reader (409 Conflict).

## Settings

| Variable | Purpose | Default |
|---|---|---|
| `RABBITMQ_HOST`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | Where the queue is (required) | |
| `RABBITMQ_PORT`, `RABBITMQ_VHOST` | | `5672`, `/` |
| `TELEGRAM_BOT_TOKEN` | The bot. Empty: log the messages instead of sending them | empty |
| `TELEGRAM_PIZZERIA_CHAT_ID` | The pizzeria's chat: a numeric id (`-100…`) or a public `@channel`. Empty: no pizzeria messages | empty |
| `TELEGRAM_API_URL` | The Bot API's address (for tests) | `https://api.telegram.org` |
| `API_URL` | The API, on the project network | `http://api:8000` |
| `INTERNAL_API_TOKEN` | The secret for the API's `/internal` routes, **the same as the API's**. Empty: customers cannot follow orders | empty |
| `WORKER_HEARTBEAT_FILE` | The file the healthcheck looks at | `/tmp/worker-alive` |

## Tests

```bash
cd worker
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt
pytest
```

The integration tests (`tests/test_rabbitmq.py`) need a RabbitMQ and run only when `RABBITMQ_TEST_HOST` is set. They **delete the worker's queues**, so never point them at a broker in use. With the one from Docker Compose:

```bash
docker compose up -d rabbitmq
set -a; source ../.env; set +a
RABBITMQ_TEST_HOST=localhost RABBITMQ_TEST_USER=$RABBITMQ_USER RABBITMQ_TEST_PASSWORD=$RABBITMQ_PASSWORD pytest
```

CI runs them against `rabbitmq:4.4.0-management-alpine`, the same version as `docker-compose.yml`.

CI also runs the whole opt-in end to end: the real API and worker against a **fake Telegram Bot API** ([`.github/scripts/fake_telegram.py`](../.github/scripts/fake_telegram.py)) that injects `/start` and `/stop` and records every message ([`e2e_telegram_optin.py`](../.github/scripts/e2e_telegram_optin.py)).

## Dependencies

The same setup as the API ([api/README.md](../api/README.md#dependencies)): edit `requirements.in` / `requirements-dev.in`, then regenerate the lock files with the image's Python:

```bash
cd worker
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/worker -w /worker \
    "python:$(cat .python-version)-slim" scripts/compile-requirements.sh
```

The image installs only what the lock file lists, hashes checked, wheels only. The worker's only dependency is `pika` (RabbitMQ); Telegram is called with the standard library.

## Structure

```
worker/
├── app/
│   ├── main.py       # entry point: settings, signals, run
│   ├── config.py     # settings from environment variables
│   ├── consumer.py   # RabbitMQ: queues, one message at a time, retries
│   ├── bot.py        # the bot's commands: /start, /stop
│   ├── api_client.py # the API's /internal routes
│   ├── messages.py   # reads events, writes the message texts
│   └── telegram.py   # sends to Telegram (or to the log), reads the bot's messages
├── tests/
├── scripts/compile-requirements.sh
├── Dockerfile
└── requirements*.in / requirements*.txt
```
