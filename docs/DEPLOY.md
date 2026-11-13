# Deploy

SlicePizza runs on a shared server at **`https://slicepizza.senatore.tech`**: the menu site at `/`, the Orders API at `/api` (see [ADR 0003](adr/0003-one-domain-caddy-in-front.md)). The docs site is separate, on GitHub Pages at `https://slicepizza-docs.senatore.tech`. Nobody deploys by hand: **merging a Pull Request into `main` is the deploy.**

```
PR merged into main ──► GitHub Actions builds the images ──► ghcr.io/senatoreteam/slicepizza-api:latest
                                                         └─► ghcr.io/senatoreteam/slicepizza-web:latest
                                                                       │
                       server checks every 5 minutes ◄─────────────────┘
                       new image? ──► replaces that container

https://slicepizza.senatore.tech ──► server proxy (HTTPS) ──► web:8080 (Caddy)
                                                                ├─ /        ► menu site
                                                                └─ /api/*   ► api:8000 ──► db:5432
```

- On a Pull Request, the [API image](../.github/workflows/api-image.yml) and [web image](../.github/workflows/web-image.yml) workflows only check that their image builds. Nothing is published. Each one runs only when its files change (`api/` for the API; `frontend/menu/` and `infra/caddy/` for web). Both use the same steps, in [build-image.yml](../.github/workflows/build-image.yml).
- The web image is also rebuilt and published every Monday, so the Alpine security fixes that the official Caddy image gets under the same tag reach the server. New Caddy versions come from Dependabot, as Pull Requests.
- On `main`, each publishes two tags: `latest` (what the server runs) and `sha-<commit>` (to know exactly which commit is live, or to go back to one).
- The images belong to the `SenatoreTeam` organization, like the repository. Registry names are lowercase, hence `senatoreteam`.

## The containers

| Container | Image | Public? | Settings |
|---|---|---|---|
| `web` | `slicepizza-web` (Caddy + the site, [`infra/caddy/`](../infra/caddy/)) | **Yes**: the domain points here, port 8080 | `API_UPSTREAM`: the API's `host:port` on the project network (default `api:8000`) |
| `api` | `slicepizza-api` ([`api/`](../api/)) | No: only `web` reaches it | `UVICORN_ROOT_PATH=/api` and `UVICORN_FORWARDED_ALLOW_IPS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`, plus the database variables below |

