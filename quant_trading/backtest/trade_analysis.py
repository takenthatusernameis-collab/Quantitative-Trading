"""Trade-level analysis for backtest results.

Examples:
    Analyze a backtest result and inspect its trade statistics::

        from quant_trading.backtest import analyze_trades

        analysis = analyze_trades(result)
        print(f"Total trades: {analysis.total_trades}")
        print(f"Win rate: {analysis.win_rate:.2%}")
        print(f"Profit factor: {analysis.profit_factor:.2f}")

    Convert the analysis to a dictionary for serialization::

        data = analysis.to_dict()
        assert data["total_trades"] == analysis.total_trades

"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.trade_log import split_trade_log
from quant_trading.risk.metrics import calculate_sharpe_ratio, calculate_sortino_ratio


@dataclass
class TradeAnalysis:
    """Detailed trade analysis results.

    Attributes:
        total_trades: Total number of completed trades with PnL.
        winning_trades: Number of winning trades.
        losing_trades: Number of losing trades.
        win_rate: Fraction of trades that were winners (0-1).
        total_pnl: Sum of all trade PnL.
        avg_pnl: Average PnL per trade.
        median_pnl: Median PnL per trade.
        std_pnl: Standard deviation of trade PnL.
        avg_win: Average PnL of winning trades.
        avg_loss: Average PnL of losing trades (negative, like the PnL of the
            losing trades themselves).
        largest_win: Largest winning trade PnL.
        largest_loss: Largest losing trade PnL.
        profit_factor: Gross profit divided by gross loss.
        avg_holding_period: Average holding period in days.
        median_holding_period: Median holding period in days.
        min_holding_period: Minimum holding period in days.
        max_holding_period: Maximum holding period in days.
        max_consecutive_wins: Longest streak of winning trades.
        max_consecutive_losses: Longest streak of losing trades.
        current_streak: Length of the current streak.
        current_streak_type: Type of the current streak ("win" or "loss").
        monthly_returns: Monthly return percentages keyed by date.
        weekly_returns: Weekly return percentages keyed by date.
        symbol_stats: Per-symbol trade statistics.
        expectancy: Expected PnL per trade.
        sharpe_ratio: Annualized Sharpe ratio of the per-trade return series.
        sortino_ratio: Annualized Sortino ratio of the per-trade return series.

    Examples:
        analysis = analyze_trades(result)
        assert 0.0 <= analysis.win_rate <= 1.0
        assert analysis.profit_factor >= 0.0

    """

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # PnL statistics
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    median_pnl: float = 0.0
    std_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0

    # Holding period statistics
    avg_holding_period: float = 0.0
    median_holding_period: float = 0.0
    min_holding_period: float = 0.0
    max_holding_period: float = 0.0

    # Consecutive wins/losses
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    current_streak: int = 0
    current_streak_type: str = ""

    # Monthly/weekly analysis
    monthly_returns: dict[str, float] | None = None
    weekly_returns: dict[str, float] | None = None

    # Per-symbol analysis
    symbol_stats: dict[str, dict[str, Any]] | None = None

    # Risk metrics
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the trade analysis to a dictionary.

        Returns:
            Dictionary of all computed trade statistics.

        """
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "avg_pnl": self.avg_pnl,
            "median_pnl": self.median_pnl,
            "std_pnl": self.std_pnl,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "profit_factor": self.profit_factor,
            "avg_holding_period": self.avg_holding_period,
            "median_holding_period": self.median_holding_period,
            "min_holding_period": self.min_holding_period,
            "max_holding_period": self.max_holding_period,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "current_streak": self.current_streak,
            "current_streak_type": self.current_streak_type,
            "monthly_returns": self.monthly_returns,
            "weekly_returns": self.weekly_returns,
            "symbol_stats": self.symbol_stats,
            "expectancy": self.expectancy,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
        }


