from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_FIELDS = {
    "CLOSE",
    "OPEN",
    "VOLUME",
    "EMA",
    "MA",
    "MOMENTUM",
    "PE_TTM",
    "ROE",
}


class Operator(str, Enum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    CROSS_ABOVE = "CROSS_ABOVE"
    CROSS_BELOW = "CROSS_BELOW"


class Condition(BaseModel):
    field: str
    operator: Operator
    value: int | float | str
    params: dict[str, int | float | str] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in ALLOWED_FIELDS:
            raise ValueError(f"不支持的策略字段: {value}")
        return normalized


Market = Literal["CN_A", "HK", "US"]
Benchmark = Literal["000300.SH", "HSI.HK", "SPY.US"]


class UniverseSpec(BaseModel):
    market: Market = "CN_A"
    index: Benchmark = "000300.SH"
    filters: list[Condition] = Field(default_factory=list)

    @field_validator("index")
    @classmethod
    def validate_market_index(cls, value: str, info):
        expected = {"CN_A": "000300.SH", "HK": "HSI.HK", "US": "SPY.US"}
        market = info.data.get("market", "CN_A")
        if value != expected[market]:
            raise ValueError(f"{market} 市场基准必须为 {expected[market]}")
        return value


class RuleGroup(BaseModel):
    logic: Literal["AND", "OR"] = "AND"
    conditions: list[Condition]


class RiskControls(BaseModel):
    stop_loss_pct: Annotated[float | None, Field(ge=0, le=50)] = 8
    take_profit_pct: Annotated[float | None, Field(ge=0, le=200)] = None
    max_position_pct: Annotated[float | None, Field(gt=0, le=100)] = 100


class ExitSpec(RuleGroup):
    risk_controls: RiskControls = Field(default_factory=RiskControls)


class BacktestSpec(BaseModel):
    start_date: date = date(2019, 1, 1)
    end_date: date = date(2026, 6, 19)
    benchmark: Benchmark = "000300.SH"
    initial_capital: Annotated[float, Field(gt=1000, le=1_000_000_000)] = 1_000_000
    rebalance: Literal["daily", "weekly", "monthly", "quarterly"] = "daily"

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, value: date, info):
        start = info.data.get("start_date")
        if start and value <= start:
            raise ValueError("回测结束日期必须晚于开始日期")
        return value


class StrategySpecV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["1.0"] = "1.0"
    name: str = Field(min_length=2, max_length=80)
    universe: UniverseSpec = Field(default_factory=UniverseSpec)
    entry: RuleGroup
    exit: ExitSpec
    backtest: BacktestSpec = Field(default_factory=BacktestSpec)


