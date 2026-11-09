# Notification worker

> ⏳ **Starts in Phase 3.** See the [ROADMAP](../docs/ROADMAP.md#phase-3-customers-want-to-know-when-their-pizza-is-on-the-way).

A Python service that listens to the RabbitMQ queue. When an `order.status_changed` event arrives, it sends the customer a message on Telegram.

Why a separate service instead of the API itself? See "Order flow" in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#order-flow).
