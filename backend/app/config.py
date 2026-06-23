from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "QuantPartner API"
    app_env: str = "development"
    database_url: str = "sqlite:///./quantpartner.db"
    redis_url: str = "redis://localhost:6379/0"
    frontend_origin: str = "http://localhost:3000"
    tushare_token: str | None = None
    tushare_api_url: str = "https://api.tushare.pro"
    twelve_data_api_key: str | None = None
    twelve_data_api_url: str = "https://api.twelvedata.com/time_series"
    hk_benchmark_vendor_symbol: str = "HSI"
    us_benchmark_vendor_symbol: str = "SPY"
    data_cache_dir: str = "./data/cache"
    deepseek_api_key: str | None = None
    deepseek_api_url: str = "https://api.deepseek.com/chat/completions"
    deepseek_model: str = "deepseek-chat"
    kimi_api_key: str | None = None
    kimi_api_url: str = "https://api.moonshot.cn/v1/chat/completions"
    kimi_model: str = "kimi-k2-0711-preview"
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_duty_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    slippage_rate: float = 0.0005
    live_trading_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
