"""Backtest metrics calculation.

This module aggregates return, risk, and trade-level statistics from an
equity curve and a trades DataFrame into a single ``BacktestMetrics``
dataclass. The underlying risk calculations are delegated to
``quant_trading.risk.metrics``.

Examples:
    >>> import pandas as pd
    >>> equity = pd.Series([100000, 105000, 110000])
    >>> trades = pd.DataFrame({"pnl": [1000, -500, 2000]})
    >>> from quant_trading.backtest.metrics import calculate_backtest_metrics
    >>> metrics = calculate_backtest_metrics(equity, trades=trades)
    >>> metrics.num_trades
    3
    >>> metrics.win_rate
    0.6666666666666666

"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant_trading.backtest.trade_log import split_trade_log
from quant_trading.risk.metrics import (
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_var,
    calculate_volatility,
)


@dataclass
class BacktestMetrics:
    """Comprehensive backtest performance metrics.

    Aggregates return, risk, and trade-level statistics computed from an
    equity curve and a trades DataFrame. All monetary fields are expressed
    in the account's base currency, while ratios and percentages are
    unitless or expressed as percentages.

    Attributes:
        total_return: Absolute net profit/loss (final value - initial value).
        total_pnl: The realized PnL of the run (sum of the trade log PnL).
            This is the PnL the run booked from trades, so it is not the same
            as ``total_return`` (which includes unrealized PnL of positions
            still open).
        unrealized_pnl: The mark-to-market PnL of the positions that were
            still open when the run ended. Together with ``total_pnl`` it
            explains the change of the portfolio value:
            ``final_value - initial_capital == total_pnl + unrealized_pnl``.
            The engine populates this field because it is the only place that
            knows the open positions;
            :func:`~quant_trading.backtest.metrics.calculate_backtest_metrics`
            sees an equity curve and a trade log, neither of which carries the
            market value of an open position, so the field stays ``0.0`` when
            the function is called directly. A run that ended with every
            position closed also reports ``0.0``. This is not the same figure
            as ``TradeAnalysis.open_position_pnl``, which is the part of
            ``total_pnl`` that the positions that are still open booked.
        total_return_pct: Total return as a percentage of initial value.
        annual_return: Annualized mean return (decimal).
        annual_return_pct: Annualized mean return as a percentage.
        volatility: Annualized volatility of returns.
        max_drawdown: Maximum drawdown as a negative decimal.
        max_drawdown_pct: Maximum drawdown as a negative percentage.
        sharpe_ratio: Annualized Sharpe ratio.
        sortino_ratio: Annualized Sortino ratio.
        calmar_ratio: Calmar ratio (annual return / |max drawdown|).
        win_rate: Fraction of the round trips that were profitable (0.0 - 1.0).
        profit_factor: Gross profit / gross loss (0.0 if no losers).
        num_trades: Number of completed round trips (opening rows excluded).
        num_winning_trades: Number of round trips with a positive PnL.
        num_losing_trades: Number of round trips with a negative PnL.
        avg_win: Average PnL of winning trades (0.0 if none).
        avg_loss: Average PnL of losing trades (negative, 0.0 if none).
        largest_win: Largest single-trade PnL (0.0 if none).
        largest_loss: Smallest (most negative) single-trade PnL (0.0 if none).
        var_95: Value at Risk at 95% confidence (historical method).

    Examples:
        >>> metrics = BacktestMetrics(total_return=1000.0, sharpe_ratio=1.5)
        >>> metrics.total_return
        1000.0
        >>> metrics.to_dict()["sharpe_ratio"]
        1.5

    """

    # Returns
    total_return: float = 0.0
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    annual_return: float = 0.0
    annual_return_pct: float = 0.0

    # Risk
    volatility: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0

    # Ratios
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Other
    win_rate: float = 0.0
    profit_factor: float = 0.0
    num_trades: int = 0
    num_winning_trades: int = 0
    num_losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    var_95: float = 0.0

    # Unrealized PnL of the positions that are still open. It is declared last
    # so that the positional order of the fields above stays the same for
    # callers that build a metrics object positionally.
    unrealized_pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a dictionary.

        Returns:
            Dictionary containing all metric values with keys matching
            the attribute names of this dataclass.

        """
        return {
            "total_return": self.total_return,
            "total_pnl": self.total_pnl,
            "total_return_pct": self.total_return_pct,
            "annual_return": self.annual_return,
            "annual_return_pct": self.annual_return_pct,
            "volatility": self.volatility,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "num_trades": self.num_trades,
            "num_winning_trades": self.num_winning_trades,
            "num_losing_trades": self.num_losing_trades,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "var_95": self.var_95,
            "unrealized_pnl": self.unrealized_pnl,
        }


