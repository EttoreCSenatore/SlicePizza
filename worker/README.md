# Notification worker

> 🚧 **Phase 3.** The pizzeria's Telegram chat gets a message for every new order and every status change. Next: customers who ask for it get their own order's updates. See the [ROADMAP](../docs/ROADMAP.md#phase-3-customers-want-to-know-when-their-pizza-is-on-the-way).

A Python service that reads order events from its RabbitMQ queue and sends Telegram messages. It never talks to the API or the database: everything it needs is in the event.

Why a separate service? If Telegram is slow or down, the API keeps answering, and the messages wait in the queue until the worker can send them. How it handles each kind of failure: [ADR 0005](../docs/adr/0005-notification-worker.md).

```
slicepizza.events ──order.#──► notifications ──► worker ──► Telegram (pizzeria chat)
                                     │
                       unreadable / refused / crashed 20×
                                     ▼
                         notifications.dead-letter
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

## Running

With the rest of the stack, from the repository root:

```bash
docker compose up --build
docker compose logs -f worker
```

Without `TELEGRAM_BOT_TOKEN` in `.env`, the worker **writes each message to its log** instead of sending it. Place an order at <http://localhost:8080> and watch it appear.

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

## Settings

| Variable | Purpose | Default |
|---|---|---|
| `RABBITMQ_HOST`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | Where the queue is (required) | |
| `RABBITMQ_PORT`, `RABBITMQ_VHOST` | | `5672`, `/` |
| `TELEGRAM_BOT_TOKEN` | The bot. Empty: log the messages instead of sending them | empty |
| `TELEGRAM_PIZZERIA_CHAT_ID` | The pizzeria's chat: a numeric id (`-100…`) or a public `@channel`. Empty: no pizzeria messages | empty |
| `TELEGRAM_API_URL` | The Bot API's address (for tests) | `https://api.telegram.org` |
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

CI runs them against `rabbitmq:4.3.4-management-alpine`, the same version as `docker-compose.yml`.

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
│   ├── messages.py   # reads events, writes the message texts
│   └── telegram.py   # sends to Telegram (or to the log)
├── tests/
├── scripts/compile-requirements.sh
├── Dockerfile
└── requirements*.in / requirements*.txt
```
