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
from .schemas import BacktestDiagnosis, BacktestResult, DiagnosisItem, ImprovementSuggestion, MarketDataSnapshotMeta, MetricSet, SeriesPoint, StrategySpecV1, TradeOut


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
    entry = next((condition for condition in spec.entry.conditions if condition.enabled), None)
    exit_condition = next((condition for condition in spec.exit.conditions if condition.enabled), None)
    close = frame["close"]
    empty = pd.Series(False, index=frame.index)
    if entry is None:
        return empty, empty

    if entry.field == "EMA":
        fast = int(entry.params.get("fast", 20))
        slow = int(entry.params.get("slow", 60))
        fast_line = close.ewm(span=fast, adjust=False).mean()
        slow_line = close.ewm(span=slow, adjust=False).mean()
        buy = (fast_line > slow_line) & (fast_line.shift(1) <= slow_line.shift(1))
        exit_period = int(exit_condition.params.get("period", fast)) if exit_condition else fast
        exit_line = close.ewm(span=exit_period, adjust=False).mean()
        sell = (close < exit_line) & (close.shift(1) >= exit_line.shift(1)) if exit_condition else empty
    elif entry.field == "MOMENTUM":
        period = int(entry.params.get("period", 20))
        momentum = close.pct_change(period)
        buy = momentum > float(entry.value)
        sell = momentum < float(exit_condition.value) if exit_condition else empty
    else:
        slow = close.rolling(80, min_periods=20).mean()
        buy = close > slow
        sell = close < slow if exit_condition else empty
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


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _diagnosis(spec: StrategySpecV1, metrics: MetricSet, benchmark_annual: float, trade_count: int, benchmark_name: str) -> BacktestDiagnosis:
    excess = metrics.annual_return - benchmark_annual
    stop_loss = spec.exit.risk_controls.stop_loss_pct or 0
    entry = next((condition for condition in spec.entry.conditions if condition.enabled), spec.entry.conditions[0] if spec.entry.conditions else None)
    exit_condition = next((condition for condition in spec.exit.conditions if condition.enabled), spec.exit.conditions[0] if spec.exit.conditions else None)
    summary = (
        f"该策略在当前历史样本中的年化收益为 {_pct(metrics.annual_return)}，"
        f"{'跑赢' if excess >= 0 else '落后'}{benchmark_name} {abs(excess) * 100:.1f} 个百分点；"
        f"最大回撤 {_pct(metrics.max_drawdown)}，下一步应围绕信号质量、离场规则和分行情稳定性继续验证。"
    )

    return BacktestDiagnosis(
        summary=summary,
        items=[
            DiagnosisItem(
                title="收益能力",
                level="positive" if excess >= 0.03 else "warning" if excess >= -0.03 else "danger",
                metric_refs=["annual_return", "alpha"],
                explanation=(
                    f"策略年化收益 {_pct(metrics.annual_return)}，"
                    f"{'高于' if excess >= 0 else '低于'}{benchmark_name} {abs(excess) * 100:.1f} 个百分点。"
                    + ("当前规则在该样本内捕捉到了一部分超额收益。" if excess >= 0 else "当前买入条件没有稳定捕捉主要上涨阶段。")
                ),
            ),
            DiagnosisItem(
                title="风险控制",
                level="danger" if metrics.max_drawdown <= -0.2 else "warning" if metrics.max_drawdown <= -0.12 else "positive",
                metric_refs=["max_drawdown", "sharpe"],
                explanation=(
                    f"最大回撤为 {_pct(metrics.max_drawdown)}，夏普比率 {metrics.sharpe:.2f}。"
                    + ("回撤压力偏高，说明止损或卖出条件没有及时压缩下行风险。" if metrics.max_drawdown <= -0.2 else "风险暴露仍需结合不同市场阶段继续观察。")
                ),
            ),
            DiagnosisItem(
                title="交易效率",
                level="danger" if metrics.win_rate < 0.35 and metrics.profit_loss_ratio < 1.2 else "warning" if metrics.win_rate < 0.45 else "positive",
                metric_refs=["win_rate", "profit_loss_ratio"],
                explanation=(
                    f"回测共形成 {trade_count} 条成交记录，胜率 {_pct(metrics.win_rate)}，盈亏比 {metrics.profit_loss_ratio:.2f}。"
                    + ("信号命中率偏低，需要减少噪音触发或增加趋势确认。" if metrics.win_rate < 0.35 else "单笔盈亏结构可以继续用样本外区间验证。")
                ),
            ),
            DiagnosisItem(
                title="稳定性",
                level="warning",
                metric_refs=["annual_return", "max_drawdown", "beta"],
                explanation=(
                    f"当前诊断来自 {spec.backtest.start_date} 至 {spec.backtest.end_date} 的完整样本，Beta 为 {metrics.beta:.2f}。"
                    "仍需拆分牛市、震荡市和熊市分别回测，确认表现是否依赖单一市场环境。"
                ),
            ),
        ],
        suggestions=[
            ImprovementSuggestion(
                title="收紧买入条件",
                rationale=f"当前入场规则为 {entry.field if entry else '未启用'} {entry.operator.value if entry else ''}，若胜率偏低，可加入更长周期确认或提高动量阈值来减少噪音交易。",
                action_type="condition_change",
                patch={"entry_condition": {"field": entry.field, "operator": entry.operator.value, "params": entry.params}} if entry else None,
                safety_note="仅作为下一轮历史回测实验，不代表未来收益改善。",
            ),
            ImprovementSuggestion(
                title="优化离场与止损",
                rationale=f"当前止损为 {stop_loss:.1f}%，卖出规则为 {exit_condition.field if exit_condition else '未启用'} {exit_condition.operator.value if exit_condition else ''}。若最大回撤偏高，可测试更紧的止损或移动止损。",
                action_type="risk_control",
                patch={"risk_controls": {"stop_loss_pct": max(round(stop_loss - 2, 1), 3) if stop_loss else 6}},
                safety_note="风控参数变动可能降低回撤，也可能增加频繁止损成本，需要重新回测验证。",
            ),
            ImprovementSuggestion(
                title="执行分阶段压力测试",
                rationale="把完整样本拆成 2019-2021、2022、2023-2026 三段，分别观察收益、回撤和胜率，避免单一区间结论过拟合。",
                action_type="stress_test",
                patch={"windows": [["2019-01-01", "2021-12-31"], ["2022-01-01", "2022-12-31"], ["2023-01-01", str(spec.backtest.end_date)]]},
                safety_note="压力测试用于识别历史环境依赖，不构成实盘运行依据。",
            ),
        ],
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
    diagnosis = _diagnosis(spec, metrics, benchmark_annual, len(trades), benchmark_names[symbol])
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
        diagnosis=diagnosis,
        equity_curve=[SeriesPoint(date=str(day.date()), value=round(float(equity.loc[day] / initial), 4)) for day in points],
        benchmark_curve=[SeriesPoint(date=str(day.date()), value=round(float(benchmark.loc[day] / initial), 4)) for day in points],
        drawdown_curve=[SeriesPoint(date=str(day.date()), value=round(float(drawdown.loc[day]), 4)) for day in points],
        trades=trades[-20:][::-1],
        data_source=data_source,
        data_snapshot=data_snapshot,
        strategy_hash=strategy_hash,
    )
