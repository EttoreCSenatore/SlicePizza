# Worker de notificações

> ⏳ **Começa na Fase 3.** Veja o [ROADMAP](../docs/ROADMAP.md#fase-3-o-cliente-quer-saber-quando-a-pizza-sai).

Serviço em Python que fica escutando a fila do RabbitMQ. Quando chega um evento `pedido.status_alterado`, ele envia uma mensagem para o cliente pelo Telegram.

Por que um serviço separado, e não a própria API? Veja o "Fluxo de um pedido" em [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#fluxo-de-um-pedido).
