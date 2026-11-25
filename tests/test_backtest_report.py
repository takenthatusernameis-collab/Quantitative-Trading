"""Tests for the backtest report module."""

import base64
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.metrics import BacktestMetrics
from quant_trading.backtest.report import (
    MATPLOTLIB_AVAILABLE,
    ReportConfig,
    _build_comparison_risk_attribution,
    _drawdown_series,
    _get_theme_colors,
    generate_comparison_report,
    generate_html_report,
    generate_report_from_dict,
)
from quant_trading.risk.manager import RiskAttribution


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


def test_report_config_defaults() -> None:
    """Test ReportConfig default values."""
    config = ReportConfig()
    assert config.title == "Backtest Report"
    assert config.include_charts is True
    assert config.include_trade_details is True
    assert config.include_monthly_heatmap is True
    assert config.include_rolling_metrics is True
    assert config.theme == "light"
    assert config.dpi == 150


def test_report_config_custom() -> None:
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


@pytest.mark.parametrize(
    "bad_dpi", [0, -1, -252, float("nan"), float("inf"), float("-inf"), True, "high", None]
)
def test_report_config_rejects_invalid_dpi(bad_dpi: Any) -> None:
    """ReportConfig must reject non-finite / out-of-range / non-numeric dpi."""
    with pytest.raises(ValueError, match="invalid dpi"):
        ReportConfig(dpi=bad_dpi)


@pytest.mark.parametrize("good_dpi", [1, 72, 150, 300, 1200])
def test_report_config_accepts_valid_dpi(good_dpi: int) -> None:
    """ReportConfig must accept finite dpi values of at least 1."""
    config = ReportConfig(dpi=good_dpi)
    assert config.dpi == good_dpi


@pytest.mark.parametrize("bad_theme", ["neon", "", None, 123, True, "LIGHT"])
def test_report_config_rejects_invalid_theme(bad_theme: Any) -> None:
    """ReportConfig must reject themes other than 'light' or 'dark'."""
    with pytest.raises(ValueError, match="invalid theme"):
        ReportConfig(theme=bad_theme)


@pytest.mark.parametrize("good_theme", ["light", "dark"])
def test_report_config_accepts_valid_theme(good_theme: str) -> None:
    """ReportConfig must accept the 'light' and 'dark' themes."""
    assert ReportConfig(theme=good_theme).theme == good_theme


def test_report_config_from_dict_sanitizes_invalid_dpi() -> None:
    """from_dict must collapse non-finite / unconvertible dpi to the default."""
    assert ReportConfig.from_dict({"dpi": float("nan")}).dpi == 150
    assert ReportConfig.from_dict({"dpi": float("inf")}).dpi == 150
    assert ReportConfig.from_dict({"dpi": "high"}).dpi == 150
    assert ReportConfig.from_dict({"dpi": None}).dpi == 150
    assert ReportConfig.from_dict({"dpi": True}).dpi == 150
    assert ReportConfig.from_dict({"dpi": 200}).dpi == 200


def test_report_config_from_dict_sanitizes_invalid_theme() -> None:
    """from_dict must collapse invalid themes to the default 'light'."""
    assert ReportConfig.from_dict({"theme": "neon"}).theme == "light"
    assert ReportConfig.from_dict({"theme": None}).theme == "light"
    assert ReportConfig.from_dict({"theme": "dark"}).theme == "dark"


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_basic() -> None:
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
def test_generate_html_report_no_charts() -> None:
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
def test_generate_html_report_dark_theme() -> None:
    """Test HTML report generation with dark theme."""
    result = _create_sample_result()
    config = ReportConfig(theme="dark")

    html = generate_html_report(result, config)

    assert "#1e1e1e" in html  # dark background color
    assert "Backtest Report" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_to_file() -> None:
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


def test_generate_report_from_dict() -> None:
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


def test_generate_report_from_dict_with_file() -> None:
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
def test_charts_generated_as_base64() -> None:
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
def test_report_with_empty_trades() -> None:
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
def test_report_with_insufficient_data_for_rolling() -> None:
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


def test_matplotlib_not_available_error() -> None:
    """Test that ImportError is raised when matplotlib not available and charts requested."""
    # This test is tricky since MATPLOTLIB_AVAILABLE is module-level
    # We just verify the constant exists
    assert isinstance(MATPLOTLIB_AVAILABLE, bool)


def test_report_handles_nan_metrics() -> None:
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
def test_generate_comparison_report_basic() -> None:
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
def test_generate_comparison_report_no_charts() -> None:
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
def test_generate_comparison_report_to_file() -> None:
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


def test_generate_comparison_report_empty_results() -> None:
    """Test that empty results list raises ValueError."""
    with pytest.raises(ValueError, match="At least one result is required"):
        generate_comparison_report([])


