# API de pedidos

> ⏳ **Começa na Fase 1.** Veja o [ROADMAP](../docs/ROADMAP.md#fase-1-quero-ver-funcionando-no-seu-computador).

API em **Python + FastAPI** que expõe o cardápio e recebe os pedidos da pizzaria.

## Rotas planejadas

| Método | Rota | O que faz |
|---|---|---|
| GET | `/health` | Diz se a API está viva (usado pelo Docker e pelo monitoramento) |
| GET | `/cardapio` | Lista as pizzas |
| POST | `/pedidos` | Cria um pedido |
| GET | `/pedidos/{id}` | Consulta um pedido |
| PATCH | `/pedidos/{id}/status` | Muda o status do pedido |

## Estrutura sugerida

```
api/
├── app/
│   └── main.py            # rotas da API
├── tests/
│   └── test_main.py       # testes automatizados (pytest)
├── Dockerfile             # como construir a imagem
├── requirements.txt       # dependências para rodar
└── requirements-dev.txt   # dependências para desenvolver (inclui pytest)
```

## Variáveis de ambiente planejadas

| Variável | Para que serve | Exemplo |
|---|---|---|
| `DATABASE_URL` | Conexão com o Postgres | `postgresql://usuario:senha@db:5432/slicepizza` |

## Links úteis para começar

- [Tutorial do FastAPI (em português)](https://fastapi.tiangolo.com/pt/tutorial/)
- [Docker: primeiros passos](https://docs.docker.com/get-started/)
- [Docker Compose: guia rápido](https://docs.docker.com/compose/gettingstarted/)
