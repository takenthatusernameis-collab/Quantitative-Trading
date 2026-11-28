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

import math
import os
import typing
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from typing import Any

import yaml


def _finite(value: Any, default: float = 0.0) -> float:
    """Convert a value to a finite float, falling back to ``default``.

    Non-numeric, non-finite (NaN/inf), and unconvertible values are replaced
    with ``default`` so a corrupted dictionary cannot poison a reconstructed
    object with NaN/inf.

    Args:
        value: The value to sanitize.
        default: The fallback value when ``value`` is not a finite number.

    Returns:
        A finite float.

    Examples:
        >>> _finite(1.5)
        1.5
        >>> _finite(float("nan"))
        0.0
        >>> _finite(float("inf"))
        0.0
        >>> _finite("not a number")
        0.0
        >>> _finite(None)
        0.0
        >>> _finite(True)
        0.0
        >>> _finite(False)
        0.0
        >>> _finite("3.14")
        3.14
    """
    # Explicitly reject bool since bool is a subclass of int but we don't want
    # True/False to be treated as 1.0/0.0
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _validate_init_param(value: Any, name: str, predicate: Any, message: str) -> None:
    """Validate a numeric config parameter at construction time.

    Rejects booleans, non-numeric values, and non-finite numbers, then applies
    ``predicate``. Bool is rejected even though it is a subclass of int, so
    ``True``/``False`` are never silently coerced to ``1``/``0``.

    Args:
        value: The raw parameter value.
        name: Parameter name, used in the error message.
        predicate: Callable accepting a number and returning ``True`` when valid.
        message: Requirement fragment included in the error message.

    Raises:
        ValueError: When ``value`` is a boolean, non-numeric, non-finite, or
            fails ``predicate``.

    Examples:
        >>> _validate_init_param(365, "synthetic_days", lambda v: v >= 1, "the value must be at least 1 and finite")
        >>> _validate_init_param(True, "synthetic_days", lambda v: v >= 1, "the value must be at least 1 and finite")
        Traceback (most recent call last):
            ...
        ValueError: invalid synthetic_days: the value must be at least 1 and finite (got True)
        >>> _validate_init_param("365", "synthetic_days", lambda v: v >= 1, "the value must be at least 1 and finite")
        Traceback (most recent call last):
            ...
        ValueError: invalid synthetic_days: the value must be at least 1 and finite (got 365)
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not predicate(value)
    ):
        raise ValueError(f"invalid {name}: {message} (got {value})")


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
        synthetic_end_date: End date for synthetic data generation. Defaults to a
            fixed date for determinism. If None, defaults to 2024-01-01.
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
    synthetic_end_date: datetime | None = None
    alphavantage_api_key: str | None = None

    def __post_init__(self) -> None:
        """Reject out-of-range data-config inputs at construction time.

        Invalid values are rejected when a config is built (directly, from a
        dictionary, or from YAML) instead of silently propagating to the data
        layer. Booleans and non-numeric values are rejected with a clear
        ``ValueError`` instead of being silently coerced (``True`` -> ``1``)
        or raising an opaque ``TypeError``.

        Examples:
            >>> from quant_trading.config.settings import DataConfig
            >>> data = DataConfig(provider="synthetic", synthetic_days=30, synthetic_seed=7)
            >>> data.provider, data.synthetic_days, data.synthetic_seed
            ('synthetic', 30, 7)
            >>> DataConfig(provider="")
            Traceback (most recent call last):
                ...
            ValueError: invalid provider: the value must be a non-empty string (got '')
            >>> DataConfig(synthetic_days=True)
            Traceback (most recent call last):
                ...
            ValueError: invalid synthetic_days: the value must be at least 1 and finite (got True)
            >>> DataConfig(default_interval="")
            Traceback (most recent call last):
                ...
            ValueError: invalid default_interval: the value must be a non-empty string (got '')
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
        max_seed = 2**32 - 1
        _validate_init_param(
            self.synthetic_days,
            "synthetic_days",
            lambda v: v >= 1,
            "the value must be at least 1 and finite",
        )
        _validate_init_param(
            self.synthetic_seed,
            "synthetic_seed",
            lambda v: 0 <= v <= max_seed,
            f"the value must be between 0 and {max_seed} and finite",
        )
        if self.synthetic_end_date is not None and not isinstance(
            self.synthetic_end_date, datetime
        ):
            raise ValueError(
                f"invalid synthetic_end_date: must be a datetime or None "
                f"(got {type(self.synthetic_end_date).__name__})"
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
            "synthetic_end_date": (
                self.synthetic_end_date.isoformat() if self.synthetic_end_date else None
            ),
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
            >>> restored.synthetic_end_date is None
            True

        """
        known = {f.name for f in fields(cls)}
        init_kwargs = {name: value for name, value in data.items() if name in known}
        end_date = init_kwargs.get("synthetic_end_date")
        if isinstance(end_date, str):
            init_kwargs["synthetic_end_date"] = datetime.fromisoformat(end_date)
        return cls(**init_kwargs)


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

    Examples:
        >>> from quant_trading.config.settings import _type_matches
        >>> _type_matches(int, 5)
        True
        >>> _type_matches(int, True)
        False
        >>> _type_matches(bool, 1)
        False
        >>> _type_matches(float, 5)
        True
        >>> _type_matches(str | None, None)
        True
        >>> _type_matches(str | None, 5)
        False

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

    Examples:
        >>> from quant_trading.config.settings import _check_field_types, DataConfig
        >>> _check_field_types(DataConfig, {"provider": "yfinance", "synthetic_days": 30})
        >>> _check_field_types(DataConfig, {"synthetic_days": True})
        Traceback (most recent call last):
            ...
        ValueError: invalid config field DataConfig.synthetic_days: expected <class 'int'>, got bool (True)

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

        Examples:
            >>> from quant_trading.config.settings import BacktestConfig
            >>> cfg = BacktestConfig(initial_capital=50000.0, commission=0.002)
            >>> cfg.initial_capital, cfg.commission
            (50000.0, 0.002)
            >>> BacktestConfig(initial_capital=0.0)
            Traceback (most recent call last):
                ...
            ValueError: invalid initial_capital: the value must be positive and finite (got 0.0)
            >>> BacktestConfig(periods_per_year=True)
            Traceback (most recent call last):
                ...
            ValueError: invalid periods_per_year: the value must be at least 1 and finite (got True)
            >>> BacktestConfig(risk_free_rate=float("nan"))
            Traceback (most recent call last):
                ...
            ValueError: invalid risk_free_rate: the value must be finite (got nan)
        """
        _validate_init_param(
            self.initial_capital,
            "initial_capital",
            lambda v: v > 0,
            "the value must be positive and finite",
        )
        _validate_init_param(
            self.periods_per_year,
            "periods_per_year",
            lambda v: v >= 1,
            "the value must be at least 1 and finite",
        )
        _validate_init_param(
            self.commission,
            "commission",
            lambda v: 0.0 <= v <= 1.0,
            "the value must be in the range [0, 1] and finite",
        )
        _validate_init_param(
            self.slippage,
            "slippage",
            lambda v: 0.0 <= v <= 1.0,
            "the value must be in the range [0, 1] and finite",
        )
        _validate_init_param(
            self.risk_free_rate,
            "risk_free_rate",
            lambda v: True,
            "the value must be finite",
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
            50000
            >>> restored.periods_per_year
            252

        """
        known = {f.name for f in fields(cls)}
        init_kwargs = {name: value for name, value in data.items() if name in known}
        return cls(**init_kwargs)


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

        Examples:
            >>> from quant_trading.config.settings import RiskConfig
            >>> cfg = RiskConfig(max_position_size=0.15, max_drawdown=0.10)
            >>> cfg.max_position_size, cfg.max_drawdown
            (0.15, 0.1)
            >>> RiskConfig(max_leverage=0.0)
            Traceback (most recent call last):
                ...
            ValueError: invalid max_leverage: the value must be positive and finite (got 0.0)
            >>> RiskConfig(max_position_size=0.0)
            Traceback (most recent call last):
                ...
            ValueError: invalid max_position_size: the value must be in the range (0, 1] and finite (got 0.0)
            >>> RiskConfig(max_drawdown=1.5)
            Traceback (most recent call last):
                ...
            ValueError: invalid max_drawdown: the value must be in the range [0, 1] and finite (got 1.5)
        """
        _validate_init_param(
            self.max_position_size,
            "max_position_size",
            lambda v: 0.0 < v <= 1.0,
            "the value must be in the range (0, 1] and finite",
        )
        _validate_init_param(
            self.max_portfolio_risk,
            "max_portfolio_risk",
            lambda v: 0.0 < v <= 1.0,
            "the value must be in the range (0, 1] and finite",
        )
        _validate_init_param(
            self.max_drawdown,
            "max_drawdown",
            lambda v: 0.0 <= v <= 1.0,
            "the value must be in the range [0, 1] and finite",
        )
        _validate_init_param(
            self.stop_loss_pct,
            "stop_loss_pct",
            lambda v: 0.0 <= v <= 1.0,
            "the value must be in the range [0, 1] and finite",
        )
        _validate_init_param(
            self.take_profit_pct,
            "take_profit_pct",
            lambda v: 0.0 <= v <= 1.0,
            "the value must be in the range [0, 1] and finite",
        )
        _validate_init_param(
            self.max_leverage,
            "max_leverage",
            lambda v: v >= 1e-9,
            "the value must be positive and finite",
        )
        _validate_init_param(
            self.trailing_stop_pct,
            "trailing_stop_pct",
            lambda v: 0.0 <= v <= 1.0,
            "the value must be in the range [0, 1] and finite",
        )
        _validate_init_param(
            self.trailing_stop_activation_pct,
            "trailing_stop_activation_pct",
            lambda v: 0.0 <= v <= 1.0,
            "the value must be in the range [0, 1] and finite",
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
        known = {f.name for f in fields(cls)}
        init_kwargs = {name: value for name, value in data.items() if name in known}
        return cls(**init_kwargs)


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

        Examples:
            >>> from quant_trading.config.settings import PortfolioConfig
            >>> cfg = PortfolioConfig(rebalance_frequency="weekly", max_positions=10)
            >>> cfg.rebalance_frequency, cfg.max_positions
            ('weekly', 10)
            >>> PortfolioConfig(max_positions=0)
            Traceback (most recent call last):
                ...
            ValueError: invalid max_positions: the value must be at least 1 and finite (got 0)
            >>> PortfolioConfig(max_positions=True)
            Traceback (most recent call last):
                ...
            ValueError: invalid max_positions: the value must be at least 1 and finite (got True)
            >>> PortfolioConfig(min_position_size=1.5)
            Traceback (most recent call last):
                ...
            ValueError: invalid min_position_size: the value must be in the range [0, 1] (got 1.5)
        """
        _validate_init_param(
            self.max_positions,
            "max_positions",
            lambda v: v >= 1,
            "the value must be at least 1 and finite",
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
        known = {f.name for f in fields(cls)}
        init_kwargs = {name: value for name, value in data.items() if name in known}
        return cls(**init_kwargs)


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

        Examples:
            >>> import tempfile, os
            >>> from quant_trading.config.settings import Config
            >>> path = os.path.join(tempfile.mkdtemp(), "config.yaml")
            >>> Config().to_yaml(path)
            >>> loaded = Config.from_yaml(path)
            >>> loaded.logging_level == "INFO"
            True

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

        Examples:
            >>> import tempfile, os
            >>> from quant_trading.config.settings import Config
            >>> path = os.path.join(tempfile.mkdtemp(), "config.yaml")
            >>> Config().to_yaml(path)
            >>> os.path.exists(path)
            True

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

        Examples:
            >>> from quant_trading.config.settings import Config
            >>> config = Config(logging_level="DEBUG", output_dir="./out")
            >>> d = config._to_dict()
            >>> d["logging_level"]
            'DEBUG'
            >>> d["output_dir"]
            './out'
            >>> d["data"]["provider"]
            'yfinance'
            >>> d["backtest"]["initial_capital"]
            100000.0
            >>> sorted(d.keys())
            ['backtest', 'data', 'logging_level', 'output_dir', 'portfolio', 'risk']

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

        Examples:
            >>> from quant_trading.config.settings import Config
            >>> config = Config()
            >>> config.update(logging_level="DEBUG")
            >>> config.logging_level == "DEBUG"
            True

        """
        for key, value in kwargs.items():
            if not hasattr(self, key):
                continue
            field_type = self.__dataclass_fields__[key].type
            if isinstance(value, dict) and is_dataclass(field_type):
                current = getattr(self, key)
                to_dict = getattr(current, "to_dict", None)
                constructor = getattr(field_type, "from_dict", None)
                if callable(to_dict) and callable(constructor):
                    merged = {**to_dict(), **value}
                    setattr(self, key, constructor(merged))
                    continue
            setattr(self, key, value)


DEFAULT_CONFIG = Config()


__all__ = [
    "BacktestConfig",
    "Config",
    "DataConfig",
    "PortfolioConfig",
    "RiskConfig",
]
