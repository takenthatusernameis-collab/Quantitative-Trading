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
    trades = pd.DataFrame([
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
    ])

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