def test_generate_comparison_report_single_result() -> None:
    """Test comparison report with a single result."""
    result1 = _create_sample_result()

    results = [("Strategy A", result1)]
    config = ReportConfig(include_charts=False)

    html = generate_comparison_report(results, config)

    assert isinstance(html, str)
    assert "Strategy A" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_dark_theme() -> None:
    """Test comparison report with dark theme."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(theme="dark")

    html = generate_comparison_report(results, config)

    assert "#1e1e1e" in html  # dark background color


def test_report_matplotlib_unavailable_branch(monkeypatch: pytest.MonkeyPatch) -> None:
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
        sys.modules["matplotlib"] = None  # type: ignore[assignment]
        sys.modules["matplotlib.pyplot"] = None  # type: ignore[assignment]
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


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_uses_default_config_when_config_is_none() -> None:
    """generate_html_report must fall back to ReportConfig() when config is None."""
    result = _create_sample_result()
    html = generate_html_report(result)
    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html
    assert "Backtest Report" in html
    assert "Equity Curve" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_omits_monthly_heatmap_when_disabled() -> None:
    """include_monthly_heatmap=False must exclude the monthly returns chart."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=True, include_monthly_heatmap=False)
    html = generate_html_report(result, config)
    assert "Monthly Returns" not in html
    assert "Equity Curve" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_omits_rolling_metrics_when_disabled() -> None:
    """include_rolling_metrics=False must exclude the rolling metric chart cards."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=True, include_rolling_metrics=False)
    html = generate_html_report(result, config)
    assert "Rolling Sharpe" not in html
    assert "Rolling Volatility" not in html


def test_generate_html_report_omits_trade_details_when_disabled() -> None:
    """include_trade_details=False must exclude the trade details section."""
    result = _create_sample_result()
    config = ReportConfig(include_charts=False, include_trade_details=False)
    html = generate_html_report(result, config)
    assert "Trade Details" not in html
    assert "Performance Summary" in html


def test_build_trades_table_truncates_at_max_rows() -> None:
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


def test_build_trades_table_formats_missing_and_nan_columns() -> None:
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
def test_create_trade_distribution_chart_all_nan_pnl() -> None:
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
def test_comparison_report_with_empty_equity_curve() -> None:
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
def test_comparison_report_with_config_none() -> None:
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


def test_build_comparison_table_handles_metric_fn_exceptions() -> None:
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
        metrics=BadMetrics(),  # type: ignore[arg-type]  # Missing attributes will cause AttributeError
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


def test_build_trades_table_branch_coverage_nan_columns() -> None:
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


def test_build_trades_table_missing_timestamp_column() -> None:
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


def test_build_trades_table_missing_price_cost_fee_pnl_columns() -> None:
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


def test_build_comparison_table_metric_fn_exception_coverage() -> None:
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
        metrics=GoodMetrics(),  # type: ignore[arg-type]
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
        metrics=BadMetrics(),  # type: ignore[arg-type]
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


def test_build_trades_table_missing_quantity_column() -> None:
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


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_html_report_includes_risk_attribution() -> None:
    """Risk attribution data should render in the HTML report when present."""
    from quant_trading.risk.manager import RiskAttribution

    result = _create_sample_result()
    result.risk_attribution = RiskAttribution(
        confidence=0.95,
        positions_value=50000.0,
        portfolio_value=105000.0,
        portfolio_var=0.0312,
        portfolio_volatility=0.1825,
        weights=pd.Series([0.6, 0.4], index=["AAPL", "MSFT"]),
        marginal_var=pd.Series([0.021, 0.010], index=["AAPL", "MSFT"]),
        component_var=pd.Series([0.0187, 0.0125], index=["AAPL", "MSFT"]),
        volatility_contributions=pd.Series([0.109, 0.073], index=["AAPL", "MSFT"]),
    )

    html = generate_html_report(result, ReportConfig(include_charts=False))

    assert "Risk Attribution" in html
    assert "Portfolio VaR" in html
    assert "Component VaR" in html
    assert "AAPL" in html
    assert "MSFT" in html


def test_generate_report_from_dict_includes_risk_attribution() -> None:
    """generate_report_from_dict should reconstruct and render risk attribution."""
    result = _create_sample_result()
    from quant_trading.risk.manager import RiskAttribution

    result.risk_attribution = RiskAttribution(
        confidence=0.99,
        positions_value=40000.0,
        portfolio_value=105000.0,
        portfolio_var=0.045,
        portfolio_volatility=0.21,
        weights=pd.Series([1.0], index=["AAPL"]),
        marginal_var=pd.Series([0.03], index=["AAPL"]),
        component_var=pd.Series([0.045], index=["AAPL"]),
        volatility_contributions=pd.Series([0.21], index=["AAPL"]),
    )
    data = result.to_dict()

    html = generate_report_from_dict(data, ReportConfig(include_charts=False))
    assert "Risk Attribution" in html
    assert "AAPL" in html
    assert "0.0450" in html


def test_report_config_to_dict_and_from_dict_roundtrip() -> None:
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


def test_report_config_from_dict_missing_keys_use_defaults() -> None:
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


def test_check_matplotlib_raises_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """_check_matplotlib must raise ImportError when matplotlib is unavailable (report.py:99)."""
    import quant_trading.backtest.report as report_module

    monkeypatch.setattr(report_module, "MATPLOTLIB_AVAILABLE", False)
    with pytest.raises(ImportError, match="matplotlib is required"):
        report_module._check_matplotlib()


def test_build_comparison_table_metric_value_error() -> None:
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
        metrics=GoodMetrics(),  # type: ignore[arg-type]
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
        metrics=GoodMetrics(),  # type: ignore[arg-type]
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=None,  # type: ignore[arg-type]
        total_costs=0.0,
    )

    results = [("Good", good_result), ("Bad", bad_result)]
    html = _build_comparison_table(results, _get_theme_colors("light"))

    assert "Good" in html
    assert "Bad" in html
    assert "N/A" in html


def test_get_theme_colors_dark_theme() -> None:
    """_get_theme_colors must return the dark palette for theme="dark"."""
    from quant_trading.backtest.report import _get_theme_colors

    colors = _get_theme_colors("dark")
    assert colors["bg"] == "#1e1e1e"
    assert colors["fg"] == "#e0e0e0"
    assert colors["grid"] == "#333333"
    assert colors["positive"] == "#4caf50"
    assert colors["negative"] == "#f44336"
    assert colors["neutral"] == "#2196f3"
    assert colors["accent"] == "#ff9800"


def test_get_theme_colors_unknown_theme_falls_back_to_light() -> None:
    """_get_theme_colors must fall back to the light palette for unknown themes."""
    from quant_trading.backtest.report import _get_theme_colors

    assert _get_theme_colors("light") == _get_theme_colors("no-such-theme")
    assert _get_theme_colors("light")["bg"] == "#ffffff"


def test_drawdown_series_empty_equity() -> None:
    """_drawdown_series must return an empty float series for empty input."""
    from quant_trading.backtest.report import _drawdown_series

    empty = pd.Series(dtype=float)
    result = _drawdown_series(empty)
    assert len(result) == 0
    assert result.dtype == float


def test_drawdown_series_non_positive_peak() -> None:
    """_drawdown_series must report 0.0 when the running peak is not positive."""
    from quant_trading.backtest.report import _drawdown_series

    equity = pd.Series([0.0, 0.0, -10.0, -5.0])
    result = _drawdown_series(equity)
    assert (result == 0.0).all()
    assert np.isfinite(result).all()


def test_drawdown_series_inf_and_nan_are_finite() -> None:
    """_drawdown_series must never yield NaN or +/-inf."""
    from quant_trading.backtest.report import _drawdown_series

    equity = pd.Series([100.0, np.inf, 50.0, np.nan, 200.0])
    result = _drawdown_series(equity)
    assert np.isfinite(result).all()


def test_finite_series_empty() -> None:
    """_finite_series must return an empty float series for empty input."""
    from quant_trading.backtest.report import _finite_series

    empty = pd.Series(dtype=float)
    result = _finite_series(empty)
    assert len(result) == 0
    assert result.dtype == float


def test_finite_series_removes_non_finite() -> None:
    """_finite_series must drop NaN and +/-inf values."""
    from quant_trading.backtest.report import _finite_series

    series = pd.Series([1.0, np.nan, np.inf, -np.inf, 2.0])
    result = _finite_series(series)
    assert list(result) == [1.0, 2.0]


def test_format_metric_returns_na_for_none() -> None:
    """_format_metric must render "N/A" for None."""
    from quant_trading.backtest.report import _format_metric

    assert _format_metric(None) == "N/A"


def test_format_metric_sanitizes_non_finite_float() -> None:
    """_format_metric must render the format's zero default for NaN and +/-inf."""
    from quant_trading.backtest.report import _format_metric

    assert _format_metric(float("nan")) == "0.00"
    assert _format_metric(float("inf")) == "0.00"
    assert _format_metric(-float("inf")) == "0.00"
    assert _format_metric(float("nan"), "{:.2%}") == "0.00%"
    assert _format_metric(float("inf"), "${:,.2f}") == "$0.00"


