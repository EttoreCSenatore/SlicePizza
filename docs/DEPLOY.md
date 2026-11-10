# Deploy

The API runs on a shared server, behind `https://senatore.tech`. Nobody deploys by hand: **merging a Pull Request into `main` is the deploy.**

```
PR merged into main ──► GitHub Actions builds api/ ──► ghcr.io/ettorecsenatore/slicepizza-api:latest
                                                              │
                     server checks every 5 minutes ◄──────────┘
                     new image? ──► replaces the container ──► https://senatore.tech
```

- On a Pull Request, the [API image](../.github/workflows/api-image.yml) workflow only checks that the image builds. Nothing is published.
- On `main`, it publishes two tags: `latest` (what the server runs) and `sha-<commit>` (to know exactly which commit is live, or to go back to one).
- Until `api/Dockerfile` exists, the workflow skips the build and passes.

## What the image must do

| Requirement | Why |
|---|---|
| Listen on `0.0.0.0:8000` | The proxy sends `senatore.tech` traffic to port 8000 |
| Run as a non-root user, needing no special Linux capabilities | The container runs with all capabilities dropped and `no-new-privileges` |
| Fit in 512 MB of RAM and 1 CPU | Those are the container's limits |
| Read settings from environment variables (e.g. `DATABASE_URL`) | Variables and secrets are set on the server, never in Git |

The server owner controls how the container runs (network, limits, volumes, domain). If the system needs something new there, such as Postgres in Phase 1, environment variables, or another domain like `api.senatore.tech`, ask for it in an issue: it is a change on the server, not in this repository.

## One-time setup

1. After the first image is published, make the package public: GitHub → your profile → **Packages** → `slicepizza-api` → **Package settings** → **Change visibility** → Public. (The server downloads it without a password.)
2. Point the domain's DNS to the server: `A senatore.tech → 179.66.139.4` (optionally `AAAA → 2a02:4780:95:91b7::1`). The HTTPS certificate is issued automatically once the DNS points there.
