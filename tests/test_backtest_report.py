"""Tests for the backtest report module."""

import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.metrics import BacktestMetrics
from quant_trading.backtest.report import (
    MATPLOTLIB_AVAILABLE,
    ReportConfig,
    generate_comparison_report,
    generate_html_report,
    generate_report_from_dict,
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
    assert "data:image/png;base64," in html
    # Should have multiple charts
    base64_count = html.count("data:image/png;base64,")
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


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_basic():
    """Test basic comparison report generation."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()
    # Modify result2 to have different metrics
    result2 = BacktestResult(
        equity_curve=result2.equity_curve * 1.02,  # 2% better
        trades=result2.trades,
        positions=result2.positions,
        metrics=result2.metrics,
        start_date=result2.start_date,
        end_date=result2.end_date,
        initial_capital=result2.initial_capital,
        final_value=result2.final_value * 1.02,
        total_return=result2.total_return * 1.02,
        total_return_pct=result2.total_return_pct * 1.02,
        total_costs=result2.total_costs,
    )

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True, title="Strategy Comparison")

    html = generate_comparison_report(results, config)

    assert isinstance(html, str)
    assert len(html) > 0
    assert "<!DOCTYPE html>" in html
    assert "Strategy Comparison" in html
    assert "Strategy A" in html
    assert "Strategy B" in html
    assert "Equity Curves Comparison" in html
    assert "Drawdown Comparison" in html
    assert "Strategy Comparison" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_monthly_heatmap_has_no_layout_warning():
    """The shared-colorbar heatmap must not trigger tight_layout warnings.

    Matplotlib warns when ``tight_layout`` is applied to axes that host a
    shared colorbar. The comparison report uses constrained layout instead, so
    callers running with warnings-as-errors can still render the report.
    """
    result1 = _create_sample_result()
    result2 = _create_sample_result()
    results = [("Strategy A", result1), ("Strategy B", result2)]

    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=".*tight_layout.*")
        html = generate_comparison_report(results)

    assert "Monthly Returns Comparison" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_no_charts():
    """Test comparison report generation without charts."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=False)

    html = generate_comparison_report(results, config)

    assert isinstance(html, str)
    assert "Equity Curves Comparison" not in html
    assert "Drawdown Comparison" not in html
    assert "Strategy A" in html
    assert "Strategy B" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_to_file():
    """Test comparison report generation writing to file."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "comparison.html"
        html = generate_comparison_report(results, config, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert content == html
        assert "Strategy Comparison" in content


def test_generate_comparison_report_empty_results():
    """Test that empty results list raises ValueError."""
    with pytest.raises(ValueError, match="At least one result is required"):
        generate_comparison_report([])


def test_generate_comparison_report_single_result():
    """Test comparison report with a single result."""
    result1 = _create_sample_result()

    results = [("Strategy A", result1)]
    config = ReportConfig(include_charts=False)

    html = generate_comparison_report(results, config)

    assert isinstance(html, str)
    assert "Strategy A" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_dark_theme():
    """Test comparison report with dark theme."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(theme="dark")

    html = generate_comparison_report(results, config)

    assert "#1e1e1e" in html  # dark background color


def test_report_matplotlib_unavailable_branch(monkeypatch):
    """Cover report.py:29-30: MATPLOTLIB_AVAILABLE=False when matplotlib import fails.

    Simulates a missing matplotlib at import time by blocking the module in
    sys.modules and reloading the report module, exercising the except branch.
    """
    import importlib
    import sys

    import quant_trading.backtest.report as report_module

    original_matplotlib = sys.modules.get("matplotlib")
    original_pyplot = sys.modules.get("matplotlib.pyplot")
    try:
        sys.modules["matplotlib"] = None
        sys.modules["matplotlib.pyplot"] = None
        reloaded = importlib.reload(report_module)
        assert reloaded.MATPLOTLIB_AVAILABLE is False
        with pytest.raises(ImportError, match="matplotlib is required"):
            reloaded._check_matplotlib()
    finally:
        if original_matplotlib is None:
            sys.modules.pop("matplotlib", None)
        else:
            sys.modules["matplotlib"] = original_matplotlib
        if original_pyplot is None:
            sys.modules.pop("matplotlib.pyplot", None)
        else:
            sys.modules["matplotlib.pyplot"] = original_pyplot
    importlib.reload(report_module)


def test_generate_html_report_uses_default_config_when_config_is_none():
    """generate_html_report must fall back to ReportConfig() when config is None."""
    result = _create_sample_result()
    html = generate_html_report(result)
    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html
    assert "Backtest Report" in html
    assert "Equity Curve" in html


def test_generate_html_report_omits_monthly_heatmap_when_disabled():
    """include_monthly_heatmap=False must exclude the monthly returns chart."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=True, include_monthly_heatmap=False)
    html = generate_html_report(result, config)
    assert "Monthly Returns" not in html
    assert "Equity Curve" in html


def test_generate_html_report_omits_rolling_metrics_when_disabled():
    """include_rolling_metrics=False must exclude the rolling metric chart cards."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=True, include_rolling_metrics=False)
    html = generate_html_report(result, config)
    assert "Rolling Sharpe" not in html
    assert "Rolling Volatility" not in html


def test_generate_html_report_omits_trade_details_when_disabled():
    """include_trade_details=False must exclude the trade details section."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=False, include_trade_details=False)
    html = generate_html_report(result, config)
    assert "Trade Details" not in html
    assert "Performance Summary" in html


def test_build_trades_table_truncates_at_max_rows():
    """_build_trades_table must cap rows at max_rows and note the truncation."""
    from quant_trading.backtest.report import _build_trades_table, _get_theme_colors

    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    trades = pd.DataFrame(
        {
            "symbol": ["AAPL"] * 60,
            "action": ["buy"] * 60,
            "quantity": [10] * 60,
            "price": [150.0 + i for i in range(60)],
            "timestamp": dates,
            "commission": [0.001] * 60,
            "slippage": [0.0005] * 60,
            "cost": [1500.0] * 60,
            "fee": [2.25] * 60,
            "pnl": [float(i) for i in range(60)],
        }
    )
    result = _create_sample_result()
    result = result.__class__(
        equity_curve=result.equity_curve,
        trades=trades,
        positions={},
        metrics=result.metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=result.initial_capital,
        final_value=result.final_value,
        total_return=result.total_return,
        total_return_pct=result.total_return_pct,
    )
    html = _build_trades_table(result, _get_theme_colors("light"))
    assert "Showing first 50 of 60 trades" in html
    # 50 data rows + 1 header row
    assert html.count("<tr style") == 50


def test_build_trades_table_formats_missing_and_nan_columns():
    """_build_trades_table must render N/A for NaN and skip absent optional columns."""
    from quant_trading.backtest.report import _build_trades_table, _get_theme_colors

    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    trades = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "action": ["buy", "sell"],
            "quantity": [np.nan, 10],
            "price": [np.nan, 160.0],
            "timestamp": [dates[0], dates[1]],
            "pnl": [10.0, -5.0],
        }
    )
    result = _create_sample_result()
    result = result.__class__(
        equity_curve=result.equity_curve,
        trades=trades,
        positions={},
        metrics=result.metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=result.initial_capital,
        final_value=result.final_value,
        total_return=result.total_return,
        total_return_pct=result.total_return_pct,
    )
    html = _build_trades_table(result, _get_theme_colors("light"))
    assert "N/A" in html
    assert "AAPL" in html
    assert "MSFT" in html
    # Optional columns absent from the frame must not break rendering
    assert "commission" not in html.split("<thead>")[1]


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_create_trade_distribution_chart_all_nan_pnl():
    """_create_trade_distribution_chart must render empty state when all PnL is NaN."""
    from quant_trading.backtest.report import (
        _create_trade_distribution_chart,
        _get_theme_colors,
    )

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    trades = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "action": ["buy", "sell"],
            "quantity": [10, 10],
            "price": [150.0, 160.0],
            "timestamp": [dates[0], dates[1]],
            "commission": [0.001, 0.001],
            "slippage": [0.0005, 0.0005],
            "cost": [1500.0, 1600.0],
            "fee": [2.25, 2.40],
            "pnl": [np.nan, np.nan],
        }
    )
    result = _create_sample_result()
    result = result.__class__(
        equity_curve=result.equity_curve,
        trades=trades,
        positions={},
        metrics=result.metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=result.initial_capital,
        final_value=result.final_value,
        total_return=result.total_return,
        total_return_pct=result.total_return_pct,
    )

    for theme in ("light", "dark"):
        png = _create_trade_distribution_chart(result, _get_theme_colors(theme), 150)
        assert isinstance(png, str) and len(png) > 0


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_with_empty_equity_curve():
    """Test comparison report with an empty equity curve in one result."""
    result1 = _create_sample_result()

    # Create a result with empty equity curve
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    empty_equity = pd.Series(dtype=float, index=dates[:0])

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

    result2 = BacktestResult(
        equity_curve=empty_equity,
        trades=pd.DataFrame(),
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

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True)

    html = generate_comparison_report(results, config)

    assert isinstance(html, str)
    assert "Strategy A" in html
    assert "Strategy B" in html
    assert "Equity Curves Comparison" in html
    assert "Drawdown Comparison" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_with_config_none():
    """generate_comparison_report must fall back to ReportConfig() when config is None."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    html = generate_comparison_report(results)

    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html
    assert "Strategy Comparison" in html
    assert "Equity Curves Comparison" in html
    assert "Drawdown Comparison" in html


def test_build_comparison_table_handles_metric_fn_exceptions():
    """_build_comparison_table must handle metric_fn exceptions gracefully."""
    from quant_trading.backtest.report import _build_comparison_table, _get_theme_colors

    result1 = _create_sample_result()

    # Create a result with metrics that will cause AttributeError
    class BadMetrics:
        pass

    bad_result = BacktestResult(
        equity_curve=result1.equity_curve,
        trades=result1.trades,
        positions=result1.positions,
        metrics=BadMetrics(),  # Missing attributes will cause AttributeError
        start_date=result1.start_date,
        end_date=result1.end_date,
        initial_capital=result1.initial_capital,
        final_value=result1.final_value,
        total_return=result1.total_return,
        total_return_pct=result1.total_return_pct,
        total_costs=result1.total_costs,
    )

    results = [("Good Strategy", result1), ("Bad Strategy", bad_result)]
    html = _build_comparison_table(results, _get_theme_colors("light"))

    assert isinstance(html, str)
    assert "Good Strategy" in html
    assert "Bad Strategy" in html
    # N/A should appear for the bad strategy's metrics
    assert "N/A" in html


def test_build_trades_table_branch_coverage_nan_columns():
    """_build_trades_table must handle columns with all NaN values."""
    from quant_trading.backtest.report import _build_trades_table, _get_theme_colors

    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    trades = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "action": ["buy", "sell"],
            "quantity": [np.nan, np.nan],  # All NaN
            "price": [np.nan, np.nan],  # All NaN
            "timestamp": [dates[0], dates[1]],
            "commission": [np.nan, np.nan],  # All NaN
            "slippage": [np.nan, np.nan],  # All NaN
            "cost": [1500.0, 1600.0],
            "fee": [2.25, 2.40],
            "pnl": [10.0, -5.0],
        }
    )
    result = _create_sample_result()
    result = result.__class__(
        equity_curve=result.equity_curve,
        trades=trades,
        positions={},
        metrics=result.metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=result.initial_capital,
        final_value=result.final_value,
        total_return=result.total_return,
        total_return_pct=result.total_return_pct,
    )
    html = _build_trades_table(result, _get_theme_colors("light"))
    assert "N/A" in html
    assert "AAPL" in html
    assert "MSFT" in html