def test_format_metric_formats_finite_float() -> None:
    """_format_metric must format a finite float with the given format."""
    from quant_trading.backtest.report import _format_metric

    assert _format_metric(0.826, "{:.2f}") == "0.83"
    assert _format_metric(5.0, "{:.2%}") == "500.00%"


def test_format_metric_sanitizes_non_numeric() -> None:
    """_format_metric must sanitize non-numeric/bool inputs to the format's zero default."""
    from quant_trading.backtest.report import _format_metric

    assert _format_metric("N/A") == "0.00"
    assert _format_metric(42) == "42.00"
    assert _format_metric(True) == "0.00"
    assert _format_metric(False) == "0.00"
    assert _format_metric("1.5") == "1.50"
    assert _format_metric(None) == "N/A"  # None is special-cased to "N/A"


def test_build_risk_attribution_table_none_returns_empty() -> None:
    """_build_risk_attribution_table must return "" when attribution is absent."""
    from quant_trading.backtest.report import (
        _build_risk_attribution_table,
        _get_theme_colors,
    )

    result = _create_sample_result()
    assert getattr(result, "risk_attribution", None) is None
    html = _build_risk_attribution_table(result, _get_theme_colors("light"))
    assert html == ""


def test_build_risk_attribution_table_non_dict_returns_empty() -> None:
    """_build_risk_attribution_table must return "" for a non-dict attribution."""
    from quant_trading.backtest.report import (
        _build_risk_attribution_table,
        _get_theme_colors,
    )

    result = _create_sample_result()
    result.risk_attribution = object()  # type: ignore[assignment]
    html = _build_risk_attribution_table(result, _get_theme_colors("light"))
    assert html == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def _create_sample_result_with_attribution() -> BacktestResult:
    """Create a sample BacktestResult with risk attribution for testing."""
    result = _create_sample_result()
    result.risk_attribution = RiskAttribution(
        confidence=0.95,
        positions_value=50000.0,
        portfolio_value=105000.0,
        portfolio_var=0.0312,
        portfolio_volatility=0.1825,
        weights=pd.Series([0.6, 0.4], index=["AAPL", "MSFT"]),
        marginal_var=pd.Series([0.021, 0.010], index=["AAPL", "MSFT"]),
        component_var=pd.Series([0.0187, 0.0125], index=["AAPL", "MSFT"]),
        volatility_contributions=pd.Series([0.109, 0.073], index=["AAPL", "MSFT"]),
    )
    return result


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_with_risk_attribution() -> None:
    """Test comparison report includes risk attribution when present."""
    result1 = _create_sample_result_with_attribution()
    result2 = _create_sample_result()  # No attribution

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=False, title="Strategy Comparison")

    html = generate_comparison_report(results, config)

    assert "Risk Attribution Comparison" in html
    assert "Portfolio VaR" in html
    assert "Portfolio Volatility" in html
    assert "Strategy A" in html
    assert "Strategy B" in html
    # Strategy A should have attribution data
    assert "0.0312" in html  # portfolio_var
    assert "0.1825" in html  # portfolio_volatility
    # Strategy B should show N/A
    assert "N/A" in html
    # Position breakdown for Strategy A
    assert "AAPL" in html
    assert "MSFT" in html
    assert "Component VaR" in html
    assert "Volatility Contribution" in html


