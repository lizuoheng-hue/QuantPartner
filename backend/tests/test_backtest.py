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
    assert first.diagnosis.summary
    assert len(first.diagnosis.items) == 4
    assert len(first.diagnosis.suggestions) == 3
    assert all(item.metric_refs for item in first.diagnosis.items)


def test_disabled_entry_condition_is_respected():
    spec = ema_template()
    spec.entry.conditions[0].enabled = False
    result = run_backtest(spec)
    assert result.trades == []
    assert result.metrics.win_rate == 0
