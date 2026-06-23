from app.backtest import run_backtest
from app.templates import ema_template


def test_backtest_is_deterministic_and_has_no_invalid_metrics():
    spec = ema_template()
    first = run_backtest(spec)
    second = run_backtest(spec)
    assert first.strategy_hash == second.strategy_hash
    assert first.metrics == second.metrics
    assert "def strategy" in first.code_preview
    assert len(first.equity_curve) > 50
    assert first.equity_curve[0].value > 0
    assert first.metrics.max_drawdown <= 0
