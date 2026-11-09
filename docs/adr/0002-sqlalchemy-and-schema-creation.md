# 0002: SQLAlchemy ORM and schema creation on startup

- **Status:** Accepted
- **Date:** 2026-11-09
- **Phase:** 1

## Context

Phase 1 needs the API to talk to PostgreSQL, create the `pizzas` and `orders` tables and run tests without requiring a database server.

The roadmap suggests SQLAlchemy or psycopg. The choice affects how queries are written, how the schema is kept in sync, and how easy it is to test.

## Options considered

1. **Raw psycopg with SQL strings**: little abstraction and no ORM to learn. But every query is hand-written, results are tuples, and the schema is defined in yet another place (`schema.sql`). Tests would need a real Postgres or careful mocking.
2. **SQLAlchemy 2.0 ORM**: models are Python classes, relationships (order → items → pizza) are explicit, and the same code runs on PostgreSQL and SQLite. The API layer uses typed objects instead of tuples.
3. **SQLModel**: nicer syntax on top of SQLAlchemy, but a smaller ecosystem and one more abstraction while learning the fundamentals.

## Decision

Use **SQLAlchemy 2.0** with the `psycopg` (v3) driver, through the `postgresql+psycopg://` URL.

The schema is defined in `api/app/models.py` and created with `Base.metadata.create_all()` at application startup. The menu is seeded if the `pizzas` table is empty. Tests use an in-memory SQLite database by default, so they run fast and without Docker. Setting `TEST_DATABASE_URL` runs the same suite against Postgres.

## Consequences

- Locally, the API is tested against a different engine (SQLite) than production (Postgres). CI runs the suite on both, plus a Docker Compose smoke test, so Postgres-only behavior (32-bit integers, NUL characters, concurrent transactions) is still covered.
- `create_all()` does not alter existing tables. This is fine while the schema is young, but it is not a migration strategy.
- Before the schema changes in a deployed environment (around Phase 6, when backups and infrastructure as code arrive), introduce **Alembic** and replace `create_all()`.
- SQLAlchemy adds a dependency and some learning curve, but it keeps SQL injection protection and relationship loading consistent.
