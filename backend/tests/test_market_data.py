import json

from app.config import Settings
import pytest

from app.backtest import load_market
from app.market_data import _fetch_tushare, _fetch_twelve_data
from app.templates import ema_template


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_tushare_dataset_is_validated_versioned_and_cached(tmp_path, monkeypatch):
    settings = Settings(tushare_token="test-token", data_cache_dir=str(tmp_path))
    payload = {"code": 0, "data": {"fields": ["ts_code", "trade_date", "open", "close"], "items": [
        ["000300.SH", "20190103", 101, 102], ["000300.SH", "20190102", 100, 101],
    ]}}
    monkeypatch.setattr("app.market_data.httpx.post", lambda *args, **kwargs: FakeResponse(payload))
    first = _fetch_tushare(ema_template(), settings)
    assert first.source.startswith("tushare:")
    assert first.cache_path.exists()
    metadata = json.loads(first.cache_path.with_suffix(".meta.json").read_text())
    assert metadata["snapshot_id"] == first.snapshot_id
    monkeypatch.setattr("app.market_data.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cache not used")))
    second = _fetch_tushare(ema_template(), settings)
    assert second.snapshot_id == first.snapshot_id


def test_twelve_data_supports_hk_and_us_daily_cache(tmp_path, monkeypatch):
    settings = Settings(twelve_data_api_key="test-key", data_cache_dir=str(tmp_path))
    payload = {"status": "ok", "values": [
        {"datetime": "2019-01-02", "open": "25000", "close": "25100"},
        {"datetime": "2019-01-03", "open": "25120", "close": "25200"},
    ]}
    monkeypatch.setattr("app.market_data.httpx.get", lambda *args, **kwargs: FakeResponse(payload))
    for market, benchmark in [("HK", "HSI.HK"), ("US", "SPY.US")]:
        spec = ema_template()
        spec.universe.market = market
        spec.universe.index = benchmark
        spec.backtest.benchmark = benchmark
        dataset = _fetch_twelve_data(spec, settings)
        assert dataset.source.startswith("twelve-data:")
        assert list(dataset.frame.columns) == ["open", "close", "market_return"]


def test_beta_environment_never_falls_back_to_demo(monkeypatch):
    monkeypatch.setattr("app.backtest.get_settings", lambda: Settings(app_env="beta", tushare_token=None, twelve_data_api_key=None))
    with pytest.raises(RuntimeError, match="尚未配置授权行情源"):
        load_market(ema_template())