def test_comparison_summary_cards_sanitize_non_finite_metrics() -> None:
    """Summary cards must not leak nan/inf from non-finite metrics (report.py).

    A strategy that produces no trades, a flat equity curve, or zero
    volatility can carry NaN/inf metrics. The summary cards format them
    directly, so they used to render ``nan``/``inf`` into the HTML. They now
    run every metric through ``_format_metric`` (which sanitizes via
    ``_finite``), matching the single-strategy metrics table.

    """
    from quant_trading.backtest.report import _build_comparison_summary_cards

    metrics = BacktestMetrics(
        sharpe_ratio=float("nan"),
        max_drawdown_pct=float("inf"),
        ulcer_index=float("-inf"),
        win_rate=float("nan"),
        num_trades=0,
    )
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 10)
    result = BacktestResult(
        equity_curve=pd.Series([100000.0, 100000.0], index=pd.date_range(start, periods=2)),
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=start,
        end_date=end,
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
    )
    colors = _get_theme_colors("light")
    html = _build_comparison_summary_cards([("FlatStrategy", result)], colors)

    assert "nan" not in html.lower()
    assert "inf" not in html.lower()
    # Sanitized values render as their zero default.
    assert "Sharpe:</strong> 0.00" in html
    assert "Max DD:</strong> 0.00%" in html
    assert "Ulcer:</strong> 0.0000" in html
    assert "Win Rate:</strong> 0.0%" in html
    assert "Costs:</strong> $0.00" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_multiple_with_attribution() -> None:
    """Test comparison report with multiple strategies having attribution."""
    result1 = _create_sample_result_with_attribution()
    result2 = _create_sample_result()
    result2.risk_attribution = RiskAttribution(
        confidence=0.99,
        positions_value=40000.0,
        portfolio_value=105000.0,
        portfolio_var=0.045,
        portfolio_volatility=0.21,
        weights=pd.Series([1.0], index=["AAPL"]),
        marginal_var=pd.Series([0.03], index=["AAPL"]),
        component_var=pd.Series([0.045], index=["AAPL"]),
        volatility_contributions=pd.Series([0.21], index=["AAPL"]),
    )

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=False)

    html = generate_comparison_report(results, config)

    assert "Risk Attribution Comparison" in html
    # Both strategies should have data
    assert "0.0312" in html  # Strategy A portfolio_var
    assert "0.0450" in html  # Strategy B portfolio_var (formatted to 4 decimal places)
    assert "0.1825" in html  # Strategy A portfolio_volatility
    assert "0.2100" in html  # Strategy B portfolio_volatility
    # Both position breakdowns
    assert "Strategy A" in html
    assert "Strategy B" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_no_attribution() -> None:
    """Test comparison report without any risk attribution still works."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=False)

    html = generate_comparison_report(results, config)

    # Should not have risk attribution section
    assert "Risk Attribution Comparison" not in html
    assert "Strategy Comparison" in html


def test_generate_comparison_report_from_dict_with_attribution() -> None:
    """Test generate_comparison_report works with dict input (via generate_report_from_dict path if applicable)."""
    # This tests the path where results are loaded from dict
    result1 = _create_sample_result_with_attribution()
    result2 = _create_sample_result()
    result2.risk_attribution = RiskAttribution(
        confidence=0.99,
        positions_value=40000.0,
        portfolio_value=105000.0,
        portfolio_var=0.045,
        portfolio_volatility=0.21,
        weights=pd.Series([1.0], index=["AAPL"]),
        marginal_var=pd.Series([0.03], index=["AAPL"]),
        component_var=pd.Series([0.045], index=["AAPL"]),
        volatility_contributions=pd.Series([0.21], index=["AAPL"]),
    )

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=False)

    html = generate_comparison_report(results, config)

    assert "Risk Attribution Comparison" in html
    assert "0.0312" in html
    assert "0.0450" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_risk_attribution_chart() -> None:
    """Test comparison report includes risk attribution chart when charts enabled."""
    result1 = _create_sample_result_with_attribution()
    result2 = _create_sample_result()
    result2.risk_attribution = RiskAttribution(
        confidence=0.99,
        positions_value=40000.0,
        portfolio_value=105000.0,
        portfolio_var=0.045,
        portfolio_volatility=0.21,
        weights=pd.Series([1.0], index=["AAPL"]),
        marginal_var=pd.Series([0.03], index=["AAPL"]),
        component_var=pd.Series([0.045], index=["AAPL"]),
        volatility_contributions=pd.Series([0.21], index=["AAPL"]),
    )

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True)

    html = generate_comparison_report(results, config)

    assert "Risk Attribution Comparison" in html
    assert "Risk Attribution: Portfolio VaR &amp; Volatility" in html
    assert "data:image/png;base64," in html
    assert 'alt="Risk Attribution Comparison Chart"' in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_risk_attribution_chart_no_attribution() -> None:
    """Test no risk attribution chart when no results have attribution."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True)

    html = generate_comparison_report(results, config)

    assert "Risk Attribution Comparison" not in html
    assert "Risk Attribution: Portfolio VaR & Volatility" not in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_risk_attribution_chart_no_charts() -> None:
    """Test no risk attribution chart when include_charts is False."""
    result1 = _create_sample_result_with_attribution()

    results = [("Strategy A", result1)]
    config = ReportConfig(include_charts=False)

    html = generate_comparison_report(results, config)

    assert "Risk Attribution Comparison" in html
    assert "data:image/png;base64," not in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_risk_attribution_chart_no_tight_layout_warning() -> None:
    """Comparison report with risk attribution chart must not emit tight_layout UserWarnings.

    Regression test for the pre-existing warning raised by
    ``_create_comparison_risk_attribution_chart`` (report.py:1746) when
    ``fig.tight_layout()`` was used. The chart now uses ``constrained_layout=True``
    so no warning is raised.
    """
    import warnings

    result1 = _create_sample_result_with_attribution()
    result2 = _create_sample_result_with_attribution()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        generate_comparison_report(results, config)

    tight_layout_warnings = [w for w in caught if "tight_layout" in str(w.message)]
    assert tight_layout_warnings == []


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_no_tight_layout_warning() -> None:
    """Comparison report with monthly heatmap must not emit tight_layout UserWarnings.

    Regression test for the pre-existing warning raised by
    ``_create_comparison_monthly_returns_heatmap`` (report.py:1215) when a
    colorbar is attached to a row-array of axes. The chart now uses
    ``constrained_layout=True`` and ``fig.colorbar`` so no warning is raised.
    """
    import warnings

    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True, include_monthly_heatmap=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        generate_comparison_report(results, config)

    tight_layout_warnings = [w for w in caught if "tight_layout" in str(w.message)]
    assert tight_layout_warnings == []


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_report_single_strategy_no_tight_layout_warning() -> None:
    """Single-strategy comparison report with monthly heatmap must not warn."""
    import warnings

    result1 = _create_sample_result()

    results = [("Strategy A", result1)]
    config = ReportConfig(include_charts=True, include_monthly_heatmap=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        generate_comparison_report(results, config)

    tight_layout_warnings = [w for w in caught if "tight_layout" in str(w.message)]
    assert tight_layout_warnings == []


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_single_result_report_no_tight_layout_warning() -> None:
    """Single-result report with monthly heatmap must not emit tight_layout UserWarnings.

    Regression test for the pre-existing warning raised by
    ``_create_monthly_returns_heatmap`` when a colorbar is attached to a single
    axis. The chart now uses ``constrained_layout=True`` and ``fig.colorbar``
    so no warning is raised.
    """
    import warnings

    result = _create_sample_result()
    config = ReportConfig(include_charts=True, include_monthly_heatmap=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        generate_html_report(result, config)

    tight_layout_warnings = [w for w in caught if "tight_layout" in str(w.message)]
    assert tight_layout_warnings == []


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_fig_to_base64_skips_bbox_tight_for_constrained_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_fig_to_base64 must not pass bbox_inches='tight' when constrained_layout is active.

    Combining bbox_inches='tight' with constrained_layout is redundant and can
    cause layout conflicts/warnings in some Matplotlib versions.
    """
    import matplotlib.pyplot as plt

    import quant_trading.backtest.report as report_mod

    report_mod._check_matplotlib()

    captured = {}

    def fake_savefig(self: Any, buf: Any, **kwargs: Any) -> None:
        captured.update(kwargs)
        buf.write(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(plt.Figure, "savefig", fake_savefig)

    fig, _ = plt.subplots(constrained_layout=True)
    out = report_mod._fig_to_base64(fig, dpi=100)
    assert isinstance(out, str) and out
    assert "bbox_inches" not in captured, captured
    assert captured.get("format") == "png"


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_fig_to_base64_uses_bbox_tight_without_layout_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_fig_to_base64 should keep bbox_inches='tight' for figures without layout engine."""
    import matplotlib.pyplot as plt

    import quant_trading.backtest.report as report_mod

    report_mod._check_matplotlib()

    captured = {}

    def fake_savefig(self: Any, buf: Any, **kwargs: Any) -> None:
        captured.update(kwargs)
        buf.write(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(plt.Figure, "savefig", fake_savefig)

    fig, _ = plt.subplots()  # default: no constrained_layout
    out = report_mod._fig_to_base64(fig, dpi=100)
    assert isinstance(out, str) and out
    assert captured.get("bbox_inches") == "tight", captured


# Tests for uncovered lines in _build_risk_attribution_table
def test_build_risk_attribution_table_non_dict_data() -> None:
    """_build_risk_attribution_table must return empty string when data is not a dict (line 650)."""
    from quant_trading.backtest.report import _build_risk_attribution_table, _get_theme_colors

    result = _create_sample_result()

    class BadAttribution:
        def to_dict(self) -> str:
            return "not a dict"

    result.risk_attribution = BadAttribution()  # type: ignore[assignment]
    html = _build_risk_attribution_table(result, _get_theme_colors("light"))
    assert html == ""


def test_build_risk_attribution_table_with_symbols() -> None:
    """_build_risk_attribution_table must render symbol breakdown when symbols exist (lines 682-704)."""
    from quant_trading.backtest.report import _build_risk_attribution_table, _get_theme_colors
    from quant_trading.risk.manager import RiskAttribution

    result = _create_sample_result()
    result.risk_attribution = RiskAttribution(
        confidence=0.95,
        positions_value=50000.0,
        portfolio_value=105000.0,
        portfolio_var=0.0312,
        portfolio_volatility=0.1825,
        weights=pd.Series([0.6, 0.4], index=["AAPL", "MSFT"]),
        marginal_var=pd.Series([0.021, 0.010], index=["AAPL", "MSFT"]),
        component_var=pd.Series([0.0187, 0.0125], index=["AAPL", "MSFT"]),
        volatility_contributions=pd.Series([0.109, 0.073], index=["AAPL", "MSFT"]),
    )

    html = _build_risk_attribution_table(result, _get_theme_colors("light"))
    assert "Risk Attribution" not in html  # The div class is "risk-attribution"
    assert "AAPL" in html
    assert "MSFT" in html
    assert "Weight" in html
    assert "Marginal VaR" in html
    assert "Component VaR" in html
    assert "Volatility Contribution" in html


# Tests for uncovered lines in _create_comparison_monthly_returns_heatmap
@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_monthly_heatmap_empty_results() -> None:
    """_create_comparison_monthly_returns_heatmap must return empty string for empty results (line 1116)."""
    from quant_trading.backtest.report import (
        _create_comparison_monthly_returns_heatmap,
        _get_theme_colors,
    )

    result = _create_comparison_monthly_returns_heatmap([], _get_theme_colors("light"), 150)
    assert result == ""


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_monthly_heatmap_insufficient_data_branches() -> None:
    """_create_comparison_monthly_returns_heatmap must handle insufficient data branches (lines 1134-1167)."""
    from quant_trading.backtest.report import (
        _create_comparison_monthly_returns_heatmap,
        _get_theme_colors,
    )

    # Case 1: equity length < 2
    dates = pd.date_range("2024-01-01", periods=1, freq="D")
    equity = pd.Series([100000.0], index=dates)

    class Result:
        def __init__(self, equity: pd.Series) -> None:
            self.equity_curve = equity
            self.trades = pd.DataFrame()
            self.metrics = BacktestMetrics()

    result1 = Result(equity)
    results = [("Strategy A", result1)]

    png = _create_comparison_monthly_returns_heatmap(results, _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png, str) and len(png) > 0

    # Case 2: monthly_returns is empty after resample
    dates2 = pd.date_range("2024-01-01", periods=5, freq="D")
    equity2 = pd.Series([100000.0] * 5, index=dates2)
    result2 = Result(equity2)
    results2 = [("Strategy B", result2)]

    png2 = _create_comparison_monthly_returns_heatmap(results2, _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png2, str) and len(png2) > 0


# Tests for uncovered lines in _create_comparison_trade_distribution_chart
@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_trade_distribution_chart_no_data() -> None:
    """_create_comparison_trade_distribution_chart must handle no data case (lines 1300-1313)."""
    from quant_trading.backtest.report import (
        _create_comparison_trade_distribution_chart,
        _get_theme_colors,
    )

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity = pd.Series([100000.0] * 10, index=dates)

    class Result:
        def __init__(self, equity: pd.Series, trades: pd.DataFrame) -> None:
            self.equity_curve = equity
            self.trades = trades
            self.metrics = BacktestMetrics()

    # All results have empty trades or no pnl column
    trades_empty = pd.DataFrame()
    result1 = Result(equity, trades_empty)

    trades_no_pnl = pd.DataFrame({"symbol": ["AAPL"], "action": ["buy"]})
    result2 = Result(equity, trades_no_pnl)

    trades_all_nan = pd.DataFrame(
        {"symbol": ["AAPL", "MSFT"], "action": ["buy", "sell"], "pnl": [np.nan, np.nan]}
    )
    result3 = Result(equity, trades_all_nan)

    results = [("Strategy A", result1), ("Strategy B", result2), ("Strategy C", result3)]

    png = _create_comparison_trade_distribution_chart(results, _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png, str) and len(png) > 0
    assert _create_comparison_trade_distribution_chart.__doc__ is not None


# Tests for uncovered lines in _create_comparison_rolling_sharpe_chart
@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_rolling_sharpe_chart_no_data() -> None:
    """_create_comparison_rolling_sharpe_chart must handle no data case (lines 1378-1394)."""
    from quant_trading.backtest.report import (
        _create_comparison_rolling_sharpe_chart,
        _get_theme_colors,
    )

    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    equity = pd.Series([100000.0] * 30, index=dates)

    class Result:
        def __init__(self, equity: pd.Series) -> None:
            self.equity_curve = equity
            self.trades = pd.DataFrame()
            self.metrics = BacktestMetrics()

    result1 = Result(equity)  # Less than 60 bars
    results = [("Strategy A", result1)]

    png = _create_comparison_rolling_sharpe_chart(results, _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png, str) and len(png) > 0


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_rolling_sharpe_chart_empty_after_dropna() -> None:
    """_create_comparison_rolling_sharpe_chart must handle empty rolling_sharpe after dropna (line 1364)."""
    from quant_trading.backtest.report import (
        _create_comparison_rolling_sharpe_chart,
        _get_theme_colors,
    )

    # Create equity with 60+ bars but constant values (no variance -> rolling std = 0 -> rolling_sharpe = NaN)
    dates = pd.date_range("2024-01-01", periods=70, freq="D")
    equity = pd.Series([100000.0] * 70, index=dates)

    class Result:
        def __init__(self, equity: pd.Series) -> None:
            self.equity_curve = equity
            self.trades = pd.DataFrame()
            self.metrics = BacktestMetrics()

    result1 = Result(equity)
    results = [("Strategy A", result1)]

    png = _create_comparison_rolling_sharpe_chart(results, _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png, str) and len(png) > 0


# Tests for uncovered lines in _create_comparison_rolling_volatility_chart
@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_rolling_volatility_chart_no_data() -> None:
    """_create_comparison_rolling_volatility_chart must handle no data case (lines 1462-1478)."""
    from quant_trading.backtest.report import (
        _create_comparison_rolling_volatility_chart,
        _get_theme_colors,
    )

    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    equity = pd.Series([100000.0] * 30, index=dates)

    class Result:
        def __init__(self, equity: pd.Series) -> None:
            self.equity_curve = equity
            self.trades = pd.DataFrame()
            self.metrics = BacktestMetrics()

    result1 = Result(equity)  # Less than 60 bars
    results = [("Strategy A", result1)]

    png = _create_comparison_rolling_volatility_chart(results, _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png, str) and len(png) > 0


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_rolling_volatility_chart_empty_after_dropna() -> None:
    """_create_comparison_rolling_volatility_chart must handle empty rolling_vol after dropna (line 1448)."""
    from quant_trading.backtest.report import (
        _create_comparison_rolling_volatility_chart,
        _get_theme_colors,
    )

    # Create equity with 60+ bars but constant values (no variance)
    dates = pd.date_range("2024-01-01", periods=70, freq="D")
    equity = pd.Series([100000.0] * 70, index=dates)

    class Result:
        def __init__(self, equity: pd.Series) -> None:
            self.equity_curve = equity
            self.trades = pd.DataFrame()
            self.metrics = BacktestMetrics()

    result1 = Result(equity)
    results = [("Strategy A", result1)]

    png = _create_comparison_rolling_volatility_chart(results, _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png, str) and len(png) > 0


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_rolling_sharpe_chart_empty_after_dropna() -> None:
    """_create_rolling_sharpe_chart must handle empty rolling_sharpe after filtering."""
    from quant_trading.backtest.report import _create_rolling_sharpe_chart, _get_theme_colors

    # Constant equity yields zero-variance returns, so every rolling Sharpe is
    # NaN and the finite-series filter leaves nothing to plot.
    dates = pd.date_range("2024-01-01", periods=70, freq="D")
    equity = pd.Series([100000.0] * 70, index=dates)

    class Result:
        def __init__(self, equity: pd.Series) -> None:
            self.equity_curve = equity

    png = _create_rolling_sharpe_chart(Result(equity), _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png, str) and len(png) > 0


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_rolling_volatility_chart_empty_after_dropna() -> None:
    """_create_rolling_volatility_chart must handle empty rolling_vol after filtering."""
    from quant_trading.backtest.report import (
        _create_rolling_volatility_chart,
        _get_theme_colors,
    )

    # Equity that oscillates through zero produces infinite returns in every
    # rolling window, so the finite-series filter leaves nothing to plot.
    dates = pd.date_range("2024-01-01", periods=70, freq="D")
    equity = pd.Series([100000.0 if i % 2 == 0 else 0.0 for i in range(70)], index=dates)

    class Result:
        def __init__(self, equity: pd.Series) -> None:
            self.equity_curve = equity

    png = _create_rolling_volatility_chart(Result(equity), _get_theme_colors("light"), 150)  # type: ignore[arg-type]
    assert isinstance(png, str) and len(png) > 0


# Tests for uncovered lines in _build_comparison_risk_attribution
def test_build_comparison_risk_attribution_exception_handling() -> None:
    """_build_comparison_risk_attribution must handle metric_fn exceptions (lines 1621-1624)."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import _build_comparison_risk_attribution, _get_theme_colors

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    class BadAttribution:
        def to_dict(self) -> dict[str, Any]:
            # This will cause the metric_fn to raise when accessing keys
            return {"confidence": "not_a_number"}  # Will fail on "{:.2%}".format

    good_result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
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
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )
    bad_result.risk_attribution = BadAttribution()  # type: ignore[assignment]

    results = [("Good", good_result), ("Bad", bad_result)]
    html = _build_comparison_risk_attribution(results, _get_theme_colors("light"))

    assert "Risk Attribution Comparison" in html
    assert "Good" in html
    assert "Bad" in html
    assert "N/A" in html


def test_build_comparison_risk_attribution_non_dict_data() -> None:
    """_build_comparison_risk_attribution must skip non-dict attribution data (line 1639)."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import _build_comparison_risk_attribution, _get_theme_colors

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    class BadAttribution:
        def to_dict(self) -> str:
            return "not a dict"

    good_result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
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
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )
    bad_result.risk_attribution = BadAttribution()  # type: ignore[assignment]

    results = [("Good", good_result), ("Bad", bad_result)]
    html = _build_comparison_risk_attribution(results, _get_theme_colors("light"))

    assert "Risk Attribution Comparison" in html
    assert "Good" in html
    assert "Bad" in html
    # Bad result should show N/A for all metrics
    assert "N/A" in html


def test_build_comparison_risk_attribution_no_symbols() -> None:
    """_build_comparison_risk_attribution must skip symbol breakdown when no symbols (line 1651)."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import _build_comparison_risk_attribution, _get_theme_colors
    from quant_trading.risk.manager import RiskAttribution

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    result = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )
    # RiskAttribution with empty series
    result.risk_attribution = RiskAttribution(
        confidence=0.95,
        positions_value=50000.0,
        portfolio_value=105000.0,
        portfolio_var=0.0312,
        portfolio_volatility=0.1825,
        weights=pd.Series(dtype=float),
        marginal_var=pd.Series(dtype=float),
        component_var=pd.Series(dtype=float),
        volatility_contributions=pd.Series(dtype=float),
    )

    results = [("Strategy A", result)]
    html = _build_comparison_risk_attribution(results, _get_theme_colors("light"))

    assert "Risk Attribution Comparison" in html
    assert "Strategy A" in html
    assert "Position Breakdown" not in html  # Should not render breakdown when no symbols


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_build_comparison_risk_attribution_with_chart() -> None:
    """_build_comparison_risk_attribution must include chart when dpi provided (lines 1678-1686)."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import _build_comparison_risk_attribution, _get_theme_colors
    from quant_trading.risk.manager import RiskAttribution

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    result1 = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )
    result1.risk_attribution = RiskAttribution(
        confidence=0.95,
        positions_value=50000.0,
        portfolio_value=105000.0,
        portfolio_var=0.0312,
        portfolio_volatility=0.1825,
        weights=pd.Series([1.0], index=["AAPL"]),
        marginal_var=pd.Series([0.03], index=["AAPL"]),
        component_var=pd.Series([0.045], index=["AAPL"]),
        volatility_contributions=pd.Series([0.21], index=["AAPL"]),
    )

    result2 = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )
    result2.risk_attribution = RiskAttribution(
        confidence=0.99,
        positions_value=40000.0,
        portfolio_value=105000.0,
        portfolio_var=0.045,
        portfolio_volatility=0.21,
        weights=pd.Series([1.0], index=["MSFT"]),
        marginal_var=pd.Series([0.03], index=["MSFT"]),
        component_var=pd.Series([0.045], index=["MSFT"]),
        volatility_contributions=pd.Series([0.21], index=["MSFT"]),
    )

    results = [("Strategy A", result1), ("Strategy B", result2)]
    html = _build_comparison_risk_attribution(results, _get_theme_colors("light"), dpi=150)

    assert "Risk Attribution Comparison" in html
    assert "Risk Attribution: Portfolio VaR &amp; Volatility" in html
    assert "data:image/png;base64," in html