def _calculate_holding_periods(trades: pd.DataFrame) -> list[float]:
    """Calculate holding periods in days for each completed round trip.

    Buys and sells are matched per symbol using a FIFO queue of open
    entries. Each sell (or portion of a sell) is paired with the oldest
    open entry, and the elapsed days between entry and fill are recorded.

    Args:
        trades: Trade DataFrame with at least ``symbol``, ``timestamp``,
            ``action``, and ``quantity`` columns.

    Returns:
        List of holding periods in days (as floats). Empty when there are
        no completed round trips, and empty when the trades carry no
        ``action`` column (there are then no entries and exits to pair).

    """
    if trades.empty or "pnl" not in trades.columns or "action" not in trades.columns:
        return []

    # Group trades by symbol to find round trips
    holding_periods = []
    for symbol in trades["symbol"].unique():
        symbol_trades = trades[trades["symbol"] == symbol].copy()
        symbol_trades = symbol_trades.sort_values("timestamp")

        # Track long entries (buy -> sell) and short entries (short -> cover)
        # independently, each with its own FIFO queue.
        long_times: list[datetime] = []
        long_quantities: list[float] = []
        short_times: list[datetime] = []
        short_quantities: list[float] = []

        for _, trade in symbol_trades.iterrows():
            action = trade["action"]
            if action == "buy":
                long_times.append(trade["timestamp"])
                long_quantities.append(trade["quantity"])
            elif action == "sell" and long_times:
                qty_sold = trade["quantity"]
                while qty_sold > 0 and long_times:
                    entry_time = long_times[0]
                    entry_qty = long_quantities[0]
                    holding_periods.append(
                        (trade["timestamp"] - entry_time).total_seconds() / 86400
                    )
                    if qty_sold >= entry_qty:
                        qty_sold -= entry_qty
                        long_times.pop(0)
                        long_quantities.pop(0)
                    else:
                        long_quantities[0] -= qty_sold
                        qty_sold = 0
            elif action == "short":
                short_times.append(trade["timestamp"])
                short_quantities.append(trade["quantity"])
            elif action == "cover" and short_times:
                qty_covered = trade["quantity"]
                while qty_covered > 0 and short_times:
                    entry_time = short_times[0]
                    entry_qty = short_quantities[0]
                    holding_periods.append(
                        (trade["timestamp"] - entry_time).total_seconds() / 86400
                    )
                    if qty_covered >= entry_qty:
                        qty_covered -= entry_qty
                        short_times.pop(0)
                        short_quantities.pop(0)
                    else:
                        short_quantities[0] -= qty_covered
                        qty_covered = 0

    return holding_periods


def _calculate_consecutive_streaks(trades: pd.DataFrame) -> tuple[int, int, int, str]:
    """Calculate max consecutive wins/losses and the current streak.

    Streaks are temporal sequences, so the trades are ordered by their
    timestamp before the streaks are counted. The ordering is stable, so trades
    that share a timestamp keep the order they were given in.

    Args:
        trades: Trade DataFrame with a ``pnl`` column and, optionally, a
            ``timestamp`` column used to order the trades.

    Returns:
        Tuple of ``(max_wins, max_losses, current_streak, current_streak_type)``.
        ``current_streak_type`` is ``"win"`` or ``"loss"`` (empty string when
        the streak is zero).

    """
    if trades.empty or "pnl" not in trades.columns:
        return 0, 0, 0, ""

    if "timestamp" in trades.columns:
        trades = trades.sort_values("timestamp", kind="stable")

    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0
    current_streak = 0
    current_streak_type = ""

    for _, trade in trades.iterrows():
        pnl = trade.get("pnl", 0)
        if pnl > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif pnl < 0:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)

    if current_wins > 0:
        current_streak = current_wins
        current_streak_type = "win"
    elif current_losses > 0:
        current_streak = current_losses
        current_streak_type = "loss"

    return max_wins, max_losses, current_streak, current_streak_type


def _calculate_monthly_returns(equity_curve: pd.Series) -> dict[str, float]:
    """Calculate monthly returns from an equity curve.

    The equity curve is resampled to month-end, the percentage change between
    consecutive month-ends is computed, and the result is keyed by the
    month-end date as ``"YYYY-MM-DD"``.

    Args:
        equity_curve: Time-indexed portfolio equity values.

    Returns:
        Mapping of month-end date string to monthly return percentage. Empty
        when fewer than two month-end values are available or when the equity
        curve is not indexed by time.

    """
    if len(equity_curve) < 2:
        return {}
    if not isinstance(equity_curve.index, pd.DatetimeIndex):
        return {}

    monthly = equity_curve.resample("ME").last()
    if len(monthly) < 2:
        return {}

    monthly_returns = monthly.pct_change().dropna() * 100
    return {str(k.date()): float(v) for k, v in monthly_returns.items()}


