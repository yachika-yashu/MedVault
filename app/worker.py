import os
import asyncio
from arq.connections import RedisSettings
from app.core.config import REDIS_URL

async def startup(ctx):
    """Initialize resources for the worker."""
    print("Worker starting up...")

async def shutdown(ctx):
    """Cleanup resources."""
    print("Worker shutting down...")

class WorkerSettings:
    """Configuration for the arq worker."""
    functions = [] # Add background functions here
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", REDIS_URL))
    on_startup = startup
    on_shutdown = shutdown
    # Optionally add more settings like job_timeout, keep_result, etc.
