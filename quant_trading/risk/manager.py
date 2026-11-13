"""Risk management orchestration.

>>> from quant_trading.risk.manager import RiskManager
>>> from quant_trading.strategies.base import Signal
>>> rm = RiskManager(initial_capital=100000.0, max_position_size=0.1)
>>> signal = Signal(symbol="AAPL", action="buy", price=150.0, strength=1.0)
>>> result = rm.check_signal(signal, portfolio_value=100000.0)
>>> result.passed in (True, False)
True

"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from quant_trading.risk.limits import CheckResult, PortfolioLimit, PositionLimit
from quant_trading.risk.metrics import (
    RiskMetrics,
    calculate_all_metrics,
    calculate_component_var,
    calculate_equal_risk_contribution_weights,
    calculate_marginal_var,
    calculate_risk_budget_weights,
    calculate_volatility,
    calculate_volatility_contributions,
)
from quant_trading.strategies.base import Position, Signal


def _series_to_mapping(series: pd.Series) -> dict[str, float]:
    """Copy a series into a plain mapping keyed by its index labels.

    Args:
        series: Series to convert. An empty series yields an empty mapping.

    Returns:
        Mapping from index label to float value.

    """
    return {str(label): float(value) for label, value in series.items()}


def _mapping_to_series(data: Any) -> pd.Series:
    """Restore a series from a mapping (or an index/value list).

    Args:
        data: Mapping keyed by symbol, a two-element list of index labels and
            values, or None. Anything else yields an empty series.

    Returns:
        Series indexed by symbol, or an empty float series.

    """
    if isinstance(data, dict):
        if not data:
            return pd.Series(dtype=float)
        return pd.Series(
            [float(value) for value in data.values()],
            index=[str(label) for label in data],
            dtype=float,
        )
    if isinstance(data, (list, tuple)) and len(data) == 2:
        index, values = data
        if isinstance(index, (list, tuple)) and isinstance(values, (list, tuple)):
            return pd.Series(
                [float(value) for value in values],
                index=[str(label) for label in index],
                dtype=float,
            )
    return pd.Series(dtype=float)


def _validate_confidence(confidence: float) -> None:
    """Reject a confidence level outside the open interval (0, 1).

    Args:
        confidence: Confidence level to validate.

    Returns:
        None.

    Raises:
        ValueError: When ``confidence`` is not finite or not in (0, 1).

    """
    if not math.isfinite(confidence) or not (0.0 < confidence < 1.0):
        raise ValueError(
            f"invalid confidence: the value must be in the range (0, 1) (got {confidence})"
        )


def _validate_periods_per_year(periods_per_year: int) -> None:
    """Reject an annualization factor below one.

    Args:
        periods_per_year: Periods per year to validate.

    Returns:
        None.

    Raises:
        ValueError: When ``periods_per_year`` is below one.

    """
    if not math.isfinite(periods_per_year) or periods_per_year < 1:
        raise ValueError(
            f"invalid periods_per_year: the value must be at least 1 (got {periods_per_year})"
        )


@dataclass
class RiskAttribution:
    """Risk attribution of the current portfolio positions.

    Produced by :meth:`RiskManager.calculate_risk_attribution`.

    The position weights are the share of the portfolio value each position
    carries (market value / portfolio value). They sum to 1.0 for a fully
    invested, long-only portfolio.

    VaR is expressed as a positive loss: a component VaR of ``0.01`` means
    the position contributes ``0.01`` of portfolio value at risk at the
    chosen confidence level. The volatility contributions sum exactly to the
    portfolio volatility (Euler decomposition). The component VaRs sum to the
    portfolio VaR for a long-only portfolio under the historical simulation
    convention; they sum to the mean portfolio return in the tail (the
    expected shortfall) instead of the portfolio VaR when the return
    distribution is not degenerate, so read ``portfolio_var`` as the
    quantile loss and the component sum as the tail-decomposition loss.

    Attributes:
        confidence: Confidence level used for the VaR figures.
        positions_value: Market value of the positions the attribution
            covers.
        portfolio_value: Portfolio value used to size the position weights.
        portfolio_var: Portfolio Value at Risk as a positive fraction of the
            portfolio value, measured as the loss at the confidence level
            (the negative of the lower quantile of the portfolio return).
        portfolio_volatility: Portfolio volatility, annualized when the
            attribution was computed with ``annualize=True``.
        weights: Position weights (share of the portfolio value), indexed by
            symbol.
        marginal_var: Marginal VaR of each position (portfolio return change
            per unit of position return), indexed by symbol.
        component_var: Component VaR of each position, as a fraction of the
            portfolio value, indexed by symbol.
        volatility_contributions: Contribution of each position to the
            portfolio volatility, indexed by symbol.

    Examples:
        >>> import pandas as pd
        >>> attribution = RiskAttribution()
        >>> empty = pd.Series(dtype=float)
        >>> attribution.portfolio_var, attribution.component_var.equals(empty)
        (0.0, True)

    """

    confidence: float = 0.95
    positions_value: float = 0.0
    portfolio_value: float = 0.0
    portfolio_var: float = 0.0
    portfolio_volatility: float = 0.0
    weights: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    marginal_var: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    component_var: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    volatility_contributions: pd.Series = field(
        default_factory=lambda: pd.Series(dtype=float)
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert the risk attribution to a plain dictionary.

        The per-position figures are keyed by symbol, so a position that has
        no history is reported with a zero contribution instead of dropping
        out of the breakdown.

        Returns:
            Dictionary with the aggregate figures and one entry per
            position symbol for ``weights``, ``marginal_var``,
            ``component_var``, and ``volatility_contributions``.

        Examples:
            >>> from quant_trading.risk.manager import RiskAttribution
            >>> import pandas as pd
            >>> attribution = RiskAttribution(
            ...     portfolio_var=0.03,
            ...     component_var=pd.Series([0.03], index=["AAPL"]),
            ... )
            >>> attribution.to_dict()["component_var"]
            {'AAPL': 0.03}

        """
        return {
            "confidence": self.confidence,
            "positions_value": self.positions_value,
            "portfolio_value": self.portfolio_value,
            "portfolio_var": self.portfolio_var,
            "portfolio_volatility": self.portfolio_volatility,
            "weights": _series_to_mapping(self.weights),
            "marginal_var": _series_to_mapping(self.marginal_var),
            "component_var": _series_to_mapping(self.component_var),
            "volatility_contributions": _series_to_mapping(self.volatility_contributions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RiskAttribution":
        """Deserialize a :class:`RiskAttribution` from a dictionary.

        Missing keys fall back to the class defaults. The per-position series
        accept either a mapping keyed by symbol or an index/value list.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`RiskAttribution`.

        Examples:
            >>> from quant_trading.risk.manager import RiskAttribution
            >>> restored = RiskAttribution.from_dict({"portfolio_var": 0.02})
            >>> restored.portfolio_var
            0.02

        """
        return cls(
            confidence=float(data.get("confidence", 0.95)),
            positions_value=float(data.get("positions_value", 0.0)),
            portfolio_value=float(data.get("portfolio_value", 0.0)),
            portfolio_var=float(data.get("portfolio_var", 0.0)),
            portfolio_volatility=float(data.get("portfolio_volatility", 0.0)),
            weights=_mapping_to_series(data.get("weights")),
            marginal_var=_mapping_to_series(data.get("marginal_var")),
            component_var=_mapping_to_series(data.get("component_var")),
            volatility_contributions=_mapping_to_series(data.get("volatility_contributions")),
        )

    def as_frame(self) -> pd.DataFrame:
        """Per-position breakdown as a single frame.

        Returns:
            One row per position symbol with the ``weight``,
            ``marginal_var``, ``component_var``, and
            ``volatility_contribution`` columns, ordered by symbol.

        Examples:
            >>> from quant_trading.risk.manager import RiskAttribution
            >>> import pandas as pd
            >>> attribution = RiskAttribution(
            ...     weights=pd.Series([0.5], index=["AAPL"]),
            ... )
            >>> attribution.as_frame().columns.tolist()
            ['weight', 'marginal_var', 'component_var', 'volatility_contribution']

        """
        symbols = self.weights.index
        aligned = [
            series.reindex(symbols) if isinstance(series, pd.Series) else pd.Series(index=symbols)
            for series in (
                self.weights,
                self.marginal_var,
                self.component_var,
                self.volatility_contributions,
            )
        ]
        frame = pd.concat(aligned, axis=1)
        frame.columns = [
            "weight",
            "marginal_var",
            "component_var",
            "volatility_contribution",
        ]
        return frame.sort_index()

    def total_component_var(self) -> float:
        """Sum of the component VaR over all positions.

        For a long-only portfolio this equals :attr:`portfolio_var` by the
        Euler decomposition. A portfolio with short positions reports the
        net figure: the shorts reduce the sum instead of adding to it.

        Returns:
            The component VaR summed over every position.

        Examples:
            >>> from quant_trading.risk.manager import RiskAttribution
            >>> import pandas as pd
            >>> attribution = RiskAttribution(
            ...     component_var=pd.Series([0.01, 0.02], index=["A", "B"]),
            ... )
            >>> round(attribution.total_component_var(), 4)
            0.03

        """
        if len(self.component_var) == 0:
            return 0.0
        return float(self.component_var.sum())

    def total_volatility_contribution(self) -> float:
        """Sum of the volatility contributions over all positions.

        For a long-only portfolio this equals :attr:`portfolio_volatility`
        by the Euler decomposition.

        Returns:
            The volatility contribution summed over every position.

        Examples:
            >>> from quant_trading.risk.manager import RiskAttribution
            >>> import pandas as pd
            >>> attribution = RiskAttribution(
            ...     volatility_contributions=pd.Series([0.1, 0.2], index=["A", "B"]),
            ... )
            >>> round(attribution.total_volatility_contribution(), 4)
            0.3

        """
        if len(self.volatility_contributions) == 0:
            return 0.0
        return float(self.volatility_contributions.sum())


@dataclass
class PortfolioRisk:
    """Current portfolio risk state.

    Attributes:
        total_market_value: Total market value of portfolio (cash + positions).
        cash: Available cash balance.
        positions_value: Market value of all positions.
        leverage: Gross portfolio leverage ratio (sum of the absolute market
            values of the positions / total_value).
        current_drawdown: Current drawdown from peak (0.0 = at peak, negative
            while the portfolio is below its peak).
        peak_value: Peak portfolio value observed.

    Examples:
        >>> pr = PortfolioRisk(total_market_value=100000.0, cash=50000.0, positions_value=50000.0)
        >>> pr.total_value == 100000.0
        True

    """

    total_market_value: float = 0.0
    cash: float = 0.0
    positions_value: float = 0.0
    leverage: float = 0.0
    current_drawdown: float = 0.0
    peak_value: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert the portfolio risk state to a plain dictionary.

        Returns:
            Dictionary with keys ``total_market_value``, ``cash``,
            ``positions_value``, ``leverage``, ``current_drawdown``, and
            ``peak_value``.

        Examples:
            >>> from quant_trading.risk.manager import PortfolioRisk
            >>> pr = PortfolioRisk(total_market_value=100000.0, cash=50000.0, positions_value=50000.0)
            >>> d = pr.to_dict()
            >>> d["cash"], d["positions_value"]
            (50000.0, 50000.0)

        """
        return {
            "total_market_value": self.total_market_value,
            "cash": self.cash,
            "positions_value": self.positions_value,
            "leverage": self.leverage,
            "current_drawdown": self.current_drawdown,
            "peak_value": self.peak_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PortfolioRisk":
        """Deserialize a :class:`PortfolioRisk` from a dictionary.

        Missing keys fall back to the class defaults. Extra keys are ignored.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`PortfolioRisk`.

        Examples:
            >>> from quant_trading.risk.manager import PortfolioRisk
            >>> restored = PortfolioRisk.from_dict({"total_market_value": 100000.0, "cash": 50000.0})
            >>> restored.total_market_value, restored.cash
            (100000.0, 50000.0)
            >>> restored.leverage
            0.0

        """
        return cls(
            total_market_value=float(data.get("total_market_value", 0.0)),
            cash=float(data.get("cash", 0.0)),
            positions_value=float(data.get("positions_value", 0.0)),
            leverage=float(data.get("leverage", 0.0)),
            current_drawdown=float(data.get("current_drawdown", 0.0)),
            peak_value=float(data.get("peak_value", 0.0)),
        )

    @property
    def total_value(self) -> float:
        """Total portfolio value.

        Returns:
            Equal to ``total_market_value``.

        """
        return self.total_market_value


class RiskManager:
    """Manages risk for trading operations.

    Attributes:
        initial_capital: Starting capital.
        risk_free_rate: Annual risk-free rate used for risk-adjusted metrics.
        position_limit: Position limit configuration.
        portfolio_limit: Portfolio limit configuration.
        portfolio_risk: Current portfolio risk state.
        positions: Current positions by symbol.
        equity_curve: History of total portfolio values.
        peak_value: Peak value observed in equity curve.
        risk_metrics: Last computed risk metrics (if any).
        risk_enabled: Whether risk checks are enabled.
        history: Historical risk snapshots.
        trailing_stop_pct: Distance of the trailing stop from the best price
            the position has reached, as a fraction (``0.0`` disables it).
        trailing_stop_activation_pct: How far a position must move in its
            favour before its trailing stop starts to trail.

    Examples:
        >>> rm = RiskManager(initial_capital=50000.0, max_position_size=0.2)
        >>> rm.initial_capital == 50000.0
        True
        >>> rm.risk_enabled
        True

    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        max_position_size: float = 0.1,
        max_portfolio_risk: float = 0.02,
        max_drawdown: float = 0.20,
        max_positions: int = 20,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15,
        risk_free_rate: float = 0.02,
        max_leverage: float = 1.0,
        trailing_stop_pct: float = 0.0,
        trailing_stop_activation_pct: float = 0.0,
    ):
        """Initialize risk manager.

        Args:
            initial_capital: Initial capital for risk calculations.
            max_position_size: Maximum position size as fraction of portfolio.
            max_portfolio_risk: Maximum fraction of the portfolio value that may
                be at risk at any time.
            max_drawdown: Maximum drawdown before new positions are stopped
                (fraction).
            max_positions: Maximum number of positions allowed.
            stop_loss_pct: Default stop loss percentage.
            take_profit_pct: Default take profit percentage.
            risk_free_rate: Annual risk-free rate used for risk-adjusted
                metrics (Sharpe/Sortino/alpha). Defaults to 0.02 to match
                the rest of the framework.
            max_leverage: Maximum gross exposure as a multiple of the portfolio
                value (1.0 = fully invested with no borrowing).
            trailing_stop_pct: Distance of the trailing stop from the best
                price the position has reached, as a fraction. Trailing stops
                are disabled when this is ``0.0`` (the default).
            trailing_stop_activation_pct: How far a position must move in its
                favour, as a fraction of the entry price, before its trailing
                stop starts to trail. ``0.0`` (the default) activates the
                trailing stop as soon as the position is at its entry price.

        Returns:
            None.

        """
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate

        # Validate the risk manager configuration before the limit objects are
        # built from these values, so invalid input raises here with a clear
        # message instead of silently producing misleading risk decisions.
        if not math.isfinite(initial_capital) or initial_capital <= 0:
            raise ValueError(
                f"invalid initial_capital: the value must be positive and finite "
                f"(got {initial_capital})"
            )
        if not (0.0 < max_position_size <= 1.0):
            raise ValueError(
                f"invalid max_position_size: the value must be in the range (0, 1] "
                f"(got {max_position_size})"
            )
        if not (0.0 < max_portfolio_risk <= 1.0):
            raise ValueError(
                f"invalid max_portfolio_risk: the value must be in the range (0, 1] "
                f"(got {max_portfolio_risk})"
            )
        if not (0.0 <= max_drawdown <= 1.0):
            raise ValueError(
                f"invalid max_drawdown: the value must be in the range [0, 1] "
                f"(got {max_drawdown})"
            )
        if not math.isfinite(max_positions) or max_positions < 1:
            raise ValueError(
                f"invalid max_positions: the value must be at least 1 and finite "
                f"(got {max_positions})"
            )
        if not (0.0 <= stop_loss_pct <= 1.0):
            raise ValueError(
                f"invalid stop_loss_pct: the value must be in the range [0, 1] "
                f"(got {stop_loss_pct})"
            )
        if not (0.0 <= take_profit_pct <= 1.0):
            raise ValueError(
                f"invalid take_profit_pct: the value must be in the range [0, 1] "
                f"(got {take_profit_pct})"
            )
        if not math.isfinite(max_leverage) or max_leverage < 1e-9:
            raise ValueError(
                f"invalid max_leverage: the value must be positive and finite "
                f"(got {max_leverage})"
            )
        if not (0.0 <= trailing_stop_pct <= 1.0):
            raise ValueError(
                f"invalid trailing_stop_pct: the value must be in the range [0, 1] "
                f"(got {trailing_stop_pct})"
            )
        if not (0.0 <= trailing_stop_activation_pct <= 1.0):
            raise ValueError(
                f"invalid trailing_stop_activation_pct: the value must be in the range [0, 1] "
                f"(got {trailing_stop_activation_pct})"
            )

        self.position_limit = PositionLimit(
            max_size=max_position_size,
            max_value=initial_capital * max_position_size,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )
        self.portfolio_limit = PortfolioLimit(
            max_positions=max_positions,
            max_position_size=max_position_size,
            max_portfolio_risk=max_portfolio_risk,
            max_drawdown=max_drawdown,
            max_leverage=max_leverage,
            stop_loss_pct=stop_loss_pct,
        )

        self.portfolio_risk = PortfolioRisk(
            total_market_value=initial_capital,
            cash=initial_capital,
            peak_value=initial_capital,
        )
        self.positions: dict[str, Position] = {}
        self.equity_curve: list[float] = [initial_capital]
        self.peak_value = initial_capital
        self.risk_metrics: RiskMetrics | None = None
        self.risk_enabled = True
        self.history: list[dict[str, Any]] = []
        self._returns: dict[str, list[float]] = {}
        self.trailing_stop_pct = trailing_stop_pct
        self.trailing_stop_activation_pct = trailing_stop_activation_pct
        self._trailing_stops: dict[str, float] = {}
        self._trailing_highs: dict[str, float] = {}
        self._trailing_lows: dict[str, float] = {}

    def update_portfolio_value(self, positions: dict[str, Position], cash: float) -> None:
        """Update portfolio value and track equity curve.

        Args:
            positions: Current positions by symbol.
            cash: Current cash balance.

        Returns:
            None.

        Examples:
            Update portfolio after a trade execution::

                >>> from quant_trading.risk.manager import RiskManager
                >>> from quant_trading.strategies.base import Position
                >>> rm = RiskManager(initial_capital=50000.0)
                >>> positions = {"AAPL": Position("AAPL", 100, 150.0, 152.0)}
                >>> rm.update_portfolio_value(positions, 35000.0)
                >>> rm.portfolio_risk.positions_value > 0.0
                True

        """
        self.positions = positions
        positions_value = sum(p.market_value for p in positions.values())
        total_value = cash + positions_value

        # A position that is no longer held cannot carry a trailing stop, and
        # the price of the positions that are still held is fed to the
        # trailing stop tracker so its stop keeps following the market.
        for symbol in self._tracked_trailing_symbols():
            if symbol not in positions:
                self._clear_trailing_state(symbol)
        for symbol, position in positions.items():
            self.update_trailing_stop(symbol, position.current_price)

        # The peak is updated first so the drawdown is measured against the
        # peak the portfolio is actually at. Measuring against the previous
        # peak would report a positive drawdown at a new high.
        peak_value = max(self.peak_value, total_value)

        self.portfolio_risk = PortfolioRisk(
            total_market_value=total_value,
            cash=cash,
            positions_value=positions_value,
            leverage=(
                sum(abs(p.market_value) for p in positions.values()) / total_value
                if total_value > 0
                else 0
            ),
            current_drawdown=((total_value - peak_value) / peak_value if peak_value > 0 else 0),
            peak_value=peak_value,
        )

        self.equity_curve.append(total_value)
        self.peak_value = peak_value

        self.history.append(
            {
                "timestamp": datetime.now(),
                "total_value": total_value,
                "cash": cash,
                "positions_value": positions_value,
                "drawdown": self.portfolio_risk.current_drawdown,
            }
        )

    def sync_position(self, symbol: str, position: Position | None) -> None:
        """Refresh the manager's view of a single position.

        The portfolio snapshot is otherwise only refreshed by
        :meth:`update_portfolio_value`, which a caller naturally calls once
        per update cycle. A caller that executes several trades between two
        such refreshes can keep the snapshot current with this method, so a
        risk check performed after the first trade already sees the exposure
        that trade created instead of the exposure of the previous cycle.

        Only the position view is refreshed. The totals held in
        ``portfolio_risk`` and the equity curve are not recomputed; call
        :meth:`update_portfolio_value` for a full refresh.

        Args:
            symbol: Symbol whose position changed.
            position: The new position, or None when the position was closed.

        Returns:
            None.

        Examples:
            Keep the snapshot current while a batch of trades is executed::

                >>> from quant_trading.risk.manager import RiskManager
                >>> from quant_trading.strategies.base import Position
                >>> rm = RiskManager(initial_capital=100000.0, max_leverage=0.5)
                >>> rm.sync_position("AAPL", Position("AAPL", 100, 150.0, 150.0))
                >>> "AAPL" in rm.positions
                True

        """
        if position is None:
            self.positions.pop(symbol, None)
            self._clear_trailing_state(symbol)
            return

        previous = self.positions.get(symbol)
        if previous is not None and previous.quantity * position.quantity < 0:
            # The position flipped direction, so the trailing stop tracked for
            # the old direction no longer applies to the new one.
            self._clear_trailing_state(symbol)

        self.positions[symbol] = position
        self.update_trailing_stop(symbol, position.current_price)

    def _open_position_count(self) -> int:
        """Number of symbols currently carrying a non-flat position.

        The gate counts the positions the risk manager currently knows about
        (``self.positions``), which is refreshed by
        :meth:`update_portfolio_value` and kept current by
        :meth:`sync_position` as trades are executed. A flat position (a
        symbol present in the view with a zero quantity) is not a position, so
        it does not count towards the limit.

        Returns:
            Number of open positions.

        """
        return sum(1 for position in self.positions.values() if position.quantity != 0)

    def _reject_new_position_if_at_the_limit(
        self,
        result: CheckResult,
        label: str,
        symbol: str,
    ) -> bool:
        """Reject a signal that would open a new position beyond the limit.

        A ``"buy"`` or a ``"short"`` signal that would open a **new** position
        (the symbol has no position, or a flat one) is rejected when the
        portfolio already holds ``portfolio_limit.max_positions`` positions.
        A signal that tops up a position that is already open does not add a
        position and must stay allowed, so it is not gated here.

        Args:
            result: Check result that collects the violations.
            label: Name of the signal used in the violation messages.
            symbol: Symbol the signal would open a position for.

        Returns:
            True when the signal was rejected, False when it may proceed.

        """
        position = self.positions.get(symbol)
        if position is not None and position.quantity != 0:
            # The symbol already holds an open position, so the signal tops it
            # up instead of opening a new one. It does not add a position.
            return False

        count = self._open_position_count()
        limit = self.portfolio_limit.max_positions
        if count >= limit:
            result.add_violation(f"{label} signal would exceed max positions: {count} >= {limit}")
            return True
        return False

    def _reject_signal_if_in_drawdown_breach(
        self,
        result: CheckResult,
        label: str,
    ) -> bool:
        """Reject a signal that would add exposure during a drawdown breach.

        A portfolio that has fallen ``max_drawdown`` below its peak is in a
        breach of its drawdown limit. A signal that adds exposure is rejected
        while that breach lasts, which is the same rule the rebalancer
        applies when it refuses to buy
        (``quant_trading/portfolio/rebalancer.py``).

        A ``"buy"`` that covers an open short reduces the gross exposure, so
        it is not gated: the caller returns before it reaches this check. A
        ``"sell"`` reduces a long and is not gated either.

        A ``max_drawdown`` of ``0.0`` disables the limit, exactly as it
        disables it in the rebalancer.

        The drawdown is the one of the manager's current view
        (``portfolio_risk.current_drawdown``), which is refreshed by
        :meth:`update_portfolio_value`. A breach that happens on a bar is
        therefore seen by the gate on the next bar.

        Args:
            result: Check result that collects the violations.
            label: Name of the signal used in the violation message.

        Returns:
            True when the signal was rejected, False when it may proceed.

        """
        limit = self.portfolio_limit.max_drawdown
        if limit <= 0:
            return False

        drawdown = self.portfolio_risk.current_drawdown
        if drawdown <= -limit:
            result.add_violation(
                f"{label} signal rejected: portfolio drawdown {drawdown:.2%} exceeds max {limit:.2%}"
            )
            return True
        return False

    def check_signal(self, signal: Signal, portfolio_value: float | None = None) -> CheckResult:
        """Check if a trading signal passes risk limits.

        The position limits are measured against the manager's current
        position view, which is refreshed by :meth:`update_portfolio_value`
        and kept up to date with :meth:`sync_position` as trades are
        executed.

        A signal that adds exposure is measured against the exposure the
        position would carry once the trade is done: the trade brings the
        position to its target, so the position size limit is checked on the
        target when the position is below it and on the exposure the position
        already carries when it is above it. The portfolio risk budget and
        the leverage limit are increased by the increment alone, so a
        position that is already part of the way to its target is not
        charged for exposure it already carries.

        A ``"buy"`` signal against an open short covers that short. Covering
        reduces the gross exposure of the portfolio, so it cannot breach any
        of the position limits and only the presence of a price is checked. A
        ``"short"`` signal is gated exactly like a ``"buy"`` signal, because
        both add gross exposure.

        The number of open positions is gated before a trade as well: a
        ``"buy"`` or a ``"short"`` that would open a new position is rejected
        when the portfolio already holds ``max_positions`` positions. A signal
        that tops up a position that is already open, or that covers an open
        short, does not add a position and stays allowed.

        The drawdown limit is gated before a trade too: a signal that adds
        exposure is rejected while the portfolio is in a breach of
        ``portfolio_limit.max_drawdown``, exactly as the rebalancer refuses to
        buy while that breach lasts. A ``"buy"`` that covers an open short
        reduces the exposure and stays allowed, and a ``"sell"`` reduces a long
        and is not gated. The drawdown the gate reads is the one of the
        manager's current view, which is refreshed by
        :meth:`update_portfolio_value`, so a breach that happens on a bar is
        seen by the gate on the next bar.

        Args:
            signal: Trading signal to evaluate.
            portfolio_value: Current portfolio value. The manager's internal
                portfolio value is used when this is ``None``; any explicit
                value overrides it, including ``0.0`` (a wiped-out portfolio,
                which is rejected below).

        Returns:
            CheckResult with pass/fail and any violations.

        Examples:
            Buy signal is rejected when position size limits are violated::

                >>> from quant_trading.risk.manager import RiskManager
                >>> from quant_trading.strategies.base import Signal
                >>> rm = RiskManager(initial_capital=100000.0, max_position_size=0.1)
                >>> signal = Signal(symbol="AAPL", action="buy", price=150.0, strength=2.0)
                >>> result = rm.check_signal(signal)
                >>> result.passed in (True, False)
                True

        """
        result = CheckResult(passed=True)

        if not self.risk_enabled:
            return result

        value = (
            self.portfolio_risk.total_market_value if portfolio_value is None else portfolio_value
        )
        if value <= 0:
            result.add_violation("Portfolio value is zero or negative")
            return result

        if signal.action == "buy":
            position = self.positions.get(signal.symbol)
            if signal.price is None:
                result.add_violation("Buy signal has no price")
                return result
            if position is not None and position.quantity < 0:
                # The buy covers an open short. Covering reduces the gross
                # exposure, so no position limit can be breached by it.
                return result
            if self._reject_signal_if_in_drawdown_breach(result, "Buy"):
                return result
            if self._reject_new_position_if_at_the_limit(result, "Buy", signal.symbol):
                return result
            current_gross = abs(position.quantity) * signal.price if position else 0.0
            self._check_exposure_increase(
                result,
                label="Buy",
                target_value=signal.strength * value * self.position_limit.max_size,
                current_gross=current_gross,
                portfolio_value=value,
            )

        elif signal.action == "sell":
            position = self.positions.get(signal.symbol)
            if position is None or position.quantity == 0:
                result.add_violation("Sell signal for position with no holdings")
            elif position.quantity < 0:
                result.add_violation("Sell signal for position with an open short")

        elif signal.action == "short":
            position = self.positions.get(signal.symbol)
            if position is not None and position.quantity > 0:
                result.add_violation("Short signal for position with long holdings")
                return result
            if signal.price is None:
                result.add_violation("Short signal has no price")
                return result
            if self._reject_signal_if_in_drawdown_breach(result, "Short"):
                return result
            if self._reject_new_position_if_at_the_limit(result, "Short", signal.symbol):
                return result
            current_gross = abs(position.quantity) * signal.price if position else 0.0
            self._check_exposure_increase(
                result,
                label="Short",
                target_value=signal.strength * value * self.position_limit.max_size,
                current_gross=current_gross,
                portfolio_value=value,
            )

        return result

    def _check_exposure_increase(
        self,
        result: CheckResult,
        label: str,
        target_value: float,
        current_gross: float,
        portfolio_value: float,
    ) -> None:
        """Check the limits that bound an increase of the gross exposure.

        The trade is measured on its gross exposure, so a short is limited
        exactly like a long of the same size. The position size is checked on
        the gross exposure the symbol would carry after the trade, the
        portfolio risk budget on the risk the trade adds, and the leverage
        limit on the gross exposure the trade adds to the portfolio.

        A trade brings the position to its target, so the exposure the symbol
        carries afterwards is the target itself when the position is below it,
        and the exposure it already carries when it is above it. The risk
        budget and the leverage limit are increased by the increment alone
        (the target less the exposure the symbol already carries), not by the
        whole target: the exposure the position already has is already
        counted in the current portfolio risk and in the current leverage.

        Args:
            result: Check result that collects the violations.
            label: Name of the signal used in the violation messages.
            target_value: Dollar value of the exposure the signal targets.
            current_gross: Gross exposure the symbol already carries.
            portfolio_value: Current portfolio value.

        Returns:
            None.

        """
        post_trade_size = max(current_gross, target_value)
        increment = max(0.0, target_value - current_gross)

        if post_trade_size > self.position_limit.max_value:
            result.add_violation(
                f"{label} signal would exceed max position value: ${post_trade_size:,.2f} > ${self.position_limit.max_value:,.2f}"
            )

        position_pct = post_trade_size / portfolio_value if portfolio_value > 0 else 0
        if position_pct > self.position_limit.max_size:
            result.add_violation(
                f"{label} signal would exceed max position size: {position_pct:.2%} > {self.position_limit.max_size:.2%}"
            )

        # Gate the trade on the portfolio risk budget and the leverage limit,
        # so a strategy cannot keep opening positions until the post-hoc
        # portfolio check reports a breach. The trade adds the increment of
        # gross exposure and increment * stop_loss_pct of risk.
        current_risk = self.portfolio_limit.portfolio_risk_pct(self.positions, portfolio_value)
        new_risk = current_risk + (increment * self.portfolio_limit.stop_loss_pct / portfolio_value)
        if new_risk > self.portfolio_limit.max_portfolio_risk:
            result.add_violation(
                f"{label} signal would exceed max portfolio risk: {new_risk:.2%} > {self.portfolio_limit.max_portfolio_risk:.2%}"
            )

        current_gross_exposure = self.portfolio_limit.leverage(self.positions, portfolio_value)
        new_leverage = current_gross_exposure + (increment / portfolio_value)
        if new_leverage > self.portfolio_limit.max_leverage:
            result.add_violation(
                f"{label} signal would exceed max leverage: {new_leverage:.2f}x > {self.portfolio_limit.max_leverage:.2f}x"
            )

    def check_portfolio(self) -> CheckResult:
        """Check overall portfolio risk limits.

        Returns:
            CheckResult with pass/fail and any violations.

        Examples:
            Check portfolio constraints after updating values::

                >>> from quant_trading.risk.manager import RiskManager
                >>> rm = RiskManager(initial_capital=100000.0, max_positions=20)
                >>> rm.update_portfolio_value({}, 100000.0)
                >>> result = rm.check_portfolio()
                >>> result.passed
                True

        """
        result = CheckResult(passed=True)

        if not self.risk_enabled:
            return result

        violations = self.portfolio_limit.check(
            self.positions,
            self.portfolio_risk.total_market_value,
            self.peak_value,
        )
        for v in violations:
            result.add_violation(v)

        return result

    def calculate_metrics(
        self,
        market_returns: pd.Series | None = None,
        periods_per_year: int = 252,
        risk_free_rate: float | None = None,
    ) -> RiskMetrics:
        """Calculate current risk metrics from equity curve.

        Args:
            market_returns: Optional benchmark returns for beta/alpha.
            periods_per_year: Number of periods per year used for annualization
                (default 252 for daily data).
            risk_free_rate: Annual risk-free rate used for risk-adjusted
                metrics. Defaults to the manager's configured rate.

        Returns:
            Computed RiskMetrics object.

        """
        equity_series = pd.Series(self.equity_curve)
        self.risk_metrics = calculate_all_metrics(
            equity_series,
            market_returns=market_returns,
            risk_free_rate=self.risk_free_rate if risk_free_rate is None else risk_free_rate,
            periods_per_year=periods_per_year,
        )
        return self.risk_metrics

    def _open_returns_frame(
        self,
        returns: pd.DataFrame | None,
        lookback: int | None,
    ) -> pd.DataFrame:
        """Returns frame of the open positions, aligned and validated.

        Args:
            returns: Asset returns keyed by symbol. When None, the frame is
                built from the tracked portfolio snapshots.
            lookback: Number of trailing observations to keep.

        Returns:
            Cleaned return frame holding one column per open position. The
            frame is empty when no position is open, or when a position has
            no return data.

        """
        if returns is None:
            frame = pd.DataFrame(
                {symbol: pd.Series(values, dtype=float) for symbol, values in self._returns.items()}
            )
        else:
            frame = returns.copy()
        if len(frame) == 0:
            return pd.DataFrame(index=frame.index)

        missing = sorted(symbol for symbol in self.positions if symbol not in frame.columns)
        if missing:
            raise KeyError(f"missing return data for open positions: {missing}")
        if len(self.positions) == 0:
            return frame.iloc[0:0]

        frame = frame[list(self.positions)].replace([np.inf, -np.inf], np.nan).dropna()
        if lookback is not None:
            if not math.isfinite(lookback) or lookback < 1:
                raise ValueError(
                    f"invalid lookback: the value must be at least 1 (got {lookback})"
                )
            frame = frame.iloc[-int(lookback) :]
        return frame

    def _position_weights(self, frame: pd.DataFrame) -> np.ndarray:
        """Portfolio weights of the open positions from the current view.

        The weight of a position is its market value divided by the total
        market value of the positions, so the weights are scale free and sum
        to 1.0 even when the snapshot carries no cash.

        Args:
            frame: Return frame whose columns name the positions.

        Returns:
            Weight array aligned with ``frame.columns``.

        Raises:
            ValueError: When the open positions have no market value.

        """
        total = sum(abs(position.market_value) for position in self.positions.values())
        if total <= 0:
            raise ValueError("cannot attribute risk: the open positions carry no market value")
        return np.array(
            [abs(self.positions[symbol].market_value) / total for symbol in frame.columns],
            dtype=float,
        )

    def record_return(self, symbol: str, value: float) -> None:
        """Record one period return of a symbol.

        The recorded returns feed :meth:`calculate_risk_attribution` when it
        is called without a return frame, so a caller that only knows the
        positions and their returns does not have to assemble a frame.

        Args:
            symbol: Symbol the return belongs to.
            value: Simple return of the period (for example ``0.01``).

        Returns:
            None.

        Raises:
            ValueError: When ``value`` is not finite.

        Examples:
            >>> from quant_trading.risk.manager import RiskManager
            >>> rm = RiskManager()
            >>> rm.record_return("AAPL", 0.01)
            >>> rm.returns["AAPL"]
            [0.01]

        """
        if not math.isfinite(value):
            raise ValueError(f"invalid return: the value must be finite (got {value})")
        self._returns.setdefault(symbol, []).append(float(value))

    def record_returns(self, values: dict[str, float]) -> None:
        """Record one period return for each symbol of a mapping.

        Args:
            values: Mapping from symbol to simple return of the period.

        Returns:
            None.

        Examples:
            >>> from quant_trading.risk.manager import RiskManager
            >>> rm = RiskManager()
            >>> rm.record_returns({"AAPL": 0.01, "MSFT": -0.005})
            >>> sorted(rm.returns)
            ['AAPL', 'MSFT']

        """
        for symbol, value in values.items():
            self.record_return(symbol, value)

    @property
    def returns(self) -> dict[str, list[float]]:
        """Recorded period returns per symbol.

        Returns:
            Mapping from symbol to the list of recorded returns, in the order
            they were recorded.

        Examples:
            >>> from quant_trading.risk.manager import RiskManager
            >>> rm = RiskManager()
            >>> rm.record_return("AAPL", 0.01)
            >>> rm.record_return("AAPL", 0.02)
            >>> rm.returns
            {'AAPL': [0.01, 0.02]}

        """
        return {symbol: list(values) for symbol, values in self._returns.items()}

    def reset_returns(self) -> None:
        """Drop every recorded return.

        Returns:
            None.

        """
        self._returns = {}

    def clear_returns(self) -> None:
        """Drop every recorded return.

        Alias of :meth:`reset_returns`.

        Returns:
            None.

        """
        self.reset_returns()

    def calculate_risk_attribution(
        self,
        returns: pd.DataFrame | None = None,
        confidence: float = 0.95,
        annualize: bool = True,
        periods_per_year: int = 252,
        lookback: int | None = None,
    ) -> RiskAttribution:
        """Attribute portfolio risk to the open positions.

        The attribution decomposes the risk of the current positions into a
        marginal VaR, a component VaR, and a volatility contribution per
        position, together with the portfolio VaR and volatility.

        Position weights are the share of the gross position value each
        position carries, measured on the current position view. The VaR
        figures are reported as positive losses: the portfolio VaR is the
        loss at the confidence level (the negative of the lower quantile of
        the portfolio return), and the component VaRs sum to the mean
        portfolio loss in the tail of the distribution.

        Args:
            returns: DataFrame of asset returns (columns = symbols, rows =
                periods). Defaults to the returns recorded with
                :meth:`record_return` / :meth:`record_returns`.
            confidence: VaR confidence level, in (0, 1). Default 0.95.
            annualize: Whether to annualize the volatility. Default True.
            periods_per_year: Periods per year for annualization (default 252).
            lookback: Number of trailing observations to use. Defaults to the
                full history.

        Returns:
            A :class:`RiskAttribution` covering the open positions. The
            attribution is empty (all figures zero, empty per-position series)
            when no position is open, or when the return data does not carry
            at least two usable observations for every open position.

        Raises:
            KeyError: When ``returns`` is given but a column of an open
                position is missing.
            ValueError: When the confidence, the annualization factor, or the
                lookback is invalid.

        Notes:
            The per-position series are aligned with the position weights, so
            a symbol with no usable return history carries a zero contribution
            instead of dropping out of the breakdown.

        Examples:
            >>> import numpy as np
            >>> import pandas as pd
            >>> from quant_trading.risk.manager import RiskManager
            >>> from quant_trading.strategies.base import Position
            >>> rm = RiskManager(initial_capital=100000.0)
            >>> rm.update_portfolio_value(
            ...     {
            ...         "AAPL": Position("AAPL", 100, 150.0, 150.0),
            ...         "MSFT": Position("MSFT", 100, 300.0, 300.0),
            ...     },
            ...     40000.0,
            ... )
            >>> np.random.seed(42)
            >>> data = pd.DataFrame(
            ...     {
            ...         "AAPL": np.random.normal(0.001, 0.02, 200),
            ...         "MSFT": np.random.normal(0.001, 0.02, 200),
            ...     }
            ... )
            >>> attribution = rm.calculate_risk_attribution(data)
            >>> sorted(attribution.weights.index)
            ['AAPL', 'MSFT']
            >>> bool(round(attribution.weights.sum(), 6) == 1.0)
            True
            >>> bool(attribution.component_var.sum() < 0)
            True

        """
        _validate_confidence(confidence)
        _validate_periods_per_year(periods_per_year)
        empty = RiskAttribution(
            confidence=confidence,
            positions_value=self.portfolio_risk.positions_value,
            portfolio_value=self.portfolio_risk.total_market_value,
        )
        if not self.positions:
            return empty

        frame = self._open_returns_frame(returns, lookback)
        if len(frame) < 2 or len(frame.columns) == 0:
            return empty

        weights = self._position_weights(frame)
        marginal_var = calculate_marginal_var(frame, weights, confidence)
        component_var = calculate_component_var(frame, weights, confidence)
        volatility_contributions = calculate_volatility_contributions(
            frame,
            weights,
            annualize=annualize,
            periods_per_year=periods_per_year,
        )
        portfolio_returns = pd.Series(
            frame.to_numpy(dtype=float) @ weights, index=frame.index
        )
        portfolio_var = float(-np.percentile(portfolio_returns, (1 - confidence) * 100))
        portfolio_volatility = calculate_volatility(
            portfolio_returns,
            annualize=annualize,
            periods_per_year=periods_per_year,
        )

        symbols = list(self.positions)
        market_total = sum(abs(position.market_value) for position in self.positions.values())
        return RiskAttribution(
            confidence=confidence,
            positions_value=self.portfolio_risk.positions_value,
            portfolio_value=self.portfolio_risk.total_market_value,
            portfolio_var=portfolio_var,
            portfolio_volatility=portfolio_volatility,
            weights=pd.Series(
                [abs(self.positions[symbol].market_value) / market_total for symbol in symbols],
                index=symbols,
                dtype=float,
            ),
            marginal_var=marginal_var.reindex(symbols).fillna(0.0),
            component_var=component_var.reindex(symbols).fillna(0.0),
            volatility_contributions=volatility_contributions.reindex(symbols).fillna(0.0),
        )

    def suggest_erc_weights(
        self,
        returns: pd.DataFrame | None = None,
        annualize: bool = True,
        periods_per_year: int = 252,
        lookback: int | None = None,
        long_only: bool = True,
        max_iter: int = 1000,
        tol: float = 1e-8,
    ) -> pd.Series:
        """Weights that equalize the risk contribution of the open positions.

        Equal risk contribution (ERC) weights assign the same share of the
        portfolio volatility to every position, so a position with a higher
        volatility receives a smaller weight.

        Args:
            returns: DataFrame of asset returns (columns = symbols, rows =
                periods). Defaults to the recorded returns.
            annualize: Whether to annualize volatility. Default True.
            periods_per_year: Periods per year for annualization (default 252).
            lookback: Number of trailing observations to use.
            long_only: Restrict the weights to be non-negative. Default True.
            max_iter: Maximum solver iterations.
            tol: Convergence tolerance of the solver.

        Returns:
            Series of target weights indexed by symbol, summing to 1.0. The
            series is empty when no position is open or the return data does
            not carry at least two usable observations for every position.

        Examples:
            >>> import numpy as np
            >>> import pandas as pd
            >>> from quant_trading.risk.manager import RiskManager
            >>> from quant_trading.strategies.base import Position
            >>> rm = RiskManager(initial_capital=100000.0)
            >>> rm.update_portfolio_value(
            ...     {
            ...         "AAPL": Position("AAPL", 100, 150.0, 150.0),
            ...         "MSFT": Position("MSFT", 100, 300.0, 300.0),
            ...     },
            ...     40000.0,
            ... )
            >>> np.random.seed(42)
            >>> data = pd.DataFrame(
            ...     {
            ...         "AAPL": np.random.normal(0.001, 0.01, 200),
            ...         "MSFT": np.random.normal(0.001, 0.03, 200),
            ...     }
            ... )
            >>> weights = rm.suggest_erc_weights(data, annualize=False)
            >>> bool(weights["AAPL"] > weights["MSFT"])
            True

        """
        _validate_periods_per_year(periods_per_year)
        if not self.positions:
            return pd.Series(dtype=float)
        frame = self._open_returns_frame(returns, lookback)
        if len(frame) < 2 or len(frame.columns) == 0:
            return pd.Series(dtype=float)
        return calculate_equal_risk_contribution_weights(
            frame,
            max_iter=max_iter,
            tol=tol,
            annualize=annualize,
            periods_per_year=periods_per_year,
            long_only=long_only,
        )

    def suggest_risk_budget_weights(
        self,
        risk_budget: np.ndarray | pd.Series | dict[str, float],
        returns: pd.DataFrame | None = None,
        annualize: bool = True,
        periods_per_year: int = 252,
        lookback: int | None = None,
        long_only: bool = True,
        max_iter: int = 1000,
        tol: float = 1e-8,
    ) -> pd.Series:
        """Weights that match a target risk budget across the open positions.

        The risk budget is the share of the portfolio volatility each
        position should contribute. A budget given as a mapping is matched to
        the open positions by symbol; an array or series is matched
        positionally against the columns of ``returns``.

        Args:
            risk_budget: Target risk contribution per position (must sum to
                1.0).
            returns: DataFrame of asset returns (columns = symbols, rows =
                periods). Defaults to the recorded returns.
            annualize: Whether to annualize volatility. Default True.
            periods_per_year: Periods per year for annualization (default 252).
            lookback: Number of trailing observations to use.
            long_only: Restrict the weights to be non-negative. Default True.
            max_iter: Maximum solver iterations.
            tol: Convergence tolerance of the solver.

        Returns:
            Series of target weights indexed by symbol, summing to 1.0. The
            series is empty when no position is open or the return data does
            not carry at least two usable observations for every position.

        Raises:
            ValueError: When the budget does not sum to 1.0, or when a
                mapping budget does not name the open positions.

        Examples:
            >>> import numpy as np
            >>> import pandas as pd
            >>> from quant_trading.risk.manager import RiskManager
            >>> from quant_trading.strategies.base import Position
            >>> rm = RiskManager(initial_capital=100000.0)
            >>> rm.update_portfolio_value(
            ...     {
            ...         "AAPL": Position("AAPL", 100, 150.0, 150.0),
            ...         "MSFT": Position("MSFT", 100, 300.0, 300.0),
            ...     },
            ...     40000.0,
            ... )
            >>> np.random.seed(42)
            >>> data = pd.DataFrame(
            ...     {
            ...         "AAPL": np.random.normal(0.001, 0.01, 200),
            ...         "MSFT": np.random.normal(0.001, 0.03, 200),
            ...     }
            ... )
            >>> weights = rm.suggest_risk_budget_weights(
            ...     {"AAPL": 0.5, "MSFT": 0.5}, data, annualize=False
            ... )
            >>> bool(round(weights.sum(), 6) == 1.0)
            True

        """
        _validate_periods_per_year(periods_per_year)
        if not self.positions:
            return pd.Series(dtype=float)
        frame = self._open_returns_frame(returns, lookback)
        if len(frame) < 2 or len(frame.columns) == 0:
            return pd.Series(dtype=float)

        if isinstance(risk_budget, dict):
            missing = [symbol for symbol in frame.columns if symbol not in risk_budget]
            if missing:
                raise KeyError(f"missing risk budget for open positions: {sorted(missing)}")
            budget = pd.Series(
                [float(risk_budget[symbol]) for symbol in frame.columns],
                index=frame.columns,
                dtype=float,
            )
        else:
            budget = risk_budget

        return calculate_risk_budget_weights(
            frame,
            budget,
            max_iter=max_iter,
            tol=tol,
            annualize=annualize,
            periods_per_year=periods_per_year,
            long_only=long_only,
        )

    def is_short_position(self, symbol: str) -> bool:
        """Whether the tracked position for a symbol is a short.

        The direction of a position is the sign of its quantity: a positive
        quantity is a long, a negative quantity is a short. A symbol without
        a position, or with a flat one, is not a short.

        Args:
            symbol: Symbol to query.

        Returns:
            True when the position is a short, False otherwise.

        Examples:
            A short position is recognised by its negative quantity::

                >>> from quant_trading.risk.manager import RiskManager
                >>> from quant_trading.strategies.base import Position
                >>> rm = RiskManager()
                >>> rm.sync_position("AAPL", Position("AAPL", -100, 150.0, 150.0))
                >>> rm.is_short_position("AAPL")
                True

        """
        position = self.positions.get(symbol)
        return position is not None and position.quantity < 0

    def get_position_stop_loss(self, symbol: str) -> float | None:
        """Get stop loss price for a position.

        The level is direction aware. For a long position the stop sits
        below the average entry price (``avg_price * (1 - stop_loss_pct)``);
        for a short position it sits above it
        (``avg_price * (1 + stop_loss_pct)``), because a short loses when the
        price rises. If a trailing stop is active and is tighter (better) than
        the fixed stop, it will be used.

        Args:
            symbol: Symbol to query.

        Returns:
            Stop loss price, or None if no position/invalid price.

        """
        position = self.positions.get(symbol)
        if position is None or position.avg_price <= 0:
            return None
        if position.quantity < 0:
            fixed_stop = position.avg_price * (1 + self.position_limit.stop_loss_pct)
        else:
            fixed_stop = position.avg_price * (1 - self.position_limit.stop_loss_pct)

        trailing_stop = self.get_trailing_stop(symbol)
        if trailing_stop is None:
            return fixed_stop
        if position.quantity < 0:
            # A short is stopped out above its entry price, so the lower of
            # the two levels is the tighter one.
            return min(fixed_stop, trailing_stop)
        # A long is stopped out below its entry price, so the higher of the
        # two levels is the tighter one.
        return max(fixed_stop, trailing_stop)

    def get_trailing_stop(self, symbol: str) -> float | None:
        """Get the trailing stop price tracked for a position.

        A trailing stop follows the price of a position once it has moved far
        enough in its favour. It sits ``trailing_stop_pct`` away from the best
        price the position has reached since it was opened: below the highest
        price for a long, above the lowest price for a short. The stop only
        ratchets in the favourable direction, so it never gives back ground it
        has already locked in.

        Trailing stops are only tracked when ``trailing_stop_pct`` is greater
        than zero; they are disabled by default.

        Args:
            symbol: Symbol to query.

        Returns:
            Trailing stop price, or None when no trailing stop is active for
            the symbol.

        Examples:
            A trailing stop follows the best price of a long position::

                >>> from quant_trading.risk.manager import RiskManager
                >>> from quant_trading.strategies.base import Position
                >>> rm = RiskManager(trailing_stop_pct=0.05)
                >>> rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
                >>> rm.update_trailing_stop("AAPL", 120.0)
                114.0

        """
        return self._trailing_stops.get(symbol)

    def update_trailing_stop(self, symbol: str, price: float) -> float | None:
        """Feed a market price into the trailing stop tracker.

        The tracker records the best price the position has reached and
        moves the trailing stop accordingly. The stop only ratchets in the
        favourable direction: for a long it never moves down, for a short it
        never moves up.

        The trailing stop only starts to trail once the position has moved
        ``trailing_stop_activation_pct`` in its favour, measured from the
        average entry price. Before that the position keeps the trailing stop
        it already has.

        Args:
            symbol: Symbol whose position is tracked.
            price: Latest market price of the symbol.

        Returns:
            The trailing stop price after the update, or None when trailing
            stops are disabled or the symbol has no position.

        Examples:
            The trailing stop of a short follows the lowest price it reached::

                >>> from quant_trading.risk.manager import RiskManager
                >>> from quant_trading.strategies.base import Position
                >>> rm = RiskManager(trailing_stop_pct=0.05)
                >>> rm.sync_position("AAPL", Position("AAPL", -100, 100.0, 100.0))
                >>> rm.update_trailing_stop("AAPL", 80.0)
                84.0

        """
        if self.trailing_stop_pct <= 0 or price <= 0:
            return None

        position = self.positions.get(symbol)
        if position is None or position.quantity == 0 or position.avg_price <= 0:
            return None

        if position.quantity > 0:
            activation_price = position.avg_price * (1 + self.trailing_stop_activation_pct)
            if price < activation_price:
                return self._trailing_stops.get(symbol)
            high = self._trailing_highs.get(symbol)
            high = price if high is None else max(high, price)
            self._trailing_highs[symbol] = high
            stop = high * (1 - self.trailing_stop_pct)
        else:
            activation_price = position.avg_price * (1 - self.trailing_stop_activation_pct)
            if price > activation_price:
                return self._trailing_stops.get(symbol)
            low = self._trailing_lows.get(symbol)
            low = price if low is None else min(low, price)
            self._trailing_lows[symbol] = low
            stop = low * (1 + self.trailing_stop_pct)

        existing = self._trailing_stops.get(symbol)
        if existing is not None:
            if position.quantity > 0:
                stop = max(stop, existing)
            else:
                stop = min(stop, existing)

        self._trailing_stops[symbol] = stop
        return stop

    def _tracked_trailing_symbols(self) -> set[str]:
        """Symbols that currently carry trailing stop state.

        Returns:
            Set of symbols present in any of the trailing stop state
            dictionaries.

        """
        return set(self._trailing_stops) | set(self._trailing_highs) | set(self._trailing_lows)

    def _clear_trailing_state(self, symbol: str) -> None:
        """Drop the trailing stop state of a symbol.

        Args:
            symbol: Symbol whose trailing stop state is discarded.

        Returns:
            None.

        """
        self._trailing_stops.pop(symbol, None)
        self._trailing_highs.pop(symbol, None)
        self._trailing_lows.pop(symbol, None)

    def get_position_take_profit(self, symbol: str) -> float | None:
        """Get take profit price for a position.

        The level is direction aware. For a long position the target sits
        above the average entry price (``avg_price * (1 + take_profit_pct)``);
        for a short position it sits below it
        (``avg_price * (1 - take_profit_pct)``), because a short profits when
        the price falls.

        Args:
            symbol: Symbol to query.

        Returns:
            Take profit price, or None if no position/invalid price.

        """
        position = self.positions.get(symbol)
        if position is None or position.avg_price <= 0:
            return None
        if position.quantity < 0:
            return position.avg_price * (1 - self.position_limit.take_profit_pct)
        return position.avg_price * (1 + self.position_limit.take_profit_pct)

    def should_stop_loss(self, symbol: str, current_price: float) -> bool:
        """Check if position should trigger stop loss.

        The comparison follows the direction of the position: the stop is
        hit when the price falls to (or below) the stop level for a long,
        and when it rises to (or above) the stop level for a short.

        Args:
            symbol: Symbol to query.
            current_price: Current market price.

        Returns:
            True if stop loss triggered.

        """
        stop = self.get_position_stop_loss(symbol)
        if stop is None:
            return False
        if self.is_short_position(symbol):
            return bool(current_price >= stop)
        return bool(current_price <= stop)

    def should_take_profit(self, symbol: str, current_price: float) -> bool:
        """Check if position should trigger take profit.

        The comparison follows the direction of the position: the target is
        hit when the price rises to (or above) the target level for a long,
        and when it falls to (or below) the target level for a short.

        Args:
            symbol: Symbol to query.
            current_price: Current market price.

        Returns:
            True if take profit triggered.

        """
        tp = self.get_position_take_profit(symbol)
        if tp is None:
            return False
        if self.is_short_position(symbol):
            return bool(current_price <= tp)
        return bool(current_price >= tp)

    def reset(self) -> None:
        """Reset risk manager state.

        The portfolio state, the equity curve, the peak, the history and the
        last computed risk metrics are all cleared, so no value from the
        discarded run is left behind.

        Returns:
            None.

        """
        self.portfolio_risk = PortfolioRisk(
            total_market_value=self.initial_capital,
            cash=self.initial_capital,
            peak_value=self.initial_capital,
        )
        self.positions = {}
        self.equity_curve = [self.initial_capital]
        self.peak_value = self.initial_capital
        self.risk_metrics = None
        self.history = []
        self._returns = {}
        for symbol in self._tracked_trailing_symbols():
            self._clear_trailing_state(symbol)

    def enable(self) -> None:
        """Enable risk management.

        Returns:
            None.

        """
        self.risk_enabled = True

    def disable(self) -> None:
        """Disable risk management.

        Returns:
            None.

        """
        self.risk_enabled = False


__all__ = [
    "PortfolioRisk",
    "RiskManager",
]
