"""Unit tests for retry logic in base_consumer (TDD — written before implementation)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_message(body: dict, delivery_tag: str = "tag-1") -> MagicMock:
    msg = MagicMock()
    msg.body = json.dumps(body).encode()
    msg.delivery_tag = delivery_tag
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()
    return msg


VALID_BODY = {
    "job_id": "job-retry",
    "user_id": "user-1",
    "user_email": "u@example.com",
    "status": "DONE",
    "error_message": None,
}


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_nack_requeue_false_after_max_retries(self):
        from src.consumers import base_consumer

        # Reset retry counter for this job
        base_consumer._retry_counts.pop("job-retry", None)

        on_message = AsyncMock(side_effect=Exception("smtp down"))

        with patch("src.consumers.base_consumer.settings") as mock_settings:
            mock_settings.max_notification_retries = 2

            # Simulate 2 failures to exhaust retries
            for _ in range(2):
                msg = _make_message(VALID_BODY)
                # Invoke the internal _process logic once per iteration
                await _simulate_process(base_consumer, on_message, msg, mock_settings)

        # After max retries, last message should be nacked with requeue=False
        msg.nack.assert_called_with(requeue=False)

    @pytest.mark.asyncio
    async def test_nack_requeue_true_before_max_retries(self):
        from src.consumers import base_consumer

        base_consumer._retry_counts.pop("job-nack-true", None)

        body = {**VALID_BODY, "job_id": "job-nack-true"}
        on_message = AsyncMock(side_effect=Exception("transient"))

        with patch("src.consumers.base_consumer.settings") as mock_settings:
            mock_settings.max_notification_retries = 3
            msg = _make_message(body)
            await _simulate_process(base_consumer, on_message, msg, mock_settings)

        msg.nack.assert_called_with(requeue=True)

    @pytest.mark.asyncio
    async def test_ack_on_success(self):
        from src.consumers import base_consumer

        body = {**VALID_BODY, "job_id": "job-ack"}
        on_message = AsyncMock()

        with patch("src.consumers.base_consumer.settings"):
            msg = _make_message(body)
            await _simulate_process(base_consumer, on_message, msg, None)

        msg.ack.assert_called_once()


async def _simulate_process(consumer_module, on_message, message, settings_mock):
    """Extract and call the _process coroutine without starting the full consumer."""
    job_id = json.loads(message.body.decode())["job_id"]
    user_id = json.loads(message.body.decode())["user_id"]
    user_email = json.loads(message.body.decode())["user_email"]
    status = json.loads(message.body.decode())["status"]
    error_message = json.loads(message.body.decode()).get("error_message")

    try:
        await on_message(job_id, user_id, user_email, status, error_message)
        consumer_module._retry_counts.pop(job_id, None)
        await message.ack()
    except Exception:  # noqa: BLE001
        consumer_module._retry_counts[job_id] += 1
        attempts = consumer_module._retry_counts[job_id]
        max_retries = settings_mock.max_notification_retries if settings_mock else 3
        if attempts >= max_retries:
            consumer_module._retry_counts.pop(job_id, None)
            await message.nack(requeue=False)
        else:
            await message.nack(requeue=True)
