"""Tests for trade analysis module."""

from datetime import datetime

import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.metrics import BacktestMetrics
from quant_trading.backtest.trade_analysis import (
    TradeAnalysis,
    analyze_trades,
    print_trade_analysis,
)


def _create_mock_result() -> BacktestResult:
    """Create a mock BacktestResult for testing."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    equity = pd.Series(100000 + np.arange(100) * 100 + np.random.randn(100) * 500, index=dates)

    trades_data = [
        {
            "symbol": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
            "timestamp": datetime(2024, 1, 5),
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1500.0,
            "pnl": 0.0,
        },
        {
            "symbol": "AAPL",
            "action": "sell",
            "quantity": 10,
            "price": 160.0,
            "timestamp": datetime(2024, 1, 15),
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1600.0,
            "pnl": 95.0,
        },
        {
            "symbol": "MSFT",
            "action": "buy",
            "quantity": 5,
            "price": 300.0,
            "timestamp": datetime(2024, 2, 1),
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1500.0,
            "pnl": 0.0,
        },
        {
            "symbol": "MSFT",
            "action": "sell",
            "quantity": 5,
            "price": 290.0,
            "timestamp": datetime(2024, 2, 20),
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1450.0,
            "pnl": -55.0,
        },
        {
            "symbol": "AAPL",
            "action": "buy",
            "quantity": 8,
            "price": 165.0,
            "timestamp": datetime(2024, 3, 1),
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1320.0,
            "pnl": 0.0,
        },
        {
            "symbol": "AAPL",
            "action": "sell",
            "quantity": 8,
            "price": 175.0,
            "timestamp": datetime(2024, 3, 15),
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1400.0,
            "pnl": 72.0,
        },
        {
            "symbol": "GOOGL",
            "action": "buy",
            "quantity": 3,
            "price": 140.0,
            "timestamp": datetime(2024, 4, 1),
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 420.0,
            "pnl": 0.0,
        },
        {
            "symbol": "GOOGL",
            "action": "sell",
            "quantity": 3,
            "price": 150.0,
            "timestamp": datetime(2024, 4, 10),
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 450.0,
            "pnl": 28.0,
        },
    ]
    trades = pd.DataFrame(trades_data)

    metrics = BacktestMetrics(
        total_return=1500.0,
        total_return_pct=1.5,
        annual_return=0.02,
        annual_return_pct=2.0,
        volatility=0.15,
        max_drawdown=0.05,
        max_drawdown_pct=5.0,
        sharpe_ratio=1.2,
        sortino_ratio=1.5,
        calmar_ratio=0.8,
        win_rate=0.75,
        profit_factor=2.5,
        num_trades=4,
        num_winning_trades=3,
        num_losing_trades=1,
        avg_win=65.0,
        avg_loss=-55.0,
        largest_win=95.0,
        largest_loss=-55.0,
        var_95=-2.0,
    )

    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=metrics,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 4, 10),
        initial_capital=100000.0,
        final_value=101500.0,
        total_return=1500.0,
        total_return_pct=1.5,
    )


def test_analyze_trades_basic():
    """Test basic trade analysis."""
    import numpy as np

    np.random.seed(42)
    result = _create_mock_result()
    analysis = analyze_trades(result)

    assert isinstance(analysis, TradeAnalysis)
    assert analysis.total_trades == 4
    assert analysis.winning_trades == 3
    assert analysis.losing_trades == 1
    assert analysis.win_rate == 0.75
    assert analysis.total_pnl == 140.0  # 95 - 55 + 72 + 28


def test_analyze_trades_pnl_stats():
    """Test PnL statistics calculation."""
    import numpy as np

    np.random.seed(42)
    result = _create_mock_result()
    analysis = analyze_trades(result)

    # PnLs: 95, -55, 72, 28
    assert abs(analysis.avg_pnl - 35.0) < 0.01
    assert abs(analysis.median_pnl - 50.0) < 0.01
    assert analysis.largest_win == 95.0
    assert analysis.largest_loss == -55.0
    assert abs(analysis.avg_win - 65.0) < 0.01  # (95 + 72 + 28) / 3
    assert abs(analysis.avg_loss - 55.0) < 0.01  # abs(-55)


def test_analyze_trades_holding_periods():
    """Test holding period calculation."""
    import numpy as np

    np.random.seed(42)
    result = _create_mock_result()
    analysis = analyze_trades(result)

    # Holding periods: 10 days (AAPL), 19 days (MSFT), 14 days (AAPL), 9 days (GOOGL)
    assert abs(analysis.avg_holding_period - 13.0) < 0.1
    assert analysis.min_holding_period == 9.0
    assert analysis.max_holding_period == 19.0


def test_analyze_trades_streaks():
    """Test consecutive streaks calculation."""
    import numpy as np

    np.random.seed(42)
    result = _create_mock_result()
    analysis = analyze_trades(result)

    # Sequence: Win, Loss, Win, Win
    assert analysis.max_consecutive_wins == 2
    assert analysis.max_consecutive_losses == 1
    assert analysis.current_streak == 2
    assert analysis.current_streak_type == "win"


def test_analyze_trades_symbol_stats():
    """Test per-symbol statistics."""
    import numpy as np

    np.random.seed(42)
    result = _create_mock_result()
    analysis = analyze_trades(result)

    assert analysis.symbol_stats is not None
    assert "AAPL" in analysis.symbol_stats
    assert "MSFT" in analysis.symbol_stats
    assert "GOOGL" in analysis.symbol_stats

    # AAPL: 2 trades, 2 wins, PnL = 95 + 72 = 167
    assert analysis.symbol_stats["AAPL"]["total_trades"] == 2
    assert analysis.symbol_stats["AAPL"]["winning_trades"] == 2
    assert analysis.symbol_stats["AAPL"]["total_pnl"] == 167.0

    # MSFT: 1 trade, 1 loss, PnL = -55
    assert analysis.symbol_stats["MSFT"]["total_trades"] == 1
    assert analysis.symbol_stats["MSFT"]["losing_trades"] == 1
    assert analysis.symbol_stats["MSFT"]["total_pnl"] == -55.0


def test_analyze_trades_monthly_returns():
    """Test monthly returns calculation."""
    import numpy as np

    np.random.seed(42)
    result = _create_mock_result()
    analysis = analyze_trades(result)

    assert analysis.monthly_returns is not None
    assert len(analysis.monthly_returns) > 0


def test_analyze_trades_empty():
    """Test analysis with empty trades."""
    import numpy as np

    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity = pd.Series(100000.0, index=dates)
    trades = pd.DataFrame()

    metrics = BacktestMetrics()
    result = BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=metrics,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 10),
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )

    analysis = analyze_trades(result)
    assert analysis.total_trades == 0
    assert analysis.winning_trades == 0
    assert analysis.losing_trades == 0


def test_analyze_trades_only_opening():
    """Test analysis with only opening trades (no PnL)."""
    import numpy as np

    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity = pd.Series(100000.0, index=dates)
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "action": "buy",
                "quantity": 10,
                "price": 150.0,
                "timestamp": datetime(2024, 1, 5),
                "commission": 0.001,
                "slippage": 0.0005,
                "cost": 1500.0,
                "pnl": 0.0,
            }
        ]
    )

    metrics = BacktestMetrics()
    result = BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=metrics,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 10),
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )

    analysis = analyze_trades(result)
    assert analysis.total_trades == 0  # Only opening trades, no closed trades with PnL


def test_trade_analysis_to_dict():
    """Test TradeAnalysis to_dict method."""
    import numpy as np

    np.random.seed(42)
    result = _create_mock_result()
    analysis = analyze_trades(result)

    d = analysis.to_dict()
    assert isinstance(d, dict)
    assert d["total_trades"] == 4
    assert d["win_rate"] == 0.75


def test_print_trade_analysis():
    """Test print_trade_analysis runs without error."""
    import numpy as np

    np.random.seed(42)
    result = _create_mock_result()
    analysis = analyze_trades(result)
    print_trade_analysis(analysis)  # Should not raise


import numpy as np

# Additional tests for coverage


def test_calculate_holding_periods_empty():
    """Test _calculate_holding_periods with empty trades."""
    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_holding_periods

    # Empty trades
    trades = pd.DataFrame()
    result = _calculate_holding_periods(trades)
    assert result == []

    # Trades without pnl column
    trades = pd.DataFrame({"symbol": ["AAPL"], "action": ["buy"]})
    result = _calculate_holding_periods(trades)
    assert result == []


def test_calculate_holding_periods_partial_fill_executes():
    """Ensure partial fill else branch executes (lines 124-125)."""
    from datetime import datetime

    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_holding_periods

    # Buy 10, sell 3: qty_sold < entry_qty triggers else branch
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "action": "buy",
                "quantity": 10.0,
                "timestamp": datetime(2024, 1, 1),
                "pnl": 0.0,
            },
            {
                "symbol": "AAPL",
                "action": "sell",
                "quantity": 3.0,
                "timestamp": datetime(2024, 1, 11),
                "pnl": 5.0,
            },
            {
                "symbol": "AAPL",
                "action": "sell",
                "quantity": 7.0,
                "timestamp": datetime(2024, 1, 21),
                "pnl": 15.0,
            },
        ]
    )
    result = _calculate_holding_periods(trades)
    # Partial sell records a holding period for the 3 units sold on Jan 11
    # (10 days), then the remaining 7 units are sold fully on Jan 21 (20 days).
    assert len(result) == 2
    assert abs(result[0] - 10.0) < 0.001  # Jan 1 -> Jan 11
    assert abs(result[1] - 20.0) < 0.001  # Jan 1 -> Jan 21


def test_calculate_consecutive_streaks_empty():
    """Test _calculate_consecutive_streaks with empty/no-pnl cases."""
    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_consecutive_streaks

    # Empty trades
    trades = pd.DataFrame()
    result = _calculate_consecutive_streaks(trades)
    assert result == (0, 0, 0, "")

    # Trades without pnl column
    trades = pd.DataFrame(
        {"symbol": ["AAPL"], "pnl": [10.0]}
    )  # but we'll remove? no - just structure
    trades_no_pnl = pd.DataFrame({"symbol": ["AAPL"], "action": ["buy"]})
    result = _calculate_consecutive_streaks(trades_no_pnl)
    assert result == (0, 0, 0, "")


def test_calculate_consecutive_streaks_loss_streak():
    """Test _calculate_consecutive_streaks with loss streak branch."""
    from datetime import datetime

    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_consecutive_streaks

    # Consecutive losses to hit the elif current_losses > 0 branch
    trades = pd.DataFrame(
        [
            {"symbol": "AAPL", "pnl": -10.0, "timestamp": datetime(2024, 1, 1)},
            {"symbol": "AAPL", "pnl": -5.0, "timestamp": datetime(2024, 1, 2)},
        ]
    )
    result = _calculate_consecutive_streaks(trades)
    assert result[1] == 2  # max_losses
    assert result[2] == 2  # current_streak
    assert result[3] == "loss"


def test_calculate_monthly_returns_short():
    """Test _calculate_monthly_returns with short series."""
    from datetime import datetime

    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_monthly_returns

    # Less than 2 points
    equity = pd.Series([100000.0], index=[datetime(2024, 1, 1)])
    result = _calculate_monthly_returns(equity)
    assert result == {}

    # 2 points but same month? Or resample gives < 2
    equity = pd.Series([100000.0, 101000.0], index=[datetime(2024, 1, 1), datetime(2024, 1, 31)])
    result = _calculate_monthly_returns(equity)
    # Both in same month - after resample last, len < 2?
    assert isinstance(result, dict)


def test_calculate_weekly_returns_short():
    """Test _calculate_weekly_returns with short series."""
    from datetime import datetime

    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_weekly_returns

    # Less than 2 points
    equity = pd.Series([100000.0], index=[datetime(2024, 1, 1)])
    result = _calculate_weekly_returns(equity)
    assert result == {}

    # 2 points same week
    equity = pd.Series([100000.0, 101000.0], index=[datetime(2024, 1, 1), datetime(2024, 1, 2)])
    result = _calculate_weekly_returns(equity)
    assert isinstance(result, dict)


def test_analyze_trades_single_trade():
    """Test analyze_trades with single completed trade (to hit len<=1 sharpe case)."""
    from datetime import datetime

    import numpy as np
    import pandas as pd

    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import BacktestMetrics
    from quant_trading.backtest.trade_analysis import analyze_trades

    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    equity = pd.Series([100000.0, 100500.0, 100500.0, 100500.0, 100500.0], index=dates)

    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "action": "buy",
                "quantity": 10,
                "price": 150.0,
                "timestamp": datetime(2024, 1, 1),
                "commission": 0.0,
                "slippage": 0.0,
                "cost": 1500.0,
                "pnl": 0.0,
            },
            {
                "symbol": "AAPL",
                "action": "sell",
                "quantity": 10,
                "price": 155.0,
                "timestamp": datetime(2024, 1, 3),
                "commission": 0.0,
                "slippage": 0.0,
                "cost": 1550.0,
                "pnl": 50.0,
            },
        ]
    )

    metrics = BacktestMetrics()
    result = BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=metrics,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 5),
        initial_capital=100000.0,
        final_value=100050.0,
        total_return=50.0,
        total_return_pct=0.05,
    )

    analysis = analyze_trades(result)
    assert analysis.total_trades == 1


def test_calculate_symbol_stats_empty_cases():
    """Test _calculate_symbol_stats edge cases."""
    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_symbol_stats

    # Empty trades
    assert _calculate_symbol_stats(pd.DataFrame()) == {}
    # No pnl column
    assert _calculate_symbol_stats(pd.DataFrame({"symbol": ["AAPL"]})) == {}


def test_calculate_holding_periods_sell_without_entry():
    """A sell with no prior buy leaves entry_times empty, so the
    `elif trade["action"] == "sell" and entry_times` guard is False (110->105)."""
    from datetime import datetime

    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_holding_periods

    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "action": "sell",
                "quantity": 5.0,
                "timestamp": datetime(2024, 1, 11),
                "pnl": 5.0,
            },
        ]
    )
    assert _calculate_holding_periods(trades) == []


def test_calculate_consecutive_streaks_zero_pnl():
    """Trades with pnl == 0 fall through both `if pnl > 0` and `elif pnl < 0`,
    leaving current_wins and current_losses at 0 (148->142 and 156->160)."""
    from datetime import datetime

    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_consecutive_streaks

    trades = pd.DataFrame(
        [
            {"symbol": "AAPL", "pnl": 0.0, "timestamp": datetime(2024, 1, 1)},
            {"symbol": "AAPL", "pnl": 0.0, "timestamp": datetime(2024, 1, 2)},
        ]
    )
    result = _calculate_consecutive_streaks(trades)
    assert result == (0, 0, 0, "")


def test_print_trade_analysis_empty_report():
    """print_trade_analysis with no monthly_returns or symbol_stats exercises the
    `if analysis.monthly_returns` (354->359) and `if analysis.symbol_stats`
    (359->exit) False branches."""
    from quant_trading.backtest.trade_analysis import TradeAnalysis, print_trade_analysis

    print_trade_analysis(TradeAnalysis())  # Should not raise


def test_calculate_consecutive_streaks_with_zeros():
    """Zeros should not break or count as part of streaks."""
    from datetime import datetime

    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_consecutive_streaks

    # Win, zero, win - zeros don't increment, so win streak continues
    trades = pd.DataFrame(
        [
            {"symbol": "AAPL", "pnl": 10.0, "timestamp": datetime(2024, 1, 1)},
            {"symbol": "AAPL", "pnl": 0.0, "timestamp": datetime(2024, 1, 2)},
            {"symbol": "AAPL", "pnl": 5.0, "timestamp": datetime(2024, 1, 3)},
        ]
    )
    result = _calculate_consecutive_streaks(trades)
    assert result == (2, 0, 2, "win")

    # Loss, zero, loss
    trades = pd.DataFrame(
        [
            {"symbol": "AAPL", "pnl": -10.0, "timestamp": datetime(2024, 1, 1)},
            {"symbol": "AAPL", "pnl": 0.0, "timestamp": datetime(2024, 1, 2)},
            {"symbol": "AAPL", "pnl": -5.0, "timestamp": datetime(2024, 1, 3)},
        ]
    )
    result = _calculate_consecutive_streaks(trades)
    assert result == (0, 2, 2, "loss")

    # Win streak followed by zero - current streak remains win
    trades = pd.DataFrame(
        [
            {"symbol": "AAPL", "pnl": 10.0, "timestamp": datetime(2024, 1, 1)},
            {"symbol": "AAPL", "pnl": 5.0, "timestamp": datetime(2024, 1, 2)},
            {"symbol": "AAPL", "pnl": 0.0, "timestamp": datetime(2024, 1, 3)},
        ]
    )
    result = _calculate_consecutive_streaks(trades)
    assert result == (2, 0, 2, "win")


def test_calculate_holding_periods_partial_sell_records_each_leg():
    """Regression: a partial sell must record a holding period for the sold
    portion, not silently drop it (previously only the final full sell was
    recorded, undercounting round-trip holding periods).

    Buy 10 on day 0; sell 3 on day 10 (partial); sell 7 on day 20 (rest).
    Expected holding periods: 10 and 20 days.
    """
    from datetime import datetime

    import pandas as pd

    from quant_trading.backtest.trade_analysis import _calculate_holding_periods

    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "action": "buy",
                "quantity": 10.0,
                "timestamp": datetime(2024, 1, 1),
                "pnl": 0.0,
            },
            {
                "symbol": "AAPL",
                "action": "sell",
                "quantity": 3.0,
                "timestamp": datetime(2024, 1, 11),
                "pnl": 5.0,
            },
            {
                "symbol": "AAPL",
                "action": "sell",
                "quantity": 7.0,
                "timestamp": datetime(2024, 1, 21),
                "pnl": 15.0,
            },
        ]
    )
    result = _calculate_holding_periods(trades)
    assert len(result) == 2
    assert abs(result[0] - 10.0) < 0.001
    assert abs(result[1] - 20.0) < 0.001


def _result_with_trades(pnls, equity_values=None):
    """Build a BacktestResult with one closing trade per PnL.

    The equity curve is indexed by day starting at 2024-01-01, so the n-th
    trade is stamped on the n-th equity point.
    """
    from datetime import datetime, timedelta

    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import BacktestMetrics

    start = datetime(2024, 1, 1)
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "action": "sell",
                "quantity": 10,
                "price": 100.0,
                "timestamp": start + timedelta(days=index),
                "commission": 0.0,
                "slippage": 0.0,
                "cost": 1000.0,
                "pnl": pnl,
            }
            for index, pnl in enumerate(pnls)
        ]
    )

    if equity_values is None:
        equity_values = [10000.0] * len(pnls)
    equity = pd.Series(equity_values, index=pd.date_range(start, periods=len(equity_values)))

    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=BacktestMetrics(),
        start_date=start,
        end_date=start + timedelta(days=max(len(pnls) - 1, 0)),
        initial_capital=10000.0,
        final_value=10000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )


def test_expectancy_is_positive_when_every_trade_wins():
    """Regression: expectancy must not collapse to zero when no trade lost.

    The expectancy is ``win_rate * avg_win - loss_rate * avg_loss``. With no
    losing trades the second term is zero, so the expectancy is the average
    winning trade.
    """
    analysis = analyze_trades(_result_with_trades([50.0, 75.0]))

    assert analysis.losing_trades == 0
    assert analysis.avg_win == pytest.approx(62.5)
    assert analysis.expectancy == pytest.approx(62.5)


def test_expectancy_is_negative_when_every_trade_loses():
    """Every trade losing must give the negative average loss as expectancy."""
    analysis = analyze_trades(_result_with_trades([-50.0, -20.0]))

    assert analysis.winning_trades == 0
    assert analysis.avg_loss == pytest.approx(35.0)
    assert analysis.expectancy == pytest.approx(-35.0)


def test_expectancy_matches_the_weighted_average():
    """The expectancy is the win rate weighted average of wins and losses."""
    analysis = analyze_trades(_result_with_trades([50.0, -20.0]))

    assert analysis.expectancy == pytest.approx(0.5 * 50.0 - 0.5 * 20.0)


def test_trade_sharpe_changes_with_the_risk_free_rate():
    """Regression: the documented risk_free_rate must reach the trade Sharpe."""
    result = _result_with_trades([50.0, -20.0, -30.0, 10.0])

    without_risk_free = analyze_trades(result, risk_free_rate=0.0)
    with_risk_free = analyze_trades(result, risk_free_rate=0.10)

    assert without_risk_free.sharpe_ratio != pytest.approx(with_risk_free.sharpe_ratio)
    assert with_risk_free.sharpe_ratio < without_risk_free.sharpe_ratio


def test_trade_sharpe_uses_the_per_trade_return_series():
    """The trade-level Sharpe is the Sharpe of the per-trade return series."""
    from quant_trading.risk.metrics import calculate_sharpe_ratio

    pnls = [50.0, -20.0, -30.0, 10.0]
    equity_values = [10000.0, 10200.0, 10000.0, 9800.0, 9900.0]
    result = _result_with_trades(pnls, equity_values=equity_values)

    analysis = analyze_trades(result, risk_free_rate=0.02, periods_per_year=252)

    expected_returns = pd.Series([pnl / equity for pnl, equity in zip(pnls, equity_values)])
    expected = calculate_sharpe_ratio(expected_returns, 0.02, periods_per_year=252)
    assert analysis.sharpe_ratio == pytest.approx(expected)


def test_trade_sortino_uses_the_per_trade_return_series():
    """The trade-level Sortino is the Sortino of the per-trade return series."""
    from quant_trading.risk.metrics import calculate_sortino_ratio

    pnls = [50.0, -20.0, -30.0, 10.0]
    equity_values = [10000.0, 10200.0, 10000.0, 9800.0, 9900.0]
    result = _result_with_trades(pnls, equity_values=equity_values)

    analysis = analyze_trades(result, risk_free_rate=0.02, periods_per_year=252)

    expected_returns = pd.Series([pnl / equity for pnl, equity in zip(pnls, equity_values)])
    expected = calculate_sortino_ratio(expected_returns, 0.02, periods_per_year=252)
    assert analysis.sortino_ratio == pytest.approx(expected)


def test_trade_risk_metrics_are_zero_without_a_usable_equity_curve():
    """An unusable equity curve yields zero risk metrics instead of raising."""
    result = _result_with_trades([50.0, -20.0, -30.0])
    result.equity_curve = pd.Series(dtype=float)

    analysis = analyze_trades(result)

    assert analysis.sharpe_ratio == 0.0
    assert analysis.sortino_ratio == 0.0


def test_trade_risk_metrics_survive_an_equity_curve_without_dates():
    """An equity curve that is not indexed by time yields zero risk metrics."""
    result = _result_with_trades([50.0, -20.0, -30.0])
    result.equity_curve = pd.Series([10000.0, 10000.0, 10000.0], index=[0, 1, 2])

    analysis = analyze_trades(result)

    assert analysis.sharpe_ratio == 0.0
    assert analysis.sortino_ratio == 0.0


def test_calculate_consecutive_streaks_uses_chronological_order():
    """Regression: streaks are temporal, so trades are ordered by timestamp."""
    from datetime import datetime

    from quant_trading.backtest.trade_analysis import _calculate_consecutive_streaks

    trades = pd.DataFrame(
        [
            {"symbol": "AAPL", "pnl": -10.0, "timestamp": datetime(2024, 1, 3)},
            {"symbol": "AAPL", "pnl": 10.0, "timestamp": datetime(2024, 1, 1)},
            {"symbol": "AAPL", "pnl": 10.0, "timestamp": datetime(2024, 1, 2)},
        ]
    )

    max_wins, max_losses, current_streak, current_type = _calculate_consecutive_streaks(trades)

    assert max_wins == 2
    assert max_losses == 1
    assert current_streak == 1
    assert current_type == "loss"


def test_analyze_trades_reports_the_chronological_current_streak():
    """The reported current streak follows the order the trades happened in."""
    from datetime import datetime, timedelta

    start = datetime(2024, 1, 1)
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "action": "sell",
                "quantity": 10,
                "price": 100.0,
                "timestamp": start + timedelta(days=offset),
                "commission": 0.0,
                "slippage": 0.0,
                "cost": 1000.0,
                "pnl": pnl,
            }
            for offset, pnl in ((2, -10.0), (0, 10.0), (1, 10.0))
        ]
    )
    equity = pd.Series([10000.0, 10000.0, 10000.0], index=pd.date_range(start, periods=3))
    result = BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=BacktestMetrics(),
        start_date=start,
        end_date=start + timedelta(days=2),
        initial_capital=10000.0,
        final_value=10000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )

    analysis = analyze_trades(result)

    assert analysis.max_consecutive_wins == 2
    assert analysis.max_consecutive_losses == 1
    assert analysis.current_streak == 1
    assert analysis.current_streak_type == "loss"


def _short_result(trades_rows):
    """Build a BacktestResult whose trades are the given short/cover rows."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import BacktestMetrics

    trades = pd.DataFrame(trades_rows)
    first = trades["timestamp"].min()
    last = trades["timestamp"].max()
    equity = pd.Series(100000.0, index=pd.date_range(first, last, freq="D"))

    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=BacktestMetrics(),
        start_date=first,
        end_date=last,
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )


