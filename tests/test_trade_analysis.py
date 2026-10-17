"""Tests for trade analysis module."""

from datetime import datetime

import pandas as pd

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
