import logging
from typing import Optional

import redis.asyncio as redis

from app.core.config import REDIS_URL

logger = logging.getLogger("clinical_intelligence.redis")

_redis_client: Optional[redis.Redis] = None

# detailed explanation of the all the functions refer to the `code_understanding.md` file. 

def get_redis_client() -> redis.Redis:
    """Return a shared async Redis client for exact-cache operations."""
    global _redis_client
    if _redis_client is None:
        # decode_responses keeps JSON payload handling simple and readable.
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


async def init_redis() -> bool:
    """
    Attempt to create a connection with Redis during startup.
    If connection is established, return True. Otherwise, log a warning and return False.
    """
    client = get_redis_client()
    try:
        await client.ping()
        logger.info("REDIS: Connected to exact-cache backend.")
        return True
    except Exception as exc:
        logger.warning("REDIS: Unavailable during startup, exact cache disabled. %s", exc)
        return False


async def close_redis() -> None:
    """Close the shared Redis connection cleanly on shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
