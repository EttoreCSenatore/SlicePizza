# Infrastructure

> ⏳ **Starts in Phase 2.** See the [ROADMAP](../docs/ROADMAP.md).

Everything that describes **where and how** the system runs. Planned structure:

```
infra/
├── caddy/        # Reverse proxy and HTTPS                  → Phase 2
├── monitoring/   # Prometheus, Grafana, Loki                → Phase 5
├── terraform/    # Network, virtual machine, firewall, DNS  → Phase 6
├── ansible/      # Server configuration                     → Phase 6
└── k8s/          # Kubernetes manifests and Helm            → Phase 7
```

Rule from Phase 6 on: **no manual changes on the server.** If it's not here, it doesn't exist.
