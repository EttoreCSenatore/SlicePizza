# Como contribuir

## Fluxo de trabalho

1. Atualize a `main`: `git checkout main && git pull`
2. Crie uma branch para a tarefa: `git checkout -b feat/criar-pedido`
3. Faça commits pequenos e com mensagens claras.
4. Envie a branch: `git push -u origin feat/criar-pedido`
5. Abra um Pull Request no GitHub e peça revisão.
6. Depois de aprovado, faça o merge e apague a branch.

**Nunca faça push direto na `main`.**

## Nomes de branch

| Prefixo | Quando usar | Exemplo |
|---|---|---|
| `feat/` | Funcionalidade nova | `feat/criar-pedido` |
| `fix/` | Correção de bug | `fix/status-invalido` |
| `docs/` | Só documentação | `docs/adr-rabbitmq` |
| `infra/` | Docker, Terraform, CI/CD | `infra/pipeline-api` |

## Mensagens de commit

Seguimos o padrão [Conventional Commits](https://www.conventionalcommits.org/pt-br/):

```
feat(api): adiciona rota POST /pedidos
fix(api): impede status inválido no pedido
docs: adiciona ADR sobre RabbitMQ
infra: adiciona Postgres ao docker-compose
```

## Antes de abrir o Pull Request

- [ ] `docker compose up --build` sobe sem erros (a partir da Fase 1)
- [ ] Os testes passam (a partir da Fase 1)
- [ ] Nenhum segredo (senha, token, chave) foi incluído no commit
- [ ] Documentação atualizada, se a mudança afetar como rodar ou usar o sistema
- [ ] Caixas do [ROADMAP](docs/ROADMAP.md) marcadas, se a tarefa estava lá
