import logging
import signal

from redis.exceptions import RedisError

from .cache import BACKTEST_PENDING, BACKTEST_PROCESSING, redis_client
from .db import init_db
from .main import execute_backtest


logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","message":"%(message)s"}')
logger = logging.getLogger("quantpartner.worker")
running = True


def stop(*_args) -> None:
    global running
    running = False


def recover_interrupted_jobs() -> None:
    client = redis_client()
    while True:
        task_id = client.rpoplpush(BACKTEST_PROCESSING, BACKTEST_PENDING)
        if not task_id:
            return


def run() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    init_db()
    recover_interrupted_jobs()
    client = redis_client()
    logger.info("backtest_worker_started")
    while running:
        try:
            task_id = client.brpoplpush(BACKTEST_PENDING, BACKTEST_PROCESSING, timeout=2)
            if not task_id:
                continue
            execute_backtest(task_id)
            client.lrem(BACKTEST_PROCESSING, 1, task_id)
        except RedisError:
            logger.exception("backtest_worker_redis_error")


if __name__ == "__main__":
    run()
