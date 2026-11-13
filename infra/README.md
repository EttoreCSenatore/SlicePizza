# Infrastructure

> 🚧 **Phase 2:** [`caddy/`](caddy/) is in use. The rest arrives in later phases. See the [ROADMAP](../docs/ROADMAP.md).

Everything that describes **where and how** the system runs. Planned structure:

```
infra/
├── caddy/        # The web container: site + /api proxy     → Phase 2 (ADR 0003)
├── monitoring/   # Prometheus, Grafana, Loki                → Phase 5
├── terraform/    # Network, virtual machine, firewall, DNS  → Phase 6
├── ansible/      # Server configuration                     → Phase 6
└── k8s/          # Kubernetes manifests and Helm            → Phase 7
```

Rule from Phase 6 on: **no manual changes on the server.** If it's not here, it doesn't exist.
