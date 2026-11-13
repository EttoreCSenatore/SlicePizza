"""Entry point: ``python -m app.main``."""

import logging
import signal
import sys

from .config import ConfigError, load_settings
from .consumer import Consumer, Notifier
from .telegram import LogSender, TelegramSender

logger = logging.getLogger("app")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # pika logs connection errors with tracebacks on every retry; the worker
    # logs one line per failure itself.
    logging.getLogger("pika").setLevel(logging.CRITICAL)

    try:
        settings = load_settings()
    except ConfigError as error:
        logger.error("%s", error)
        return 2

    pizzeria_chat = settings.telegram_pizzeria_chat_id
    if settings.telegram_bot_token:
        sender = TelegramSender(settings.telegram_bot_token, settings.telegram_api_url)
        if not pizzeria_chat:
            logger.warning("TELEGRAM_PIZZERIA_CHAT_ID is not set: the pizzeria chat gets nothing.")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is not set: messages are logged, not sent.")
        sender = LogSender()
        # Show the pizzeria's messages in the log even without a chat id.
        pizzeria_chat = pizzeria_chat or "<pizzeria chat>"

    consumer = Consumer(settings, Notifier(sender, pizzeria_chat))

    def stop(signum, _frame):
        logger.info("Received %s, stopping after the current message", signal.Signals(signum).name)
        consumer.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    logger.info("Starting with %r", settings)
    consumer.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