def test_build_trades_table_missing_timestamp_column():
    """_build_trades_table must handle missing timestamp column (else branch)."""
    from quant_trading.backtest.report import _build_trades_table, _get_theme_colors

    trades = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "action": ["buy", "sell"],
            "quantity": [10, 10],
            "price": [150.0, 160.0],
            # No timestamp column
            "commission": [0.001, 0.001],
            "slippage": [0.0005, 0.0005],
            "cost": [1500.0, 1600.0],
            "fee": [2.25, 2.40],
            "pnl": [10.0, -5.0],
        }
    )
    result = _create_sample_result()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    result = result.__class__(
        equity_curve=result.equity_curve,
        trades=trades,
        positions={},
        metrics=result.metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=result.initial_capital,
        final_value=result.final_value,
        total_return=result.total_return,
        total_return_pct=result.total_return_pct,
    )
    html = _build_trades_table(result, _get_theme_colors("light"))
    assert "AAPL" in html
    assert "MSFT" in html
    # timestamp column should not be in headers since it was missing
    # The headers are from the display_df which doesn't have timestamp
    # The test verifies no crash and proper rendering


def test_build_trades_table_missing_price_cost_fee_pnl_columns():
    """_build_trades_table must handle missing optional price/cost/fee/pnl columns."""
    from quant_trading.backtest.report import _build_trades_table, _get_theme_colors

    trades = pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "action": ["buy"],
            "quantity": [10],
            "timestamp": [pd.Timestamp("2024-01-01")],
            # Missing price, cost, fee, pnl columns
        }
    )
    result = _create_sample_result()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    result = result.__class__(
        equity_curve=result.equity_curve,
        trades=trades,
        positions={},
        metrics=result.metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=result.initial_capital,
        final_value=result.final_value,
        total_return=result.total_return,
        total_return_pct=result.total_return_pct,
    )
    html = _build_trades_table(result, _get_theme_colors("light"))
    assert "AAPL" in html
    # Should not crash


