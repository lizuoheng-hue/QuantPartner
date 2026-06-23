import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from .config import get_settings
from .market_data import MarketDataError, load_real_market, market_data_status, snapshot_record_id
from .parser import generate_code_preview
from .schemas import BacktestResult, MarketDataSnapshotMeta, MetricSet, SeriesPoint, StrategySpecV1, TradeOut


@dataclass
class Costs:
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    slippage_rate: float


def _demo_market(spec: StrategySpecV1) -> pd.DataFrame:
    dates = pd.bdate_range(spec.backtest.start_date, spec.backtest.end_date)
    seed = int(hashlib.sha256(f"{spec.name}:{spec.backtest.benchmark}".encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    regime = np.sin(np.linspace(0, 14 * math.pi, len(dates))) * 0.0018
    market_returns = rng.normal(0.00024, 0.0105, len(dates)) + regime
    market_returns[0] = 0
    close = 100 * np.cumprod(1 + market_returns)
    overnight = rng.normal(0, 0.0025, len(dates))
    open_price = close * (1 + overnight)
    return pd.DataFrame({"open": open_price, "close": close, "market_return": market_returns}, index=dates)


def _snapshot_meta(dataset) -> MarketDataSnapshotMeta:
    record_id = snapshot_record_id(
        provider=dataset.provider,
        market=dataset.market,
        symbol=dataset.symbol,
        frequency=dataset.frequency,
        start_date=dataset.start_date,
        end_date=dataset.end_date,
        snapshot_id=dataset.snapshot_id,
    )
    return MarketDataSnapshotMeta(
        id=record_id,
        provider=dataset.provider,
        market=dataset.market,
        symbol=dataset.symbol,
        vendor_symbol=dataset.vendor_symbol,
        frequency=dataset.frequency,
        start_date=dataset.start_date,
        end_date=dataset.end_date,
        rows=dataset.rows,
        snapshot_hash=dataset.snapshot_id,
        storage_path=str(dataset.cache_path),
        source=dataset.source,
        status="ready",
        fetched_at=datetime.fromisoformat(dataset.fetched_at),
    )


def load_market(spec: StrategySpecV1) -> tuple[pd.DataFrame, str, MarketDataSnapshotMeta | None]:
    settings = get_settings()
    configured = market_data_status(settings)[spec.universe.market] == "configured"
    if configured:
        try:
            dataset = load_real_market(spec)
            return dataset.frame, dataset.source, _snapshot_meta(dataset)
        except MarketDataError:
            if settings.app_env in {"beta", "production"}:
                raise RuntimeError("生产行情暂不可用，回测已安全终止")
            return _demo_market(spec), "deterministic-demo-fallback", None
    if settings.app_env in {"beta", "production"}:
        raise RuntimeError(f"{spec.universe.market} 市场尚未配置授权行情源")
    return _demo_market(spec), "deterministic-demo", None


def _signals(frame: pd.DataFrame, spec: StrategySpecV1) -> tuple[pd.Series, pd.Series]:
    entry = spec.entry.conditions[0]
    exit_condition = spec.exit.conditions[0]
    close = frame["close"]

    if entry.field == "EMA":
        fast = int(entry.params.get("fast", 20))
        slow = int(entry.params.get("slow", 60))
        fast_line = close.ewm(span=fast, adjust=False).mean()
        slow_line = close.ewm(span=slow, adjust=False).mean()
        buy = (fast_line > slow_line) & (fast_line.shift(1) <= slow_line.shift(1))
        exit_period = int(exit_condition.params.get("period", fast))
        exit_line = close.ewm(span=exit_period, adjust=False).mean()
        sell = (close < exit_line) & (close.shift(1) >= exit_line.shift(1))
    elif entry.field == "MOMENTUM":
        period = int(entry.params.get("period", 20))
        momentum = close.pct_change(period)
        buy = momentum > float(entry.value)
        sell = momentum < float(exit_condition.value)
    else:
        slow = close.rolling(80, min_periods=20).mean()
        buy = close > slow
        sell = close < slow
    return buy.fillna(False), sell.fillna(False)


def _metrics(equity: pd.Series, benchmark: pd.Series, trade_returns: list[float]) -> MetricSet:
    returns = equity.pct_change().fillna(0)
    benchmark_returns = benchmark.pct_change().fillna(0)
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1 / 252)
    annual = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    bench_annual = (benchmark.iloc[-1] / benchmark.iloc[0]) ** (1 / years) - 1
    drawdown = equity / equity.cummax() - 1
    sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() else 0
    covariance = np.cov(returns, benchmark_returns)
    beta = covariance[0, 1] / covariance[1, 1] if covariance[1, 1] else 0
    alpha = annual - (0.02 + beta * (bench_annual - 0.02))
    wins = [value for value in trade_returns if value > 0]
    losses = [value for value in trade_returns if value <= 0]
    win_rate = len(wins) / len(trade_returns) if trade_returns else 0
    ratio = (np.mean(wins) / abs(np.mean(losses))) if wins and losses and np.mean(losses) else 0
    return MetricSet(
        annual_return=round(float(annual), 4),
        max_drawdown=round(float(drawdown.min()), 4),
        sharpe=round(float(sharpe), 2),
        win_rate=round(float(win_rate), 4),
        profit_loss_ratio=round(float(ratio), 2),
        alpha=round(float(alpha), 4),
        beta=round(float(beta), 2),
    )


def run_backtest(spec: StrategySpecV1) -> BacktestResult:
    settings = get_settings()
    costs = Costs(
        settings.commission_rate,
        settings.min_commission,
        settings.stamp_duty_rate,
        settings.transfer_fee_rate,
        settings.slippage_rate,
    )
    frame, data_source, data_snapshot = load_market(spec)
    buy_signal, sell_signal = _signals(frame, spec)
    initial = spec.backtest.initial_capital
    cash = initial
    shares = 0
    entry_value = 0.0
    pending: str | None = None
    equity_values: list[float] = []
    trade_returns: list[float] = []
    trades: list[TradeOut] = []
    stop_loss = (spec.exit.risk_controls.stop_loss_pct or 0) / 100
    max_position = (spec.exit.risk_controls.max_position_pct or 100) / 100
    benchmark_names = {"000300.SH": "沪深300", "HSI.HK": "恒生指数", "SPY.US": "标普500"}
    symbol_names = {"000300.SH": "沪深300组合", "HSI.HK": "恒生指数篮子", "SPY.US": "标普500组合"}
    symbol = spec.backtest.benchmark

    for position, (day, row) in enumerate(frame.iterrows()):
        open_price = float(row.open)
        if pending == "buy" and shares == 0:
            execution = open_price * (1 + costs.slippage_rate)
            budget = cash * max_position
            quantity = int(budget / execution / 100) * 100
            gross = quantity * execution
            fee = max(gross * costs.commission_rate, costs.min_commission) + gross * costs.transfer_fee_rate
            if quantity > 0 and gross + fee <= cash:
                cash -= gross + fee
                shares = quantity
                entry_value = gross + fee
                trades.append(TradeOut(date=str(day.date()), symbol=symbol, name=symbol_names[symbol], side="买入", price=round(execution, 2), quantity=quantity, fee=round(fee, 2)))
        elif pending == "sell" and shares > 0:
            execution = open_price * (1 - costs.slippage_rate)
            gross = shares * execution
            fee = max(gross * costs.commission_rate, costs.min_commission) + gross * (costs.stamp_duty_rate + costs.transfer_fee_rate)
            cash += gross - fee
            trade_returns.append((gross - fee - entry_value) / entry_value)
            trades.append(TradeOut(date=str(day.date()), symbol=symbol, name=symbol_names[symbol], side="卖出", price=round(execution, 2), quantity=shares, fee=round(fee, 2)))
            shares = 0
            entry_value = 0
        pending = None

        current_equity = cash + shares * float(row.close)
        equity_values.append(current_equity)
        if position < len(frame) - 1:
            if shares == 0 and bool(buy_signal.loc[day]):
                pending = "buy"
            elif shares > 0:
                drawdown_from_entry = (shares * float(row.close) - entry_value) / entry_value if entry_value else 0
                if bool(sell_signal.loc[day]) or drawdown_from_entry <= -stop_loss:
                    pending = "sell"

    equity = pd.Series(equity_values, index=frame.index)
    benchmark = initial * (frame["close"] / frame["close"].iloc[0])
    drawdown = equity / equity.cummax() - 1
    metrics = _metrics(equity, benchmark, trade_returns)
    benchmark_annual = (benchmark.iloc[-1] / benchmark.iloc[0]) ** (365.25 / max((benchmark.index[-1] - benchmark.index[0]).days, 1)) - 1
    excess = metrics.annual_return - benchmark_annual
    summary = (
        f"策略年化收益 {metrics.annual_return * 100:.1f}%，"
        f"{'跑赢' if excess >= 0 else '落后'}{benchmark_names[symbol]} {abs(excess) * 100:.1f} 个百分点；"
        f"最大回撤 {abs(metrics.max_drawdown) * 100:.1f}%，"
        + ("风险调整后表现较稳健。" if metrics.sharpe >= 1 else "风险调整后收益仍有改进空间。")
    )
    indices = np.linspace(0, len(frame) - 1, min(180, len(frame))).astype(int)
    points = frame.index[indices]
    strategy_hash = hashlib.sha256(json.dumps(spec.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()[:16]
    return BacktestResult(
        summary=summary,
        code_preview=generate_code_preview(spec),
        metrics=metrics,
        equity_curve=[SeriesPoint(date=str(day.date()), value=round(float(equity.loc[day] / initial), 4)) for day in points],
        benchmark_curve=[SeriesPoint(date=str(day.date()), value=round(float(benchmark.loc[day] / initial), 4)) for day in points],
        drawdown_curve=[SeriesPoint(date=str(day.date()), value=round(float(drawdown.loc[day]), 4)) for day in points],
        trades=trades[-20:][::-1],
        data_source=data_source,
        data_snapshot=data_snapshot,
        strategy_hash=strategy_hash,
    )