def _trade(symbol, action, quantity, price, timestamp, pnl):
    return {
        "symbol": symbol,
        "action": action,
        "quantity": quantity,
        "price": price,
        "timestamp": timestamp,
        "commission": 0.0,
        "slippage": 0.0,
        "cost": 0.0,
        "pnl": pnl,
    }


def test_short_round_trip_that_wins_counts_as_one_trade():
    """A short entered below the exit price is a winner: one trade, one holding
    period, and the entry fee is folded into the cover rather than counted as a
    separate losing trade."""
    from datetime import datetime

    result = _short_result(
        [
            _trade("TEST", "short", 200.0, 50.0, datetime(2024, 1, 1), 0.0),
            _trade("TEST", "cover", 200.0, 40.0, datetime(2024, 1, 3), 2000.0),
        ]
    )
    analysis = analyze_trades(result)

    assert analysis.total_trades == 1
    assert analysis.winning_trades == 1
    assert analysis.losing_trades == 0
    assert analysis.win_rate == 1.0
    assert analysis.total_pnl == 2000.0
    assert analysis.avg_holding_period == 2.0
    assert analysis.min_holding_period == 2.0
    assert analysis.max_holding_period == 2.0


def test_short_round_trip_that_loses_counts_as_one_trade():
    """A short exited above the entry price is a loser: one trade, one holding
    period."""
    from datetime import datetime

    result = _short_result(
        [
            _trade("TEST", "short", 200.0, 40.0, datetime(2024, 1, 1), 0.0),
            _trade("TEST", "cover", 200.0, 50.0, datetime(2024, 1, 3), -2000.0),
        ]
    )
    analysis = analyze_trades(result)

    assert analysis.total_trades == 1
    assert analysis.winning_trades == 0
    assert analysis.losing_trades == 1
    assert analysis.win_rate == 0.0
    assert analysis.total_pnl == -2000.0
    assert analysis.avg_holding_period == 2.0


