"""Interpretation of the raw backtest trade log.

The engine records one row per executed trade, so a round trip contributes an
opening row and a closing row. :class:`~quant_trading.backtest.metrics.BacktestMetrics`
and :class:`~quant_trading.backtest.trade_analysis.TradeAnalysis` both report how
many trades a backtest made, how many of them won and what the win rate was.
They can only agree when they count the same rows, so the rules that turn the
raw trade log into completed round trips live here once and both of them use
them.

Examples:
    >>> import pandas as pd
    >>> from quant_trading.backtest.trade_log import split_trade_log
    >>> trades = pd.DataFrame(
    ...     {
    ...         "symbol": ["AAPL", "AAPL"],
    ...         "action": ["buy", "sell"],
    ...         "quantity": [10.0, 10.0],
    ...         "price": [100.0, 110.0],
    ...         "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
    ...         "pnl": [0.0, 100.0],
    ...     }
    ... )
    >>> log = split_trade_log(trades)
    >>> len(log.entries)
    2
    >>> len(log.round_trips)
    1
    >>> float(log.entries["pnl"].sum())
    100.0
    >>> float(log.round_trips["pnl"].sum())
    100.0

"""

from typing import NamedTuple

import pandas as pd

# The columns that are needed to pair a short entry with the cover that
# closes it. A log that does not carry all of them cannot be paired, so it is
# read as a log of long round trips only.
PAIRING_COLUMNS = ("action", "symbol", "quantity")


class TradeLog(NamedTuple):
    """A trade log split into its entries and its completed round trips.

    Attributes:
        entries: Every row of the log, with the PnL the run booked on that
            row. The short rows are kept, because a short entry carries the
            timestamp its cover has to be matched against.
        round_trips: The rows that stand for completed round trips. The PnL
            of a short entry is folded into the cover that closed it, so one
            completed round trip is one row and it carries the PnL of the
            whole round trip. The long entry rows are gone (they open a round
            trip instead of closing one). One completed round trip is one
            row, and it is a row even when the round trip closed at exactly
            zero PnL.
        open_pnl: The PnL that the positions which are still open at the end
            of the run booked. A long entry books no PnL, so this is the
            entry fee of the shorts that were never (fully) covered. It is
            0.0 when every position was closed.

    """

    entries: pd.DataFrame
    round_trips: pd.DataFrame
    open_pnl: float = 0.0


def split_trade_log(trades: pd.DataFrame) -> TradeLog:
    """Split a trade log into its entries and its completed round trips.

    A long entry books no PnL and the row that closes it books the PnL of the
    whole round trip, so the entry row is not a trade. A short is the mirror
    image: the entry books the fee it paid and the cover books the price move,
    so both belong to the same round trip. The PnL of the short entry is
    therefore folded into the cover that closes it and the entry row is
    dropped, which leaves one row per completed round trip.

    The entries keep the PnL the log booked: the fee of a short is folded
    into the round trips only, so the fee is not counted twice and the sum of
    the entries is the PnL of the run. The fee of a short that was never
    covered belongs to a position that is still open at the end of the run,
    and it is reported as ``open_pnl``.

    A round trip is recognized by the row that closes it and not by the PnL
    that row booked: a round trip that closed at exactly zero PnL is a trade,
    and a closing row that closes no open position is not a trade.

    Args:
        trades: Trade log. It needs a ``pnl`` column. The short entries are
            only paired with their covers when the log carries an ``action``,
            a ``symbol`` and a ``quantity`` column as well; without them the
            log is read as a log of long round trips only.

    Returns:
        The split trade log. The round trips are empty when the log is empty
        or carries no ``pnl`` column.

    """
    if trades.empty or "pnl" not in trades.columns:
        return TradeLog(entries=trades.copy(), round_trips=trades.iloc[0:0].copy())

    if not all(column in trades.columns for column in PAIRING_COLUMNS):
        entries = trades.copy()
        return TradeLog(entries=entries, round_trips=entries[entries["pnl"] != 0].copy())

    entries = trades.copy()
    if "timestamp" in entries.columns:
        entries = entries.sort_values("timestamp", kind="stable")
    entries = entries.reset_index(drop=True)

    # The PnL is carried as a float, so folding a fee into a cover cannot
    # truncate the result.
    pnl = entries["pnl"].astype(float)

    # Short entries are paired with their covers FIFO per symbol; the entry's
    # fee is folded into the cover that closes it and the entry row is dropped.
    # Long entries are paired with the sells that close them FIFO per symbol,
    # the way ``_calculate_holding_periods()`` already does: a sell that closes
    # (part of) an open long entry is a round trip, a sell that closes nothing
    # is not. Long entry rows are dropped by construction, so the ``pnl != 0``
    # filter is no longer needed and a round trip that closes at exactly zero
    # PnL is counted as a trade.
    short_queues: dict[str, list[list[float]]] = {}
    long_queues: dict[str, list[list[float]]] = {}
    round_trip_rows: set[int] = set()
    for index, row in entries.iterrows():
        symbol = row["symbol"]
        action = row["action"]
        if action == "short":
            short_queues.setdefault(symbol, []).append(
                [float(row["quantity"]), float(pnl.iloc[index])]
            )
        elif action == "cover":
            quantity = float(row["quantity"])
            folded = 0.0
            closed_any = False
            queue = short_queues.setdefault(symbol, [])
            while quantity > 0 and queue:
                entry = queue[0]
                closed_any = True
                if quantity >= entry[0]:
                    folded += entry[1]
                    quantity -= entry[0]
                    queue.pop(0)
                else:
                    portion = quantity / entry[0]
                    folded += entry[1] * portion
                    entry[0] -= quantity
                    entry[1] *= 1 - portion
                    quantity = 0
            if folded:
                pnl.iloc[index] = pnl.iloc[index] + folded
            if closed_any:
                round_trip_rows.add(index)
        elif action == "sell":
            quantity = float(row["quantity"])
            closed_any = False
            queue = long_queues.setdefault(symbol, [])
            while quantity > 0 and queue:
                entry = queue[0]
                closed_any = True
                if quantity >= entry[0]:
                    quantity -= entry[0]
                    queue.pop(0)
                else:
                    entry[0] -= quantity
                    quantity = 0
            if closed_any:
                round_trip_rows.add(index)
        elif action == "buy":
            long_queues.setdefault(symbol, []).append([float(row["quantity"])])

    # The entries keep the PnL the log booked; the fee of a short is folded
    # into the round trips only, so it is not counted twice.
    selected = sorted(round_trip_rows)
    round_trips = entries.loc[selected].copy()
    round_trips["pnl"] = pnl.loc[selected]
    round_trips = round_trips.reset_index(drop=True)

    # The shorts that were never covered are still open at the end of the
    # run. They booked their entry fee, and that fee is part of the PnL of
    # the run, so it is reported apart from the round trips.
    open_pnl = sum(entry[1] for queue in short_queues.values() for entry in queue)

    return TradeLog(entries=entries, round_trips=round_trips, open_pnl=open_pnl)


__all__ = [
    "TradeLog",
    "split_trade_log",
]
