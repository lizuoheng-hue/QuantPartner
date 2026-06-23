import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .backtest import run_backtest
from .auth import AuthContext, create_session, hash_password, require_auth, verify_password
from .cache import cache_task_state, enqueue_backtest, redis_health
from .config import get_settings
from .db import (
    AuditEventRecord,
    BacktestRecord,
    MarketDataSnapshotRecord,
    MembershipRecord,
    OrderRecord,
    SessionLocal,
    SessionRecord,
    StrategyRecord,
    UserRecord,
    VersionRecord,
    WorkspaceRecord,
    get_db,
    init_db,
    utcnow,
)
from .parser import generate_code_preview, parse_strategy
from .market_data import market_data_status
from .schemas import (
    AgentBacktestCreate,
    BacktestCreate,
    BacktestOut,
    BacktestResult,
    AgentCapabilityOut,
    AgentManifestOut,
    AgentToolOut,
    AgentWorkspaceOut,
    DashboardMetric,
    DashboardOut,
    ExperimentSnapshotOut,
    HealthResponse,
    IntegrationOut,
    AuditEventOut,
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    MarketDataSnapshotMeta,
    NotificationChannelOut,
    OrderCreate,
    OrderOut,
    MarketplaceTemplateOut,
    ParseRequest,
    ParseResponse,
    ProductRoadmapOut,
    StrategyCreate,
    StrategyOut,
    StrategySpecV1,
    LiveOrderRequest,
    RegisterRequest,
    UserOut,
    VersionCreate,
    VersionOut,
    WorkspaceOut,
)
from .templates import TEMPLATES


logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","message":"%(message)s"}')
logger = logging.getLogger("quantpartner")
settings = get_settings()


def audit(db: Session, auth: AuthContext, action: str, resource_type: str, resource_id: str | None = None, metadata: dict | None = None) -> None:
    db.add(AuditEventRecord(
        workspace_id=auth.workspace.id,
        actor_user_id=auth.user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
    ))


def auth_response(auth_token: str, user: UserRecord, workspace: WorkspaceRecord, role: str) -> AuthResponse:
    return AuthResponse(
        access_token=auth_token,
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
        workspace=WorkspaceOut(id=workspace.id, name=workspace.name, slug=workspace.slug, role=role),
    )