def test_partially_covered_short_records_one_holding_period_per_cover():
    """Several covers against one short: each cover is its own trade (mirrors
    the long side selling in parts) and each cover records its own holding
    period against the FIFO short entry."""
    from datetime import datetime

    result = _short_result(
        [
            _trade("TEST", "short", 100.0, 50.0, datetime(2024, 1, 1), 0.0),
            _trade("TEST", "cover", 40.0, 40.0, datetime(2024, 1, 11), 400.0),
            _trade("TEST", "cover", 60.0, 40.0, datetime(2024, 1, 21), 600.0),
        ]
    )
    analysis = analyze_trades(result)

    assert analysis.total_trades == 2
    assert analysis.winning_trades == 2
    assert analysis.losing_trades == 0
    assert analysis.win_rate == 1.0
    assert analysis.total_pnl == 1000.0
    assert abs(analysis.avg_holding_period - 15.0) < 0.001
    assert analysis.min_holding_period == 10.0
    assert analysis.max_holding_period == 20.0
    stats = analysis.symbol_stats["TEST"]
    assert stats["total_trades"] == 2
    assert stats["winning_trades"] == 2


def test_short_never_covered_is_not_counted():
    """A short with no cover is not a round trip: it contributes no trade even
    though its entry booked a (fee) PnL."""
    from datetime import datetime

    result = _short_result([_trade("TEST", "short", 100.0, 50.0, datetime(2024, 1, 1), -5.0)])
    analysis = analyze_trades(result)

    assert analysis.total_trades == 0
    assert analysis.winning_trades == 0
    assert analysis.losing_trades == 0
    assert analysis.total_pnl == 0.0


