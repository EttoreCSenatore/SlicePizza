# 0007: The kitchen board at /kitchen, behind a Caddy login and a token

- **Status:** Accepted
- **Date:** 2026-11-13
- **Phase:** 3

## Context

The kitchen needs a screen that lists the open orders (with each customer's name, phone and address) and moves them along: received → preparing → out for delivery → delivered, or cancelled.

Until now, `PATCH /orders/{id}/status` was public: anyone who knew an order's id could change its status, and that change now messages the customer on Telegram ([ADR 0006](0006-customer-telegram-opt-in.md)). A list of every order would also expose customers' personal data. Both must be for the kitchen only.

Constraints:

- It's one pizzeria, with one or a few shared screens (a tablet by the oven). No per-person accounts are needed yet, and building user management now would be a project of its own.
- The site is plain HTML and JavaScript with no build step ([frontend/README.md](../../frontend/README.md)). A secret in the page's JavaScript is not a secret.
- One domain, with Caddy in front of the API ([ADR 0003](0003-one-domain-caddy-in-front.md)).

## Options considered

1. **A token typed into the page and kept in the browser** (localStorage): simple, but the token then lives in every browser that used the board, and any script injected into the page could read it.
2. **User accounts in the API** (passwords in Postgres, sessions or JWTs, a login form): the right end state for several people with different roles, but a lot to build, secure and test for one shared kitchen login.
3. **An external identity provider** (OAuth with Google, an auth proxy): no password to manage, but another service to run or depend on, and every kitchen device needs an account with it.
4. **Caddy asks for a password at `/kitchen`, and adds a token** when it forwards the page's calls to the API: the browser holds only the login (which it manages itself), the token stays on the server, and the API checks the token without knowing about logins.

## Decision

Option 4.

```
browser ──/kitchen/ (login: user + password)──► Caddy ── files of frontend/kitchen/
browser ──/kitchen/api/orders (same login)────► Caddy ──/orders + "Authorization: Bearer <KITCHEN_API_TOKEN>"──► API
anyone  ──/api/orders, PATCH /api/orders/{id}/status ─────────────────────────► API: 401 (no token)
```

- **Caddy** (`web`) answers `/kitchen` and `/kitchen/*` only after HTTP Basic authentication: `KITCHEN_USERNAME` (default `kitchen`) and `KITCHEN_PASSWORD_HASH`, a bcrypt hash from `caddy hash-password`, base64-encoded so it has no `$` signs for `.env` files or a deployment tool to mangle. Without a hash, `/kitchen` answers 404.
- Behind the login, `/kitchen/api/*` is forwarded to the API with the prefix removed, and Caddy **replaces** the browser's `Authorization` header (the login) with `Bearer <KITCHEN_API_TOKEN>`.
- **The API** requires that token (at least 32 characters, compared in constant time) for `GET /orders`, a new route that lists orders, the open ones by default and oldest first, and for `PATCH /orders/{id}/status`, which is no longer public. Without `KITCHEN_API_TOKEN` on the API, both answer 503: nobody can change a status until the server is set up. Everything else stays public: the menu, placing an order, and reading one order by its id (the customer's tracking page).
- The token is a different secret from the worker's `INTERNAL_API_TOKEN`: the kitchen can't call the worker's routes, and the worker can't change statuses.
- **The board** ([`frontend/kitchen/`](../../frontend/kitchen/)) is plain HTML and JavaScript, like the menu site, inside the same `web` image. It refreshes every 5 seconds.

## Consequences

- **Status changes and the order list are private.** The public `/api` can no longer change a status, even with the kitchen's login: only the token Caddy adds works. A leaked order id only shows that one order, as before.
- **The token never reaches a browser.** It exists only in the `web` and `api` settings on the server.
- **One shared login, no roles.** Everyone in the kitchen uses the same user and password, and the API can't tell who changed what. To give someone access, share the password; to remove it, change the password (a new hash) for everyone. Per-person accounts and an audit of who did what would need option 2 or 3 later.
- **Basic authentication's limits**: the browser keeps the login until it is closed (there's no "log out" button), and Caddy doesn't limit repeated wrong passwords. bcrypt makes each guess take about a second, so guessing a long password is hopeless, but a flood of wrong guesses costs the server a second of CPU each. A correct login is cached, so the board's refreshes cost almost nothing. Rate limiting belongs to Phase 8 (security). Caddy's access log shows the login header as `REDACTED`.
- **A breaking change for anyone changing statuses with curl**: they now need the token, and the server's API is not exposed directly. The CI scripts call `/kitchen/api` with the login (compose smoke test) or the API with the token (Telegram end-to-end test).
- **HTTPS is required**, since Basic authentication sends the password with every request. The server's proxy already terminates HTTPS in front of `web` ([ADR 0003](0003-one-domain-caddy-in-front.md)); locally it's plain HTTP on localhost.
- Listing orders filters on `status` without an index. With a pizzeria's volume that's fine; an index would need a migration ([ADR 0002](0002-sqlalchemy-and-schema-creation.md)), so it waits until one is needed.
