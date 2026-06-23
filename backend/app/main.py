import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
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
    BacktestCreate,
    BacktestOut,
    BacktestResult,
    HealthResponse,
    AuditEventOut,
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    MarketDataSnapshotMeta,
    OrderCreate,
    OrderOut,
    ParseRequest,
    ParseResponse,
    StrategyCreate,
    StrategyOut,
    StrategySpecV1,
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


@app.post("/api/v1/backtests", response_model=BacktestOut, status_code=202)
def create_backtest(payload: BacktestCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), auth: AuthContext = Depends(require_auth)) -> BacktestOut:
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
    audit(db, auth, "backtest.submit", "backtest", record.id, {"market": payload.spec.universe.market})
    db.commit()
    cache_task_state(record.id, {"status": "queued", "progress": 0, "stage": "等待执行"})
    if settings.app_env in {"beta", "production"}:
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
