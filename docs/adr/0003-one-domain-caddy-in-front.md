# 0003: One domain for the site and the API, with Caddy in front

- **Status:** Accepted
- **Date:** 2026-11-13
- **Phase:** 2

## Context

Phase 2 puts the menu website online. The system's domain is **`slicepizza.senatore.tech`** (the docs live at `slicepizza-docs.senatore.tech`). Until now that domain pointed straight at the API container, so `/health`, `/menu` and `/orders` were the API's routes at the root of the domain.

The roadmap imagined the site on a CDN at `www` and the API at `api`, two origins. That would require CORS on the API ([issue #25](https://github.com/SenatoreTeam/SlicePizza/issues/25)) and a second public domain. The site has to live at `slicepizza.senatore.tech` itself, so the site and the API must share that domain.

## Options considered

1. **Caddy in front: the site at `/`, the API at `/api`.** A small `web` container serves the static files and forwards `/api/*` to the API. One origin, so no CORS. The API container needs no public domain. Costs one more image to build and run, and the API's URLs move under `/api`.
2. **The API also serves the site.** FastAPI can serve static files next to its routes. No new container, but every change to the site rebuilds and restarts the API, and the API image grows a frontend it has nothing to do with.
3. **The API on its own subdomain** (e.g. `api-slicepizza.senatore.tech`) and the site on a CDN at `slicepizza.senatore.tech`. Closest to the roadmap, but needs CORS, a second DNS record and certificate, and a CDN to set up and pay attention to.

## Decision

Option 1. The `web` image ([`infra/caddy/`](../../infra/caddy/)) is Caddy with the menu site copied in:

```
https://slicepizza.senatore.tech ──► server proxy (Dokploy, HTTPS) ──► web:8080 (Caddy)
                                                                         ├─ /        ► menu site files
                                                                         └─ /api/*   ► api:8000 (prefix removed)
```

- The server's proxy keeps terminating HTTPS, as it already does. Caddy listens on plain HTTP `:8080` and never asks for certificates.
- Caddy removes `/api` before forwarding, so the API's own routes do not change. The API runs with `UVICORN_ROOT_PATH=/api` so the links it generates (the interactive docs) include the prefix.
- The site calls `/api/...` on its own origin (`frontend/menu/config.js`). The same layout runs locally with `docker compose up` on port 8080, so local and production behave the same.
- CORS stays available in the API (`CORS_ORIGINS`), but off by default: it is only for a future site on another origin.

## Consequences

- Public API addresses change: `https://slicepizza.senatore.tech/health` becomes `https://slicepizza.senatore.tech/api/health`. Anything that checks the old address (monitors, bookmarks) must follow.
- The server runs one more container (`web`) and pulls one more image (`ghcr.io/senatoreteam/slicepizza-web`), which must also be updated automatically. The domain moves from the API container to the web container; the API stops being reachable directly from the internet.
- The roadmap's "CDN" step is not done this way: the site's files are served by our server, not from edge locations. For a pizzeria site that is fine; Phase 7 (load) can put a CDN in front of the whole domain if the numbers ask for it.
- Caddy is the natural place for the next proxy concerns: rate limiting (Phase 8), access logs (Phase 5) and, in Phase 3, the kitchen dashboard as another path or host.
