# 0001: Usar um único repositório (monorepo)

- **Status:** Aceito
- **Data:** 2026-11-09
- **Fase:** 1

## Contexto

O sistema vai ter vários serviços (API, worker, frontend) e a infraestrutura (Terraform, Ansible, Kubernetes). Precisamos decidir se cada um fica em um repositório separado ou se tudo fica junto.

## Opções consideradas

1. **Um repositório por serviço**: cada serviço tem seu próprio histórico e pipeline. Por outro lado, uma mudança que mexe na API e no worker vira dois Pull Requests, e é preciso coordenar versões entre repositórios.
2. **Monorepo**: tudo em um repositório, separado por pastas. Uma mudança que atravessa vários serviços vira um único Pull Request. Por outro lado, o pipeline precisa saber qual pasta mudou para não rodar tudo sempre.

## Decisão

Monorepo, com uma pasta por componente: `api/`, `worker/`, `frontend/`, `infra/`.

O projeto é pequeno, tem poucas pessoas e é de estudo. Ver tudo num lugar só facilita entender como as partes se conectam.

## Consequências

- O `docker-compose.yml` na raiz vai subir o sistema inteiro com um comando.
- Na Fase 4, o pipeline do GitHub Actions deve usar filtros de caminho (`paths:`) para só testar e publicar o serviço que mudou.
- Se algum serviço crescer muito, podemos separá-lo depois com um novo ADR.