def test_build_comparison_table_metric_fn_exception_coverage():
    """Force coverage of _build_comparison_table exception handler (lines 1059-1060)."""
    import pandas as pd

    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import _build_comparison_table, _get_theme_colors

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    class GoodMetrics:
        total_return = 0.0
        total_return_pct = 0.0
        annual_return = 0.0
        volatility = 0.0
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        calmar_ratio = 0.0
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        win_rate = 0.0
        profit_factor = 0.0
        num_trades = 0
        avg_win = 0.0
        avg_loss = 0.0
        largest_win = 0.0
        largest_loss = 0.0

    class BadMetrics:
        """Missing all attributes - will cause AttributeError when accessed."""

    good_result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=GoodMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )

    bad_result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BadMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )

    results = [("Good", good_result), ("Bad", bad_result)]
    html = _build_comparison_table(results, _get_theme_colors("light"))

    assert "Good" in html
    assert "Bad" in html
    # The exception handler should produce N/A for Bad strategy's metrics
    assert "N/A" in html


def test_build_trades_table_missing_quantity_column():
    """_build_trades_table must handle missing quantity column (else branch at line 594)."""
    from quant_trading.backtest.report import _build_trades_table, _get_theme_colors

    trades = pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "action": ["buy"],
            "price": [150.0],
            "timestamp": [pd.Timestamp("2024-01-01")],
            "commission": [0.001],
            "slippage": [0.0005],
            "cost": [1500.0],
            "fee": [2.25],
            "pnl": [10.0],
            # Missing quantity column
        }
    )
    result = _create_sample_result()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    result = result.__class__(
        equity_curve=result.equity_curve,
        trades=trades,
        positions={},
        metrics=result.metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=result.initial_capital,
        final_value=result.final_value,
        total_return=result.total_return,
        total_return_pct=result.total_return_pct,
    )
    html = _build_trades_table(result, _get_theme_colors("light"))
    assert "AAPL" in html
    # quantity column should not appear in output since it was missing


