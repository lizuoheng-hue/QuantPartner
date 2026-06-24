from .schemas import (
    BacktestSpec,
    Condition,
    ExitSpec,
    Operator,
    RiskControls,
    RuleGroup,
    StrategySpecV1,
    UniverseSpec,
)


def ema_template() -> StrategySpecV1:
    return StrategySpecV1(
        name="EMA 双均线",
        universe=UniverseSpec(),
        entry=RuleGroup(conditions=[Condition(field="EMA", operator=Operator.CROSS_ABOVE, value=60, params={"fast": 20, "slow": 60})]),
        exit=ExitSpec(
            conditions=[Condition(field="CLOSE", operator=Operator.CROSS_BELOW, value="EMA", params={"period": 20})],
            risk_controls=RiskControls(stop_loss_pct=8),
        ),
        backtest=BacktestSpec(),
    )


def momentum_template() -> StrategySpecV1:
    return StrategySpecV1(
        name="20日动量",
        universe=UniverseSpec(),
        entry=RuleGroup(conditions=[Condition(field="MOMENTUM", operator=Operator.GT, value=0.05, params={"period": 20})]),
        exit=ExitSpec(
            conditions=[Condition(field="MOMENTUM", operator=Operator.LT, value=0, params={"period": 20})],
            risk_controls=RiskControls(stop_loss_pct=10),
        ),
        backtest=BacktestSpec(rebalance="weekly"),
    )


def value_template() -> StrategySpecV1:
    return StrategySpecV1(
        name="价值质量",
        universe=UniverseSpec(
            filters=[
                Condition(field="PE_TTM", operator=Operator.LT, value=30),
                Condition(field="ROE", operator=Operator.GT, value=15),
            ]
        ),
        entry=RuleGroup(conditions=[Condition(field="ROE", operator=Operator.GT, value=15)]),
        exit=ExitSpec(
            conditions=[Condition(field="ROE", operator=Operator.LT, value=10)],
            risk_controls=RiskControls(stop_loss_pct=12),
        ),
        backtest=BacktestSpec(rebalance="quarterly"),
    )


def ma_breakout_template() -> StrategySpecV1:
    return StrategySpecV1(
        name="MA 突破",
        universe=UniverseSpec(),
        entry=RuleGroup(conditions=[Condition(field="MA", operator=Operator.CROSS_ABOVE, value=50, params={"period": 50})]),
        exit=ExitSpec(
            conditions=[Condition(field="CLOSE", operator=Operator.CROSS_BELOW, value="MA", params={"period": 50})],
            risk_controls=RiskControls(stop_loss_pct=9),
        ),
        backtest=BacktestSpec(rebalance="weekly"),
    )


def turtle_template() -> StrategySpecV1:
    return StrategySpecV1(
        name="海龟突破",
        universe=UniverseSpec(),
        entry=RuleGroup(conditions=[Condition(field="MOMENTUM", operator=Operator.GT, value=0.08, params={"period": 55})]),
        exit=ExitSpec(
            conditions=[Condition(field="MOMENTUM", operator=Operator.LT, value=-0.03, params={"period": 20})],
            risk_controls=RiskControls(stop_loss_pct=6, max_position_pct=50),
        ),
        backtest=BacktestSpec(rebalance="weekly"),
    )


def mean_reversion_template() -> StrategySpecV1:
    return StrategySpecV1(
        name="均值回归",
        universe=UniverseSpec(),
        entry=RuleGroup(conditions=[Condition(field="CLOSE", operator=Operator.LT, value="MA", params={"period": 80, "offset_pct": -5})]),
        exit=ExitSpec(
            conditions=[Condition(field="CLOSE", operator=Operator.GT, value="MA", params={"period": 80})],
            risk_controls=RiskControls(stop_loss_pct=7, take_profit_pct=15, max_position_pct=60),
        ),
        backtest=BacktestSpec(rebalance="daily"),
    )


TEMPLATES = {
    "ema-cross": ema_template,
    "momentum-20": momentum_template,
    "value-quality": value_template,
    "ma-breakout": ma_breakout_template,
    "turtle-breakout": turtle_template,
    "mean-reversion": mean_reversion_template,
}