def _calculate_weekly_returns(equity_curve: pd.Series) -> dict[str, float]:
    """Calculate weekly returns from an equity curve.

    The equity curve is resampled to week-end, the percentage change between
    consecutive week-ends is computed, and the result is keyed by the
    week-end date as ``"YYYY-MM-DD"``.

    Args:
        equity_curve: Time-indexed portfolio equity values.

    Returns:
        Mapping of week-end date string to weekly return percentage. Empty
        when fewer than two week-end values are available or when the equity
        curve is not indexed by time.

    """
    if len(equity_curve) < 2:
        return {}
    if not isinstance(equity_curve.index, pd.DatetimeIndex):
        return {}

    weekly = equity_curve.resample("W").last()
    if len(weekly) < 2:
        return {}

    weekly_returns = weekly.pct_change().dropna() * 100
    return {str(k.date()): float(v) for k, v in weekly_returns.items()}


def _calculate_symbol_stats(trades: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Calculate per-symbol trade statistics.

    Args:
        trades: Trade DataFrame with at least ``symbol`` and ``pnl`` columns.

    Returns:
        Mapping of symbol to a dict with ``total_trades``,
        ``winning_trades``, ``losing_trades``, ``win_rate``, ``total_pnl``,
        ``avg_pnl``, ``avg_win``, ``avg_loss``, ``largest_win``, and
        ``largest_loss``. The loss figures are signed, like the top level
        figures of the same name. Empty when there are no trades.

    """
    if trades.empty or "pnl" not in trades.columns:
        return {}

    stats = {}
    for symbol in trades["symbol"].unique():
        symbol_trades = trades[trades["symbol"] == symbol]
        winning = symbol_trades[symbol_trades["pnl"] > 0]
        losing = symbol_trades[symbol_trades["pnl"] < 0]

        stats[symbol] = {
            "total_trades": len(symbol_trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": len(winning) / len(symbol_trades) if len(symbol_trades) > 0 else 0,
            "total_pnl": float(symbol_trades["pnl"].sum()),
            "avg_pnl": float(symbol_trades["pnl"].mean()) if len(symbol_trades) > 0 else 0,
            "avg_win": float(winning["pnl"].mean()) if len(winning) > 0 else 0,
            "avg_loss": float(losing["pnl"].mean()) if len(losing) > 0 else 0,
            "largest_win": float(winning["pnl"].max()) if len(winning) > 0 else 0,
            "largest_loss": float(losing["pnl"].min()) if len(losing) > 0 else 0,
        }

    return stats


def _equity_at_trade_times(equity_curve: pd.Series, timestamps: pd.Series) -> pd.Series:
    """Look up the portfolio equity at each trade timestamp.

    The equity curve is treated as the value of the account over time, so the
    value known at or before a trade's timestamp is the capital the trade was
    taken with.

    Args:
        equity_curve: Time-indexed portfolio equity values.
        timestamps: Trade timestamps to look up.

    Returns:
        Series of equity values aligned with ``timestamps``. Entries are NaN
        when the equity curve is empty, is not indexed by time, or does not
        cover the timestamp.

    """
    resolved: pd.Series = pd.Series(np.nan, index=timestamps.index, dtype=float)

    if equity_curve is None or len(equity_curve) == 0:
        return resolved
    if not isinstance(equity_curve.index, pd.DatetimeIndex):
        return resolved

    equity = equity_curve.sort_index()
    values: list[Any] = []
    for timestamp in timestamps:
        try:
            values.append(equity.asof(timestamp))
        except (TypeError, ValueError):
            values.append(np.nan)

    resolved = pd.Series(values, index=timestamps.index, dtype=float)
    return resolved


def _calculate_trade_returns(pnl_trades: pd.DataFrame, equity_curve: pd.Series) -> pd.Series:
    """Convert trade PnL into per-trade portfolio returns.

    Each trade's PnL is expressed as a fraction of the portfolio equity at the
    time of the trade. A return series is what a Sharpe or Sortino ratio is
    defined on, and it is comparable between accounts of different sizes.

    Args:
        pnl_trades: Trades with a ``pnl`` column and a ``timestamp`` column.
        equity_curve: Time-indexed portfolio equity values.

    Returns:
        Series of per-trade returns aligned with ``pnl_trades``. Entries are
        NaN when the equity at the trade time is unknown or not positive.

    """
    returns: pd.Series = pd.Series(np.nan, index=pnl_trades.index, dtype=float)

    if pnl_trades.empty or "timestamp" not in pnl_trades.columns:
        return returns

    equity = _equity_at_trade_times(equity_curve, pnl_trades["timestamp"])
    usable = equity > 0
    if not usable.any():
        return returns

    returns.loc[usable] = pnl_trades.loc[usable, "pnl"] / equity.loc[usable]

    return returns


def analyze_trades(
    result: BacktestResult,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> TradeAnalysis:
    """Perform detailed trade analysis on a backtest result.

    The trade level risk metrics are computed on the per-trade return series:
    the PnL of every trade is expressed as a fraction of the portfolio equity
    at the time of the trade. The trade level metrics treat one trade as one
    period, so ``risk_free_rate`` is converted to a per-period rate with
    ``periods_per_year`` and subtracted from the per-trade returns before the
    ratio is annualized.

    A trade is a completed round trip, and the loss figures (``avg_loss``
    and ``largest_loss``) are signed, so they are negative when there are
    losing trades. They report the same numbers as the same figures in
    :class:`~quant_trading.backtest.metrics.BacktestMetrics`.

    Args:
        result: BacktestResult to analyze.
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino. It is
            applied to the per-trade return series as a per-period rate.
        periods_per_year: Number of periods per year for annualization. The
            trade level metrics treat a trade as a period, so this is also the
            number of trades per year they assume.

    Returns:
        TradeAnalysis with detailed statistics.

    Examples:
        analysis = analyze_trades(result, risk_free_rate=0.02)
        assert analysis.total_trades > 0
        print(f"Expectancy: ${analysis.expectancy:,.2f}")

    """
    trades = result.trades.copy()

    if trades.empty or "pnl" not in trades.columns:
        return TradeAnalysis()

    # The short entries are paired with the covers that close them, so a short
    # round trip counts as one trade (entry fee + price move belong to the
    # same round trip), mirroring the long side. The metrics use the same
    # split, so both APIs count the same trades.
    log = split_trade_log(trades)

    # Holding periods are computed before the short entry rows are dropped:
    # a short's entry row carries the entry timestamp its cover must be
    # matched against. Dropping it first would leave every short with no
    # holding period (long entries are never dropped).
    holding_periods = _calculate_holding_periods(log.entries)

    # The round trips are the trades with a PnL (opening trades excluded).
    pnl_trades = log.round_trips

    if pnl_trades.empty:
        return TradeAnalysis()

    winning = pnl_trades[pnl_trades["pnl"] > 0]
    losing = pnl_trades[pnl_trades["pnl"] < 0]

    total_pnl = float(pnl_trades["pnl"].sum())
    gross_profit = float(winning["pnl"].sum()) if len(winning) > 0 else 0.0
    gross_loss = float(abs(losing["pnl"].sum())) if len(losing) > 0 else 0.0

    # Consecutive streaks
    max_wins, max_losses, current_streak, current_streak_type = _calculate_consecutive_streaks(
        pnl_trades
    )

    # Monthly/weekly returns
    monthly_returns = _calculate_monthly_returns(result.equity_curve)
    weekly_returns = _calculate_weekly_returns(result.equity_curve)

    # Symbol stats
    symbol_stats = _calculate_symbol_stats(pnl_trades)

    # Expectancy
    win_rate = len(winning) / len(pnl_trades) if len(pnl_trades) > 0 else 0
    avg_win = float(winning["pnl"].mean()) if len(winning) > 0 else 0
    # The loss figures are signed, like the PnL of the losing trades
    # themselves, so the expectancy is the win rate weighted average of the
    # wins and the losses.
    avg_loss = float(losing["pnl"].mean()) if len(losing) > 0 else 0
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    # Trade-level Sharpe/Sortino, computed on the per-trade return series so
    # that the risk-free rate can be applied to it.
    trade_returns = _calculate_trade_returns(pnl_trades, result.equity_curve)
    sharpe = calculate_sharpe_ratio(
        trade_returns,
        risk_free_rate,
        periods_per_year=periods_per_year,
    )
    sortino = calculate_sortino_ratio(
        trade_returns,
        risk_free_rate,
        periods_per_year=periods_per_year,
    )

    return TradeAnalysis(
        total_trades=len(pnl_trades),
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_pnl=float(pnl_trades["pnl"].mean()),
        median_pnl=float(pnl_trades["pnl"].median()),
        std_pnl=float(pnl_trades["pnl"].std()) if len(pnl_trades) > 1 else 0.0,
        avg_win=avg_win,
        avg_loss=avg_loss,
        largest_win=float(winning["pnl"].max()) if len(winning) > 0 else 0.0,
        largest_loss=float(losing["pnl"].min()) if len(losing) > 0 else 0.0,
        profit_factor=gross_profit / gross_loss if gross_loss > 0 else 0.0,
        avg_holding_period=float(np.mean(holding_periods)) if holding_periods else 0.0,
        median_holding_period=float(np.median(holding_periods)) if holding_periods else 0.0,
        min_holding_period=float(np.min(holding_periods)) if holding_periods else 0.0,
        max_holding_period=float(np.max(holding_periods)) if holding_periods else 0.0,
        max_consecutive_wins=max_wins,
        max_consecutive_losses=max_losses,
        current_streak=current_streak,
        current_streak_type=current_streak_type,
        monthly_returns=monthly_returns,
        weekly_returns=weekly_returns,
        symbol_stats=symbol_stats,
        expectancy=expectancy,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
    )


def print_trade_analysis(analysis: TradeAnalysis) -> None:
    """Print a formatted trade analysis report.

    Args:
        analysis: TradeAnalysis to print.

    Examples:
        analysis = analyze_trades(result)
        print_trade_analysis(analysis)

    """
    print(f"\n{'=' * 60}")
    print("Trade Analysis")
    print(f"{'=' * 60}")

    print(f"\n{'Overview':-^60}")
    print(f"Total Trades:      {analysis.total_trades}")
    print(f"Winning Trades:    {analysis.winning_trades}")
    print(f"Losing Trades:     {analysis.losing_trades}")
    print(f"Win Rate:          {analysis.win_rate:.2%}")

    print(f"\n{'PnL Statistics':-^60}")
    print(f"Total PnL:         ${analysis.total_pnl:,.2f}")
    print(f"Avg PnL/Trade:     ${analysis.avg_pnl:,.2f}")
    print(f"Median PnL/Trade:  ${analysis.median_pnl:,.2f}")
    print(f"Std Dev PnL:       ${analysis.std_pnl:,.2f}")
    print(f"Avg Win:           ${analysis.avg_win:,.2f}")
    print(f"Avg Loss:          ${analysis.avg_loss:,.2f}")
    print(f"Largest Win:       ${analysis.largest_win:,.2f}")
    print(f"Largest Loss:      ${analysis.largest_loss:,.2f}")
    print(f"Profit Factor:     {analysis.profit_factor:.2f}")
    print(f"Expectancy:        ${analysis.expectancy:,.2f}")

    print(f"\n{'Holding Periods':-^60}")
    print(f"Avg Holding Period: {analysis.avg_holding_period:.1f} days")
    print(f"Median Holding:     {analysis.median_holding_period:.1f} days")
    print(f"Min Holding:        {analysis.min_holding_period:.1f} days")
    print(f"Max Holding:        {analysis.max_holding_period:.1f} days")

    print(f"\n{'Streaks':-^60}")
    print(f"Max Consecutive Wins:   {analysis.max_consecutive_wins}")
    print(f"Max Consecutive Losses: {analysis.max_consecutive_losses}")
    print(f"Current Streak:         {analysis.current_streak} ({analysis.current_streak_type})")

    print(f"\n{'Trade-Level Risk':-^60}")
    print(f"Trade Sharpe:   {analysis.sharpe_ratio:.2f}")
    print(f"Trade Sortino:  {analysis.sortino_ratio:.2f}")

    if analysis.monthly_returns:
        print(f"\n{'Monthly Returns':-^60}")
        for month, ret in list(analysis.monthly_returns.items())[-12:]:
            print(f"  {month}: {ret:+.2f}%")

    if analysis.symbol_stats:
        print(f"\n{'Per-Symbol Statistics':-^60}")
        print(
            f"{'Symbol':<10} {'Trades':>7} {'Win%':>7} {'PnL':>12} {'Avg Win':>10} {'Avg Loss':>10}"
        )
        print(f"{'-' * 60}")
        for symbol, stats in sorted(analysis.symbol_stats.items()):
            print(
                f"{symbol:<10} {stats['total_trades']:>7} {stats['win_rate']:>6.1%} "
                f"${stats['total_pnl']:>10,.2f} ${stats['avg_win']:>9,.2f} ${stats['avg_loss']:>9,.2f}"
            )


__all__ = [
    "TradeAnalysis",
    "analyze_trades",
    "print_trade_analysis",
]
