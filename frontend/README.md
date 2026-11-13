# Frontend

Plain HTML, CSS and JavaScript, with no build step and no framework (the project's focus is DevOps, not front-end).

| Page | Folder | Address | For whom | Phase |
|---|---|---|---|---|
| Menu website | [`menu/`](menu/) | `https://slicepizza.senatore.tech/` | Customers pick pizzas, place an order and follow its status | 2 |
| Kitchen dashboard | `kitchen/` | to be decided in Phase 3 | The kitchen sees orders and updates their status | 3 |

## Menu website

```
menu/
├── index.html   # the page: menu, delivery form, order tracking
├── app.js       # talks to the API and renders the page
├── styles.css
├── config.js    # the API address: the only file that changes per environment
└── favicon.svg
```

What it does:

1. Loads the menu from `GET /menu`.
2. The customer picks quantities and fills in name, phone and address.
3. **Place order** sends `POST /orders`, then opens `#/order/<id>`.
4. The order page calls `GET /orders/<id>` every 10 seconds until the order is delivered or cancelled. The last order is remembered in the browser, so the customer can find it again from the menu.

The page is a single file with two views selected by the URL hash, so any static host can serve it: no server-side routing needed.

### Running it locally

With the rest of the stack, from the repository root:

```bash
docker compose up --build
```

Open <http://localhost:8080>. The `web` service is the production image ([`infra/caddy/`](../infra/caddy/)): Caddy serves `frontend/menu/` and forwards `/api/*` to the API. Compose also mounts the folder into the container, so you can edit a file and just reload the page.

Without Docker, run the API with Uvicorn on port 8000 (see [api/README.md](../api/README.md#running)) and Caddy with the same Caddyfile, pointing it at your folders:

```bash
SITE_ROOT=frontend/menu API_UPSTREAM=localhost:8000 caddy run --config infra/caddy/Caddyfile
```

### Talking to the API

The site calls the API at **`/api`, on its own domain** (`config.js`). In production that is `https://slicepizza.senatore.tech/api/...`; locally, `http://localhost:8080/api/...`. Same origin, so the browser needs no CORS ([ADR 0003](../docs/adr/0003-one-domain-caddy-in-front.md)).

Every call goes through the `api()` helper in `app.js`. It always sends **`Content-Type: application/json`** with a body, which the API requires ([issue #25](https://github.com/SenatoreTeam/SlicePizza/issues/25)), and turns the API's errors into messages for the customer.

If the page says "Couldn't reach the pizzeria", open `/api/health` in the same browser: if it fails, the API is down or `web` cannot reach it (check `API_UPSTREAM`).

### Pointing it at another API

`config.js` holds the API address and is the only file that knows it:

```js
window.SLICEPIZZA_CONFIG = {
  apiUrl: "/api",
};
```

To use an API on another origin (e.g. `"http://localhost:8000"`), put its full address there and add this site's origin to the API's `CORS_ORIGINS` (see [api/README.md](../api/README.md#calling-the-api-from-a-browser-cors)).
