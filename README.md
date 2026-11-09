# 🍕 SlicePizza

Projeto de estudo de **DevOps na prática**: um sistema de pedidos online para uma pizzaria fictícia, a **Pizzaria do Zé**.

O sistema começa pequeno e evolui em **fases**. Em cada fase o "dono da pizzaria" faz um pedido novo, e esse pedido obriga a aprender uma tecnologia nova: Docker, DNS, nuvem, filas, CI/CD, observabilidade, Terraform, Kubernetes...

> A ideia é **sentir o problema antes de usar a ferramenta**. Não usamos Kubernetes na Fase 1, porque ainda não existe o problema que ele resolve.

---

## Arquitetura (objetivo final)

```
Cliente ──► www.seudominio.com.br ──► Site do cardápio (estático, CDN)
                                            │ chama a API
                                            ▼
            api.seudominio.com.br ──► Proxy (Caddy) ──► API de pedidos ──► Postgres
                                                            │      └────► Redis (cache)
                                                            ▼
                                                     Fila (RabbitMQ)
                                                            │
                                                            ▼
                                                 Worker de notificações ──► Telegram

Cozinha ──► admin.seudominio.com.br ──► Painel da cozinha ──► API
```

Detalhes de cada componente em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack

| Componente | Tecnologia | Entra na fase |
|---|---|---|
| API de pedidos | Python + FastAPI | 1 |
| Banco de dados | PostgreSQL | 1 |
| Containers | Docker + Docker Compose | 1 |
| Nuvem | AWS ou Oracle Cloud (free tier) | 2 |
| DNS | Cloudflare | 2 |
| Proxy reverso + HTTPS | Caddy | 2 |
| Fila | RabbitMQ | 3 |
| Notificações | Bot do Telegram | 3 |
| CI/CD | GitHub Actions + GHCR | 4 |
| Observabilidade | Prometheus, Grafana, Loki | 5 |
| Infraestrutura como código | Terraform + Ansible | 6 |
| Cache | Redis | 7 |
| Orquestração | Kubernetes (k3s) + Helm | 7 |
| Segurança | Trivy, gerenciador de segredos | 8 |

## Estrutura do repositório

```
SlicePizza/
├── api/            # API de pedidos (FastAPI)          → Fase 1
├── worker/         # Worker de notificações           → Fase 3
├── frontend/       # Site do cardápio + painel        → Fase 2
├── infra/          # Terraform, Ansible, Kubernetes   → Fases 6 e 7
├── docs/           # Documentação, roadmap e ADRs
├── .github/        # Templates e pipelines de CI/CD   → Fase 4
├── docker-compose.yml   # sobe tudo localmente      → Fase 1
└── .env.example         # modelo das variáveis       → Fase 1
```

## Por onde começar

**Pré-requisitos:** [Git](https://git-scm.com/), [Docker](https://docs.docker.com/get-docker/) com o Docker Compose e Python 3.12 ou mais novo.

1. Clone o repositório:
   ```bash
   git clone git@github.com:EttoreCSenatore/SlicePizza.git
   cd SlicePizza
   ```
2. Leia a [arquitetura](docs/ARCHITECTURE.md) para entender aonde o sistema vai chegar.
3. Leia o [fluxo de trabalho](CONTRIBUTING.md): branches, commits e Pull Requests.
4. Abra a [Fase 1 do ROADMAP](docs/ROADMAP.md#fase-1-quero-ver-funcionando-no-seu-computador) e comece pela primeira tarefa.

Ao final da Fase 1, esta seção vai explicar como subir o sistema com `docker compose up`.

## Roadmap

| Fase | Pedido do Zé | Status |
|---|---|---|
| 1 | "Quero ver funcionando no seu computador" | 🚧 Em andamento |
| 2 | "Quero o site no ar com o meu domínio" | ⏳ |
| 3 | "O cliente quer saber quando a pizza sai" | ⏳ |
| 4 | "Toda vez que você mexe, alguma coisa quebra" | ⏳ |
| 5 | "O site caiu sexta à noite e ninguém percebeu" | ⏳ |
| 6 | "O servidor morreu e perdemos os pedidos" | ⏳ |
| 7 | "Vamos fazer promoção de pizza a R$ 20 na sexta" | ⏳ |
| 8 | "Ouvi falar que hackers atacam pizzarias" | ⏳ |

Tarefas e critérios de pronto de cada fase em [docs/ROADMAP.md](docs/ROADMAP.md).

## Regras do jogo

1. **Tudo fica no Git.** A partir da Fase 6, é proibido mudar algo direto no servidor.
2. **Nada vai direto na `main`.** Toda mudança entra por Pull Request (veja [CONTRIBUTING.md](CONTRIBUTING.md)).
3. **Toda decisão importante vira um ADR** em [docs/adr/](docs/adr/). Por exemplo: "por que RabbitMQ e não Redis?".
4. **Segredos nunca vão para o Git.** Use o `.env` (que está no `.gitignore`).
5. **Ao fechar uma fase, atualize este README** (diagrama, stack e roadmap).

## Licença

[Apache 2.0](LICENSE)
