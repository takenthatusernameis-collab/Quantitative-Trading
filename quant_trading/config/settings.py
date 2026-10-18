"""Configuration management for the trading system.

This module defines the dataclass-based configuration hierarchy consumed by
the backtest engine, risk manager, portfolio rebalancer, and data layer. The
top-level :class:`Config` aggregates four sub-configs and supports
serialization to and from YAML.

Examples:
    Load a configuration from YAML and inspect it::

        import tempfile, os
        from quant_trading.config.settings import Config

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.yaml")
            Config().to_yaml(path)
            loaded = Config.from_yaml(path)
            assert loaded.logging_level == "INFO"

    Update configuration fields via keyword arguments::

        from quant_trading.config.settings import Config

        config = Config()
        config.update(logging_level="DEBUG")
        assert config.logging_level == "DEBUG"
"""

import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class DataConfig:
    """Configuration for market data retrieval and caching.

    Attributes:
        provider: Data provider name (e.g. ``"yfinance"``).
        cache_dir: Directory used to cache downloaded market data.
        default_interval: Default bar interval for fetched data (e.g. ``"1d"``).
        default_period: Default history span for fetched data (e.g. ``"1y"``).
        offline: When True, skip live data fetching and use cached/synthetic
            data only.
        synthetic_days: Number of days to generate when synthesizing data.
        synthetic_seed: RNG seed for deterministic synthetic data generation.
        alphavantage_api_key: Optional Alpha Vantage API key, used when the
            provider is set to ``"alphavantage"``.

    Examples:
        Create a data config with custom defaults::

            from quant_trading.config.settings import DataConfig

            data = DataConfig(provider="alphavantage", default_interval="1h")
            assert data.default_interval == "1h"
            assert data.alphavantage_api_key is None
    """

    provider: str = "yfinance"
    cache_dir: str = "./data/cache"
    default_interval: str = "1d"
    default_period: str = "1y"
    offline: bool = False
    synthetic_days: int = 365
    synthetic_seed: int = 42
    alphavantage_api_key: str | None = None


def _filter_fields(dataclass_type: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Keep only values whose keys are valid dataclass fields.

    Used when deserializing YAML so unknown keys do not raise errors.

    Args:
        dataclass_type: Dataclass whose fields define the allow-list.
        values: Mapping of candidate key/value pairs.

    Returns:
        A new dict containing only the entries whose keys are declared
        fields of ``dataclass_type``. Returns an empty dict when ``values``
        is not a dict.

    Examples:
        >>> from quant_trading.config.settings import _filter_fields, DataConfig
        >>> _filter_fields(DataConfig, {"provider": "x", "bogus": 1}) == {"provider": "x"}
        True
        >>> _filter_fields(DataConfig, None)
        {}
    """
    if not isinstance(values, dict):
        return {}
    valid = {f.name for f in dataclass_type.__dataclass_fields__.values()}
    return {k: v for k, v in values.items() if k in valid}


@dataclass
class BacktestConfig:
    """Configuration for backtesting execution.

    Attributes:
        initial_capital: Starting capital for each backtest run.
        commission: Commission rate per trade (as a fraction of trade
            value).
        slippage: Slippage rate applied to each fill (as a fraction of
            trade value).
        risk_free_rate: Risk-free rate used for risk-adjusted metrics.
        halt_on_portfolio_violation: When True, stop the backtest if the
            portfolio breaches a configured risk limit.

    Examples:
        >>> from quant_trading.config.settings import BacktestConfig
        >>> cfg = BacktestConfig(initial_capital=50000.0, commission=0.002)
        >>> cfg.initial_capital
        50000.0
        >>> cfg.slippage
        0.0005
    """

    initial_capital: float = 100000.0
    commission: float = 0.001
    slippage: float = 0.0005
    risk_free_rate: float = 0.02
    halt_on_portfolio_violation: bool = False


@dataclass
class RiskConfig:
    """Configuration for risk management limits.

    Attributes:
        max_position_size: Maximum fraction of portfolio value a single
            position may occupy.
        max_portfolio_risk: Maximum fraction of portfolio value that may be
            at risk at any time.
        stop_loss_pct: Stop-loss distance as a fraction of entry price.
        take_profit_pct: Take-profit distance as a fraction of entry price.
        max_drawdown: Maximum tolerated portfolio drawdown as a fraction.

    Examples:
        >>> from quant_trading.config.settings import RiskConfig
        >>> RiskConfig().max_position_size
        0.1
    """

    max_position_size: float = 0.1
    max_portfolio_risk: float = 0.02
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.15
    max_drawdown: float = 0.20


@dataclass
class PortfolioConfig:
    """Configuration for portfolio construction and rebalancing.

    Attributes:
        rebalance_frequency: Rebalancing cadence (e.g. ``"monthly"``).
        max_positions: Maximum number of simultaneous positions allowed.
        min_position_size: Minimum fraction of portfolio value for a new
            position.

    Examples:
        >>> from quant_trading.config.settings import PortfolioConfig
        >>> PortfolioConfig().rebalance_frequency
        'monthly'
    """

    rebalance_frequency: str = "monthly"
    max_positions: int = 20
    min_position_size: float = 0.01


@dataclass
class Config:
    """Main configuration object aggregating all subsystem settings.

    Aggregates :class:`DataConfig`, :class:`BacktestConfig`,
    :class:`RiskConfig`, and :class:`PortfolioConfig` into a single
    serializable object that can be loaded from or saved to YAML.

    Attributes:
        data: Market data retrieval configuration.
        backtest: Backtesting execution configuration.
        risk: Risk management limits configuration.
        portfolio: Portfolio construction and rebalancing configuration.
        logging_level: Logging level name (e.g. ``"INFO"``).
        output_dir: Directory where outputs are written.

    Examples:
        Create a config and update a field::

            from quant_trading.config.settings import Config

            config = Config()
            config.update(logging_level="DEBUG")
            assert config.logging_level == "DEBUG"

        Unknown keys are silently ignored::

            config.update(unknown_key="value")
            assert not hasattr(config, "unknown_key")
    """

    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    logging_level: str = "INFO"
    output_dir: str = "./output"

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from a YAML file.

        Unknown keys are filtered out per-sub-config so partial or
        forward-compatible files still load.

        Args:
            path: Path to the YAML file.

        Returns:
            A new :class:`Config` instance populated from the file.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            ValueError: If the file contains invalid YAML or the top-level
                document is not a mapping.
            yaml.YAMLError: If the YAML cannot be parsed.
        """
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
        """Save configuration to a YAML file as plain mappings.

        Parent directories for ``path`` are created if they do not exist.
        A bare filename (no directory component) is written to the current
        working directory.

        Args:
            path: Destination path for the YAML file.

        Returns:
            None.
        """
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self._to_dict(), f, default_flow_style=False)

    def _to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a plain dict for YAML.

        Returns:
            Dictionary with ``data``, ``backtest``, ``risk``,
            ``portfolio``, ``logging_level``, and ``output_dir`` keys.
        """
        return {
            "data": self.data.__dict__,
            "backtest": self.backtest.__dict__,
            "risk": self.risk.__dict__,
            "portfolio": self.portfolio.__dict__,
            "logging_level": self.logging_level,
            "output_dir": self.output_dir,
        }

    def update(self, **kwargs: Any) -> None:
        """Update configuration attributes from keyword arguments.

        Only attributes that already exist on the config are updated;
        unknown keys are silently ignored.

        Args:
            **kwargs: Attribute name/value pairs to set.

        Returns:
            None.
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


DEFAULT_CONFIG = Config()