def test_short_entry_fee_is_folded_into_the_cover():
    """The short's entry fee belongs to the cover that closes it.

    The entry fee is booked on the short row, but the short row is dropped
    because it is not a round trip on its own. The fee therefore has to be
    added to the cover, otherwise it is lost from the trade statistics.
    """
    from datetime import datetime

    result = _short_result(
        [
            _trade("TEST", "short", 100.0, 50.0, datetime(2024, 1, 1), -5.0),
            _trade("TEST", "cover", 100.0, 40.0, datetime(2024, 1, 3), 1000.0),
        ]
    )

    analysis = analyze_trades(result)

    assert analysis.total_trades == 1
    assert analysis.winning_trades == 1
    assert analysis.losing_trades == 0
    assert analysis.total_pnl == 995.0
    assert analysis.avg_holding_period == 2.0


def test_calculate_consecutive_streaks_without_a_timestamp_column():
    """Trades that carry no timestamp are counted in the order they are given.

    There is no chronology to sort by, so the given order is the order the
    trades happened in.
    """
    from quant_trading.backtest.trade_analysis import _calculate_consecutive_streaks

    trades = pd.DataFrame(
        [
            {"symbol": "AAPL", "pnl": 10.0},
            {"symbol": "AAPL", "pnl": 20.0},
            {"symbol": "AAPL", "pnl": -5.0},
        ]
    )

    max_wins, max_losses, current_streak, current_type = _calculate_consecutive_streaks(trades)

    assert max_wins == 2
    assert max_losses == 1
    assert current_streak == 1
    assert current_type == "loss"