def calculate_backtest_metrics(
    equity_curve: pd.Series,
    trades: pd.DataFrame | None = None,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
    unrealized_pnl: float | None = None,
    positions: dict[str, Any] | None = None,
) -> BacktestMetrics:
    """Calculate comprehensive backtest metrics from an equity curve.

    Computes return, risk, and trade-level statistics. When the equity
    curve has fewer than two points, all return/risk fields remain at their
    default zero values. Trade statistics are only populated when ``trades``
    is provided, contains at least one row, and includes a ``pnl`` column.

    A trade is a completed round trip: the opening rows are excluded and the
    PnL of a short entry is counted with the cover that closes it. The trade
    statistics therefore agree with
    :func:`~quant_trading.backtest.trade_analysis.analyze_trades` for the
    same trades.

    Args:
        equity_curve: Cumulative portfolio value series indexed by time.
        trades: Optional DataFrame of trades; must contain a ``pnl`` column
            to populate trade statistics.
        risk_free_rate: Annual risk-free rate used for Sharpe/Sortino.
        periods_per_year: Trading periods per year for annualization
            (default 252 for daily data). The same value is applied to the
            annualized return, volatility, Sharpe, Sortino and Calmar
            figures so the metrics stay mutually consistent.
        unrealized_pnl: Optional mark-to-market PnL of positions still
            open at the end of the run. If ``None`` (default), the value
            is taken from ``positions`` if provided, otherwise remains
            ``0.0``. The engine passes the value it computes from open
            positions.
        positions: Optional mapping of symbol to position objects/holdings
            with an ``unrealized_pnl`` attribute. When ``unrealized_pnl``
            is ``None`` and positions are provided, the unrealized PnL is
            summed from them.

    Returns:
        BacktestMetrics object populated with the computed values.

    Examples:
        >>> import pandas as pd
        >>> equity = pd.Series([100000, 110000, 105000, 115000])
        >>> metrics = calculate_backtest_metrics(equity)
        >>> float(metrics.total_return)
        15000.0
        >>> round(float(metrics.sharpe_ratio), 2)
        9.58

    """
    metrics = BacktestMetrics()
    if unrealized_pnl is not None:
        metrics.unrealized_pnl = float(unrealized_pnl)
    elif positions is not None:
        try:
            metrics.unrealized_pnl = float(
                sum(getattr(position, "unrealized_pnl", 0.0) for position in positions.values())
            )
        except Exception:  # noqa: BLE001
            metrics.unrealized_pnl = 0.0
    else:
        metrics.unrealized_pnl = 0.0

    if len(equity_curve) < 2:
        return metrics

    initial_value = equity_curve.iloc[0]
    final_value = equity_curve.iloc[-1]

    metrics.total_return = final_value - initial_value
    if initial_value != 0:
        metrics.total_return_pct = (final_value / initial_value - 1) * 100
    else:
        metrics.total_return_pct = 0.0

    returns = calculate_returns(equity_curve)
    if len(returns) > 0:
        metrics.annual_return = returns.mean() * periods_per_year
        metrics.annual_return_pct = metrics.annual_return * 100
        metrics.volatility = calculate_volatility(returns, periods_per_year=periods_per_year)
        metrics.max_drawdown = calculate_max_drawdown(equity_curve)
        metrics.max_drawdown_pct = metrics.max_drawdown * 100
        metrics.sharpe_ratio = calculate_sharpe_ratio(
            returns, risk_free_rate, periods_per_year=periods_per_year
        )
        metrics.sortino_ratio = calculate_sortino_ratio(
            returns, risk_free_rate, periods_per_year=periods_per_year
        )
        metrics.calmar_ratio = calculate_calmar_ratio(
            returns, equity_curve, periods_per_year=periods_per_year
        )
        metrics.var_95 = calculate_var(returns, 0.95)

    # Trade statistics
    if trades is not None and len(trades) > 0 and "pnl" in trades.columns:
        # A trade is a completed round trip: the opening rows are excluded and
        # the PnL of a short entry is counted with the cover that closes it.
        # The same split drives TradeAnalysis, so the two APIs count the same
        # trades for the same result.
        log = split_trade_log(trades)
        round_trips = log.round_trips

        # The realized PnL of the run is the sum of the trade log
        if not log.entries.empty:
            metrics.total_pnl = float(log.entries["pnl"].sum())

        winning = round_trips[round_trips["pnl"] > 0]
        losing = round_trips[round_trips["pnl"] < 0]

        metrics.num_trades = len(round_trips)
        metrics.num_winning_trades = len(winning)
        metrics.num_losing_trades = len(losing)
        metrics.win_rate = len(winning) / len(round_trips) if len(round_trips) > 0 else 0

        metrics.avg_win = winning["pnl"].mean() if len(winning) > 0 else 0
        metrics.avg_loss = losing["pnl"].mean() if len(losing) > 0 else 0
        metrics.largest_win = winning["pnl"].max() if len(winning) > 0 else 0
        metrics.largest_loss = losing["pnl"].min() if len(losing) > 0 else 0

        gross_profit = winning["pnl"].sum() if len(winning) > 0 else 0
        gross_loss = abs(losing["pnl"].sum()) if len(losing) > 0 else 0
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    return metrics
