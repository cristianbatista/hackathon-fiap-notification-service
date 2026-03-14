"""Coverage tests for base_consumer, logging, and main modules."""

import asyncio
import json
import logging
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── src/core/logging.py ──────────────────────────────────────────────────────


class TestJSONFormatter:
    def test_format_minimal(self):
        from src.core.logging import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        result = json.loads(formatter.format(record))
        assert result["message"] == "hello"
        assert result["level"] == "INFO"
        assert result["service"] == "notification-service"
        assert "timestamp" in result
        assert "trace_id" in result

    def test_format_with_job_id_and_recipient(self):
        from src.core.logging import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="sent",
            args=(),
            exc_info=None,
        )
        record.job_id = "job-1"
        record.recipient = "user@example.com"
        result = json.loads(formatter.format(record))
        assert result["job_id"] == "job-1"
        assert result["recipient_domain"] == "example.com"

    def test_format_recipient_without_at(self):
        from src.core.logging import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="sent",
            args=(),
            exc_info=None,
        )
        record.recipient = "no-at-sign"
        result = json.loads(formatter.format(record))
        assert result["recipient_domain"] == "unknown"

    def test_format_with_exc_info(self):
        from src.core.logging import JSONFormatter

        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="err",
            args=(),
            exc_info=exc_info,
        )
        result = json.loads(formatter.format(record))
        assert "exception" in result


def test_get_logger_returns_logger_with_handler():
    from src.core.logging import get_logger

    logger = get_logger("test-ns-notif")
    assert isinstance(logger, logging.Logger)
    # Calling again should not add duplicate handlers
    logger2 = get_logger("test-ns-notif")
    assert len(logger2.handlers) == 1


def test_setup_logging_sets_level():
    from src.core.logging import setup_logging

    setup_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_setup_logging_idempotent():
    """setup_logging called twice must not add duplicate handlers."""
    from src.core.logging import setup_logging

    root = logging.getLogger()
    before = len(root.handlers)
    setup_logging("INFO")
    setup_logging("INFO")
    assert len(root.handlers) == before


# ─── src/main.py ─────────────────────────────────────────────────────────────


class TestOnMessage:
    @pytest.mark.asyncio
    async def test_delegates_to_send_notification_done(self):
        from src.main import _on_message

        with patch("src.main.send_notification", new_callable=AsyncMock) as mock_send:
            await _on_message("job-1", "user-1", "u@example.com", "DONE", None)
            mock_send.assert_called_once_with("job-1", "u@example.com", "DONE", None)

    @pytest.mark.asyncio
    async def test_delegates_to_send_notification_error(self):
        from src.main import _on_message

        with patch("src.main.send_notification", new_callable=AsyncMock) as mock_send:
            await _on_message("job-2", "user-2", "u@example.com", "ERROR", "oops")
            mock_send.assert_called_once_with("job-2", "u@example.com", "ERROR", "oops")


# ─── src/consumers/base_consumer.py ──────────────────────────────────────────


class TestConnectWithBackoff:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        from src.consumers.base_consumer import _connect_with_backoff

        mock_conn = AsyncMock()
        mock_robust = AsyncMock()
        with patch(
            "src.consumers.base_consumer.aio_pika.connect", return_value=mock_conn
        ):
            with patch(
                "src.consumers.base_consumer.aio_pika.connect_robust",
                return_value=mock_robust,
            ):
                result = await _connect_with_backoff(max_attempts=3)

        mock_conn.close.assert_called_once()
        assert result is mock_robust

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        from src.consumers.base_consumer import _connect_with_backoff

        with patch(
            "src.consumers.base_consumer.aio_pika.connect",
            side_effect=Exception("refused"),
        ):
            with patch(
                "src.consumers.base_consumer.asyncio.sleep", new_callable=AsyncMock
            ):
                with pytest.raises(Exception, match="refused"):
                    await _connect_with_backoff(max_attempts=2)

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        from src.consumers.base_consumer import _connect_with_backoff

        call_count = 0

        async def flaky_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("transient")
            return AsyncMock()

        mock_robust = AsyncMock()
        with patch(
            "src.consumers.base_consumer.aio_pika.connect", side_effect=flaky_connect
        ):
            with patch(
                "src.consumers.base_consumer.aio_pika.connect_robust",
                return_value=mock_robust,
            ):
                with patch(
                    "src.consumers.base_consumer.asyncio.sleep",
                    new_callable=AsyncMock,
                ):
                    result = await _connect_with_backoff(max_attempts=3)

        assert result is mock_robust