class ComplianceStatus(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    BLOCKED = "blocked"


class ParseRequest(BaseModel):
    text: str = Field(min_length=2, max_length=1000)


class ParseResponse(BaseModel):
    spec: StrategySpecV1 | None
    confidence: float = Field(ge=0, le=1)
    clarification_questions: list[str] = Field(default_factory=list)
    compliance_status: ComplianceStatus
    message: str
    provider: str
    code_preview: str | None = None


class StrategyCreate(BaseModel):
    name: str
    spec: StrategySpecV1


class VersionCreate(BaseModel):
    spec: StrategySpecV1
    note: str | None = None


class VersionOut(BaseModel):
    id: str
    strategy_id: str
    label: str
    spec: StrategySpecV1
    note: str | None = None
    created_at: datetime


class StrategyOut(BaseModel):
    id: str
    name: str
    latest_version_id: str
    created_at: datetime


class BacktestCreate(BaseModel):
    spec: StrategySpecV1
    strategy_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class MetricSet(BaseModel):
    annual_return: float
    max_drawdown: float
    sharpe: float
    win_rate: float
    profit_loss_ratio: float
    alpha: float
    beta: float


class SeriesPoint(BaseModel):
    date: str
    value: float


class TradeOut(BaseModel):
    date: str
    symbol: str
    name: str
    side: Literal["买入", "卖出"]
    price: float
    quantity: int
    fee: float


class MarketDataSnapshotMeta(BaseModel):
    id: str
    provider: str
    market: Market
    symbol: str
    vendor_symbol: str | None = None
    frequency: str
    start_date: str
    end_date: str
    rows: int
    snapshot_hash: str
    storage_path: str
    source: str
    status: str = "ready"
    fetched_at: datetime


class BacktestResult(BaseModel):
    summary: str
    disclaimer: str = "以上分析基于历史数据模拟，不构成任何投资建议。"
    code_preview: str
    metrics: MetricSet
    equity_curve: list[SeriesPoint]
    benchmark_curve: list[SeriesPoint]
    drawdown_curve: list[SeriesPoint]
    trades: list[TradeOut]
    data_source: str
    data_snapshot: MarketDataSnapshotMeta | None = None
    strategy_hash: str


class BacktestOut(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: int
    stage: str
    result: BacktestResult | None = None
    data_snapshot_id: str | None = None
    error: str | None = None
    created_at: datetime


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: str
    redis: str
    dataset: str
    timestamp: datetime


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)
    workspace_name: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str


class WorkspaceOut(BaseModel):
    id: str
    name: str
    slug: str
    role: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut
    workspace: WorkspaceOut


class MeResponse(BaseModel):
    user: UserOut
    workspace: WorkspaceOut


class AuditEventOut(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str | None
    metadata: dict
    created_at: datetime


class DashboardMetric(BaseModel):
    label: str
    value: str
    hint: str
    tone: Literal["neutral", "positive", "warning", "danger"] = "neutral"


class DashboardOut(BaseModel):
    metrics: list[DashboardMetric]
    recent_audits: list[AuditEventOut]
    system_cards: list[dict[str, str]]


class ExperimentSnapshotOut(BaseModel):
    id: str
    strategy_id: str | None
    status: str
    stage: str
    strategy_hash: str | None = None
    data_snapshot_id: str | None = None
    data_snapshot_hash: str | None = None
    engine_version: str = "quantpartner-backtest-v1"
    cost_model: str = "cn-a-share-cost-v1"
    created_at: datetime


class MarketplaceTemplateOut(BaseModel):
    id: str
    name: str
    category: str
    risk_level: Literal["low", "medium", "high"]
    markets: list[Market]
    description: str
    status: Literal["ready", "preview", "planned"] = "ready"
    prompt: str


class IntegrationOut(BaseModel):
    id: str
    name: str
    category: Literal["data", "broker", "notification", "agent"]
    status: Literal["connected", "not_configured", "paper_only", "planned", "blocked"]
    description: str
    last_checked: datetime | None = None


class AgentCapabilityOut(BaseModel):
    id: str
    name: str
    scope: str
    status: Literal["enabled", "planned", "blocked"]
    description: str


class ProductRoadmapOut(BaseModel):
    tier: Literal["p1", "p2", "p3-ui"]
    title: str
    status: Literal["implemented", "partial", "ui_only", "planned"]
    items: list[str]


class OrderCreate(BaseModel):
    market: Market
    symbol: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    quantity: Annotated[float, Field(gt=0, le=100_000_000)]
    limit_price: Annotated[float | None, Field(gt=0)] = None
    client_order_id: str = Field(min_length=8, max_length=128)

    @field_validator("limit_price")
    @classmethod
    def require_limit_price(cls, value, info):
        if info.data.get("order_type") == "limit" and value is None:
            raise ValueError("限价单必须填写限价")
        return value


class OrderOut(BaseModel):
    id: str
    account_type: Literal["paper", "live"]
    market: Market
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: float
    limit_price: float | None
    status: Literal["accepted", "filled", "cancelled", "rejected"]
    filled_quantity: float
    average_price: float | None
    client_order_id: str
    created_at: datetime
