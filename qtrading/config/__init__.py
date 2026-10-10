from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TradingConfig(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    exchanges: list[str] = Field(default_factory=list)


class DataConfig(BaseModel):
    cache_dir: str = "./data/cache"
    lookback_days: int = 365
    update_interval_seconds: int = 60
    db_path: str = "./data/market_data.db"
    max_price_deviation: float = 0.5
    min_volume: float = 0.0
    max_gap_pct: float = 0.2
    max_reconnect_attempts: int = 10
    reconnect_delay_seconds: float = 5.0


class BacktestConfig(BaseModel):
    initial_capital: float = 100000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    max_positions: int = 10


class RiskConfig(BaseModel):
    max_drawdown: float = 0.15
    max_position_size: float = 0.1
    max_daily_loss: float = 0.05
    var_confidence: float = 0.95
    correlation_threshold: float = 0.7


class ExecutionConfig(BaseModel):
    order_type: str = "limit"
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: int = 1


class MonitoringConfig(BaseModel):
    log_level: str = "INFO"
    metrics_port: int = 9090
    health_check_interval: int = 30


class Settings(BaseModel):
    trading: TradingConfig = Field(default_factory=TradingConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)


@lru_cache
def get_settings(config_path: str | None = None) -> Settings:
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"

    with open(config_path) as f:
        raw_config: dict[str, Any] = yaml.safe_load(f) or {}

    return Settings(**raw_config)


def reload_settings(config_path: str | None = None) -> Settings:
    get_settings.cache_clear()
    return get_settings(config_path)
