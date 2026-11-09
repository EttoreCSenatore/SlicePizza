# Infraestrutura

> ⏳ **Começa na Fase 2.** Veja o [ROADMAP](../docs/ROADMAP.md).

Tudo o que descreve **onde e como** o sistema roda. Estrutura planejada:

```
infra/
├── caddy/        # Proxy reverso e HTTPS                → Fase 2
├── monitoring/   # Prometheus, Grafana, Loki            → Fase 5
├── terraform/    # Rede, máquina virtual, firewall, DNS → Fase 6
├── ansible/      # Configuração do servidor             → Fase 6
└── k8s/          # Manifests e Helm do Kubernetes       → Fase 7
```

Regra a partir da Fase 6: **nenhuma mudança manual no servidor.** Se não está aqui, não existe.
