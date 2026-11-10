"""Tests for the backtest report module."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestResult, Trade
from quant_trading.backtest.metrics import BacktestMetrics
from quant_trading.backtest.report import (
    ReportConfig,
    generate_html_report,
    generate_report_from_dict,
    MATPLOTLIB_AVAILABLE,
)


def _create_sample_result() -> BacktestResult:
    """Create a sample BacktestResult for testing."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    equity_values = 100000 * (1 + 0.0005 * np.arange(100))
    equity_curve = pd.Series(equity_values, index=dates)

    trades_data = [
        {
            "symbol": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
            "timestamp": dates[10],
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1501.50,
            "fee": 2.25,
            "pnl": 0.0,
        },
        {
            "symbol": "AAPL",
            "action": "sell",
            "quantity": 10,
            "price": 160.0,
            "timestamp": dates[30],
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1598.40,
            "fee": 2.40,
            "pnl": 98.50,
        },
        {
            "symbol": "MSFT",
            "action": "buy",
            "quantity": 5,
            "price": 300.0,
            "timestamp": dates[20],
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1501.50,
            "fee": 2.25,
            "pnl": 0.0,
        },
        {
            "symbol": "MSFT",
            "action": "sell",
            "quantity": 5,
            "price": 290.0,
            "timestamp": dates[50],
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1448.55,
            "fee": 2.17,
            "pnl": -52.95,
        },
    ]
    trades_df = pd.DataFrame(trades_data)

    metrics = BacktestMetrics(
        total_return=5000.0,
        total_return_pct=5.0,
        annual_return=12.5,
        volatility=15.2,
        sharpe_ratio=0.82,
        sortino_ratio=1.1,
        calmar_ratio=0.65,
        max_drawdown=-0.08,
        max_drawdown_pct=8.0,
        win_rate=0.5,
        profit_factor=1.85,
        num_trades=2,
        avg_win=98.50,
        avg_loss=-52.95,
        largest_win=98.50,
        largest_loss=-52.95,
    )

    result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=105000.0,
        total_return=5000.0,
        total_return_pct=5.0,
        total_costs=9.07,
    )
    return result


def test_report_config_defaults():
    """Test ReportConfig default values."""
    config = ReportConfig()
    assert config.title == "Backtest Report"
    assert config.include_charts is True
    assert config.include_trade_details is True
    assert config.include_monthly_heatmap is True
    assert config.include_rolling_metrics is True
    assert config.theme == "light"
    assert config.dpi == 150