| `db` | `postgres:16-alpine` | No: only `api` reaches it | See [Database](#database) |
| `rabbitmq` | `rabbitmq:4.3.4-management-alpine` | No: only `api` and `worker` reach it | See [RabbitMQ](#rabbitmq) |
| `worker` | `slicepizza-worker` ([`worker/`](../worker/)) | No: no port at all, it only connects out (RabbitMQ, Telegram) | `RABBITMQ_HOST`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PIZZERIA_CHAT_ID`. See [Worker](#worker) |

Both trust the forwarding headers of the proxy in front of them: Caddy those of the server's proxy (from private addresses, see the Caddyfile), and the API those of Caddy (also from private addresses only). That way the access logs show the customer's IP, and links and redirects the API generates keep `https`.

Both images meet the server's rules:

| Requirement | Why | How |
|---|---|---|
| Listen on `0.0.0.0` on a port above 1024 | The proxy forwards plain HTTP to the container | `api`: Uvicorn on 8000. `web`: Caddy on 8080, with no HTTPS of its own (the server's proxy has the certificate) |
| Run as a non-root user, needing no special Linux capabilities | The containers run with all capabilities dropped and `no-new-privileges` | Both run as uid 10001. The web image removes the port-binding capability the official Caddy image gives its binary |
| Fit in 512 MB of RAM and 1 CPU | Those are each container's limits | Caddy uses a few tens of MB |
| Read settings from environment variables | Variables and secrets are set on the server, never in Git | |

`docker-compose.yml` runs the same containers with the same restrictions, so `docker compose up` on your machine behaves like the server.

`CORS_ORIGINS` (see [api/README.md](../api/README.md#calling-the-api-from-a-browser-cors)) is not needed: the site and the API share one origin. Set it only if a site on another domain must call the API from the browser.

## Database

The API **refuses to start without a database** (see `api/app/config.py`): there is no silent fallback to a local file, because that would lose orders on every redeploy. On the server it uses PostgreSQL, the same way `docker-compose.yml` does locally.

| Item | On the server |
|---|---|
| Image | `postgres:16-alpine`, the same version as `docker-compose.yml` and CI |
| Network | The project's isolated network only. **No published port**: only the API reaches it, by service name |
| Data | A named volume, so the data survives API updates. The automatic update replaces **only the `api` and `web` containers**, never the database |
| API variables | `POSTGRES_HOST` (the database service name), `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Passed separately, not as a URL, so the password can contain any character |
| Password | Strong, random, stored on the server. Never in Git |
| Backup | A daily `pg_dump`, kept outside the volume. Without it, losing the volume means losing every order |

On first boot the API waits for Postgres to accept connections, creates the tables and seeds the menu (see [ADR 0002](adr/0002-sqlalchemy-and-schema-creation.md)). An empty database is all it needs.

`create_all()` does not alter existing tables. Before a change to `api/app/models.py` reaches the server, the project needs migrations (Alembic, planned in ADR 0002); until then, a schema change on the server means adjusting the tables by hand.

## RabbitMQ

Order events go from the API to RabbitMQ through the outbox ([ADR 0004](adr/0004-order-events-outbox-rabbitmq.md)). The API does not depend on it: if RabbitMQ is missing or down, orders still work and their events wait in the `order_events` table.

| Item | On the server |
|---|---|
| Image | `rabbitmq:4.3.4-management-alpine`, the same as `docker-compose.yml` |
| Hostname | **Fixed** (e.g. `rabbitmq`). RabbitMQ stores its data under `rabbit@<hostname>`: with a new random hostname after a redeploy, the queues in the volume would seem gone |
| Network | The project's network only. **No published port** and no domain: the management UI (15672) is reached through an SSH tunnel when needed |
| Data | A named volume on `/var/lib/rabbitmq`, so queued messages survive restarts. Never replaced by the automatic update |
| User | `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` on the RabbitMQ container: a strong, random password, stored on the server. Created on first boot only |
| API variables | `RABBITMQ_HOST` (the service name), `RABBITMQ_USER`, `RABBITMQ_PASSWORD`; optionally `RABBITMQ_PORT` (5672) and `RABBITMQ_VHOST` (`/`) |

**Deploy RabbitMQ and the worker together.** Until the worker has declared its queue, events have nowhere to go: nothing is lost (they wait in `order_events`), but with `RABBITMQ_HOST` set the API logs a warning on every retry.

## Worker

The notification worker ([`worker/`](../worker/), [ADR 0005](adr/0005-notification-worker.md)) reads order events from its queue and sends Telegram messages. It has no port and no domain.

| Item | On the server |
|---|---|
| Image | `ghcr.io/senatoreteam/slicepizza-worker:latest`, updated automatically like the others |
| Network | The project's network, to reach `rabbitmq`. It also needs outgoing HTTPS to `api.telegram.org` |
| Variables | `RABBITMQ_HOST`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD` (the same user as the API), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PIZZERIA_CHAT_ID` |
| Secrets | The bot token is a password: stored on the server only, never in Git |
| Health | Healthy while `/tmp/worker-alive` is less than 30 s old (see `docker-compose.yml`) |
| Restarts | Safe at any time: a message is acknowledged only after it was sent; an interrupted one goes back to the queue |

How to create the bot and find the chat id: [worker/README.md](../worker/README.md#setting-up-telegram). Without `TELEGRAM_BOT_TOKEN` the worker writes the messages to its log instead of sending them. That is meant for local development and CI: the messages include customers' names, so on the server set the token when you deploy the worker (or accept names in the logs until you do).

## Checking the deploy

- `https://slicepizza.senatore.tech/` shows the menu, and placing an order from a phone works end to end.
- `https://slicepizza.senatore.tech/api/health` answers when the API is up and connected to the database. (Before ADR 0003 this was `/health`; update any monitor that still checks the old address.)
- `https://slicepizza.senatore.tech/api/docs` shows the API's interactive docs.
- The tag `sha-<commit>` on each running image shows which commit is live.

## One-time setup

1. After the first image of each kind is published, make the packages public: GitHub → **SenatoreTeam** organization → **Packages** → `slicepizza-api`, `slicepizza-web` and `slicepizza-worker` → **Package settings** → **Change visibility** → Public. (The server downloads them without a password.) Only organization owners can change it.
2. On the server (in the project's compose in Dokploy):
   - Postgres: the `db` container and its volume (see [Database](#database)).
   - `api`: `ghcr.io/senatoreteam/slicepizza-api:latest`, with the database variables, `UVICORN_ROOT_PATH=/api` and `UVICORN_FORWARDED_ALLOW_IPS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`. **No domain.**
   - `web`: `ghcr.io/senatoreteam/slicepizza-web:latest`, on the same network as `api`, with `API_UPSTREAM` set to the API's service name and port (e.g. `api:8000`).
   - Route `slicepizza.senatore.tech` to `web` on port **8080** (`senatore.tech` and `www.senatore.tech` too, if they should keep showing the system).
   - Add the `web` image to the automatic update, like the API's.
   - `rabbitmq` with a fixed hostname and its volume, and `RABBITMQ_*` on `api` (see [RabbitMQ](#rabbitmq)).
   - `worker`: `ghcr.io/senatoreteam/slicepizza-worker:latest` with its variables (see [Worker](#worker)), in the automatic update too.
3. Point the domains' DNS to the server: `A slicepizza → 179.66.139.4`, `A @ → 179.66.139.4` and `CNAME www → senatore.tech` (optionally `AAAA → 2a02:4780:95:91b7::1`). The HTTPS certificate is issued automatically once the DNS points there; if the proxy tried before that, restart the `web` container so it tries again.

### Moving from the API-only setup

Until ADR 0003 the domain pointed at the API container. To switch without downtime: publish and start `web` first (step 2), check it on the server (`curl http://<web container>:8080/api/health`), then move the domain from `api` (port 8000) to `web` (port 8080), and only then remove the domain from `api`.
