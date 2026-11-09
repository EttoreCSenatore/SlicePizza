# ADRs: registros de decisões de arquitetura

Um ADR (*Architecture Decision Record*) é um texto curto que registra **uma decisão importante e o porquê dela**. Daqui a seis meses, ninguém vai lembrar por que escolhemos RabbitMQ em vez de Redis. O ADR lembra.

## Como criar um ADR

1. Copie o [template](0000-template.md) para um arquivo novo com o próximo número: `0002-titulo-curto.md`.
2. Preencha as seções. Meia página é suficiente.
3. Adicione uma linha na tabela abaixo.
4. Abra um Pull Request.

Um ADR aceito não é editado. Se a decisão mudar, crie um ADR novo e marque o antigo como "Substituído por 00XX".

## Lista de ADRs

| Nº | Título | Status |
|---|---|---|
| [0001](0001-monorepo.md) | Usar um único repositório (monorepo) | Aceito |
