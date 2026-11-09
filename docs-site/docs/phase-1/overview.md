---
sidebar_position: 1
---

# Phase 1 — Overview

**Zé's request:** _"I want to see it running on your computer."_

Phase 1 is about getting the Orders API and its database running locally with
Docker Compose, and persisting orders across restarts.

## What Phase 1 delivers

- A FastAPI Orders API
- A PostgreSQL 16 database
- A `docker compose` stack with a named volume for the data
- An initial menu seed
- A pytest suite

## The problem this phase creates

Everything runs on one machine, with no public URL and no automation. That
problem is exactly what the next phases solve — in Phase 2 Zé asks for the site
to be live on his own domain.

Continue with [the API](./api.md) or [the Docker setup](./docker.md).
