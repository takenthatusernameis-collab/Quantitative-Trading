"""Configuration management for the trading system.

This module defines the dataclass-based configuration hierarchy consumed by
the backtest engine, risk manager, portfolio rebalancer, and data layer. The
top-level :class:`Config` aggregates four sub-configs and supports
serialization to and from YAML.

Examples:
    Load a configuration from YAML and inspect it::

        >>> import tempfile, os
        >>> from quant_trading.config.settings import Config
        >>> tmpdir = tempfile.mkdtemp()
        >>> path = os.path.join(tmpdir, "config.yaml")
        >>> Config().to_yaml(path)
        >>> loaded = Config.from_yaml(path)
        >>> loaded.logging_level == "INFO"
        True

    Update configuration fields via keyword arguments::

        >>> from quant_trading.config.settings import Config
        >>> config = Config()
        >>> config.update(logging_level="DEBUG")
        >>> config.logging_level == "DEBUG"
        True

"""

import os
import typing
from dataclasses import dataclass, field, fields, is_dataclass
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
        >>> from quant_trading.config.settings import DataConfig
        >>> data = DataConfig(provider="alphavantage", default_interval="1h")
        >>> data.default_interval
        '1h'
        >>> data.alphavantage_api_key is None
        True

    """

    provider: str = "yfinance"
    cache_dir: str = "./data/cache"
    default_interval: str = "1d"
    default_period: str = "1y"
    offline: bool = False
    synthetic_days: int = 365
    synthetic_seed: int = 42
    alphavantage_api_key: str | None = None

    def __post_init__(self) -> None:
        """Reject out-of-range data-config inputs at construction time.

        Invalid values are rejected when a config is built (directly, from a
        dictionary, or from YAML) instead of silently propagating to the data
        layer.
        """
        if not self.provider:
            raise ValueError(
                f"invalid provider: the value must be a non-empty string "
                f"(got {self.provider!r})"
            )
        if not self.default_interval:
            raise ValueError(
                f"invalid default_interval: the value must be a non-empty "
                f"string (got {self.default_interval!r})"
            )
        if not self.default_period:
            raise ValueError(
                f"invalid default_period: the value must be a non-empty "
                f"string (got {self.default_period!r})"
            )
        if self.synthetic_days < 1:
            raise ValueError(
                f"invalid synthetic_days: the value must be at least 1 "
                f"(got {self.synthetic_days})"
            )
        if self.synthetic_seed < 0 or self.synthetic_seed > 2**32 - 1:
            raise ValueError(
                f"invalid synthetic_seed: the value must be between 0 and "
                f"{2**32 - 1} (got {self.synthetic_seed})"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert the data configuration to a plain, JSON-safe dictionary.

        Returns:
            Dictionary with keys ``provider``, ``cache_dir``,
            ``default_interval``, ``default_period``, ``offline``,
            ``synthetic_days``, ``synthetic_seed``, and
            ``alphavantage_api_key``.

        Examples:
            >>> from quant_trading.config.settings import DataConfig
            >>> data = DataConfig(provider="synthetic", offline=True)
            >>> d = data.to_dict()
            >>> d["provider"], d["offline"]
            ('synthetic', True)
            >>> d["alphavantage_api_key"] is None
            True

        """
        return {
            "provider": self.provider,
            "cache_dir": self.cache_dir,
            "default_interval": self.default_interval,
            "default_period": self.default_period,
            "offline": self.offline,
            "synthetic_days": self.synthetic_days,
            "synthetic_seed": self.synthetic_seed,
            "alphavantage_api_key": self.alphavantage_api_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataConfig":
        """Deserialize a :class:`DataConfig` from a dictionary.

        Missing keys fall back to the class defaults. Extra keys are ignored.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`DataConfig`.

        Examples:
            >>> from quant_trading.config.settings import DataConfig
            >>> restored = DataConfig.from_dict({"provider": "synthetic"})
            >>> restored.provider
            'synthetic'
            >>> restored.offline
            False
            >>> restored.synthetic_days
            365

        """
        return cls(
            provider=str(data.get("provider", "yfinance")),
            cache_dir=str(data.get("cache_dir", "./data/cache")),
            default_interval=str(data.get("default_interval", "1d")),
            default_period=str(data.get("default_period", "1y")),
            offline=bool(data.get("offline", False)),
            synthetic_days=int(data.get("synthetic_days", 365)),
            synthetic_seed=int(data.get("synthetic_seed", 42)),
            alphavantage_api_key=data.get("alphavantage_api_key"),
        )


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


def _type_matches(expected_type: Any, value: Any) -> bool:
    """Return True when ``value`` is an acceptable value for ``expected_type``.

    Rules:
    * ``None`` accepts only ``None``.
    * A union (e.g. ``str | None``) accepts a value matching any member.
    * ``bool`` accepts only a boolean; an ``int`` is not a boolean.
    * ``int`` accepts an ``int`` but not a ``bool`` and not a ``float``.
    * ``float`` accepts an ``int`` or a ``float`` but not a ``bool``.
    * ``str`` accepts only a string.
    * Unrecognized annotations accept anything.

    Args:
        expected_type: The annotation of the field (a type or a union).
        value: The value parsed from YAML.

    Returns:
        True when ``value`` is acceptable for a field of type
        ``expected_type``.

    """
    if expected_type is None or expected_type is type(None):
        return value is None
    origin = typing.get_origin(expected_type)
    if origin is not None:
        return any(_type_matches(arg, value) for arg in typing.get_args(expected_type))
    if expected_type is bool:
        return isinstance(value, bool)
    if expected_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type is str:
        return isinstance(value, str)
    return True


def _check_field_types(dataclass_type: type, values: dict[str, Any]) -> None:
    """Validate each value in ``values`` against the dataclass annotations.

    Args:
        dataclass_type: The dataclass whose fields declare the expected types.
        values: The values parsed from YAML for that sub-config.

    Raises:
        ValueError: If a value does not match the declared type of its field.

    """
    for field_obj in fields(dataclass_type):
        name = field_obj.name
        if name not in values:
            continue
        expected = field_obj.type
        value = values[name]
        if not _type_matches(expected, value):
            raise ValueError(
                f"invalid config field {dataclass_type.__name__}.{name}: "
                f"expected {expected}, got {type(value).__name__} ({value!r})"
            )


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
        periods_per_year: Number of trading periods per year used to annualize
            the return, volatility, Sharpe, Sortino and Calmar metrics
            (252 for daily data, 52 for weekly, 12 for monthly).
        halt_on_portfolio_violation: When True, stop the backtest if the
            portfolio breaches a configured risk limit.
        enable_stop_exits: When True, the engine closes a position on the bar
            whose close hits its stop loss, its take profit or its trailing
            stop. The exits are off by default, so the levels the risk manager
            computes stay advisory until they are switched on.

    Examples:
        >>> from quant_trading.config.settings import BacktestConfig
        >>> cfg = BacktestConfig(initial_capital=50000.0, commission=0.002)
        >>> cfg.initial_capital
        50000.0
        >>> cfg.slippage
        0.0005
        >>> cfg.enable_stop_exits
        False

    """

    initial_capital: float = 100000.0
    commission: float = 0.001
    slippage: float = 0.0005
    risk_free_rate: float = 0.02
    periods_per_year: int = 252
    halt_on_portfolio_violation: bool = False
    enable_stop_exits: bool = False

    def __post_init__(self) -> None:
        """Reject out-of-range backtest inputs at construction time.

        Mirrors :meth:`quant_trading.optimization.base.BaseOptimizer.__init__`
        so invalid values are rejected when a config is built (directly, from a
        dictionary, or from YAML) instead of silently propagating to the
        backtest engine or optimizer.
        """
        if self.initial_capital <= 0:
            raise ValueError(
                f"invalid initial_capital: the value must be positive "
                f"(got {self.initial_capital})"
            )
        if self.periods_per_year < 1:
            raise ValueError(
                f"invalid periods_per_year: the value must be at least 1 "
                f"(got {self.periods_per_year})"
            )
        if not (0.0 <= self.commission <= 1.0):
            raise ValueError(
                f"invalid commission: the value must be in the range [0, 1] "
                f"(got {self.commission})"
            )
        if not (0.0 <= self.slippage <= 1.0):
            raise ValueError(
                f"invalid slippage: the value must be in the range [0, 1] "
                f"(got {self.slippage})"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert the backtest configuration to a plain, JSON-safe dictionary.

        Returns:
            Dictionary with keys ``initial_capital``, ``commission``,
            ``slippage``, ``risk_free_rate``, ``periods_per_year``,
            ``halt_on_portfolio_violation``, and ``enable_stop_exits``.

        Examples:
            >>> from quant_trading.config.settings import BacktestConfig
            >>> cfg = BacktestConfig(initial_capital=50000.0, commission=0.002)
            >>> d = cfg.to_dict()
            >>> d["initial_capital"], d["commission"]
            (50000.0, 0.002)
            >>> d["enable_stop_exits"]
            False

        """
        return {
            "initial_capital": self.initial_capital,
            "commission": self.commission,
            "slippage": self.slippage,
            "risk_free_rate": self.risk_free_rate,
            "periods_per_year": self.periods_per_year,
            "halt_on_portfolio_violation": self.halt_on_portfolio_violation,
            "enable_stop_exits": self.enable_stop_exits,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BacktestConfig":
        """Deserialize a :class:`BacktestConfig` from a dictionary.

        Missing keys fall back to the class defaults. Extra keys are ignored.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`BacktestConfig`.

        Examples:
            >>> from quant_trading.config.settings import BacktestConfig
            >>> restored = BacktestConfig.from_dict({"initial_capital": 50000})
            >>> restored.initial_capital
            50000.0
            >>> restored.periods_per_year
            252

        """
        return cls(
            initial_capital=float(data.get("initial_capital", 100000.0)),
            commission=float(data.get("commission", 0.001)),
            slippage=float(data.get("slippage", 0.0005)),
            risk_free_rate=float(data.get("risk_free_rate", 0.02)),
            periods_per_year=int(data.get("periods_per_year", 252)),
            halt_on_portfolio_violation=bool(
                data.get("halt_on_portfolio_violation", False)
            ),
            enable_stop_exits=bool(data.get("enable_stop_exits", False)),
        )


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
        max_leverage: Maximum gross exposure as a multiple of the portfolio
            value (1.0 = fully invested with no borrowing).
        trailing_stop_pct: Distance of the trailing stop from the best price
            a position has reached, as a fraction (``0.0`` disables trailing
            stops).
        trailing_stop_activation_pct: How far a position must move in its
            favour, as a fraction of its entry price, before its trailing stop
            starts to trail.

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
    max_leverage: float = 1.0
    trailing_stop_pct: float = 0.0
    trailing_stop_activation_pct: float = 0.0

    def __post_init__(self) -> None:
        """Reject out-of-range risk-limit inputs at construction time.

        Mirrors :class:`quant_trading.risk.manager.RiskManager` so invalid
        values are rejected when a config is built (directly, from a
        dictionary, or from YAML) instead of silently producing misleading
        risk decisions.
        """
        if not (0.0 < self.max_position_size <= 1.0):
            raise ValueError(
                f"invalid max_position_size: the value must be in the range (0, 1] "
                f"(got {self.max_position_size})"
            )
        if not (0.0 < self.max_portfolio_risk <= 1.0):
            raise ValueError(
                f"invalid max_portfolio_risk: the value must be in the range (0, 1] "
                f"(got {self.max_portfolio_risk})"
            )
        if not (0.0 <= self.max_drawdown <= 1.0):
            raise ValueError(
                f"invalid max_drawdown: the value must be in the range [0, 1] "
                f"(got {self.max_drawdown})"
            )
        if not (0.0 <= self.stop_loss_pct <= 1.0):
            raise ValueError(
                f"invalid stop_loss_pct: the value must be in the range [0, 1] "
                f"(got {self.stop_loss_pct})"
            )
        if not (0.0 <= self.take_profit_pct <= 1.0):
            raise ValueError(
                f"invalid take_profit_pct: the value must be in the range [0, 1] "
                f"(got {self.take_profit_pct})"
            )
        if self.max_leverage < 1e-9:
            raise ValueError(
                f"invalid max_leverage: the value must be positive "
                f"(got {self.max_leverage})"
            )
        if not (0.0 <= self.trailing_stop_pct <= 1.0):
            raise ValueError(
                f"invalid trailing_stop_pct: the value must be in the range [0, 1] "
                f"(got {self.trailing_stop_pct})"
            )
        if not (0.0 <= self.trailing_stop_activation_pct <= 1.0):
            raise ValueError(
                f"invalid trailing_stop_activation_pct: the value must be in the range [0, 1] "
                f"(got {self.trailing_stop_activation_pct})"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert the risk configuration to a plain, JSON-safe dictionary.

        Returns:
            Dictionary with keys ``max_position_size``,
            ``max_portfolio_risk``, ``stop_loss_pct``,
            ``take_profit_pct``, ``max_drawdown``, ``max_leverage``,
            ``trailing_stop_pct``, and ``trailing_stop_activation_pct``.

        Examples:
            >>> from quant_trading.config.settings import RiskConfig
            >>> cfg = RiskConfig(max_position_size=0.15, max_drawdown=0.10)
            >>> d = cfg.to_dict()
            >>> d["max_position_size"], d["max_drawdown"]
            (0.15, 0.1)
            >>> d["max_leverage"]
            1.0

        """
        return {
            "max_position_size": self.max_position_size,
            "max_portfolio_risk": self.max_portfolio_risk,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_drawdown": self.max_drawdown,
            "max_leverage": self.max_leverage,
            "trailing_stop_pct": self.trailing_stop_pct,
            "trailing_stop_activation_pct": self.trailing_stop_activation_pct,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RiskConfig":
        """Deserialize a :class:`RiskConfig` from a dictionary.

        Missing keys fall back to the class defaults. Extra keys are ignored.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`RiskConfig`.

        Examples:
            >>> from quant_trading.config.settings import RiskConfig
            >>> restored = RiskConfig.from_dict({"max_drawdown": 0.1})
            >>> restored.max_drawdown
            0.1
            >>> restored.max_position_size
            0.1

        """
        return cls(
            max_position_size=float(data.get("max_position_size", 0.1)),
            max_portfolio_risk=float(data.get("max_portfolio_risk", 0.02)),
            stop_loss_pct=float(data.get("stop_loss_pct", 0.05)),
            take_profit_pct=float(data.get("take_profit_pct", 0.15)),
            max_drawdown=float(data.get("max_drawdown", 0.20)),
            max_leverage=float(data.get("max_leverage", 1.0)),
            trailing_stop_pct=float(data.get("trailing_stop_pct", 0.0)),
            trailing_stop_activation_pct=float(
                data.get("trailing_stop_activation_pct", 0.0)
            ),
        )


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

    def __post_init__(self) -> None:
        """Reject out-of-range portfolio inputs at construction time.

        Mirrors :class:`quant_trading.risk.manager.RiskManager` so invalid
        values are rejected when a config is built (directly, from a
        dictionary, or from YAML) instead of silently propagating to the
        portfolio rebalancer.
        """
        if self.max_positions < 1:
            raise ValueError(
                f"invalid max_positions: the value must be at least 1 "
                f"(got {self.max_positions})"
            )
        if not (0.0 <= self.min_position_size <= 1.0):
            raise ValueError(
                f"invalid min_position_size: the value must be in the range [0, 1] "
                f"(got {self.min_position_size})"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert the portfolio configuration to a plain, JSON-safe dictionary.

        Returns:
            Dictionary with keys ``rebalance_frequency``, ``max_positions``,
            and ``min_position_size``.

        Examples:
            >>> from quant_trading.config.settings import PortfolioConfig
            >>> cfg = PortfolioConfig(rebalance_frequency="weekly", max_positions=10)
            >>> d = cfg.to_dict()
            >>> d["rebalance_frequency"], d["max_positions"]
            ('weekly', 10)
            >>> d["min_position_size"]
            0.01

        """
        return {
            "rebalance_frequency": self.rebalance_frequency,
            "max_positions": self.max_positions,
            "min_position_size": self.min_position_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PortfolioConfig":
        """Deserialize a :class:`PortfolioConfig` from a dictionary.

        Missing keys fall back to the class defaults. Extra keys are ignored.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`PortfolioConfig`.

        Examples:
            >>> from quant_trading.config.settings import PortfolioConfig
            >>> restored = PortfolioConfig.from_dict({"max_positions": 10})
            >>> restored.max_positions
            10
            >>> restored.rebalance_frequency
            'monthly'

        """
        return cls(
            rebalance_frequency=str(data.get("rebalance_frequency", "monthly")),
            max_positions=int(data.get("max_positions", 20)),
            min_position_size=float(data.get("min_position_size", 0.01)),
        )


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

            >>> from quant_trading.config.settings import Config
            >>> config = Config()
            >>> config.update(logging_level="DEBUG")
            >>> config.logging_level == "DEBUG"
            True

        Unknown keys are silently ignored::

            >>> config.update(unknown_key="value")
            >>> not hasattr(config, "unknown_key")
            True

    """

    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    logging_level: str = "INFO"
    output_dir: str = "./output"

    def to_dict(self) -> dict[str, Any]:
        """Convert the configuration to a plain, JSON-safe dictionary.

        Returns:
            Dictionary with ``data``, ``backtest``, ``risk``,
            ``portfolio``, ``logging_level``, and ``output_dir`` keys;
            each sub-config is serialized via its own :meth:`to_dict`.

        Examples:
            >>> from quant_trading.config.settings import Config
            >>> config = Config(logging_level="DEBUG", output_dir="./out")
            >>> d = config.to_dict()
            >>> d["logging_level"], d["output_dir"]
            ('DEBUG', './out')
            >>> d["data"]["provider"]
            'yfinance'

        """
        return {
            "data": self.data.to_dict(),
            "backtest": self.backtest.to_dict(),
            "risk": self.risk.to_dict(),
            "portfolio": self.portfolio.to_dict(),
            "logging_level": self.logging_level,
            "output_dir": self.output_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Deserialize a :class:`Config` from a dictionary.

        Missing keys fall back to the class defaults (empty sub-configs
        reconstruct with their defaults). Extra keys are ignored.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`Config`.

        Examples:
            >>> from quant_trading.config.settings import Config
            >>> restored = Config.from_dict({"logging_level": "DEBUG"})
            >>> restored.logging_level
            'DEBUG'
            >>> restored.output_dir
            './output'
            >>> restored.data.provider
            'yfinance'

        """
        return cls(
            data=DataConfig.from_dict(data.get("data", {})),
            backtest=BacktestConfig.from_dict(data.get("backtest", {})),
            risk=RiskConfig.from_dict(data.get("risk", {})),
            portfolio=PortfolioConfig.from_dict(data.get("portfolio", {})),
            logging_level=str(data.get("logging_level", "INFO")),
            output_dir=str(data.get("output_dir", "./output")),
        )

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
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Configuration in {path} is not a mapping")  # noqa: TRY004
        data_values = _filter_fields(DataConfig, data.get("data", {}))
        backtest_values = _filter_fields(BacktestConfig, data.get("backtest", {}))
        risk_values = _filter_fields(RiskConfig, data.get("risk", {}))
        portfolio_values = _filter_fields(PortfolioConfig, data.get("portfolio", {}))
        _check_field_types(DataConfig, data_values)
        _check_field_types(BacktestConfig, backtest_values)
        _check_field_types(RiskConfig, risk_values)
        _check_field_types(PortfolioConfig, portfolio_values)
        top_level_values = {
            "logging_level": data.get("logging_level", "INFO"),
            "output_dir": data.get("output_dir", "./output"),
        }
        _check_field_types(Config, top_level_values)
        return cls(
            data=DataConfig(**data_values),
            backtest=BacktestConfig(**backtest_values),
            risk=RiskConfig(**risk_values),
            portfolio=PortfolioConfig(**portfolio_values),
            logging_level=top_level_values["logging_level"],
            output_dir=top_level_values["output_dir"],
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

        Nested sub-configs (``data``, ``backtest``, ``risk``,
        ``portfolio``) are updated through their :meth:`from_dict`
        so :meth:`__post_init__` validation runs on the merged values.
        A partial mapping such as ``{"synthetic_days": 0}`` is merged
        with the existing sub-config before validation, and a failed
        validation leaves the sub-config untouched.

        Args:
            **kwargs: Attribute name/value pairs to set.

        Returns:
            None.

        """
        for key, value in kwargs.items():
            if not hasattr(self, key):
                continue
            field_type = self.__dataclass_fields__[key].type
            if isinstance(value, dict) and is_dataclass(field_type):
                merged = {**getattr(self, key).to_dict(), **value}
                constructor = field_type.from_dict  # type: ignore[union-attr]
                setattr(self, key, constructor(merged))
            else:
                setattr(self, key, value)


DEFAULT_CONFIG = Config()


__all__ = [
    "BacktestConfig",
    "Config",
    "DataConfig",
    "PortfolioConfig",
    "RiskConfig",
]
