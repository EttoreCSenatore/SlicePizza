# Orders API

> ⏳ **Starts in Phase 1.** See the [ROADMAP](../docs/ROADMAP.md#phase-1-i-want-to-see-it-running-on-your-computer).

A **Python + FastAPI** API that serves the menu and receives the pizzeria's orders.

## Planned routes

| Method | Route | What it does |
|---|---|---|
| GET | `/health` | Tells whether the API is alive (used by Docker and monitoring) |
| GET | `/menu` | Lists the pizzas |
| POST | `/orders` | Creates an order |
| GET | `/orders/{id}` | Gets an order |
| PATCH | `/orders/{id}/status` | Changes an order's status |

## Suggested structure

```
api/
├── app/
│   └── main.py            # API routes
├── tests/
│   └── test_main.py       # automated tests (pytest)
├── Dockerfile             # how to build the image
├── requirements.txt       # runtime dependencies
└── requirements-dev.txt   # development dependencies (includes pytest)
```

## Planned environment variables

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | Postgres connection | `postgresql://user:password@db:5432/slicepizza` |

## Useful links to get started

- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/)
- [Docker: getting started](https://docs.docker.com/get-started/)
- [Docker Compose: quickstart](https://docs.docker.com/compose/gettingstarted/)
