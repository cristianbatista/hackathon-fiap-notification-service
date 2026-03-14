import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Callable, Awaitable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from src.core.config import settings

QUEUE_NAME = "notifications"

logger = logging.getLogger("notification-service")

# In-memory retry counter — resets on service restart (by design, CHK010)
_retry_counts: dict[str, int] = defaultdict(int)

MessageHandler = Callable[[str, str, str, str, str | None], Awaitable[None]]


async def _connect_with_backoff(max_attempts: int = 10) -> aio_pika.abc.AbstractRobustConnection:
    delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            # Use connect (not connect_robust) here to avoid unawaited
            # RobustConnection.close() warnings on failed attempts.
            # connect_robust is used inside start_consumer for auto-reconnect.
            conn = await aio_pika.connect(settings.rabbitmq_url)
            await conn.close()
            # Broker is reachable — now create the robust connection
            return await aio_pika.connect_robust(settings.rabbitmq_url)
        except Exception as exc:  # noqa: BLE001
            if attempt == max_attempts:
                raise
            logger.warning(
                "Broker connection failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise RuntimeError("Unreachable")  # pragma: no cover


async def start_consumer(on_message: MessageHandler, stop_event: asyncio.Event) -> None:
    """Start consuming from the notifications queue until stop_event is set.

    on_message(job_id, user_id, user_email, status, error_message) is called for
    each message. Raises EmailSendError on failure — which triggers nack+retry.
    After MAX_NOTIFICATION_RETRIES failures the message is dead-lettered.
    """
    connection = await _connect_with_backoff()

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)

        queue = await channel.declare_queue(QUEUE_NAME, durable=True)

        async def _process(message: AbstractIncomingMessage) -> None:
            delivery_tag = message.delivery_tag
            try:
                body = json.loads(message.body.decode())
                job_id = body["job_id"]
                user_id = body["user_id"]
                user_email = body["user_email"]
                status = body["status"]
                error_message = body.get("error_message")
            except (KeyError, json.JSONDecodeError) as exc:
                logger.error("Invalid message format: %s", exc)
                await message.nack(requeue=False)
                return

            try:
                await on_message(job_id, user_id, user_email, status, error_message)
                _retry_counts.pop(job_id, None)
                await message.ack()
            except Exception as exc:  # noqa: BLE001
                _retry_counts[job_id] += 1
                attempts = _retry_counts[job_id]

                if attempts >= settings.max_notification_retries:
                    logger.error(
                        json.dumps({
                            "event": "notification_failed_permanently",
                            "job_id": job_id,
                            "attempts": attempts,
                            "error": str(exc),
                        })
                    )
                    _retry_counts.pop(job_id, None)
                    await message.nack(requeue=False)
                else:
                    logger.warning(
                        "Notification failed (attempt %d/%d): %s — requeuing",
                        attempts,
                        settings.max_notification_retries,
                        exc,
                        extra={"job_id": job_id},
                    )
                    await message.nack(requeue=True)

        await queue.consume(_process)
        logger.info("Notification consumer started — listening on '%s'", QUEUE_NAME)
        await stop_event.wait()
        logger.info("Stop event received — shutting down consumer")
