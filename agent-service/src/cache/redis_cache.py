"""Redis caching layer for MCP query results.

Key pattern: mcp:{db_name}:{table_name}:{query_hash}
Stores raw SQL results + summary as JSON.
Configurable TTLs per table type.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis.asyncio as redis
import structlog

from src.config import RedisConfig

logger = structlog.get_logger(__name__)

# Table name patterns that get shorter TTLs (live data)
LIVE_DATA_PATTERNS = ("SALES", "ORDERS", "TRANSACTIONS", "EVENTS", "LOGS")
# Table name patterns that get longer TTLs (reference/target data)
REFERENCE_DATA_PATTERNS = ("TARGETS", "CONFIG", "REFERENCE", "LOOKUP", "MASTER")


class RedisCache:
    """Async Redis cache for warehouse query results."""

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._client: redis.Redis | None = None

    async def initialize(self) -> None:
        """Create the Redis connection pool."""
        self._client = redis.Redis(
            host=self._config.host,
            port=self._config.port,
            password=self._config.password or None,
            db=self._config.db,
            max_connections=self._config.max_connections,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
        )
        try:
            await self._client.ping()
            logger.info("redis_connected", host=self._config.host, port=self._config.port)
        except redis.ConnectionError as exc:
            logger.warning("redis_connection_failed", error=str(exc))
            self._client = None

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.aclose()
            logger.info("redis_closed")

    @staticmethod
    def _build_cache_key(db_name: str, table_name: str, query: str) -> str:
        """Build a deterministic cache key from db, table, and query."""
        query_hash = hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]
        return f"mcp:{db_name}:{table_name}:{query_hash}"

    @staticmethod
    def _build_query_hash(query: str) -> str:
        """Build a short hash of the query for keying."""
        return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]

    def _get_ttl(self, table_name: str) -> int:
        """Determine TTL based on table name patterns."""
        upper = table_name.upper()
        if any(pattern in upper for pattern in LIVE_DATA_PATTERNS):
            return self._config.sales_ttl
        if any(pattern in upper for pattern in REFERENCE_DATA_PATTERNS):
            return self._config.targets_ttl
        return self._config.default_ttl

    async def get(self, db_name: str, table_name: str, query: str) -> dict[str, Any] | None:
        """Retrieve cached query result. Returns None on miss or if Redis unavailable."""
        if not self._client:
            return None

        key = self._build_cache_key(db_name, table_name, query)
        try:
            data = await self._client.get(key)
            if data:
                logger.debug("cache_hit", key=key)
                return json.loads(data)
            logger.debug("cache_miss", key=key)
            return None
        except Exception as exc:
            logger.warning("cache_get_error", key=key, error=str(exc))
            return None

    async def put(
        self,
        db_name: str,
        table_name: str,
        query: str,
        result: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Store query result in cache. Returns True on success."""
        if not self._client:
            return False

        key = self._build_cache_key(db_name, table_name, query)
        effective_ttl = ttl if ttl is not None else self._get_ttl(table_name)

        try:
            payload = json.dumps(result, default=str)
            await self._client.setex(key, effective_ttl, payload)
            logger.debug("cache_put", key=key, ttl=effective_ttl)
            return True
        except Exception as exc:
            logger.warning("cache_put_error", key=key, error=str(exc))
            return False

    async def invalidate(self, db_name: str, table_name: str, query: str) -> bool:
        """Remove a specific cache entry."""
        if not self._client:
            return False

        key = self._build_cache_key(db_name, table_name, query)
        try:
            deleted = await self._client.delete(key)
            return deleted > 0
        except Exception as exc:
            logger.warning("cache_invalidate_error", key=key, error=str(exc))
            return False

    async def invalidate_table(self, db_name: str, table_name: str) -> int:
        """Invalidate all cached queries for a specific table."""
        if not self._client:
            return 0

        pattern = f"mcp:{db_name}:{table_name}:*"
        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern, count=100):
                keys.append(key)
            if keys:
                deleted = await self._client.delete(*keys)
                logger.info("cache_table_invalidated", pattern=pattern, deleted=deleted)
                return deleted
            return 0
        except Exception as exc:
            logger.warning("cache_invalidate_table_error", pattern=pattern, error=str(exc))
            return 0

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if not self._client:
            return {"status": "disconnected"}

        try:
            info = await self._client.info("stats")
            keys_count = await self._client.dbsize()
            return {
                "status": "connected",
                "total_keys": keys_count,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "evicted_keys": info.get("evicted_keys", 0),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @property
    def is_connected(self) -> bool:
        """Check if Redis is available."""
        return self._client is not None
