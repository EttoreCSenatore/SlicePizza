# Arquitetura

Este documento descreve **para onde o sistema vai**. Nem tudo existe ainda: veja a coluna "Fase" para saber quando cada parte entra.

## Visão geral

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

## Componentes

| Componente | Pasta | Responsabilidade | Fase |
|---|---|---|---|
| API de pedidos | `api/` | Cardápio, criar pedido, consultar e mudar status | 1 |
| Postgres | (imagem oficial) | Guarda pizzas, pedidos e clientes | 1 |
| Site do cardápio | `frontend/` | Página pública onde o cliente faz o pedido | 2 |
| Proxy reverso (Caddy) | `infra/` | Recebe o tráfego HTTPS e encaminha para a API | 2 |
| RabbitMQ | (imagem oficial) | Fila de eventos de pedido | 3 |
| Worker de notificações | `worker/` | Lê a fila e avisa o cliente pelo Telegram | 3 |
| Painel da cozinha | `frontend/` | A cozinha vê os pedidos e muda o status | 3 |
| Redis | (imagem oficial) | Cache do cardápio | 7 |

## Fluxo de um pedido

1. O cliente abre `www.seudominio.com.br` e escolhe as pizzas.
2. O site chama `POST /pedidos` na API. O pedido é salvo no Postgres com status `recebido`.
3. A cozinha vê o pedido no painel e muda o status para `em_preparo`.
4. A API salva o novo status e publica um evento `pedido.status_alterado` na fila.
5. O worker lê o evento e manda a mensagem no Telegram do cliente.
6. O mesmo se repete para `saiu_para_entrega` e `entregue`.

Por que usar uma fila no passo 4, em vez de a API chamar o Telegram direto? Se o Telegram estiver lento ou fora do ar, a API continua respondendo rápido, e as mensagens esperam na fila até o worker conseguir enviá-las.

## Status do pedido

```
recebido ──► em_preparo ──► saiu_para_entrega ──► entregue
    │
    └──► cancelado
```

## DNS planejado (Fase 2)

| Registro | Tipo | Aponta para |
|---|---|---|
| `www.seudominio.com.br` | CNAME | CDN do site estático |
| `api.seudominio.com.br` | A | IP da máquina virtual |
| `admin.seudominio.com.br` | A | IP da máquina virtual |
| `staging.seudominio.com.br` | A | IP da máquina virtual de homologação (Fase 4) |

## Portas locais planejadas (Docker Compose)

| Serviço | Porta |
|---|---|
| API | 8000 |
| Postgres | 5432 |
| RabbitMQ (Fase 3) | 5672, painel em 15672 |
| Grafana (Fase 5) | 3000 |
