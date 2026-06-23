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


TEMPLATES = {
    "ema-cross": ema_template,
    "momentum-20": momentum_template,
    "value-quality": value_template,
}
