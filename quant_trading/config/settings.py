"""Configuration management for the trading system."""

import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class DataConfig:
    """Data source configuration."""

    provider: str = "yfinance"
    cache_dir: str = "./data/cache"
    default_interval: str = "1d"
    default_period: str = "1y"


def _filter_fields(dataclass_type: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Keep only values whose keys are valid dataclass fields."""
    if not isinstance(values, dict):
        return {}
    valid = {f.name for f in dataclass_type.__dataclass_fields__.values()}
    return {k: v for k, v in values.items() if k in valid}


@dataclass
class BacktestConfig:
    """Backtesting configuration."""

    initial_capital: float = 100000.0
    commission: float = 0.001
    slippage: float = 0.0005
    risk_free_rate: float = 0.02


@dataclass
class RiskConfig:
    """Risk management configuration."""

    max_position_size: float = 0.1
    max_portfolio_risk: float = 0.02
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.15
    max_drawdown: float = 0.20


@dataclass
class PortfolioConfig:
    """Portfolio management configuration."""

    rebalance_frequency: str = "monthly"
    max_positions: int = 20
    min_position_size: float = 0.01


@dataclass
class Config:
    """Main configuration class."""

    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    logging_level: str = "INFO"
    output_dir: str = "./output"

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from YAML file."""
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Configuration in {path} is not a mapping")  # noqa: TRY004
        return cls(
            data=DataConfig(**_filter_fields(DataConfig, data.get("data", {}))),
            backtest=BacktestConfig(**_filter_fields(BacktestConfig, data.get("backtest", {}))),
            risk=RiskConfig(**_filter_fields(RiskConfig, data.get("risk", {}))),
            portfolio=PortfolioConfig(**_filter_fields(PortfolioConfig, data.get("portfolio", {}))),
            logging_level=data.get("logging_level", "INFO"),
            output_dir=data.get("output_dir", "./output"),
        )

    def to_yaml(self, path: str) -> None:
        """Save configuration to YAML file as plain mappings."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self._to_dict(), f, default_flow_style=False)

    def _to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a plain dict for YAML."""
        return {
            "data": self.data.__dict__,
            "backtest": self.backtest.__dict__,
            "risk": self.risk.__dict__,
            "portfolio": self.portfolio.__dict__,
            "logging_level": self.logging_level,
            "output_dir": self.output_dir,
        }

    def update(self, **kwargs: Any) -> None:
        """Update configuration with keyword arguments."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


DEFAULT_CONFIG = Config()