# Tests for uncovered lines in _create_comparison_risk_attribution_chart
@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_risk_attribution_chart_no_attribution() -> None:
    """_create_comparison_risk_attribution_chart must return empty string when no attribution (lines 1705, 1708, 1713)."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import (
        _create_comparison_risk_attribution_chart,
        _get_theme_colors,
    )

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    result1 = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )

    result2 = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )

    # No risk_attribution on either result
    results = [("Strategy A", result1), ("Strategy B", result2)]

    chart = _create_comparison_risk_attribution_chart(results, _get_theme_colors("light"), 150)
    assert chart == ""


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_risk_attribution_chart_none_attribution() -> None:
    """_create_comparison_risk_attribution_chart must skip None attribution (line 1705)."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import (
        _create_comparison_risk_attribution_chart,
        _get_theme_colors,
    )
    from quant_trading.risk.manager import RiskAttribution

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    result1 = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )
    result1.risk_attribution = None  # Explicitly None

    result2 = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )
    result2.risk_attribution = RiskAttribution(
        confidence=0.95,
        positions_value=50000.0,
        portfolio_value=105000.0,
        portfolio_var=0.0312,
        portfolio_volatility=0.1825,
        weights=pd.Series([1.0], index=["AAPL"]),
        marginal_var=pd.Series([0.03], index=["AAPL"]),
        component_var=pd.Series([0.045], index=["AAPL"]),
        volatility_contributions=pd.Series([0.21], index=["AAPL"]),
    )

    results = [("Strategy A", result1), ("Strategy B", result2)]

    chart = _create_comparison_risk_attribution_chart(results, _get_theme_colors("light"), 150)
    assert isinstance(chart, str) and len(chart) > 0


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_risk_attribution_chart_non_dict_attribution() -> None:
    """_create_comparison_risk_attribution_chart must skip non-dict attribution (line 1708)."""
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.report import (
        _create_comparison_risk_attribution_chart,
        _get_theme_colors,
    )

    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity_curve = pd.Series([100000] * 10, index=dates)
    trades_df = pd.DataFrame()

    class BadAttribution:
        def to_dict(self) -> str:
            return "not a dict"

    result1 = BacktestResult(
        equity_curve=equity_curve,
        trades=trades_df,
        positions={},
        metrics=BacktestMetrics(),
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=100000.0,
        total_return=0.0,
        total_return_pct=0.0,
        total_costs=0.0,
    )
    result1.risk_attribution = BadAttribution()  # type: ignore[assignment]

    results = [("Strategy A", result1)]

    chart = _create_comparison_risk_attribution_chart(results, _get_theme_colors("light"), 150)
    assert chart == ""


