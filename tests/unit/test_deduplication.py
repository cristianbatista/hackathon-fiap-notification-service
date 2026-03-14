"""Unit tests for Redis deduplication logic (TDD — written before implementation)."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.redis_client import has_dedup_key, set_dedup_key


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_has_dedup_key_returns_false_when_not_set(self):
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0
        with patch("src.core.redis_client.get_redis", return_value=mock_redis):
            assert await has_dedup_key("job-123") is False

    @pytest.mark.asyncio
    async def test_has_dedup_key_returns_true_when_set(self):
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1
        with patch("src.core.redis_client.get_redis", return_value=mock_redis):
            assert await has_dedup_key("job-123") is True

    @pytest.mark.asyncio
    async def test_set_dedup_key_returns_true_on_first_call(self):
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True  # NX succeeded
        with patch("src.core.redis_client.get_redis", return_value=mock_redis):
            assert await set_dedup_key("job-123") is True

    @pytest.mark.asyncio
    async def test_set_dedup_key_returns_false_if_already_exists(self):
        mock_redis = AsyncMock()
        mock_redis.set.return_value = None  # NX failed — key already exists
        with patch("src.core.redis_client.get_redis", return_value=mock_redis):
            assert await set_dedup_key("job-123") is False

    @pytest.mark.asyncio
    async def test_set_dedup_key_uses_nx_semantics(self):
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True
        with patch("src.core.redis_client.get_redis", return_value=mock_redis):
            await set_dedup_key("job-abc")
        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        # nx=True must be passed
        assert call_kwargs.kwargs.get("nx") is True or True in call_kwargs.args

    @pytest.mark.asyncio
    async def test_set_dedup_key_uses_configurable_ttl(self):
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True
        with patch("src.core.redis_client.get_redis", return_value=mock_redis):
            with patch("src.core.redis_client.settings") as mock_settings:
                mock_settings.notification_dedup_ttl_seconds = 3600
                await set_dedup_key("job-ttl")
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("ex") == 3600

    @pytest.mark.asyncio
    async def test_redis_key_format(self):
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True
        with patch("src.core.redis_client.get_redis", return_value=mock_redis):
            await set_dedup_key("my-job-id")
        key_used = mock_redis.set.call_args.args[0]
        assert key_used == "notif:sent:my-job-id"
