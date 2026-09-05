"""Cache layer. Redis when configured, in-process dict otherwise.

Redis is a cache, never the source of truth: if it disappears the app still works,
just slower. Every read falls back to Postgres.
"""

import json
import time
from typing import Any

from mastery.common.config import get_settings
from mastery.common.logging import get_logger

log = get_logger(__name__)


class _MemoryCache:
    """Fallback used in local dev and tests. Not shared across processes."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl: int) -> None:
        self._store[key] = (time.time() + ttl, value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def ping(self) -> bool:
        return True


class Cache:
    def __init__(self) -> None:
        self._backend: Any = _MemoryCache()
        self.kind = "memory"

    async def connect(self) -> None:
        url = get_settings().redis_url
        if not url:
            log.info("cache.using_memory", reason="REDIS_URL not set")
            return
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(url, decode_responses=True)
            await client.ping()
            self._backend = client
            self.kind = "redis"
            log.info("cache.connected", backend="redis")
        except Exception as exc:  # pragma: no cover - depends on external service
            log.warning("cache.redis_unavailable", error=str(exc), fallback="memory")

    async def get_json(self, key: str) -> Any | None:
        raw = await self._backend.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ttl: int = 3600) -> None:
        await self._backend.set(key, json.dumps(value), ttl)

    async def delete(self, key: str) -> None:
        await self._backend.delete(key)

    async def healthy(self) -> bool:
        try:
            await self._backend.ping()
            return True
        except Exception:  # pragma: no cover
            return False


cache = Cache()