def test_equity_at_trade_times_returns_nan_for_an_unusable_timestamp():
    """A trade timestamp that cannot be matched to the equity curve yields NaN.

    The lookup must not raise when a trade carries a timestamp the equity
    curve cannot be searched with; the trade simply has no known equity.
    """
    from quant_trading.backtest.trade_analysis import _equity_at_trade_times

    equity = pd.Series([100.0, 200.0], index=pd.date_range("2024-01-01", periods=2))
    timestamps = pd.Series([pd.Timestamp("2024-01-01"), "not-a-timestamp"])

    resolved = _equity_at_trade_times(equity, timestamps)

    assert resolved.iloc[0] == 100.0
    assert pd.isna(resolved.iloc[1])


def test_calculate_trade_returns_without_a_timestamp_column():
    """Trades without a timestamp cannot be turned into per-trade returns."""
    from quant_trading.backtest.trade_analysis import _calculate_trade_returns

    trades = pd.DataFrame([{"symbol": "AAPL", "pnl": 10.0}])
    equity = pd.Series([100.0, 200.0], index=pd.date_range("2024-01-01", periods=2))

    returns = _calculate_trade_returns(trades, equity)

    assert len(returns) == 1
    assert returns.isna().all()


def test_analyze_trades_without_an_action_column():
    """A trades frame without an action column is analysed instead of raising.

    Without an action column there are no entries and exits to pair, so there
    are no round trips and no holding periods, but the trades are still
    counted.
    """
    from datetime import datetime, timedelta

    start = datetime(2024, 1, 1)
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "quantity": 10,
                "price": 100.0,
                "timestamp": start,
                "pnl": 25.0,
            },
            {
                "symbol": "AAPL",
                "quantity": 10,
                "price": 110.0,
                "timestamp": start + timedelta(days=5),
                "pnl": -10.0,
            },
        ]
    )
    equity = pd.Series([10000.0, 10000.0], index=pd.date_range(start, periods=2))
    result = BacktestResult(
        equity_curve=equity,
        trades=trades,
        positions={},
        metrics=BacktestMetrics(),
        start_date=start,
        end_date=start + timedelta(days=1),
        initial_capital=10000.0,
        final_value=10000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )

    analysis = analyze_trades(result)

    assert analysis.total_trades == 2
    assert analysis.winning_trades == 1
    assert analysis.losing_trades == 1
    assert analysis.total_pnl == 15.0
    assert analysis.avg_holding_period == 0.0
    assert analysis.max_holding_period == 0.0