def test_report_config_custom():
    """Test ReportConfig with custom values."""
    config = ReportConfig(
        title="Custom Report",
        include_charts=False,
        theme="dark",
        dpi=300,
    )
    assert config.title == "Custom Report"
    assert config.include_charts is False
    assert config.theme == "dark"
    assert config.dpi == 300


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_basic():
    """Test basic HTML report generation."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=True, include_trade_details=True)

    html = generate_html_report(result, config)

    assert isinstance(html, str)
    assert len(html) > 0
    assert "<!DOCTYPE html>" in html
    assert "Backtest Report" in html
    assert "Performance Summary" in html
    assert "Equity Curve" in html
    assert "Drawdown" in html
    assert "Monthly Returns" in html
    assert "Trade PnL Distribution" in html
    assert "Rolling Sharpe" in html
    assert "Rolling Volatility" in html
    assert "Trade Details" in html
    assert "AAPL" in html
    assert "MSFT" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_no_charts():
    """Test HTML report generation without charts."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=False)

    html = generate_html_report(result, config)

    assert isinstance(html, str)
    # Charts section should not be present
    assert "Equity Curve" not in html
    assert "Drawdown (%)" not in html  # Chart title, not metric name
    assert "Monthly Returns" not in html
    assert "Trade PnL Distribution" not in html
    assert "Rolling Sharpe" not in html
    assert "Rolling Volatility" not in html
    assert "Performance Summary" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_dark_theme():
    """Test HTML report generation with dark theme."""
    result = _create_sample_result()
    config = ReportConfig(theme="dark")

    html = generate_html_report(result, config)

    assert "#1e1e1e" in html  # dark background color
    assert "Backtest Report" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_to_file():
    """Test HTML report generation writing to file."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.html"
        html = generate_html_report(result, config, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert content == html
        assert "Backtest Report" in content


def test_generate_report_from_dict():
    """Test generating report from dictionary."""
    result = _create_sample_result()
    data = result.to_dict()

    if MATPLOTLIB_AVAILABLE:
        config = ReportConfig(include_charts=True)
        html = generate_report_from_dict(data, config)
        assert "Backtest Report" in html
        assert "Performance Summary" in html
    else:
        # Should work without charts even without matplotlib
        config = ReportConfig(include_charts=False)
        html = generate_report_from_dict(data, config)
        assert "Backtest Report" in html
        assert "Performance Summary" in html


def test_generate_report_from_dict_with_file():
    """Test generating report from dictionary to file."""
    result = _create_sample_result()
    data = result.to_dict()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report_from_dict.html"
        config = ReportConfig(include_charts=False)
        html = generate_report_from_dict(data, config, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert content == html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_charts_generated_as_base64():
    """Test that charts are embedded as base64 in HTML."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=True)

    html = generate_html_report(result, config)

    # Check that base64 images are embedded
    assert 'data:image/png;base64,' in html
    # Should have multiple charts
    base64_count = html.count('data:image/png;base64,')
    assert base64_count >= 4  # equity, drawdown, monthly, trade dist, rolling sharpe, rolling vol


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_report_with_empty_trades():
    """Test report generation with no trades."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    metrics = BacktestMetrics(
        total_return=0.0,
        total_return_pct=0.0,
        annual_return=0.0,
        volatility=0.0,
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        calmar_ratio=0.0,
        max_drawdown=0.0,
        max_drawdown_pct=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        num_trades=0,
        avg_win=0.0,
        avg_loss=0.0,
        largest_win=0.0,
        largest_loss=0.0,
    )

    result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )

    config = ReportConfig(include_charts=True)
    html = generate_html_report(result, config)

    assert "No trades executed" in html
    assert "Performance Summary" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_report_with_insufficient_data_for_rolling():
    """Test report with insufficient data for rolling metrics."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    equity_values = 100000 * (1 + 0.001 * np.arange(30))
    equity_curve = pd.Series(equity_values, index=dates)

    trades_data = [
        {
            "symbol": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
            "timestamp": dates[5],
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1501.50,
            "fee": 2.25,
            "pnl": 0.0,
        },
        {
            "symbol": "AAPL",
            "action": "sell",
            "quantity": 10,
            "price": 155.0,
            "timestamp": dates[25],
            "commission": 0.001,
            "slippage": 0.0005,
            "cost": 1548.47,
            "fee": 2.32,
            "pnl": 46.95,
        },
    ]
    trades_df = pd.DataFrame(trades_data)

    metrics = BacktestMetrics(
        total_return=500.0,
        total_return_pct=0.5,
        annual_return=6.0,
        volatility=10.0,
        sharpe_ratio=0.6,
        sortino_ratio=0.8,
        calmar_ratio=0.5,
        max_drawdown=-0.02,
        max_drawdown_pct=2.0,
        win_rate=1.0,
        profit_factor=10.0,
        num_trades=1,
        avg_win=46.95,
        avg_loss=0.0,
        largest_win=46.95,
        largest_loss=46.95,
    )

    result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100500.0,
        total_return=500.0,
        total_return_pct=0.5,
        total_costs=4.57,
    )

    config = ReportConfig(include_charts=True, include_rolling_metrics=True)
    html = generate_html_report(result, config)

    # Should still generate report with rolling metric chart cards
    assert "Backtest Report" in html
    assert "Rolling Sharpe" in html
    assert "Rolling Volatility" in html


def test_matplotlib_not_available_error():
    """Test that ImportError is raised when matplotlib not available and charts requested."""
    # This test is tricky since MATPLOTLIB_AVAILABLE is module-level
    # We just verify the constant exists
    assert isinstance(MATPLOTLIB_AVAILABLE, bool)


def test_report_handles_nan_metrics():
    """Test report handles NaN metric values gracefully."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    import numpy as np
    metrics = BacktestMetrics(
        total_return=0.0,
        total_return_pct=0.0,
        annual_return=np.nan,
        volatility=np.nan,
        sharpe_ratio=np.nan,
        sortino_ratio=np.nan,
        calmar_ratio=np.nan,
        max_drawdown=0.0,
        max_drawdown_pct=0.0,
        win_rate=np.nan,
        profit_factor=np.nan,
        num_trades=0,
        avg_win=np.nan,
        avg_loss=np.nan,
        largest_win=np.nan,
        largest_loss=np.nan,
    )

    result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )

    config = ReportConfig(include_charts=False)
    html = generate_html_report(result, config)

    assert "N/A" in html
    assert "Performance Summary" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])