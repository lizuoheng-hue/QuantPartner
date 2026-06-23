from datetime import date

from app.market_data import MarketDataError, load_real_market
from app.templates import ema_template


MARKETS = [
    ("CN_A", "000300.SH"),
    ("HK", "HSI.HK"),
    ("US", "SPY.US"),
]


def main() -> int:
    failed = False
    for market, benchmark in MARKETS:
        spec = ema_template()
        spec.universe.market = market
        spec.universe.index = benchmark
        spec.backtest.benchmark = benchmark
        spec.backtest.end_date = date.today()
        try:
            dataset = load_real_market(spec)
            print(f"{market}: {len(dataset.frame)} rows, {dataset.frame.index[0].date()}..{dataset.frame.index[-1].date()}, snapshot={dataset.snapshot_id}")
            print(f"  {dataset.cache_path}")
        except MarketDataError as exc:
            failed = True
            print(f"{market}: FAILED - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
