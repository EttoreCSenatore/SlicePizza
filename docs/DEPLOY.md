# Deploy

The API runs on a shared server, behind `https://senatore.tech`. Nobody deploys by hand: **merging a Pull Request into `main` is the deploy.**

```
PR merged into main ──► GitHub Actions builds api/ ──► ghcr.io/senatoreteam/slicepizza-api:latest
                                                              │
                     server checks every 5 minutes ◄──────────┘
                     new image? ──► replaces the API container ──► https://senatore.tech
```

- On a Pull Request, the [API image](../.github/workflows/api-image.yml) workflow only checks that the image builds. Nothing is published.
- On `main`, it publishes two tags: `latest` (what the server runs) and `sha-<commit>` (to know exactly which commit is live, or to go back to one).
- The image belongs to the `SenatoreTeam` organization, like the repository. Registry names are lowercase, hence `senatoreteam`.

## What the image must do

| Requirement | Why |
|---|---|
| Listen on `0.0.0.0:8000` | The proxy sends `senatore.tech` traffic to port 8000 |
| Run as a non-root user, needing no special Linux capabilities | The container runs with all capabilities dropped and `no-new-privileges` |
| Fit in 512 MB of RAM and 1 CPU | Those are the container's limits |
| Read settings from environment variables | Variables and secrets are set on the server, never in Git |

`api/Dockerfile` meets all four: Uvicorn on `0.0.0.0:8000`, user `app` (uid 10001), settings from the environment.

## Database

The API **refuses to start without a database** (see `api/app/config.py`): there is no silent fallback to a local file, because that would lose orders on every redeploy. On the server it uses PostgreSQL, the same way `docker-compose.yml` does locally.

| Item | On the server |
|---|---|
| Image | `postgres:16-alpine`, the same version as `docker-compose.yml` and CI |
| Network | The project's isolated network only. **No published port**: only the API reaches it, by service name |
| Data | A named volume, so the data survives API updates. The automatic update replaces **only the API container**, never the database |
| API variables | `POSTGRES_HOST` (the database service name), `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Passed separately, not as a URL, so the password can contain any character |
| Password | Strong, random, stored on the server. Never in Git |
| Backup | A daily `pg_dump`, kept outside the volume. Without it, losing the volume means losing every order |

On first boot the API waits for Postgres to accept connections, creates the tables and seeds the menu (see [ADR 0002](adr/0002-sqlalchemy-and-schema-creation.md)). An empty database is all it needs.

`create_all()` does not alter existing tables. Before a change to `api/app/models.py` reaches the server, the project needs migrations (Alembic, planned in ADR 0002); until then, a schema change on the server means adjusting the tables by hand.

## Checking the deploy

- `https://senatore.tech/health` answers when the API is up and connected to the database.
- The tag `sha-<commit>` on the running image shows which commit is live.

## One-time setup

1. After the first image is published, make the package public: GitHub → **SenatoreTeam** organization → **Packages** → `slicepizza-api` → **Package settings** → **Change visibility** → Public. (The server downloads it without a password.) Only organization owners can change it.
2. On the server: create the Postgres container and its volume, set the API variables, run `ghcr.io/senatoreteam/slicepizza-api:latest` on port 8000 and route `senatore.tech` to it in the proxy.
3. Point the domain's DNS to the server: `A senatore.tech → 179.66.139.4` (optionally `AAAA → 2a02:4780:95:91b7::1`). The HTTPS certificate is issued automatically once the DNS points there.
