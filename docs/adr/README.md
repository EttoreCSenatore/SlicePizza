# ADRs: Architecture Decision Records

An ADR (*Architecture Decision Record*) is a short document that records **an important decision and why it was made**. Six months from now, nobody will remember why we picked RabbitMQ over Redis. The ADR will.

## How to write an ADR

1. Copy the [template](0000-template.md) to a new file with the next number: `0002-short-title.md`.
2. Fill in the sections. Half a page is enough.
3. Add a row to the table below.
4. Open a Pull Request.

An accepted ADR is not edited. If the decision changes, write a new ADR and mark the old one as "Superseded by 00XX".

## ADR list

| No. | Title | Status |
|---|---|---|
| [0001](0001-monorepo.md) | Use a single repository (monorepo) | Accepted |
