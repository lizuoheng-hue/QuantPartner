import json
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from .config import get_settings


@lru_cache
def redis_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
    )


def redis_health() -> str:
    try:
        return "connected" if redis_client().ping() else "unavailable"
    except RedisError:
        return "unavailable"


def cache_task_state(task_id: str, state: dict) -> None:
    try:
        redis_client().setex(f"backtest:{task_id}", 86_400, json.dumps(state, ensure_ascii=False))
    except RedisError:
        # PostgreSQL/SQLite remains the source of truth in demo mode.
        return


def clear_task_cache() -> None:
    try:
        client = redis_client()
        keys = list(client.scan_iter(match="backtest:*", count=100))
        if keys:
            client.delete(*keys)
    except RedisError:
        return


BACKTEST_PENDING = "queue:backtests:pending"
BACKTEST_PROCESSING = "queue:backtests:processing"


def enqueue_backtest(task_id: str) -> None:
    redis_client().lpush(BACKTEST_PENDING, task_id)
