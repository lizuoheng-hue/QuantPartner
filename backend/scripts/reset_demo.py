"""Reset local demo strategies, versions, backtests, and Redis task cache."""

from sqlalchemy import delete

from app.cache import clear_task_cache
from app.db import BacktestRecord, SessionLocal, StrategyRecord, VersionRecord, init_db


def main() -> None:
    init_db()
    with SessionLocal() as db:
        db.execute(delete(BacktestRecord))
        db.execute(delete(VersionRecord))
        db.execute(delete(StrategyRecord))
        db.commit()
    clear_task_cache()
    print("QuantPartner demo workspace reset complete.")


if __name__ == "__main__":
    main()
