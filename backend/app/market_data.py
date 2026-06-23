import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from .config import Settings, get_settings
from .schemas import StrategySpecV1


class MarketDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketDataset:
    frame: pd.DataFrame
    provider: str
    market: str
    symbol: str
    vendor_symbol: str | None
    frequency: str
    start_date: str
    end_date: str
    rows: int
    source: str
    snapshot_id: str
    cache_path: Path
    fetched_at: str


def snapshot_record_id(*, provider: str, market: str, symbol: str, frequency: str, start_date: str, end_date: str, snapshot_id: str) -> str:
    payload = f"{provider}|{market}|{symbol}|{frequency}|{start_date}|{end_date}|{snapshot_id}".encode()
    return hashlib.sha256(payload).hexdigest()[:32]


def _paths(settings: Settings, provider: str, market: str, symbol: str, start: str, end: str) -> tuple[Path, Path]:
    safe_symbol = symbol.replace(".", "_").replace("/", "_")
    directory = Path(settings.data_cache_dir) / provider / market
    directory.mkdir(parents=True, exist_ok=True)
    stem = directory / f"{safe_symbol}_{start}_{end}"
    return stem.with_suffix(".csv"), stem.with_suffix(".meta.json")


def _validate(frame: pd.DataFrame, start, end) -> pd.DataFrame:
    if frame.empty or not {"open", "close"}.issubset(frame.columns):
        raise MarketDataError("行情数据为空或缺少 open/close 字段")
    normalized = frame.copy()
    normalized.index = pd.to_datetime(normalized.index).tz_localize(None)
    normalized = normalized.sort_index()
    normalized = normalized.loc[(normalized.index.date >= start) & (normalized.index.date <= end)]
    normalized[["open", "close"]] = normalized[["open", "close"]].apply(pd.to_numeric, errors="coerce")
    normalized = normalized.dropna(subset=["open", "close"])
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    if len(normalized) < 2 or (normalized[["open", "close"]] <= 0).any().any():
        raise MarketDataError("行情记录不足或存在非法价格")
    normalized["market_return"] = normalized["close"].pct_change().fillna(0)
    return normalized[["open", "close", "market_return"]]