def order_out(record: OrderRecord) -> OrderOut:
    return OrderOut(
        id=record.id, account_type=record.account_type, market=record.market, symbol=record.symbol,
        side=record.side, order_type=record.order_type, quantity=record.quantity, limit_price=record.limit_price,
        status=record.status, filled_quantity=record.filled_quantity, average_price=record.average_price,
        client_order_id=record.client_order_id, created_at=record.created_at,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def version_out(record: VersionRecord) -> VersionOut:
    return VersionOut(
        id=record.id,
        strategy_id=record.strategy_id,
        label=record.label,
        spec=StrategySpecV1.model_validate(record.spec),
        note=record.note,
        created_at=record.created_at,
    )


def snapshot_out(record: MarketDataSnapshotRecord) -> MarketDataSnapshotMeta:
    return MarketDataSnapshotMeta(
        id=record.id,
        provider=record.provider,
        market=record.market,
        symbol=record.symbol,
        vendor_symbol=record.vendor_symbol,
        frequency=record.frequency,
        start_date=record.start_date,
        end_date=record.end_date,
        rows=record.rows,
        snapshot_hash=record.snapshot_hash,
        storage_path=record.storage_path,
        source=record.source,
        status=record.status,
        fetched_at=record.fetched_at,
    )


def upsert_market_snapshot(db: Session, snapshot: MarketDataSnapshotMeta | None) -> str | None:
    if snapshot is None:
        return None
    record = db.get(MarketDataSnapshotRecord, snapshot.id)
    values = {
        "provider": snapshot.provider,
        "market": snapshot.market,
        "symbol": snapshot.symbol,
        "vendor_symbol": snapshot.vendor_symbol,
        "frequency": snapshot.frequency,
        "start_date": snapshot.start_date,
        "end_date": snapshot.end_date,
        "rows": snapshot.rows,
        "snapshot_hash": snapshot.snapshot_hash,
        "storage_path": snapshot.storage_path,
        "source": snapshot.source,
        "status": snapshot.status,
        "fetched_at": snapshot.fetched_at,
    }
    if record:
        for key, value in values.items():
            setattr(record, key, value)
    else:
        db.add(MarketDataSnapshotRecord(id=snapshot.id, **values))
    return snapshot.id


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database_status = "connected"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"
    redis_status = redis_health()
    data_status = market_data_status(settings)
    ready = all(value == "configured" for value in data_status.values())
    data_healthy = ready or settings.app_env == "development"
    return HealthResponse(
        status="ok" if database_status == "connected" and redis_status == "connected" and data_healthy else "degraded",
        database=database_status,
        redis=redis_status,
        dataset="real-market-data-ready" if ready else ("deterministic-demo" if settings.app_env == "development" else "market-data-incomplete"),
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/api/v1/data/status")
def data_status() -> dict:
    return {
        "environment": settings.app_env,
        "markets": market_data_status(settings),
        "cache_directory": settings.data_cache_dir,
        "demo_fallback_allowed": settings.app_env == "development",
    }


@app.get("/api/v1/data/snapshots", response_model=list[MarketDataSnapshotMeta])
def list_data_snapshots(db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> list[MarketDataSnapshotMeta]:
    records = db.scalars(select(MarketDataSnapshotRecord).order_by(MarketDataSnapshotRecord.fetched_at.desc()).limit(100)).all()
    audit(db, auth, "market_data_snapshot.list", "market_data_snapshot")
    db.commit()
    return [snapshot_out(record) for record in records]


def audit_out(item: AuditEventRecord) -> AuditEventOut:
    return AuditEventOut(
        id=item.id,
        action=item.action,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        metadata=json.loads(item.metadata_json),
        created_at=item.created_at,
    )


def cost_model_for_market(market: str) -> str:
    return {
        "CN_A": "cn-a-share-cost-v1",
        "HK": "hk-equity-cost-v1",
        "US": "us-equity-cost-v1",
    }.get(market, "market-cost-v1")


def experiment_out(record: BacktestRecord) -> ExperimentSnapshotOut:
    spec = StrategySpecV1.model_validate_json(record.spec_json)
    strategy_hash = None
    data_snapshot_hash = None
    annual_return = None
    max_drawdown = None
    sharpe = None
    if record.result_json:
        try:
            result = BacktestResult.model_validate_json(record.result_json)
            strategy_hash = result.strategy_hash
            data_snapshot_hash = result.data_snapshot.snapshot_hash if result.data_snapshot else None
            annual_return = result.metrics.annual_return
            max_drawdown = result.metrics.max_drawdown
            sharpe = result.metrics.sharpe
        except Exception:
            strategy_hash = None
    return ExperimentSnapshotOut(
        id=record.id,
        strategy_id=record.strategy_id,
        status=record.status,
        stage=record.stage,
        market=spec.universe.market,
        benchmark=spec.backtest.benchmark,
        strategy_hash=strategy_hash,
        data_snapshot_id=record.data_snapshot_id,
        data_snapshot_hash=data_snapshot_hash,
        annual_return=annual_return,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        cost_model=cost_model_for_market(spec.universe.market),
        created_at=record.created_at,
    )


def agent_capability_items() -> list[AgentCapabilityOut]:
    return [
        AgentCapabilityOut(id="read", name="只读研究", scope="read:workspace read:backtest read:audit", status="enabled", description="读取策略、回测、审计和数据快照。"),
        AgentCapabilityOut(id="strategy", name="策略生成", scope="write:strategy parse:strategy", status="enabled", description="生成结构化策略与保存版本。"),
        AgentCapabilityOut(id="paper-trade", name="模拟盘交易", scope="write:paper_order", status="enabled", description="仅允许模拟盘订单。"),
        AgentCapabilityOut(id="live-trade", name="实盘交易", scope="write:live_order", status="blocked", description="高风险能力，当前只展示结构，不开放调用。"),
        AgentCapabilityOut(id="admin", name="管理员自动化", scope="admin:workspace admin:billing", status="planned", description="成员、权限、通知和配额管理。"),
    ]


@app.get("/api/v1/product/dashboard", response_model=DashboardOut)
def product_dashboard(db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> DashboardOut:
    strategies_count = db.scalar(select(func.count()).select_from(StrategyRecord).where(StrategyRecord.workspace_id == auth.workspace.id)) or 0
    backtests_count = db.scalar(select(func.count()).select_from(BacktestRecord).where(BacktestRecord.workspace_id == auth.workspace.id)) or 0
    completed_backtests = db.scalar(select(func.count()).select_from(BacktestRecord).where(BacktestRecord.workspace_id == auth.workspace.id, BacktestRecord.status == "completed")) or 0
    active_orders = db.scalar(select(func.count()).select_from(OrderRecord).where(OrderRecord.workspace_id == auth.workspace.id, OrderRecord.account_type == "paper", OrderRecord.status == "accepted")) or 0
    snapshot_count = db.scalar(select(func.count()).select_from(MarketDataSnapshotRecord)) or 0
    audits = db.scalars(select(AuditEventRecord).where(AuditEventRecord.workspace_id == auth.workspace.id).order_by(AuditEventRecord.created_at.desc()).limit(8)).all()
    health_payload = health()
    return DashboardOut(
        metrics=[
            DashboardMetric(label="策略", value=str(strategies_count), hint="已保存策略数量"),
            DashboardMetric(label="回测", value=f"{completed_backtests}/{backtests_count}", hint="完成/总任务", tone="positive" if completed_backtests else "neutral"),
            DashboardMetric(label="模拟订单", value=str(active_orders), hint="accepted 状态订单", tone="warning" if active_orders else "neutral"),
            DashboardMetric(label="行情快照", value=str(snapshot_count), hint="可追溯数据批次", tone="positive" if snapshot_count else "warning"),
        ],
        recent_audits=[audit_out(item) for item in audits],
        system_cards=[
            {"title": "数据状态", "value": health_payload.dataset, "status": health_payload.status},
            {"title": "任务队列", "value": f"Redis {health_payload.redis}", "status": "degraded" if health_payload.redis != "connected" else "ok"},
            {"title": "交易模式", "value": "模拟盘启用 · 实盘关闭", "status": "paper_only"},
        ],
    )


@app.get("/api/v1/product/experiments", response_model=list[ExperimentSnapshotOut])
def experiment_snapshots(db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> list[ExperimentSnapshotOut]:
    records = db.scalars(select(BacktestRecord).where(BacktestRecord.workspace_id == auth.workspace.id).order_by(BacktestRecord.created_at.desc()).limit(30)).all()
    return [experiment_out(record) for record in records]


@app.get("/api/v1/product/marketplace", response_model=list[MarketplaceTemplateOut])
def marketplace_templates(auth: AuthContext = Depends(require_auth)) -> list[MarketplaceTemplateOut]:
    return [
        MarketplaceTemplateOut(id="trend-following", name="趋势跟随", category="交易机器人", risk_level="medium", markets=["CN_A", "US"], description="用均线/动量识别中期趋势，适合作为模拟盘机器人起点。", prompt="近60日动量排名靠前买入，跌破20日均线卖出，10%止损"),
        MarketplaceTemplateOut(id="value-quality", name="价值质量", category="选股策略", risk_level="low", markets=["CN_A", "HK", "US"], description="以 PE、ROE 等基本面指标筛选质量和估值。", prompt="PE低于30且ROE高于12%，月度调仓，ROE跌破8%卖出"),
        MarketplaceTemplateOut(id="grid-paper", name="网格模拟盘", category="模拟交易", risk_level="high", markets=["US", "HK"], description="仅开放 UI 与模拟盘结构，不接实盘。适合震荡行情实验。", status="preview", prompt="在 SPY 上做5档网格模拟交易，单格2%，总仓位不超过50%"),
        MarketplaceTemplateOut(id="dca-plan", name="定投 DCA", category="资产配置", risk_level="medium", markets=["US", "HK"], description="按固定周期分批买入，关注成本曲线而非短期择时。", status="preview", prompt="每月定投 SPY，跌破200日均线暂停，恢复后继续"),
        MarketplaceTemplateOut(id="sector-rotation", name="行业轮动", category="组合策略", risk_level="medium", markets=["CN_A", "US"], description="根据相对强弱在板块间轮动，当前为产品化计划项。", status="planned", prompt="选择近90日强度最高的行业ETF，每月调仓"),
    ]


@app.get("/api/v1/product/integrations", response_model=list[IntegrationOut])
def integrations(db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> list[IntegrationOut]:
    status = market_data_status(settings)
    tushare_ready = status.get("CN_A") == "configured"
    twelve_ready = status.get("US") == "configured" or status.get("HK") == "configured"
    return [
        IntegrationOut(id="tushare", name="Tushare Pro", category="data", status="connected" if tushare_ready else "not_configured", description="A股/沪深300真实日线行情与指数数据。", last_checked=datetime.now(timezone.utc)),
        IntegrationOut(id="twelve-data", name="Twelve Data", category="data", status="connected" if twelve_ready else "not_configured", description="美股/港股日线行情数据源。", last_checked=datetime.now(timezone.utc)),
        IntegrationOut(id="paper-broker", name="QuantPartner Paper Broker", category="broker", status="paper_only", description="模拟盘订单、撤单和审计已启用。"),
        IntegrationOut(id="live-broker", name="Live Broker Gateway", category="broker", status="blocked", description="实盘交易入口仅保留 UI 结构，未接入真实下单。"),
        IntegrationOut(id="feishu-webhook", name="飞书/企业微信通知", category="notification", status="planned", description="回测完成、数据源失效和订单事件通知。"),
        IntegrationOut(id="mcp-agent", name="MCP Agent Gateway", category="agent", status="connected", description="给 Codex/Cursor/Claude 使用的研究、回测和模拟盘代理接口。"),
    ]


@app.get("/api/v1/product/agents", response_model=list[AgentCapabilityOut])
def agent_capabilities(auth: AuthContext = Depends(require_auth)) -> list[AgentCapabilityOut]:
    return agent_capability_items()


@app.get("/api/v1/product/notifications", response_model=list[NotificationChannelOut])
def notification_channels(auth: AuthContext = Depends(require_auth)) -> list[NotificationChannelOut]:
    return [
        NotificationChannelOut(id="in-app", name="站内通知", trigger="回测完成 / 订单状态变化", status="enabled", description="当前通过控制台和审计流展示，不依赖外部服务。"),
        NotificationChannelOut(id="webhook", name="Webhook", trigger="数据源异常 / 长任务完成", status="planned", description="预留给企业微信、飞书、Discord 或自定义 HTTP 回调。"),
        NotificationChannelOut(id="email", name="Email", trigger="账号与风险事件", status="planned", description="适合邮箱验证、密码重置和风控告警。"),
        NotificationChannelOut(id="sms", name="SMS", trigger="高风险交易确认", status="blocked", description="实盘交易未启用前不开放短信交易确认。"),
    ]


@app.get("/api/v1/product/roadmap", response_model=list[ProductRoadmapOut])
def product_roadmap(auth: AuthContext = Depends(require_auth)) -> list[ProductRoadmapOut]:
    return [
        ProductRoadmapOut(tier="p1", title="第一优先级：策略实验与回测体验", status="partial", items=["实验快照列表", "策略模板市场", "回测进度/阶段", "数据快照追踪", "澄清式策略生成"]),
        ProductRoadmapOut(tier="p2", title="第二优先级：产品化运营能力", status="partial", items=["数据源状态", "模拟盘 Broker", "审计日志", "Agent Gateway", "通知与成员权限占位"]),
        ProductRoadmapOut(tier="p3-ui", title="第三优先级：高风险/商业化功能结构", status="ui_only", items=["实盘 Broker 网关", "计费/套餐", "移动端/PWA", "多市场扩展", "高级机器人"]),
    ]


@app.get("/api/v1/templates")
def templates():
    return [
        {"id": key, "name": factory().name, "spec": factory(), "code_preview": generate_code_preview(factory())}
        for key, factory in TEMPLATES.items()
    ]


@app.post("/api/v1/strategy/parse", response_model=ParseResponse)
def parse(request: ParseRequest) -> ParseResponse:
    return parse_strategy(request.text)


@app.post("/api/v1/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.strip().lower()
    if db.scalar(select(UserRecord).where(UserRecord.email == email)):
        raise HTTPException(409, "该邮箱已注册")
    user = UserRecord(email=email, display_name=payload.display_name.strip(), password_hash=hash_password(payload.password))
    slug_base = re.sub(r"[^a-z0-9]+", "-", email.split("@", 1)[0].lower()).strip("-") or "workspace"
    workspace = WorkspaceRecord(name=payload.workspace_name.strip(), slug=f"{slug_base}-{uuid.uuid4().hex[:8]}")
    db.add_all([user, workspace])
    db.flush()
    membership = MembershipRecord(workspace_id=workspace.id, user_id=user.id, role="owner")
    db.add(membership)
    session, token = create_session(db, user.id)
    db.add(AuditEventRecord(workspace_id=workspace.id, actor_user_id=user.id, action="auth.register", resource_type="user", resource_id=user.id))
    db.commit()
    return auth_response(token, user, workspace, membership.role)


@app.post("/api/v1/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(UserRecord).where(UserRecord.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "邮箱或密码错误")
    membership = db.scalar(select(MembershipRecord).where(MembershipRecord.user_id == user.id))
    workspace = db.get(WorkspaceRecord, membership.workspace_id) if membership else None
    if not membership or not workspace:
        raise HTTPException(403, "账号没有可用工作区")
    _, token = create_session(db, user.id)
    db.add(AuditEventRecord(workspace_id=workspace.id, actor_user_id=user.id, action="auth.login", resource_type="session"))
    db.commit()
    return auth_response(token, user, workspace, membership.role)


@app.get("/api/v1/auth/me", response_model=MeResponse)
def me(auth: AuthContext = Depends(require_auth)) -> MeResponse:
    return MeResponse(
        user=UserOut(id=auth.user.id, email=auth.user.email, display_name=auth.user.display_name),
        workspace=WorkspaceOut(id=auth.workspace.id, name=auth.workspace.name, slug=auth.workspace.slug, role=auth.role),
    )


@app.post("/api/v1/auth/logout", status_code=204)
def logout(db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> Response:
    auth.session.revoked_at = utcnow()
    audit(db, auth, "auth.logout", "session", auth.session.id)
    db.commit()
    return Response(status_code=204)


@app.post("/api/v1/auth/change-password", status_code=204)
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> Response:
    if not verify_password(payload.current_password, auth.user.password_hash):
        raise HTTPException(401, "当前密码不正确")
    if payload.current_password == payload.new_password:
        raise HTTPException(400, "新密码不能与当前密码相同")

    auth.user.password_hash = hash_password(payload.new_password)
    other_sessions = db.scalars(
        select(SessionRecord).where(
            SessionRecord.user_id == auth.user.id,
            SessionRecord.id != auth.session.id,
            SessionRecord.revoked_at.is_(None),
        )
    ).all()
    now = utcnow()
    for session in other_sessions:
        session.revoked_at = now
    audit(db, auth, "auth.password.change", "user", auth.user.id, {"revoked_sessions": len(other_sessions)})
    db.commit()
    return Response(status_code=204)


@app.post("/api/v1/strategies", response_model=StrategyOut, status_code=201)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> StrategyOut:
    strategy = StrategyRecord(name=payload.name, workspace_id=auth.workspace.id)
    db.add(strategy)
    db.flush()
    now = datetime.now().astimezone()
    version = VersionRecord(
        strategy_id=strategy.id,
        label=f"v{now:%Y%m%d_%H:%M}",
        spec_json=json.dumps(payload.spec.model_dump(mode="json"), ensure_ascii=False),
        note="初始版本",
    )
    db.add(version)
    db.flush()
    strategy.latest_version_id = version.id
    audit(db, auth, "strategy.create", "strategy", strategy.id)
    db.commit()
    return StrategyOut(id=strategy.id, name=strategy.name, latest_version_id=version.id, created_at=strategy.created_at)


@app.post("/api/v1/strategies/{strategy_id}/versions", response_model=VersionOut, status_code=201)
def create_version(strategy_id: str, payload: VersionCreate, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> VersionOut:
    strategy = db.get(StrategyRecord, strategy_id)
    if not strategy or strategy.workspace_id != auth.workspace.id:
        raise HTTPException(404, "策略不存在")
    now = datetime.now().astimezone()
    version = VersionRecord(
        strategy_id=strategy_id,
        label=f"v{now:%Y%m%d_%H:%M}",
        spec_json=json.dumps(payload.spec.model_dump(mode="json"), ensure_ascii=False),
        note=payload.note,
    )
    db.add(version)
    db.flush()
    strategy.latest_version_id = version.id
    audit(db, auth, "strategy.version.create", "strategy_version", version.id, {"strategy_id": strategy.id})
    db.commit()
    return version_out(version)


@app.get("/api/v1/strategies/{strategy_id}/versions", response_model=list[VersionOut])
def list_versions(strategy_id: str, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> list[VersionOut]:
    strategy = db.get(StrategyRecord, strategy_id)
    if not strategy or strategy.workspace_id != auth.workspace.id:
        raise HTTPException(404, "策略不存在")
    records = db.scalars(select(VersionRecord).where(VersionRecord.strategy_id == strategy_id).order_by(VersionRecord.created_at.desc())).all()
    return [version_out(record) for record in records]


@app.get("/api/v1/versions/{version_id}", response_model=VersionOut)
def get_version(version_id: str, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> VersionOut:
    record = db.get(VersionRecord, version_id)
    strategy = db.get(StrategyRecord, record.strategy_id) if record else None
    if not record or not strategy or strategy.workspace_id != auth.workspace.id:
        raise HTTPException(404, "版本不存在")
    return version_out(record)


def execute_backtest(backtest_id: str) -> None:
    with SessionLocal() as db:
        record = db.get(BacktestRecord, backtest_id)
        if not record:
            return
        if record.status in {"completed", "cancelled"}:
            return
        try:
            record.status = "running"
            db.commit()
            cache_task_state(record.id, {"status": record.status, "progress": 0, "stage": "开始执行"})
            for progress, stage in [(12, "载入历史行情"), (36, "计算策略指标"), (62, "逐日推演交易"), (86, "核算绩效指标")]:
                db.refresh(record)
                if record.status == "cancelled":
                    cache_task_state(record.id, {"status": "cancelled", "progress": int(record.progress), "stage": "已终止"})
                    return
                record.progress = str(progress)
                record.stage = stage
                db.commit()
                cache_task_state(record.id, {"status": record.status, "progress": progress, "stage": stage})
                time.sleep(0.12)
            spec = StrategySpecV1.model_validate_json(record.spec_json)
            result = run_backtest(spec)
            snapshot_id = upsert_market_snapshot(db, result.data_snapshot)
            db.refresh(record)
            if record.status == "cancelled":
                cache_task_state(record.id, {"status": "cancelled", "progress": int(record.progress), "stage": "已终止"})
                return
            record.result_json = result.model_dump_json()
            record.data_snapshot_id = snapshot_id
            record.status = "completed"
            record.progress = "100"
            record.stage = "回测完成"
            if record.strategy_id:
                strategy = db.get(StrategyRecord, record.strategy_id)
                if strategy:
                    now = datetime.now().astimezone()
                    version = VersionRecord(
                        strategy_id=strategy.id,
                        label=f"v{now:%Y%m%d_%H:%M}",
                        spec_json=record.spec_json,
                        note="回测完成自动保存",
                    )
                    db.add(version)
                    db.flush()
                    strategy.latest_version_id = version.id
            db.commit()
            cache_task_state(record.id, {"status": "completed", "progress": 100, "stage": "回测完成"})
            logger.info("backtest_completed id=%s hash=%s data_snapshot_id=%s", record.id, result.strategy_hash, snapshot_id)
        except Exception as exc:
            logger.exception("backtest_failed id=%s", backtest_id)
            record.status = "failed"
            record.error = "回测执行失败，请检查策略参数后重试。"
            record.stage = "执行失败"
            db.commit()
            cache_task_state(record.id, {"status": "failed", "progress": int(record.progress), "stage": "执行失败"})


def submit_backtest_record(payload: BacktestCreate | AgentBacktestCreate, background_tasks: BackgroundTasks, db: Session, auth: AuthContext, audit_action: str = "backtest.submit") -> BacktestOut:
    if payload.idempotency_key:
        existing = db.scalar(select(BacktestRecord).where(BacktestRecord.idempotency_key == payload.idempotency_key, BacktestRecord.workspace_id == auth.workspace.id))
        if existing:
            return backtest_out(existing)
    if payload.strategy_id:
        strategy = db.get(StrategyRecord, payload.strategy_id)
        if not strategy or strategy.workspace_id != auth.workspace.id:
            raise HTTPException(404, "策略不存在")
    record = BacktestRecord(
        strategy_id=payload.strategy_id,
        workspace_id=auth.workspace.id,
        idempotency_key=payload.idempotency_key,
        spec_json=payload.spec.model_dump_json(),
    )
    db.add(record)
    audit(db, auth, audit_action, "backtest", record.id, {"market": payload.spec.universe.market, "paper_only": True})
    db.commit()
    cache_task_state(record.id, {"status": "queued", "progress": 0, "stage": "等待执行"})
    if getattr(payload, "dry_run", False):
        record.status = "cancelled"
        record.stage = "Agent dry-run 未执行"
        db.commit()
        cache_task_state(record.id, {"status": "cancelled", "progress": 0, "stage": "Agent dry-run 未执行"})
    elif settings.app_env in {"beta", "production"}:
        try:
            enqueue_backtest(record.id)
        except Exception:
            record.status = "failed"
            record.stage = "任务队列不可用"
            record.error = "任务服务暂不可用，请稍后重试。"
            db.commit()
    else:
        background_tasks.add_task(execute_backtest, record.id)
    return backtest_out(record)


@app.post("/api/v1/backtests", response_model=BacktestOut, status_code=202)
def create_backtest(payload: BacktestCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> BacktestOut:
    return submit_backtest_record(payload, background_tasks, db, auth)


def backtest_out(record: BacktestRecord) -> BacktestOut:
    return BacktestOut(
        id=record.id,
        status=record.status,
        progress=int(record.progress),
        stage=record.stage,
        result=BacktestResult.model_validate_json(record.result_json) if record.result_json else None,
        data_snapshot_id=record.data_snapshot_id,
        error=record.error,
        created_at=record.created_at,
    )


@app.get("/api/v1/backtests/{backtest_id}", response_model=BacktestOut)
def get_backtest(backtest_id: str, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> BacktestOut:
    record = db.get(BacktestRecord, backtest_id)
    if not record or record.workspace_id != auth.workspace.id:
        raise HTTPException(404, "回测任务不存在")
    return backtest_out(record)


@app.delete("/api/v1/backtests/{backtest_id}", status_code=204)
def cancel_backtest(backtest_id: str, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> Response:
    record = db.get(BacktestRecord, backtest_id)
    if not record or record.workspace_id != auth.workspace.id:
        raise HTTPException(404, "回测任务不存在")
    if record.status in {"queued", "running"}:
        record.status = "cancelled"
        record.stage = "已终止"
        audit(db, auth, "backtest.cancel", "backtest", record.id)
        db.commit()
        cache_task_state(record.id, {"status": "cancelled", "progress": int(record.progress), "stage": "已终止"})
    return Response(status_code=204)


@app.get("/api/v1/backtests/{backtest_id}/trades")
def get_trades(backtest_id: str, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)):
    record = db.get(BacktestRecord, backtest_id)
    if not record or record.workspace_id != auth.workspace.id or not record.result_json:
        raise HTTPException(404, "交易记录尚未生成")
    return BacktestResult.model_validate_json(record.result_json).trades


@app.get("/api/v1/audit-events", response_model=list[AuditEventOut])
def list_audit_events(db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> list[AuditEventOut]:
    records = db.scalars(select(AuditEventRecord).where(AuditEventRecord.workspace_id == auth.workspace.id).order_by(AuditEventRecord.created_at.desc()).limit(100)).all()
    return [AuditEventOut(id=item.id, action=item.action, resource_type=item.resource_type, resource_id=item.resource_id, metadata=json.loads(item.metadata_json), created_at=item.created_at) for item in records]


@app.post("/api/v1/paper/orders", response_model=OrderOut, status_code=201)
def create_paper_order(payload: OrderCreate, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> OrderOut:
    existing = db.scalar(select(OrderRecord).where(OrderRecord.client_order_id == payload.client_order_id))
    if existing:
        if existing.workspace_id != auth.workspace.id:
            raise HTTPException(409, "订单幂等键已占用")
        return order_out(existing)
    record = OrderRecord(
        workspace_id=auth.workspace.id, user_id=auth.user.id, account_type="paper", market=payload.market,
        symbol=payload.symbol.upper(), side=payload.side, order_type=payload.order_type, quantity=payload.quantity,
        limit_price=payload.limit_price, client_order_id=payload.client_order_id, status="accepted",
    )
    db.add(record)
    db.flush()
    audit(db, auth, "paper_order.create", "order", record.id, {"market": record.market, "symbol": record.symbol, "side": record.side})
    db.commit()
    return order_out(record)


@app.get("/api/v1/paper/orders", response_model=list[OrderOut])
def list_paper_orders(db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> list[OrderOut]:
    records = db.scalars(select(OrderRecord).where(OrderRecord.workspace_id == auth.workspace.id, OrderRecord.account_type == "paper").order_by(OrderRecord.created_at.desc())).all()
    return [order_out(record) for record in records]


@app.delete("/api/v1/paper/orders/{order_id}", response_model=OrderOut)
def cancel_paper_order(order_id: str, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> OrderOut:
    record = db.get(OrderRecord, order_id)
    if not record or record.workspace_id != auth.workspace.id:
        raise HTTPException(404, "订单不存在")
    if record.status != "accepted":
        raise HTTPException(409, "当前订单状态不可撤销")
    record.status = "cancelled"
    audit(db, auth, "paper_order.cancel", "order", record.id)
    db.commit()
    return order_out(record)


@app.get("/api/agent/v1/manifest", response_model=AgentManifestOut)
def agent_manifest(auth: AuthContext = Depends(require_auth)) -> AgentManifestOut:
    return AgentManifestOut(
        live_trading_enabled=False,
        tools=[
            AgentToolOut(name="workspace.read", method="GET", path="/api/agent/v1/workspace", scope="read:workspace", status="enabled", description="读取当前用户、工作区、能力和最近实验。"),
            AgentToolOut(name="strategy.parse", method="POST", path="/api/agent/v1/strategy/parse", scope="parse:strategy", status="enabled", description="将自然语言转换为受控 StrategySpecV1。"),
            AgentToolOut(name="backtest.submit", method="POST", path="/api/agent/v1/backtests", scope="write:backtest", status="enabled", description="提交服务端回测任务，可 dry-run。"),
            AgentToolOut(name="paper_order.create", method="POST", path="/api/agent/v1/paper/orders", scope="write:paper_order", status="paper_only", description="创建模拟盘订单，幂等并审计。"),
            AgentToolOut(name="live_order.create", method="POST", path="/api/agent/v1/live/orders", scope="write:live_order", status="blocked", description="实盘交易永久默认关闭，当前端点只返回拒绝。"),
        ],
    )


@app.get("/api/agent/v1/workspace", response_model=AgentWorkspaceOut)
def agent_workspace(db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> AgentWorkspaceOut:
    records = db.scalars(select(BacktestRecord).where(BacktestRecord.workspace_id == auth.workspace.id).order_by(BacktestRecord.created_at.desc()).limit(5)).all()
    audit(db, auth, "agent.workspace.read", "agent_gateway", auth.workspace.id, {"paper_only": True})
    db.commit()
    return AgentWorkspaceOut(
        user=UserOut(id=auth.user.id, email=auth.user.email, display_name=auth.user.display_name),
        workspace=WorkspaceOut(id=auth.workspace.id, name=auth.workspace.name, slug=auth.workspace.slug, role=auth.role),
        capabilities=agent_capability_items(),
        latest_experiments=[experiment_out(record) for record in records],
    )


@app.post("/api/agent/v1/strategy/parse", response_model=ParseResponse)
def agent_parse_strategy(payload: ParseRequest, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> ParseResponse:
    result = parse_strategy(payload.text)
    audit(db, auth, "agent.strategy.parse", "agent_gateway", metadata={"compliance_status": result.compliance_status.value, "provider": result.provider})
    db.commit()
    return result


@app.post("/api/agent/v1/backtests", response_model=BacktestOut, status_code=202)
def agent_create_backtest(payload: AgentBacktestCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> BacktestOut:
    return submit_backtest_record(payload, background_tasks, db, auth, "agent.backtest.submit")


@app.post("/api/agent/v1/paper/orders", response_model=OrderOut, status_code=201)
def agent_create_paper_order(payload: OrderCreate, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> OrderOut:
    order = create_paper_order(payload, db, auth)
    audit(db, auth, "agent.paper_order.create", "order", order.id, {"paper_only": True, "symbol": order.symbol})
    db.commit()
    return order


@app.post("/api/agent/v1/live/orders", status_code=403)
def agent_create_live_order(payload: LiveOrderRequest, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> Response:
    audit(db, auth, "agent.live_order.blocked", "live_order", metadata={"market": payload.market, "symbol": payload.symbol.upper(), "side": payload.side})
    db.commit()
    raise HTTPException(403, "实盘交易默认关闭；Agent 只能使用研究、回测和模拟盘能力。")
