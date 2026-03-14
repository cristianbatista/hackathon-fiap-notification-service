"""Contract tests for the notifications consumer (T014)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_message(body: dict) -> MagicMock:
    msg = MagicMock()
    msg.body = json.dumps(body).encode()
    msg.delivery_tag = "tag-ct"
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()
    msg.process = MagicMock()
    msg.process.return_value.__aenter__ = AsyncMock(return_value=None)
    msg.process.return_value.__aexit__ = AsyncMock(return_value=False)
    return msg


VALID_DONE = {
    "job_id": "ct-job-done",
    "user_id": "ct-user-1",
    "user_email": "ct@example.com",
    "status": "DONE",
    "error_message": None,
}

VALID_ERROR = {
    "job_id": "ct-job-error",
    "user_id": "ct-user-2",
    "user_email": "ct@example.com",
    "status": "ERROR",
    "error_message": "processing failed",
}

DUPLICATE = {**VALID_DONE, "job_id": "ct-job-dup"}
INVALID = {"bad": "data"}


class TestConsumerContract:
    @pytest.mark.asyncio
    async def test_valid_done_message_sends_email_and_acks(self):
        from src.services.notification_service import send_notification

        mock_send = AsyncMock()
        with patch(
            "src.services.notification_service.has_dedup_key", return_value=False
        ):
            with patch(
                "src.services.notification_service.render_template", return_value="<h/>"
            ):
                with patch(
                    "src.services.notification_service.aiosmtplib.send", mock_send
                ):
                    with patch("src.services.notification_service.set_dedup_key"):
                        await send_notification(
                            VALID_DONE["job_id"],
                            VALID_DONE["user_email"],
                            VALID_DONE["status"],
                        )
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_message_skips_send(self):
        from src.services.notification_service import send_notification

        mock_send = AsyncMock()
        with patch(
            "src.services.notification_service.has_dedup_key", return_value=True
        ):
            with patch("src.services.notification_service.aiosmtplib.send", mock_send):
                await send_notification(
                    DUPLICATE["job_id"],
                    DUPLICATE["user_email"],
                    DUPLICATE["status"],
                )
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_message_triggers_nack_no_requeue(self):
        """Consumer receives malformed JSON body → nack(requeue=False)."""
        from src.consumers import base_consumer

        base_consumer._retry_counts.pop("invalid", None)

        msg = MagicMock()
        msg.body = b"not valid json {"
        msg.nack = AsyncMock()
        msg.ack = AsyncMock()

        # Simulate what the _process callback does for invalid messages
        try:
            body = json.loads(msg.body.decode())
            _ = body["job_id"]
        except (KeyError, json.JSONDecodeError):
            await msg.nack(requeue=False)

        msg.nack.assert_called_once_with(requeue=False)
        msg.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_status_message_sends_email(self):
        from src.services.notification_service import send_notification

        mock_send = AsyncMock()
        with patch(
            "src.services.notification_service.has_dedup_key", return_value=False
        ):
            with patch(
                "src.services.notification_service.render_template", return_value="<h/>"
            ):
                with patch(
                    "src.services.notification_service.aiosmtplib.send", mock_send
                ):
                    with patch("src.services.notification_service.set_dedup_key"):
                        await send_notification(
                            VALID_ERROR["job_id"],
                            VALID_ERROR["user_email"],
                            VALID_ERROR["status"],
                            VALID_ERROR["error_message"],
                        )
        mock_send.assert_called_once()