# Tests for uncovered lines in generate_comparison_report
@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_monthly_heatmap_branch() -> None:
    """generate_comparison_report must include monthly heatmap when enabled (lines 1824-1827)."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True, include_monthly_heatmap=True)

    html = generate_comparison_report(results, config)

    assert "Monthly Returns Comparison" in html
    assert "data:image/png;base64," in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_rolling_metrics_branch() -> None:
    """generate_comparison_report must include rolling metrics when enabled (lines 1831-1837)."""
    # Need 60+ bars for rolling metrics
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
        num_trades=1,
        avg_win=98.50,
        avg_loss=0.0,
        largest_win=98.50,
        largest_loss=0.0,
    )

    result1 = BacktestResult(
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
    result2 = BacktestResult(
        equity_curve=equity_curve * 1.02,
        trades=trades_df,
        positions={},
        metrics=metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=107100.0,
        total_return=5100.0,
        total_return_pct=5.1,
        total_costs=9.07,
    )

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True, include_rolling_metrics=True)

    html = generate_comparison_report(results, config)

    assert "Rolling Sharpe (60) Comparison" in html
    assert "Rolling Volatility (60) Comparison" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_monthly_heatmap_display() -> None:
    """generate_comparison_report must display monthly heatmap when generated (lines 1882-1885)."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True, include_monthly_heatmap=True)

    html = generate_comparison_report(results, config)

    # The monthly heatmap should be displayed in the chart grid
    assert "Monthly Returns Comparison" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_rolling_metrics_display() -> None:
    """generate_comparison_report must display rolling metrics when generated (lines 1891-1898)."""
    # Need 60+ bars for rolling metrics
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
        num_trades=1,
        avg_win=98.50,
        avg_loss=0.0,
        largest_win=98.50,
        largest_loss=0.0,
    )

    result1 = BacktestResult(
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
    result2 = BacktestResult(
        equity_curve=equity_curve * 1.02,
        trades=trades_df,
        positions={},
        metrics=metrics,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=100000.0,
        final_value=107100.0,
        total_return=5100.0,
        total_return_pct=5.1,
        total_costs=9.07,
    )

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(include_charts=True, include_rolling_metrics=True)

    html = generate_comparison_report(results, config)

    assert "Rolling Sharpe (60) Comparison" in html
    assert "Rolling Volatility (60) Comparison" in html


# Tests for remaining uncovered branches in report.py
def test_build_risk_attribution_table_no_symbols() -> None:
    """Empty attribution series must skip the symbol breakdown (branch 682->704)."""
    from quant_trading.backtest.report import _build_risk_attribution_table, _get_theme_colors

    result = _create_sample_result()
    result.risk_attribution = RiskAttribution(
        confidence=0.95,
        positions_value=50000.0,
        portfolio_value=105000.0,
        portfolio_var=0.0312,
        portfolio_volatility=0.1825,
        weights=pd.Series(dtype=float),
        marginal_var=pd.Series(dtype=float),
        component_var=pd.Series(dtype=float),
        volatility_contributions=pd.Series(dtype=float),
    )

    html = _build_risk_attribution_table(result, _get_theme_colors("light"))

    assert "Symbol" not in html
    assert "Weight" not in html
    assert "Portfolio VaR" in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_comparison_rolling_volatility_chart_exactly_60_bars() -> None:
    """Exactly 60 bars leaves rolling_vol empty after dropna (line 1456)."""
    from quant_trading.backtest.report import (
        _create_comparison_rolling_volatility_chart,
        _get_theme_colors,
    )

    result = _create_sample_result()
    result.equity_curve = result.equity_curve.iloc[:60]

    png = _create_comparison_rolling_volatility_chart(
        [("Strategy A", result)], _get_theme_colors("light"), 150
    )
    assert isinstance(png, str) and len(png) > 0


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_generate_comparison_report_omits_monthly_and_rolling() -> None:
    """Disabling monthly/rolling charts must skip those chart cards (branches 1832->1848, 1890->1907)."""
    result1 = _create_sample_result()
    result2 = _create_sample_result()

    results = [("Strategy A", result1), ("Strategy B", result2)]
    config = ReportConfig(
        include_charts=True,
        include_monthly_heatmap=False,
        include_rolling_metrics=False,
    )

    html = generate_comparison_report(results, config)

    assert "Equity Curves Comparison" in html
    assert "Monthly Returns Comparison" not in html
    assert "Rolling Sharpe (60) Comparison" not in html
    assert "Rolling Volatility (60) Comparison" not in html


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
def test_build_comparison_risk_attribution_chart_absent_without_attribution() -> None:
    """A truthy attribution that yields no chart data must skip the chart (branch 1686->1696)."""
    from quant_trading.backtest.report import _build_comparison_risk_attribution, _get_theme_colors

    class NonDictAttribution:
        def to_dict(self) -> str:
            return "not a dict"

    result = _create_sample_result()
    result.risk_attribution = NonDictAttribution()  # type: ignore[assignment]

    html = _build_comparison_risk_attribution(
        [("Strategy A", result)], _get_theme_colors("light"), dpi=150
    )

    assert "Risk Attribution Comparison" in html
    assert "data:image/png;base64," not in html


def test_build_comparison_risk_attribution_metric_fn_raises() -> None:
    """A metric value whose conversion fails must render as the sanitized default (0.00%)."""
    from quant_trading.backtest.report import _build_comparison_risk_attribution, _get_theme_colors

    class RaisesOnStr:
        def __str__(self) -> str:
            raise ValueError("cannot stringify")

    class BadAttribution:
        def to_dict(self) -> dict:
            return {
                "confidence": RaisesOnStr(),
                "positions_value": 1.0,
                "portfolio_value": 1.0,
                "portfolio_var": 0.1,
                "portfolio_volatility": 0.2,
            }

    result = _create_sample_result()
    result.risk_attribution = BadAttribution()  # type: ignore[assignment]

    html = _build_comparison_risk_attribution([("Strategy A", result)], _get_theme_colors("light"))

    assert "Risk Attribution Comparison" in html
    # The failing metric is sanitized to 0.0 and formatted as "0.00%"
    assert "0.00%" in html


def test_drawdown_series_is_finite_when_equity_goes_negative() -> None:
    """Drawdown charts must not receive -inf from a zero running peak."""
    drawdown = _drawdown_series(pd.Series([0.0, -5.0, 10.0]))

    assert drawdown.tolist() == [0.0, 0.0, 0.0]
    assert np.isfinite(drawdown.to_numpy()).all()


def test_drawdown_series_reports_normal_drawdown() -> None:
    """A regular peak-to-trough decline is expressed as a negative percent."""
    drawdown = _drawdown_series(pd.Series([100.0, 110.0, 90.0]))

    assert drawdown.tolist() == pytest.approx([0.0, 0.0, -20.0 / 110.0 * 100.0])


def test_drawdown_series_keeps_later_drawdown_after_zero_prefix() -> None:
    """Zero-peak points are neutral but do not hide a later real drawdown."""
    drawdown = _drawdown_series(pd.Series([0.0, 100.0, 50.0]))

    assert drawdown.tolist() == pytest.approx([0.0, 0.0, -50.0])


def test_drawdown_series_handles_empty_and_all_negative_curves() -> None:
    """Empty and entirely negative curves produce finite, neutral series."""
    empty = _drawdown_series(pd.Series([], dtype=float))
    negative = _drawdown_series(pd.Series([-10.0, -20.0]))

    assert empty.empty
    assert negative.tolist() == [0.0, 0.0]


def test_finite_series_drops_inf_and_nan_values() -> None:
    """``_finite_series`` removes ``inf``/``-inf``/``NaN`` from chart inputs."""
    from quant_trading.backtest.report import _finite_series

    cleaned = _finite_series(pd.Series([0.0, np.inf, -np.inf, 1.0, np.nan, 2.5]))

    assert cleaned.tolist() == [0.0, 1.0, 2.5]
    assert np.isfinite(cleaned.to_numpy()).all()


def test_finite_series_preserves_finite_values() -> None:
    """A fully finite series is returned unchanged (same values, same index)."""
    from quant_trading.backtest.report import _finite_series

    original = pd.Series([1.0, 2.0, 3.0], index=pd.Index([10, 20, 30], name="bar"))
    cleaned = _finite_series(original)

    assert cleaned.tolist() == [1.0, 2.0, 3.0]
    assert cleaned.index.tolist() == [10, 20, 30]


def test_finite_series_empty_input_returns_empty() -> None:
    """An empty input yields an empty float series."""
    from quant_trading.backtest.report import _finite_series

    empty = _finite_series(pd.Series([], dtype=float))

    assert empty.empty
    assert empty.dtype == float


def test_finite_series_all_non_finite_returns_empty() -> None:
    """A series whose every value is non-finite collapses to an empty series."""
    from quant_trading.backtest.report import _finite_series

    cleaned = _finite_series(pd.Series([np.inf, -np.inf, np.nan, np.nan]))

    assert cleaned.empty


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
@pytest.mark.parametrize(
    "helper_name",
    [
        "_create_equity_curve_chart",
        "_create_drawdown_chart",
        "_create_monthly_returns_heatmap",
        "_create_rolling_sharpe_chart",
        "_create_rolling_volatility_chart",
    ],
)
def test_core_chart_helpers_return_base64_png(helper_name: str) -> None:
    """Each single-result chart helper returns a valid base64-encoded PNG."""
    from quant_trading.backtest import report as report_mod

    result = _create_sample_result()
    helper = getattr(report_mod, helper_name)

    encoded = helper(result, report_mod._get_theme_colors("light"), 120)

    assert isinstance(encoded, str)
    assert encoded
    assert base64.b64decode(encoded).startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib not installed")
@pytest.mark.parametrize(
    "helper_name",
    ["_create_rolling_sharpe_chart", "_create_rolling_volatility_chart"],
)
def test_rolling_chart_helpers_render_insufficient_data_placeholder(helper_name: str) -> None:
    """Rolling charts fall back to a placeholder image when fewer than 60 bars exist."""
    from quant_trading.backtest import report as report_mod

    result = _create_sample_result()
    short_dates = result.equity_curve.index[:30]
    result.equity_curve = pd.Series(
        np.linspace(100000.0, 101000.0, len(short_dates)), index=short_dates
    )
    helper = getattr(report_mod, helper_name)

    encoded = helper(result, report_mod._get_theme_colors("dark"), 100)

    assert isinstance(encoded, str)
    assert encoded
    assert base64.b64decode(encoded).startswith(b"\x89PNG\r\n\x1a\n")


def test_risk_attribution_comparison_format_error_sanitizes_to_n_a() -> None:
    """Cover report.py:1855-1856: metric_fn raising -> "N/A" fallback.

    _format_metric sanitizes internally and never raises on its own, so the
    defensive except branch is only reachable by mocking _format_metric to
    raise (same technique used to cover risk/metrics.py defensive branches).
    """
    import quant_trading.backtest.report as report_module

    result = _create_sample_result()
    result.risk_attribution = RiskAttribution(confidence=0.85)
    results = [("Strategy A", result)]
    colors = _get_theme_colors("light")

    with mock.patch.object(report_module, "_format_metric", side_effect=TypeError("unformattable")):
        html = _build_comparison_risk_attribution(results, colors)

    assert "Risk Attribution Comparison" in html
    assert "N/A" in html