def _snapshot(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(date_format="%Y-%m-%d", float_format="%.8f").encode()
    return hashlib.sha256(payload).hexdigest()[:20]


def _dataset_from_metadata(frame: pd.DataFrame, csv_path: Path, metadata: dict) -> MarketDataset:
    provider = metadata["provider"]
    market = metadata["market"]
    symbol = metadata["symbol"]
    frequency = metadata.get("frequency", "1day")
    snapshot_id = metadata["snapshot_id"]
    start_date = metadata.get("start_date", str(frame.index[0].date()))
    end_date = metadata.get("end_date", str(frame.index[-1].date()))
    fetched_at = metadata.get("fetched_at") or datetime.now(timezone.utc).isoformat()
    return MarketDataset(
        frame=frame,
        provider=provider,
        market=market,
        symbol=symbol,
        vendor_symbol=metadata.get("vendor_symbol"),
        frequency=frequency,
        start_date=start_date,
        end_date=end_date,
        rows=len(frame),
        source=f"{provider}:{snapshot_id}",
        snapshot_id=snapshot_id,
        cache_path=csv_path,
        fetched_at=fetched_at,
    )


def _save(frame: pd.DataFrame, csv_path: Path, meta_path: Path, *, provider: str, market: str, symbol: str, vendor_symbol: str | None = None) -> MarketDataset:
    snapshot_id = _snapshot(frame)
    frame.to_csv(csv_path, index_label="trade_date", date_format="%Y-%m-%d")
    metadata = {
        "provider": provider, "market": market, "symbol": symbol, "vendor_symbol": vendor_symbol,
        "frequency": "1day", "snapshot_id": snapshot_id,
        "rows": len(frame), "start_date": str(frame.index[0].date()), "end_date": str(frame.index[-1].date()),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return _dataset_from_metadata(frame, csv_path, metadata)


def _load_cache(csv_path: Path, meta_path: Path, start, end) -> MarketDataset | None:
    if not csv_path.exists() or not meta_path.exists():
        return None
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    frame = pd.read_csv(csv_path, parse_dates=["trade_date"]).set_index("trade_date")
    frame = _validate(frame, start, end)
    snapshot_id = _snapshot(frame)
    if snapshot_id != metadata.get("snapshot_id"):
        raise MarketDataError(f"缓存快照校验失败: {csv_path}")
    return _dataset_from_metadata(frame, csv_path, metadata)


def _fetch_tushare(spec: StrategySpecV1, settings: Settings) -> MarketDataset:
    if not settings.tushare_token:
        raise MarketDataError("A股真实行情需要配置 TUSHARE_TOKEN")
    start, end = str(spec.backtest.start_date), str(spec.backtest.end_date)
    csv_path, meta_path = _paths(settings, "tushare", "CN_A", spec.backtest.benchmark, start, end)
    cached = _load_cache(csv_path, meta_path, spec.backtest.start_date, spec.backtest.end_date)
    if cached:
        return cached
    response = httpx.post(settings.tushare_api_url, json={
        "api_name": "index_daily", "token": settings.tushare_token,
        "params": {"ts_code": spec.backtest.benchmark, "start_date": start.replace("-", ""), "end_date": end.replace("-", "")},
        "fields": "ts_code,trade_date,open,close",
    }, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0 or not payload.get("data", {}).get("items"):
        raise MarketDataError(payload.get("msg") or "Tushare 未返回行情")
    frame = pd.DataFrame(payload["data"]["items"], columns=payload["data"]["fields"])
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d")
    frame = _validate(frame.set_index("trade_date"), spec.backtest.start_date, spec.backtest.end_date)
    return _save(frame, csv_path, meta_path, provider="tushare", market="CN_A", symbol=spec.backtest.benchmark, vendor_symbol=spec.backtest.benchmark)


def _fetch_twelve_data(spec: StrategySpecV1, settings: Settings) -> MarketDataset:
    if not settings.twelve_data_api_key:
        raise MarketDataError("港美股真实行情需要配置 TWELVE_DATA_API_KEY")
    market = spec.universe.market
    vendor_symbol = settings.hk_benchmark_vendor_symbol if market == "HK" else settings.us_benchmark_vendor_symbol
    start, end = str(spec.backtest.start_date), str(spec.backtest.end_date)
    csv_path, meta_path = _paths(settings, "twelve-data", market, spec.backtest.benchmark, start, end)
    cached = _load_cache(csv_path, meta_path, spec.backtest.start_date, spec.backtest.end_date)
    if cached:
        return cached
    response = httpx.get(settings.twelve_data_api_url, params={
        "symbol": vendor_symbol, "interval": "1day", "start_date": start, "end_date": end,
        "outputsize": 5000, "order": "ASC", "timezone": "UTC", "apikey": settings.twelve_data_api_key,
    }, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "error" or not payload.get("values"):
        raise MarketDataError(payload.get("message") or "Twelve Data 未返回行情")
    frame = pd.DataFrame(payload["values"])
    frame["trade_date"] = pd.to_datetime(frame["datetime"])
    frame = _validate(frame.set_index("trade_date"), spec.backtest.start_date, spec.backtest.end_date)
    return _save(frame, csv_path, meta_path, provider="twelve-data", market=market, symbol=spec.backtest.benchmark, vendor_symbol=vendor_symbol)


def load_real_market(spec: StrategySpecV1) -> MarketDataset:
    settings = get_settings()
    try:
        return _fetch_tushare(spec, settings) if spec.universe.market == "CN_A" else _fetch_twelve_data(spec, settings)
    except httpx.HTTPError as exc:
        raise MarketDataError(f"行情服务请求失败: {exc.__class__.__name__}") from exc


def market_data_status(settings: Settings | None = None) -> dict[str, str]:
    active = settings or get_settings()
    return {
        "CN_A": "configured" if active.tushare_token else "missing_credentials",
        "HK": "configured" if active.twelve_data_api_key else "missing_credentials",
        "US": "configured" if active.twelve_data_api_key else "missing_credentials",
    }
