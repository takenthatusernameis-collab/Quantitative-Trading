"""Tests for the shared trade log interpretation.

The trade log rules live in :mod:`quant_trading.backtest.trade_log` because
``BacktestMetrics`` and ``TradeAnalysis`` have to count the same trades. The
tests below cover the rules themselves and the agreement between the two
public APIs.
"""

from datetime import datetime

import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.metrics import BacktestMetrics, calculate_backtest_metrics
from quant_trading.backtest.trade_analysis import TradeAnalysis, analyze_trades
from quant_trading.backtest.trade_log import split_trade_log


def _trade(
    symbol: str = "AAPL",
    action: str = "buy",
    quantity: float = 10.0,
    price: float = 100.0,
    day: int = 1,
    pnl: float = 0.0,
) -> dict:
    """Build one row of a trade log."""
    return {
        "symbol": symbol,
        "action": action,
        "quantity": quantity,
        "price": price,
        "timestamp": datetime(2024, 1, day),
        "pnl": pnl,
    }


def _log(*rows: dict) -> pd.DataFrame:
    """Build a trade log from the given rows."""
    return pd.DataFrame(list(rows))


def _result(trades: pd.DataFrame) -> BacktestResult:
    """Build a backtest result that carries the given trade log."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity = pd.Series([100000.0 + step * 10.0 for step in range(10)], index=dates)
    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=BacktestMetrics(),
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 10),
        initial_capital=100000.0,
        final_value=100090.0,
        total_return=90.0,
        total_return_pct=0.09,
    )


class TestSplitTradeLog:
    """The trade log is split into its entries and its completed round trips."""

    def test_empty_log_has_no_round_trips(self):
        """An empty log yields empty entries and empty round trips."""
        log = split_trade_log(pd.DataFrame())

        assert log.entries.empty
        assert log.round_trips.empty

    def test_log_without_pnl_column_has_no_round_trips(self):
        """A log without a ``pnl`` column cannot carry a trade."""
        log = split_trade_log(pd.DataFrame({"symbol": ["AAPL"], "action": ["buy"]}))

        assert len(log.entries) == 1
        assert log.round_trips.empty

    def test_log_without_action_column_keeps_the_non_zero_pnl_rows(self):
        """Without an ``action`` column the rows with a PnL are the trades."""
        log = split_trade_log(pd.DataFrame({"pnl": [0.0, 100.0, -50.0]}))

        assert len(log.entries) == 3
        assert log.round_trips["pnl"].tolist() == [100.0, -50.0]

    def test_long_entry_is_not_a_trade(self):
        """The opening row of a long round trip carries no PnL and is no trade."""
        log = split_trade_log(
            _log(
                _trade(action="buy", pnl=0.0),
                _trade(action="sell", day=2, pnl=100.0),
            )
        )

        assert len(log.entries) == 2
        assert len(log.round_trips) == 1
        assert log.round_trips["pnl"].tolist() == [100.0]

    def test_short_entry_is_folded_into_the_cover_that_closes_it(self):
        """A short entry books a fee that belongs to the round trip it opens."""
        log = split_trade_log(
            _log(
                _trade(action="short", pnl=-15.0),
                _trade(action="cover", day=2, pnl=100.0),
            )
        )

        # The cover carries the PnL of the whole round trip.
        assert log.entries["pnl"].tolist() == [-15.0, 85.0]
        # The short entry is no trade of its own.
        assert len(log.round_trips) == 1
        assert log.round_trips["pnl"].tolist() == [85.0]

    def test_partial_cover_folds_the_matching_share_of_the_entry_fee(self):
        """A cover that closes part of a short folds the matching share only."""
        log = split_trade_log(
            _log(
                _trade(action="short", quantity=10.0, pnl=-15.0),
                _trade(action="cover", quantity=4.0, day=2, pnl=100.0),
            )
        )

        assert log.entries["pnl"].tolist() == [-15.0, 94.0]
        assert log.round_trips["pnl"].tolist() == [94.0]

    def test_short_entry_without_a_cover_is_no_trade(self):
        """A short that is still open at the end of the run is no trade."""
        log = split_trade_log(_log(_trade(action="short", pnl=-15.0)))

        assert len(log.entries) == 1
        assert log.round_trips.empty

    def test_cover_without_a_short_closes_nothing_is_not_a_trade(self):
        """A cover that closes no open short is not a round trip, even though
        it booked a PnL; it closes nothing."""
        log = split_trade_log(_log(_trade(action="cover", day=2, pnl=100.0)))

        assert log.entries["pnl"].tolist() == [100.0]
        assert log.round_trips.empty

    def test_sell_without_an_open_entry_closes_nothing_is_not_a_trade(self):
        """A sell that closes no open long entry is not a round trip."""
        log = split_trade_log(_log(_trade(action="sell", day=2, pnl=55.0)))

        assert log.entries["pnl"].tolist() == [55.0]
        assert log.round_trips.empty

    def test_breakeven_long_round_trip_is_counted_as_a_trade(self):
        """A round trip that closes at exactly zero PnL is still a trade: it
        is neither winning nor losing, so it raises num_trades without raising
        num_winning_trades."""
        log = split_trade_log(
            _log(
                _trade(action="buy", pnl=0.0),
                _trade(action="sell", day=2, pnl=0.0),
            )
        )

        assert len(log.entries) == 2
        assert len(log.round_trips) == 1
        assert log.round_trips["pnl"].tolist() == [0.0]

    def test_hold_row_closes_nothing_is_not_a_round_trip(self):
        """A ``hold`` row closes nothing and is not a round trip; it only
        occupies a row in the entries log."""
        log = split_trade_log(
            _log(
                _trade(action="buy", pnl=0.0),
                _trade(action="hold", day=2, pnl=0.0),
                _trade(action="sell", day=3, pnl=100.0),
            )
        )

        assert len(log.entries) == 3
        assert len(log.round_trips) == 1
        assert log.round_trips["pnl"].tolist() == [100.0]

    def test_short_entries_are_paired_per_symbol(self):
        """The queues that pair a short with its cover are kept per symbol."""
        log = split_trade_log(
            _log(
                _trade(symbol="AAPL", action="short", pnl=-10.0),
                _trade(symbol="MSFT", action="short", pnl=-20.0),
                _trade(symbol="MSFT", action="cover", day=2, pnl=50.0),
                _trade(symbol="AAPL", action="cover", day=3, pnl=60.0),
            )
        )

        assert log.entries["pnl"].tolist() == [-10.0, -20.0, 30.0, 50.0]
        assert log.round_trips["pnl"].tolist() == [30.0, 50.0]

    def test_round_trips_are_ordered_by_timestamp(self):
        """The rows are ordered by timestamp before they are paired."""
        log = split_trade_log(
            _log(
                _trade(action="cover", day=3, pnl=60.0),
                _trade(action="short", day=1, pnl=-10.0),
                _trade(action="cover", day=2, pnl=50.0),
            )
        )

        assert log.entries["timestamp"].tolist() == [
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
            datetime(2024, 1, 3),
        ]
        # The day-3 cover closes nothing (the short was already covered by the
        # day-2 cover), so only the day-2 cover is a round trip.
        assert log.round_trips["pnl"].tolist() == [40.0]

    def test_log_without_timestamp_pairs_the_shorts_in_the_given_order(self):
        """A log without a timestamp is read in the order it was given."""
        trades = pd.DataFrame(
            {
                "symbol": ["AAPL", "AAPL"],
                "action": ["short", "cover"],
                "quantity": [10.0, 10.0],
                "pnl": [-15.0, 100.0],
            }
        )

        log = split_trade_log(trades)

        assert log.entries["pnl"].tolist() == [-15.0, 85.0]
        assert log.round_trips["pnl"].tolist() == [85.0]

    def test_the_caller_frame_is_left_untouched(self):
        """Splitting a log must not modify the frame it was given."""
        trades = _log(
            _trade(action="short", pnl=-15.0),
            _trade(action="cover", day=2, pnl=100.0),
        )

        split_trade_log(trades)

        assert trades["pnl"].tolist() == [-15.0, 100.0]


class TestMetricsAndAnalysisAgree:
    """``BacktestMetrics`` and ``TradeAnalysis`` count the same trades."""

    @pytest.mark.parametrize(
        ("name", "trades"),
        [
            (
                "long round trips",
                _log(
                    _trade(action="buy", pnl=0.0),
                    _trade(action="sell", day=2, pnl=100.0),
                    _trade(action="buy", day=3, pnl=0.0),
                    _trade(action="sell", day=4, pnl=-50.0),
                ),
            ),
            (
                "short round trips",
                _log(
                    _trade(action="short", pnl=-15.0),
                    _trade(action="cover", day=2, pnl=100.0),
                    _trade(action="short", day=3, pnl=-15.0),
                    _trade(action="cover", day=4, pnl=-50.0),
                ),
            ),
            (
                "a long and a short round trip",
                _log(
                    _trade(action="buy", pnl=0.0),
                    _trade(action="sell", day=2, pnl=100.0),
                    _trade(action="short", day=3, pnl=-15.0),
                    _trade(action="cover", day=4, pnl=-50.0),
                ),
            ),
        ],
    )
    def test_both_apis_count_the_same_trades(self, name, trades):
        """Both APIs report the same trade count, win count and win rate."""
        result = _result(trades)
        metrics = calculate_backtest_metrics(result.equity_curve, result.trades)
        analysis = analyze_trades(result)

        assert metrics.num_trades == analysis.total_trades, name
        assert metrics.num_winning_trades == analysis.winning_trades, name
        assert metrics.num_losing_trades == analysis.losing_trades, name
        assert metrics.win_rate == pytest.approx(analysis.win_rate), name
        assert metrics.profit_factor == pytest.approx(analysis.profit_factor), name
        assert metrics.largest_win == pytest.approx(analysis.largest_win), name
        assert metrics.largest_loss == pytest.approx(analysis.largest_loss), name

    def test_a_short_round_trip_counts_as_one_trade(self):
        """The short entry is counted with the cover that closes it."""
        trades = _log(
            _trade(action="short", pnl=-15.0),
            _trade(action="cover", day=2, pnl=100.0),
        )

        metrics = calculate_backtest_metrics(_result(trades).equity_curve, trades)
        analysis = analyze_trades(_result(trades))

        assert metrics.num_trades == 1
        assert analysis.total_trades == 1
        assert metrics.num_winning_trades == 1
        assert analysis.winning_trades == 1
        assert metrics.num_losing_trades == 0
        assert analysis.losing_trades == 0
        assert metrics.win_rate == 1.0
        assert analysis.win_rate == 1.0

    def test_the_metrics_of_a_result_match_its_analysis(self):
        """The metrics a backtest ships agree with its trade analysis."""
        trades = _log(
            _trade(action="short", pnl=-15.0),
            _trade(action="cover", day=2, pnl=100.0),
            _trade(action="buy", day=3, pnl=0.0),
            _trade(action="sell", day=4, pnl=-40.0),
        )
        result = _result(trades)
        result.metrics = calculate_backtest_metrics(result.equity_curve, result.trades)
        analysis = analyze_trades(result)

        assert isinstance(result.metrics, BacktestMetrics)
        assert isinstance(analysis, TradeAnalysis)
        assert result.metrics.num_trades == analysis.total_trades
        assert result.metrics.win_rate == pytest.approx(analysis.win_rate)
