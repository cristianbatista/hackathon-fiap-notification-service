"""Unit tests for notification_service (TDD — written before implementation)."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.metrics import notifications_deduplicated_total, notifications_sent_total


class TestNotificationService:
    @pytest.mark.asyncio
    async def test_skips_send_when_duplicate(self):
        from src.services.notification_service import send_notification

        with (
            patch("src.services.notification_service.has_dedup_key", return_value=True),
            patch("src.services.notification_service.aiosmtplib") as mock_smtp,
        ):
            await send_notification("job-1", "user@example.com", "DONE")
            mock_smtp.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_increments_dedup_counter_when_duplicate(self):
        from src.services.notification_service import send_notification

        before = notifications_deduplicated_total._value.get()
        with patch(
            "src.services.notification_service.has_dedup_key", return_value=True
        ):
            await send_notification("job-dup", "user@example.com", "DONE")
        after = notifications_deduplicated_total._value.get()
        assert after > before

    @pytest.mark.asyncio
    async def test_raises_email_send_error_on_smtp_failure(self):
        from src.services.notification_service import EmailSendError, send_notification

        with (
            patch(
                "src.services.notification_service.has_dedup_key", return_value=False
            ),
            patch(
                "src.services.notification_service.render_template",
                return_value="<html/>",
            ),
            patch(
                "src.services.notification_service.aiosmtplib.send",
                new_callable=AsyncMock,
                side_effect=Exception("SMTP error"),
            ),
        ):
            with pytest.raises(EmailSendError):
                await send_notification("job-fail", "user@example.com", "DONE")

    @pytest.mark.asyncio
    async def test_does_not_set_dedup_key_on_smtp_failure(self):
        from src.services.notification_service import EmailSendError, send_notification

        with (
            patch(
                "src.services.notification_service.has_dedup_key", return_value=False
            ),
            patch(
                "src.services.notification_service.render_template",
                return_value="<html/>",
            ),
            patch(
                "src.services.notification_service.aiosmtplib.send",
                new_callable=AsyncMock,
                side_effect=Exception("SMTP error"),
            ),
            patch("src.services.notification_service.set_dedup_key") as mock_set,
        ):
            with pytest.raises(EmailSendError):
                await send_notification("job-fail2", "user@example.com", "DONE")
            mock_set.assert_not_called()

    @pytest.mark.asyncio
    async def test_sets_dedup_key_on_success(self):
        from src.services.notification_service import send_notification

        with (
            patch(
                "src.services.notification_service.has_dedup_key", return_value=False
            ),
            patch(
                "src.services.notification_service.render_template",
                return_value="<html/>",
            ),
            patch(
                "src.services.notification_service.aiosmtplib.send",
                new_callable=AsyncMock,
            ),
            patch("src.services.notification_service.set_dedup_key") as mock_set,
        ):
            await send_notification("job-ok", "user@example.com", "DONE")
            mock_set.assert_called_once_with("job-ok")

    @pytest.mark.asyncio
    async def test_increments_sent_counter_on_success(self):
        from src.services.notification_service import send_notification

        before = notifications_sent_total.labels(status="success")._value.get()
        with (
            patch(
                "src.services.notification_service.has_dedup_key", return_value=False
            ),
            patch(
                "src.services.notification_service.render_template",
                return_value="<html/>",
            ),
            patch(
                "src.services.notification_service.aiosmtplib.send",
                new_callable=AsyncMock,
            ),
            patch("src.services.notification_service.set_dedup_key"),
        ):
            await send_notification("job-cnt", "user@example.com", "DONE")
        after = notifications_sent_total.labels(status="success")._value.get()
        assert after > before