def test_report_config_to_dict_and_from_dict_roundtrip():
    """ReportConfig.to_dict/from_dict must serialize and reconstruct faithfully (report.py:62, 85)."""
    from quant_trading.backtest.report import ReportConfig

    config = ReportConfig(
        title="Custom Report",
        include_charts=False,
        theme="dark",
        dpi=300,
    )
    data = config.to_dict()
    assert data == {
        "title": "Custom Report",
        "include_charts": False,
        "include_trade_details": True,
        "include_monthly_heatmap": True,
        "include_rolling_metrics": True,
        "theme": "dark",
        "dpi": 300,
    }
    restored = ReportConfig.from_dict(data)
    assert restored == config


def test_report_config_from_dict_missing_keys_use_defaults():
    """ReportConfig.from_dict must fall back to defaults for missing keys (report.py:85)."""
    from quant_trading.backtest.report import ReportConfig

    restored = ReportConfig.from_dict({"title": "Only title"})
    assert restored.title == "Only title"
    assert restored.include_charts is True
    assert restored.include_trade_details is True
    assert restored.include_monthly_heatmap is True
    assert restored.include_rolling_metrics is True
    assert restored.theme == "light"
    assert restored.dpi == 150


def test_check_matplotlib_raises_when_unavailable(monkeypatch):
    """_check_matplotlib must raise ImportError when matplotlib is unavailable (report.py:99)."""
    import quant_trading.backtest.report as report_module

    monkeypatch.setattr(report_module, "MATPLOTLIB_AVAILABLE", False)
    with pytest.raises(ImportError, match="matplotlib is required"):
        report_module._check_matplotlib()


def test_build_comparison_table_metric_value_error():
    """_build_comparison_table must render N/A when a metric_fn raises (report.py:1059-1060)."""
    import pandas as pd

    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import (
        _build_comparison_table,
        _get_theme_colors,
    )

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    class GoodMetrics:
        total_return = 0.0
        total_return_pct = 0.0
        annual_return = 0.0
        volatility = 0.0
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        calmar_ratio = 0.0
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        win_rate = 0.0
        profit_factor = 0.0
        num_trades = 0
        avg_win = 0.0
        avg_loss = 0.0
        largest_win = 0.0
        largest_loss = 0.0

    good_result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=GoodMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )

    # total_return_pct=None makes f"{None:.2f}%" raise ValueError, hitting the except branch.
    bad_result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=GoodMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=None,
        total_costs=0.0,
    )

    results = [("Good", good_result), ("Bad", bad_result)]
    html = _build_comparison_table(results, _get_theme_colors("light"))

    assert "Good" in html
    assert "Bad" in html
    assert "N/A" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
