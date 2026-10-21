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

        # The entries keep the PnL the log booked.
        assert log.entries["pnl"].tolist() == [-15.0, 100.0]
        # The cover carries the PnL of the whole round trip.
        assert log.round_trips["pnl"].tolist() == [85.0]
        # The short entry is no trade of its own.
        assert len(log.round_trips) == 1
        # Nothing is left open, so no PnL belongs to an open position.
        assert log.open_pnl == 0.0

    def test_partial_cover_folds_the_matching_share_of_the_entry_fee(self):
        """A cover that closes part of a short folds the matching share only."""
        log = split_trade_log(
            _log(
                _trade(action="short", quantity=10.0, pnl=-15.0),
                _trade(action="cover", quantity=4.0, day=2, pnl=100.0),
            )
        )

        assert log.entries["pnl"].tolist() == [-15.0, 100.0]
        assert log.round_trips["pnl"].tolist() == [94.0]
        # The fee of the share that was never covered belongs to the position
        # that is still open: 6 of the 10 shares, so 6/10 of the fee.
        assert log.open_pnl == pytest.approx(-9.0)

    def test_the_entries_are_the_log_the_run_booked(self):
        """The entries keep the PnL of the log, so the fee is not counted twice.

        The fee of a short entry is folded into the round trips only. The
        entries stay the raw log, so their sum is the PnL the run booked.
        """
        trades = _log(
            _trade(action="short", pnl=-15.0),
            _trade(action="cover", day=2, pnl=100.0),
            _trade(action="buy", day=3, pnl=0.0),
            _trade(action="sell", day=4, pnl=55.0),
        )

        log = split_trade_log(trades)

        assert float(log.entries["pnl"].sum()) == pytest.approx(float(trades["pnl"].sum()))
        assert float(log.entries["pnl"].sum()) == pytest.approx(140.0)
        # The round trips and the open positions add up to the same PnL.
        assert float(log.round_trips["pnl"].sum()) + log.open_pnl == pytest.approx(140.0)

    def test_an_open_short_reports_its_fee_as_open_pnl(self):
        """A short that is never covered booked a fee that is not a trade.

        The fee is the PnL of a position that is still open at the end of the
        run, so it is reported apart from the round trips.
        """
        log = split_trade_log(_log(_trade(action="short", pnl=-15.0)))

        assert log.open_pnl == pytest.approx(-15.0)
        assert log.round_trips.empty

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

        assert log.entries["pnl"].tolist() == [-10.0, -20.0, 50.0, 60.0]
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

        assert log.entries["pnl"].tolist() == [-15.0, 100.0]
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
        assert metrics.avg_win == pytest.approx(analysis.avg_win), name
        assert metrics.avg_loss == pytest.approx(analysis.avg_loss), name

    def test_the_loss_figures_are_signed_everywhere(self):
        """A loss is a negative PnL in every place the loss is reported.

        The top level figures, the per symbol figures and the metrics of the
        other public API all report the same signed value, so a report never
        shows an average loss with one sign and a largest loss with the
        other.
        """
        trades = _log(
            _trade(action="buy", pnl=0.0),
            _trade(action="sell", day=2, pnl=100.0),
            _trade(action="buy", day=3, pnl=0.0),
            _trade(action="sell", day=4, pnl=-50.0),
        )
        result = _result(trades)

        metrics = calculate_backtest_metrics(result.equity_curve, result.trades)
        analysis = analyze_trades(result)

        assert analysis.avg_loss == pytest.approx(-50.0)
        assert analysis.largest_loss == pytest.approx(-50.0)
        assert analysis.symbol_stats["AAPL"]["avg_loss"] == pytest.approx(-50.0)
        assert analysis.symbol_stats["AAPL"]["largest_loss"] == pytest.approx(-50.0)
        assert metrics.avg_loss == pytest.approx(-50.0)
        assert metrics.largest_loss == pytest.approx(-50.0)

    def test_the_per_symbol_figures_agree_with_the_top_level_figures(self):
        """A run that trades one symbol reports the same numbers twice."""
        trades = _log(
            _trade(action="buy", pnl=0.0),
            _trade(action="sell", day=2, pnl=100.0),
            _trade(action="buy", day=3, pnl=0.0),
            _trade(action="sell", day=4, pnl=-50.0),
        )

        analysis = analyze_trades(_result(trades))
        stats = analysis.symbol_stats["AAPL"]

        assert stats["total_trades"] == analysis.total_trades
        assert stats["winning_trades"] == analysis.winning_trades
        assert stats["losing_trades"] == analysis.losing_trades
        assert stats["win_rate"] == pytest.approx(analysis.win_rate)
        assert stats["total_pnl"] == pytest.approx(analysis.total_pnl)
        assert stats["avg_pnl"] == pytest.approx(analysis.avg_pnl)
        assert stats["avg_win"] == pytest.approx(analysis.avg_win)
        assert stats["avg_loss"] == pytest.approx(analysis.avg_loss)
        assert stats["largest_win"] == pytest.approx(analysis.largest_win)
        assert stats["largest_loss"] == pytest.approx(analysis.largest_loss)

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