class TestProcessCallback:
    """Test the _process inner coroutine by running start_consumer with a
    fully-mocked aio_pika connection and capturing the registered callback."""

    def _make_connection(self, consume_callback_holder: list):
        """Build a mocked aio_pika connection that captures queue.consume."""
        queue = AsyncMock()

        async def capture_consume(callback):
            consume_callback_holder.append(callback)

        queue.consume = capture_consume

        channel = AsyncMock()
        channel.declare_queue = AsyncMock(return_value=queue)
        channel.set_qos = AsyncMock()

        connection = AsyncMock()
        connection.__aenter__ = AsyncMock(return_value=connection)
        connection.__aexit__ = AsyncMock(return_value=False)
        connection.channel = AsyncMock(return_value=channel)
        return connection

    def _make_msg(self, body: dict) -> MagicMock:
        msg = MagicMock()
        msg.body = json.dumps(body).encode()
        msg.ack = AsyncMock()
        msg.nack = AsyncMock()
        return msg

    @pytest.mark.asyncio
    async def test_valid_message_acked(self):
        from src.consumers import base_consumer

        callbacks: list = []
        conn = self._make_connection(callbacks)
        on_message = AsyncMock()
        stop_event = asyncio.Event()

        base_consumer._retry_counts.pop("p-job-1", None)

        with patch(
            "src.consumers.base_consumer._connect_with_backoff", return_value=conn
        ):
            task = asyncio.create_task(
                base_consumer.start_consumer(on_message, stop_event)
            )
            await asyncio.sleep(0)
            assert callbacks, "consume callback not registered"

            msg = self._make_msg(
                {
                    "job_id": "p-job-1",
                    "user_id": "u1",
                    "user_email": "x@y.com",
                    "status": "DONE",
                    "error_message": None,
                }
            )
            await callbacks[0](msg)
            msg.ack.assert_called_once()

            stop_event.set()
            await task

    @pytest.mark.asyncio
    async def test_invalid_json_nacked_no_requeue(self):
        from src.consumers import base_consumer

        callbacks: list = []
        conn = self._make_connection(callbacks)
        on_message = AsyncMock()
        stop_event = asyncio.Event()

        with patch(
            "src.consumers.base_consumer._connect_with_backoff", return_value=conn
        ):
            task = asyncio.create_task(
                base_consumer.start_consumer(on_message, stop_event)
            )
            await asyncio.sleep(0)

            msg = MagicMock()
            msg.body = b"not-json{"
            msg.ack = AsyncMock()
            msg.nack = AsyncMock()
            await callbacks[0](msg)

            msg.nack.assert_called_once_with(requeue=False)
            stop_event.set()
            await task

    @pytest.mark.asyncio
    async def test_missing_key_nacked_no_requeue(self):
        from src.consumers import base_consumer

        callbacks: list = []
        conn = self._make_connection(callbacks)
        on_message = AsyncMock()
        stop_event = asyncio.Event()

        with patch(
            "src.consumers.base_consumer._connect_with_backoff", return_value=conn
        ):
            task = asyncio.create_task(
                base_consumer.start_consumer(on_message, stop_event)
            )
            await asyncio.sleep(0)

            msg = self._make_msg({"bad": "key"})
            await callbacks[0](msg)

            msg.nack.assert_called_once_with(requeue=False)
            stop_event.set()
            await task

    @pytest.mark.asyncio
    async def test_on_message_exception_requeues_before_max_retries(self):
        from src.consumers import base_consumer

        callbacks: list = []
        conn = self._make_connection(callbacks)
        on_message = AsyncMock(side_effect=Exception("transient"))
        stop_event = asyncio.Event()

        base_consumer._retry_counts.pop("p-job-2", None)

        with patch(
            "src.consumers.base_consumer._connect_with_backoff", return_value=conn
        ):
            with patch("src.consumers.base_consumer.settings") as ms:
                ms.max_notification_retries = 3
                task = asyncio.create_task(
                    base_consumer.start_consumer(on_message, stop_event)
                )
                await asyncio.sleep(0)

                msg = self._make_msg(
                    {
                        "job_id": "p-job-2",
                        "user_id": "u1",
                        "user_email": "x@y.com",
                        "status": "DONE",
                        "error_message": None,
                    }
                )
                await callbacks[0](msg)
                msg.nack.assert_called_with(requeue=True)

                stop_event.set()
                await task

    @pytest.mark.asyncio
    async def test_on_message_exception_deadletters_at_max_retries(self):
        from src.consumers import base_consumer

        callbacks: list = []
        conn = self._make_connection(callbacks)
        on_message = AsyncMock(side_effect=Exception("permanent"))
        stop_event = asyncio.Event()

        base_consumer._retry_counts.pop("p-job-3", None)

        with patch(
            "src.consumers.base_consumer._connect_with_backoff", return_value=conn
        ):
            with patch("src.consumers.base_consumer.settings") as ms:
                ms.max_notification_retries = 1
                task = asyncio.create_task(
                    base_consumer.start_consumer(on_message, stop_event)
                )
                await asyncio.sleep(0)

                msg = self._make_msg(
                    {
                        "job_id": "p-job-3",
                        "user_id": "u1",
                        "user_email": "x@y.com",
                        "status": "DONE",
                        "error_message": None,
                    }
                )
                await callbacks[0](msg)
                msg.nack.assert_called_with(requeue=False)

                stop_event.set()
                await task
