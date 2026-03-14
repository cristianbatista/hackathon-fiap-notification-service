import redis.asyncio as aioredis

from src.core.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def set_dedup_key(job_id: str) -> bool:
    """Set the deduplication key for a job.

    Uses SET ... NX EX for atomicity.
    Returns True if the key was set (first time), False if it already existed.
    """
    r = get_redis()
    result = await r.set(
        f"notif:sent:{job_id}",
        "1",
        ex=settings.notification_dedup_ttl_seconds,
        nx=True,
    )
    return result is True


async def has_dedup_key(job_id: str) -> bool:
    """Return True if the deduplication key exists (notification already sent)."""
    r = get_redis()
    return bool(await r.exists(f"notif:sent:{job_id}"))