class TestAnalysisReconcilesWithTheRun:
    """The analysis reports the PnL the run actually booked."""

    @pytest.mark.parametrize(
        ("name", "trades"),
        [
            (
                "a long round trip",
                _log(
                    _trade(action="buy", pnl=0.0),
                    _trade(action="sell", day=2, pnl=100.0),
                ),
            ),
            (
                "a short round trip",
                _log(
                    _trade(action="short", pnl=-15.0),
                    _trade(action="cover", day=2, pnl=100.0),
                ),
            ),
            (
                "a short that is still open",
                _log(_trade(action="short", pnl=-15.0)),
            ),
            (
                "a short that is covered in part",
                _log(
                    _trade(action="short", quantity=10.0, pnl=-15.0),
                    _trade(action="cover", quantity=4.0, day=2, pnl=100.0),
                ),
            ),
            (
                "a long and a short, one of them open",
                _log(
                    _trade(action="buy", pnl=0.0),
                    _trade(action="sell", day=2, pnl=100.0),
                    _trade(symbol="MSFT", action="short", day=3, pnl=-15.0),
                ),
            ),
        ],
    )
    def test_the_total_pnl_is_the_pnl_the_log_booked(self, name, trades):
        """The total PnL is the sum of the PnL of the trade log.

        The engine books the fee of a short on the short row itself, so a run
        that ends with an open short booked a PnL that the round trips alone
        do not carry. The analysis has to report the PnL of the run.
        """
        result = _result(trades)

        analysis = analyze_trades(result)

        assert analysis.total_pnl == pytest.approx(float(result.trades["pnl"].sum())), name

    @pytest.mark.parametrize(
        ("name", "trades"),
        [
            (
                "a long and a short round trip",
                _log(
                    _trade(symbol="AAPL", action="buy", pnl=0.0),
                    _trade(symbol="AAPL", action="sell", day=2, pnl=100.0),
                    _trade(symbol="MSFT", action="short", day=3, pnl=-15.0),
                    _trade(symbol="MSFT", action="cover", day=4, pnl=-50.0),
                ),
            ),
            (
                "a short that is still open",
                _log(
                    _trade(symbol="AAPL", action="short", pnl=-15.0),
                    _trade(symbol="MSFT", action="buy", day=2, pnl=0.0),
                    _trade(symbol="MSFT", action="sell", day=3, pnl=20.0),
                ),
            ),
        ],
    )
    def test_the_per_symbol_pnl_adds_up_to_the_total_pnl(self, name, trades):
        """The PnL of the symbols adds up to the PnL of the run."""
        analysis = analyze_trades(_result(trades))

        symbol_total = sum(stats["total_pnl"] for stats in analysis.symbol_stats.values())
        assert symbol_total == pytest.approx(analysis.total_pnl), name

    def test_the_open_position_pnl_is_reported_apart(self):
        """The PnL of the open positions is visible, not hidden.

        The PnL of the run is the PnL of the round trips plus the PnL of the
        positions that are still open, and the two are reported apart.
        """
        trades = _log(
            _trade(action="short", pnl=-15.0),
            _trade(action="cover", day=2, pnl=100.0),
            _trade(action="short", day=3, pnl=-20.0),
        )

        analysis = analyze_trades(_result(trades))

        assert analysis.open_position_pnl == pytest.approx(-20.0)
        assert analysis.total_pnl == pytest.approx(65.0)
        assert analysis.to_dict()["open_position_pnl"] == pytest.approx(-20.0)

    def test_a_liquidated_run_reports_the_pnl_of_its_round_trips(self):
        """A run that closed every position reports the PnL it made.

        The PnL of a fully liquidated run is the PnL of its round trips, so
        the reconciliation does not change the figure such a run reports.
        """
        trades = _log(
            _trade(action="short", pnl=-15.0),
            _trade(action="cover", day=2, pnl=100.0),
            _trade(action="buy", day=3, pnl=0.0),
            _trade(action="sell", day=4, pnl=-40.0),
        )

        analysis = analyze_trades(_result(trades))

        assert analysis.open_position_pnl == 0.0
        assert analysis.total_pnl == pytest.approx(45.0)
        assert analysis.total_pnl == pytest.approx(
            float(analysis.symbol_stats["AAPL"]["total_pnl"])
        )
