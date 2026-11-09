# 0001: Use a single repository (monorepo)

- **Status:** Accepted
- **Date:** 2026-11-09
- **Phase:** 1

## Context

The system will have several services (API, worker, frontend) plus the infrastructure (Terraform, Ansible, Kubernetes). We need to decide whether each one gets its own repository or everything lives together.

## Options considered

1. **One repository per service**: each service has its own history and pipeline. On the other hand, a change touching both the API and the worker becomes two Pull Requests, and versions have to be coordinated across repositories.
2. **Monorepo**: everything in one repository, split into folders. A change that spans several services is a single Pull Request. On the other hand, the pipeline needs to know which folder changed so it doesn't always run everything.

## Decision

Monorepo, with one folder per component: `api/`, `worker/`, `frontend/`, `infra/`.

The project is small, has few people and is meant for learning. Seeing everything in one place makes it easier to understand how the parts connect.

## Consequences

- The `docker-compose.yml` at the root will bring the whole system up with one command.
- In Phase 4, the GitHub Actions pipeline should use path filters (`paths:`) to only test and publish the service that changed.
- If a service grows too large, we can split it out later with a new ADR.
