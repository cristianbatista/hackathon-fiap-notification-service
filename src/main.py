"""Entry point for the notification-service worker."""

import asyncio
import logging
import signal

from src.consumers.base_consumer import start_consumer
from src.core.config import settings
from src.core.logging import setup_logging
from src.core.metrics import start_metrics_server
from src.services.notification_service import send_notification

logger = logging.getLogger("notification-service")


async def _on_message(
    job_id: str,
    user_id: str,  # noqa: ARG001
    user_email: str,
    status: str,
    error_message: str | None,
) -> None:
    """Bridge between the consumer and the notification service."""
    await send_notification(job_id, user_email, status, error_message)


async def main() -> None:
    setup_logging(settings.log_level)

    logger.info("Starting notification-service")
    start_metrics_server()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    await start_consumer(_on_message, stop_event)
    logger.info("notification-service stopped")


if __name__ == "__main__":
    asyncio.run(main())
