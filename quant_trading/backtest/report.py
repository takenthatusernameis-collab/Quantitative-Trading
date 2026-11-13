"""HTML report generation for backtest results.

This module provides functionality to generate comprehensive HTML reports
from backtest results, including equity curves, drawdown charts,
monthly returns heatmaps, trade distributions, and metrics tables.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_trading.backtest.engine import BacktestResult

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


@dataclass
class ReportConfig:
    """Configuration for report generation.

    Attributes:
        title: Report title.
        include_charts: Whether to include matplotlib charts (requires matplotlib).
        include_trade_details: Whether to include detailed trade table.
        include_monthly_heatmap: Whether to include monthly returns heatmap.
        include_rolling_metrics: Whether to include rolling metrics charts.
        theme: Color theme ("light" or "dark").
        dpi: DPI for chart images.
    """

    title: str = "Backtest Report"
    include_charts: bool = True
    include_trade_details: bool = True
    include_monthly_heatmap: bool = True
    include_rolling_metrics: bool = True
    theme: str = "light"
    dpi: int = 150

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report configuration to a dictionary.

        Returns:
            Dictionary of all report configuration fields.

        """
        return {
            "title": self.title,
            "include_charts": self.include_charts,
            "include_trade_details": self.include_trade_details,
            "include_monthly_heatmap": self.include_monthly_heatmap,
            "include_rolling_metrics": self.include_rolling_metrics,
            "theme": self.theme,
            "dpi": self.dpi,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReportConfig:
        """Deserialize a :class:`ReportConfig` from a dictionary.

        Missing keys fall back to the dataclass defaults, so a dictionary
        produced by :meth:`to_dict` (for example after a JSON round-trip) can
        be reconstructed without carrying every field. Extra keys are ignored.

        Args:
            data: Dictionary whose keys match report configuration attribute
                names.

        """
        return cls(
            title=data.get("title", "Backtest Report"),
            include_charts=data.get("include_charts", True),
            include_trade_details=data.get("include_trade_details", True),
            include_monthly_heatmap=data.get("include_monthly_heatmap", True),
            include_rolling_metrics=data.get("include_rolling_metrics", True),
            theme=data.get("theme", "light"),
            dpi=data.get("dpi", 150),
        )


def _check_matplotlib() -> None:
    """Raise ImportError if matplotlib is not available."""
    if not MATPLOTLIB_AVAILABLE:
        raise ImportError(
            "matplotlib is required for chart generation. "
            "Install with: pip install quant-trading[reporting]"
        )


def _fig_to_base64(fig: Any, dpi: int = 150) -> str:
    """Convert a matplotlib figure to a base64-encoded PNG string."""
    buf = io.BytesIO()
    savefig_kwargs: dict[str, Any] = {
        "format": "png",
        "dpi": dpi,
        "facecolor": fig.get_facecolor(),
    }
    # constrained_layout manages spacing; bbox_inches="tight" is redundant and
    # can conflict with the layout engine.
    layout_engine = fig.get_layout_engine()
    if layout_engine is None or not layout_engine.__class__.__name__.startswith("Constrained"):
        savefig_kwargs["bbox_inches"] = "tight"
    fig.savefig(buf, **savefig_kwargs)
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return img_base64


def _get_theme_colors(theme: str) -> dict[str, str]:
    """Get color palette for the specified theme."""
    if theme == "dark":
        return {
            "bg": "#1e1e1e",
            "fg": "#e0e0e0",
            "grid": "#333333",
            "positive": "#4caf50",
            "negative": "#f44336",
            "neutral": "#2196f3",
            "accent": "#ff9800",
            "table_header": "#2d2d2d",
            "table_row_even": "#252525",
            "table_row_odd": "#1e1e1e",
        }
    return {
        "bg": "#ffffff",
        "fg": "#212121",
        "grid": "#e0e0e0",
        "positive": "#2e7d32",
        "negative": "#c62828",
        "neutral": "#1565c0",
        "accent": "#ef6c00",
        "table_header": "#f5f5f5",
        "table_row_even": "#fafafa",
        "table_row_odd": "#ffffff",
    }


def _create_equity_curve_chart(result: BacktestResult, colors: dict[str, str], dpi: int) -> str:
    """Create equity curve chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 4), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    equity = result.equity_curve
    ax.plot(
        equity.index,
        equity.values,
        color=colors["neutral"],
        linewidth=1.5,
        label="Equity Curve",
    )

    # Add initial capital line
    ax.axhline(
        y=result.initial_capital,
        color=colors["fg"],
        linestyle="--",
        linewidth=0.8,
        alpha=0.5,
        label="Initial Capital",
    )

    ax.set_title("Equity Curve", color=colors["fg"], fontsize=14, fontweight="bold")
    ax.set_ylabel("Portfolio Value ($)", color=colors["fg"])
    ax.set_xlabel("Date", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"])

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_drawdown_chart(result: BacktestResult, colors: dict[str, str], dpi: int) -> str:
    """Create drawdown chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 3), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    equity = result.equity_curve
    peak = equity.expanding().max()
    drawdown = (equity - peak) / peak * 100

    ax.fill_between(
        drawdown.index,
        drawdown.values,
        0,
        color=colors["negative"],
        alpha=0.3,
        label="Drawdown",
    )
    ax.plot(
        drawdown.index,
        drawdown.values,
        color=colors["negative"],
        linewidth=1,
    )

    ax.axhline(y=0, color=colors["fg"], linewidth=0.5)
    ax.set_title("Drawdown (%)", color=colors["fg"], fontsize=14, fontweight="bold")
    ax.set_ylabel("Drawdown (%)", color=colors["fg"])
    ax.set_xlabel("Date", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_monthly_returns_heatmap(
    result: BacktestResult, colors: dict[str, str], dpi: int
) -> str:
    """Create monthly returns heatmap and return as base64 string."""
    _check_matplotlib()
    equity = result.equity_curve

    if len(equity) < 2:
        fig, ax = plt.subplots(figsize=(8, 4), dpi=dpi, facecolor=colors["bg"])
        ax.set_facecolor(colors["bg"])
        ax.text(
            0.5,
            0.5,
            "Insufficient data for monthly returns",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title("Monthly Returns", color=colors["fg"], fontsize=14, fontweight="bold")
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    # Resample to monthly and calculate returns
    monthly = equity.resample("ME").last()
    monthly_returns = monthly.pct_change().dropna() * 100

    if len(monthly_returns) == 0:
        fig, ax = plt.subplots(figsize=(8, 4), dpi=dpi, facecolor=colors["bg"])
        ax.set_facecolor(colors["bg"])
        ax.text(
            0.5,
            0.5,
            "Insufficient data for monthly returns",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title("Monthly Returns", color=colors["fg"], fontsize=14, fontweight="bold")
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    # Create pivot table for heatmap
    monthly_returns.index = pd.to_datetime(monthly_returns.index)
    pivot = monthly_returns.groupby(
        [monthly_returns.index.year, monthly_returns.index.month]
    ).first()
    pivot = pivot.unstack(level=1)

    # Ensure all 12 months are present as columns (fill missing with NaN)
    all_months = range(1, 13)
    pivot = pivot.reindex(columns=all_months)
    pivot.columns = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    fig, ax = plt.subplots(
        figsize=(10, 4),
        dpi=dpi,
        facecolor=colors["bg"],
        constrained_layout=True,
    )
    ax.set_facecolor(colors["bg"])

    im = ax.imshow(
        pivot.values,
        cmap="RdYlGn",
        aspect="auto",
        vmin=-max(abs(pivot.min().min()), abs(pivot.max().max())),
        vmax=max(abs(pivot.min().min()), abs(pivot.max().max())),
    )

    ax.set_xticks(range(12))
    ax.set_xticklabels(pivot.columns, color=colors["fg"])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(y) for y in pivot.index], color=colors["fg"])

    # Add text annotations
    for i in range(len(pivot.index)):
        for j in range(12):
            val = pivot.iloc[i, j]
            if not np.isnan(val):
                text_color = "white" if abs(val) > (pivot.max().max() * 0.5) else colors["fg"]
                ax.text(
                    j,
                    i,
                    f"{val:.1f}%",
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=9,
                    fontweight="bold",
                )

    ax.set_title("Monthly Returns (%)", color=colors["fg"], fontsize=14, fontweight="bold")

    # Add colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.ax.tick_params(colors=colors["fg"])
    cbar.outline.set_edgecolor(colors["grid"])

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_trade_distribution_chart(
    result: BacktestResult, colors: dict[str, str], dpi: int
) -> str:
    """Create trade PnL distribution chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 3.5), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    trades_df = result.trades
    if trades_df.empty or "pnl" not in trades_df.columns:
        ax.text(
            0.5,
            0.5,
            "No trades to display",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title("Trade PnL Distribution", color=colors["fg"], fontsize=14, fontweight="bold")
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    pnls = trades_df["pnl"].dropna()
    if len(pnls) == 0:
        ax.text(
            0.5,
            0.5,
            "No trade PnL data",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title("Trade PnL Distribution", color=colors["fg"], fontsize=14, fontweight="bold")
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    # Separate winning and losing trades
    winners = pnls[pnls > 0]
    losers = pnls[pnls <= 0]

    bins = 30
    ax.hist(
        winners,
        bins=bins,
        alpha=0.7,
        color=colors["positive"],
        label=f"Winners ({len(winners)})",
        edgecolor=colors["bg"],
        linewidth=0.5,
    )
    ax.hist(
        losers,
        bins=bins,
        alpha=0.7,
        color=colors["negative"],
        label=f"Losers ({len(losers)})",
        edgecolor=colors["bg"],
        linewidth=0.5,
    )

    ax.axvline(x=0, color=colors["fg"], linewidth=1, linestyle="-")
    ax.set_title("Trade PnL Distribution", color=colors["fg"], fontsize=14, fontweight="bold")
    ax.set_xlabel("PnL ($)", color=colors["fg"])
    ax.set_ylabel("Frequency", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"])

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_rolling_sharpe_chart(result: BacktestResult, colors: dict[str, str], dpi: int) -> str:
    """Create rolling Sharpe ratio chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 3), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    equity = result.equity_curve
    if len(equity) < 60:
        ax.text(
            0.5,
            0.5,
            "Insufficient data for rolling Sharpe (need 60+ bars)",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title(
            "Rolling Sharpe Ratio (60-period)", color=colors["fg"], fontsize=14, fontweight="bold"
        )
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    returns = equity.pct_change().dropna()
    rolling_sharpe = (
        returns.rolling(window=60).mean() / returns.rolling(window=60).std() * np.sqrt(252)
    )

    ax.plot(
        rolling_sharpe.index,
        rolling_sharpe.values,
        color=colors["accent"],
        linewidth=1,
        label="Rolling Sharpe (60)",
    )
    ax.axhline(y=0, color=colors["fg"], linewidth=0.5)
    ax.axhline(y=1, color=colors["positive"], linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axhline(y=-1, color=colors["negative"], linewidth=0.5, linestyle="--", alpha=0.5)

    ax.set_title(
        "Rolling Sharpe Ratio (60-period)", color=colors["fg"], fontsize=14, fontweight="bold"
    )
    ax.set_ylabel("Sharpe Ratio", color=colors["fg"])
    ax.set_xlabel("Date", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"])

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_rolling_volatility_chart(
    result: BacktestResult, colors: dict[str, str], dpi: int
) -> str:
    """Create rolling volatility chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 3), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    equity = result.equity_curve
    if len(equity) < 60:
        ax.text(
            0.5,
            0.5,
            "Insufficient data for rolling volatility (need 60+ bars)",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title(
            "Rolling Volatility (60-period)", color=colors["fg"], fontsize=14, fontweight="bold"
        )
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    returns = equity.pct_change().dropna()
    rolling_vol = returns.rolling(window=60).std() * np.sqrt(252) * 100

    ax.plot(
        rolling_vol.index,
        rolling_vol.values,
        color=colors["neutral"],
        linewidth=1,
        label="Rolling Vol (60)",
    )

    ax.set_title(
        "Rolling Volatility (60-period, Annualized %)",
        color=colors["fg"],
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Volatility (%)", color=colors["fg"])
    ax.set_xlabel("Date", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"])

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _format_metric(value: Any, fmt: str = "{:.2f}") -> str:
    """Format a metric value for display."""
    if value is None:
        return "N/A"
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return "N/A"
        return fmt.format(value)
    return str(value)


def _build_metrics_table(result: BacktestResult, colors: dict[str, str]) -> str:
    """Build HTML metrics table."""
    metrics = result.metrics

    rows = [
        ("Initial Capital", f"${result.initial_capital:,.2f}"),
        ("Final Value", f"${result.final_value:,.2f}"),
        ("Total Return", f"{result.total_return_pct:.2f}%"),
        ("Total Return ($)", f"${result.total_return:,.2f}"),
        ("Annualized Return", _format_metric(getattr(metrics, "annual_return", None), "{:.2f}%")),
        ("Volatility (Ann.)", _format_metric(getattr(metrics, "volatility", None), "{:.2f}%")),
        ("Sharpe Ratio", _format_metric(getattr(metrics, "sharpe_ratio", None))),
        ("Sortino Ratio", _format_metric(getattr(metrics, "sortino_ratio", None))),
        ("Calmar Ratio", _format_metric(getattr(metrics, "calmar_ratio", None))),
        ("Max Drawdown", _format_metric(getattr(metrics, "max_drawdown_pct", None), "{:.2f}%")),
        ("Max Drawdown ($)", _format_metric(getattr(metrics, "max_drawdown", None), "${:,.2f}")),
        ("Profit Factor", _format_metric(getattr(metrics, "profit_factor", None))),
        ("Win Rate", _format_metric(getattr(metrics, "win_rate", None), "{:.2%}")),
        ("Total Trades", _format_metric(getattr(metrics, "num_trades", None), "{:.0f}")),
        ("Avg Win", _format_metric(getattr(metrics, "avg_win", None), "${:,.2f}")),
        ("Avg Loss", _format_metric(getattr(metrics, "avg_loss", None), "${:,.2f}")),
        ("Best Trade", _format_metric(getattr(metrics, "best_trade", None), "${:,.2f}")),
        ("Worst Trade", _format_metric(getattr(metrics, "worst_trade", None), "${:,.2f}")),
        (
            "Avg Trade Duration",
            _format_metric(getattr(metrics, "avg_trade_duration", None), "{:.1f} bars"),
        ),
        ("Total Costs", f"${result.total_costs:,.2f}"),
    ]

    html = ['<table class="metrics-table">']
    html.append(
        f'<thead><tr><th style="background:{colors["table_header"]}">Metric</th><th style="background:{colors["table_header"]}">Value</th></tr></thead>'
    )
    html.append("<tbody>")
    for i, (name, value) in enumerate(rows):
        bg = colors["table_row_even"] if i % 2 == 0 else colors["table_row_odd"]
        html.append(
            f'<tr><td style="background:{bg}">{name}</td><td style="background:{bg}">{value}</td></tr>'
        )
    html.append("</tbody></table>")
    return "\n".join(html)


def _build_trades_table(result: BacktestResult, colors: dict[str, str], max_rows: int = 50) -> str:
    """Build HTML trades table."""
    trades_df = result.trades
    if trades_df.empty:
        return "<p>No trades executed.</p>"

    display_df = trades_df.copy()
    if len(display_df) > max_rows:
        display_df = display_df.head(max_rows)

    # Format columns
    if "timestamp" in display_df.columns:
        display_df["timestamp"] = pd.to_datetime(display_df["timestamp"]).dt.strftime(
            "%Y-%m-%d %H:%M"
        )
    for col in ["price", "cost", "fee", "pnl"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A"
            )
    if "quantity" in display_df.columns:
        display_df["quantity"] = display_df["quantity"].apply(
            lambda x: f"{x:.4f}" if pd.notna(x) else "N/A"
        )
    if "commission" in display_df.columns:
        display_df["commission"] = display_df["commission"].apply(
            lambda x: f"{x:.4%}" if pd.notna(x) else "N/A"
        )
    if "slippage" in display_df.columns:
        display_df["slippage"] = display_df["slippage"].apply(
            lambda x: f"{x:.4%}" if pd.notna(x) else "N/A"
        )

    html = ['<div class="table-container"><table class="trades-table">']
    headers = display_df.columns.tolist()
    html.append("<thead><tr>")
    for h in headers:
        html.append(f'<th style="background:{colors["table_header"]}">{h}</th>')
    html.append("</tr></thead><tbody>")

    for i, row in display_df.iterrows():
        bg = colors["table_row_even"] if i % 2 == 0 else colors["table_row_odd"]
        html.append(f'<tr style="background:{bg}">')
        for h in headers:
            html.append(f"<td>{row[h]}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div>")

    if len(trades_df) > max_rows:
        html.append(f"<p class='note'>Showing first {max_rows} of {len(trades_df)} trades.</p>")

    return "\n".join(html)


def _build_risk_attribution_table(result: BacktestResult, colors: dict[str, str]) -> str:
    """Build HTML risk attribution table."""
    attr = getattr(result, "risk_attribution", None)
    if attr is None:
        return ""

    data = attr.to_dict() if hasattr(attr, "to_dict") else attr
    if not isinstance(data, dict):
        return ""

    summary_rows = [
        ("Confidence", _format_metric(data.get("confidence"), "{:.2%}")),
        ("Positions Value", _format_metric(data.get("positions_value"), "${:,.2f}")),
        ("Portfolio Value", _format_metric(data.get("portfolio_value"), "${:,.2f}")),
        ("Portfolio VaR", _format_metric(data.get("portfolio_var"), "{:.4f}")),
        ("Portfolio Volatility", _format_metric(data.get("portfolio_volatility"), "{:.4f}")),
    ]

    html = ['<div class="risk-attribution">']
    html.append('<table class="metrics-table">')
    html.append(
        f'<thead><tr><th style="background:{colors["table_header"]}">Metric</th>'
        f'<th style="background:{colors["table_header"]}">Value</th></tr></thead>'
    )
    html.append("<tbody>")
    for i, (name, value) in enumerate(summary_rows):
        bg = colors["table_row_even"] if i % 2 == 0 else colors["table_row_odd"]
        html.append(
            f'<tr><td style="background:{bg}">{name}</td><td style="background:{bg}">{value}</td></tr>'
        )
    html.append("</tbody></table>")

    symbols = sorted(
        set(
            list((data.get("weights") or {}).keys())
            + list((data.get("marginal_var") or {}).keys())
            + list((data.get("component_var") or {}).keys())
            + list((data.get("volatility_contributions") or {}).keys())
        )
    )
    if symbols:
        headers = ["Symbol", "Weight", "Marginal VaR", "Component VaR", "Volatility Contribution"]
        html.append('<div class="table-container"><table class="trades-table">')
        html.append("<thead><tr>")
        for h in headers:
            html.append(f'<th style="background:{colors["table_header"]}">{h}</th>')
        html.append("</tr></thead><tbody>")
        for i, symbol in enumerate(symbols):
            bg = colors["table_row_even"] if i % 2 == 0 else colors["table_row_odd"]
            weight = (data.get("weights") or {}).get(symbol)
            mvar = (data.get("marginal_var") or {}).get(symbol)
            cvar = (data.get("component_var") or {}).get(symbol)
            volc = (data.get("volatility_contributions") or {}).get(symbol)
            html.append(f'<tr style="background:{bg}">')
            html.append(f"<td>{symbol}</td>")
            html.append(f"<td>{_format_metric(weight, '{:.4f}')}</td>")
            html.append(f"<td>{_format_metric(mvar, '{:.6f}')}</td>")
            html.append(f"<td>{_format_metric(cvar, '{:.6f}')}</td>")
            html.append(f"<td>{_format_metric(volc, '{:.6f}')}</td>")
            html.append("</tr>")
        html.append("</tbody></table></div>")

    html.append("</div>")
    return "\n".join(html)


def generate_html_report(
    result: BacktestResult,
    config: ReportConfig | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate an HTML report from a backtest result.

    Args:
        result: BacktestResult object from a backtest run.
        config: Optional ReportConfig for customization.
        output_path: Optional path to write the HTML file.

    Returns:
        HTML string of the report.

    Raises:
        ImportError: If matplotlib is required but not installed.
    """
    if config is None:
        config = ReportConfig()

    if config.include_charts:
        _check_matplotlib()

    colors = _get_theme_colors(config.theme)

    # Generate charts if enabled
    equity_chart = ""
    drawdown_chart = ""
    monthly_heatmap = ""
    trade_dist_chart = ""
    rolling_sharpe_chart = ""
    rolling_vol_chart = ""

    if config.include_charts:
        equity_chart = _create_equity_curve_chart(result, colors, config.dpi)
        drawdown_chart = _create_drawdown_chart(result, colors, config.dpi)

        if config.include_monthly_heatmap:
            monthly_heatmap = _create_monthly_returns_heatmap(result, colors, config.dpi)

        trade_dist_chart = _create_trade_distribution_chart(result, colors, config.dpi)

        if config.include_rolling_metrics:
            rolling_sharpe_chart = _create_rolling_sharpe_chart(result, colors, config.dpi)
            rolling_vol_chart = _create_rolling_volatility_chart(result, colors, config.dpi)

    # Build metrics table
    metrics_table = _build_metrics_table(result, colors)

    # Build risk attribution table
    risk_attribution_table = _build_risk_attribution_table(result, colors)

    # Build trades table
    trades_table = ""
    if config.include_trade_details:
        trades_table = _build_trades_table(result, colors)

    # Build HTML
    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>{config.title}</title>",
        f"<style>{_get_css(colors)}</style>",
        "</head>",
        "<body>",
        '<div class="container">',
        '<header class="report-header">',
        f"<h1>{config.title}</h1>",
        '<div class="report-meta">',
        f'<span>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>',
        f'<span>Period: {result.start_date.strftime("%Y-%m-%d")} to {result.end_date.strftime("%Y-%m-%d")}</span>',
        f'<span>Symbols: {", ".join(result.positions.keys()) if result.positions else "N/A"}</span>',
        "</div>",
        "</header>",
        '<section class="section">',
        "<h2>Performance Summary</h2>",
        metrics_table,
        "</section>",
    ]

    if risk_attribution_table:
        html_parts.extend(
            [
                '<section class="section">',
                "<h2>Risk Attribution</h2>",
                risk_attribution_table,
                "</section>",
            ]
        )

    if config.include_charts:
        html_parts.extend(
            [
                '<section class="section">',
                "<h2>Charts</h2>",
                '<div class="chart-grid">',
                f'<div class="chart-card"><h3>Equity Curve</h3><img src="data:image/png;base64,{equity_chart}" alt="Equity Curve"></div>',
                f'<div class="chart-card"><h3>Drawdown</h3><img src="data:image/png;base64,{drawdown_chart}" alt="Drawdown"></div>',
            ]
        )
        if monthly_heatmap:
            html_parts.append(
                f'<div class="chart-card full-width"><h3>Monthly Returns</h3><img src="data:image/png;base64,{monthly_heatmap}" alt="Monthly Returns"></div>'
            )
        html_parts.extend(
            [
                f'<div class="chart-card"><h3>Trade PnL Distribution</h3><img src="data:image/png;base64,{trade_dist_chart}" alt="Trade PnL Distribution"></div>',
            ]
        )
        if rolling_sharpe_chart:
            html_parts.append(
                f'<div class="chart-card"><h3>Rolling Sharpe (60)</h3><img src="data:image/png;base64,{rolling_sharpe_chart}" alt="Rolling Sharpe"></div>'
            )
        if rolling_vol_chart:
            html_parts.append(
                f'<div class="chart-card"><h3>Rolling Volatility (60)</h3><img src="data:image/png;base64,{rolling_vol_chart}" alt="Rolling Volatility"></div>'
            )
        html_parts.extend(["</div>", "</section>"])

    if config.include_trade_details:
        html_parts.extend(
            [
                '<section class="section">',
                "<h2>Trade Details</h2>",
                trades_table,
                "</section>",
            ]
        )

    html_parts.extend(
        [
            '<footer class="report-footer">',
            "<p>Generated by Quantitative Trading Framework</p>",
            "</footer>",
            "</div>",
            "</body>",
            "</html>",
        ]
    )

    html = "\n".join(html_parts)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

    return html


def _get_css(colors: dict[str, str]) -> str:
    """Generate CSS for the report."""
    return f"""
    * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background-color: {colors["bg"]};
        color: {colors["fg"]};
        line-height: 1.6;
    }}
    .container {{
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }}
    .report-header {{
        text-align: center;
        margin-bottom: 30px;
        padding-bottom: 20px;
        border-bottom: 1px solid {colors["grid"]};
    }}
    .report-header h1 {{
        font-size: 2rem;
        margin-bottom: 10px;
        color: {colors["fg"]};
    }}
    .report-meta {{
        display: flex;
        justify-content: center;
        gap: 20px;
        flex-wrap: wrap;
        font-size: 0.9rem;
        color: {colors["fg"]};
        opacity: 0.8;
    }}
    .section {{
        margin-bottom: 40px;
    }}
    .section h2 {{
        font-size: 1.5rem;
        margin-bottom: 15px;
        color: {colors["fg"]};
        border-bottom: 2px solid {colors["neutral"]};
        padding-bottom: 5px;
    }}
    .section h3 {{
        font-size: 1.1rem;
        margin-bottom: 10px;
        color: {colors["fg"]};
    }}
    .metrics-table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 20px;
    }}
    .metrics-table td {{
        padding: 10px 15px;
        border: 1px solid {colors["grid"]};
    }}
    .metrics-table td:first-child {{
        font-weight: 600;
    }}
    .chart-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
        gap: 20px;
    }}
    .chart-card {{
        background: {colors["table_row_even"]};
        border: 1px solid {colors["grid"]};
        border-radius: 8px;
        padding: 15px;
    }}
    .chart-card.full-width {{
        grid-column: 1 / -1;
    }}
    .chart-card img {{
        width: 100%;
        height: auto;
        border-radius: 4px;
    }}
    .table-container {{
        overflow-x: auto;
    }}
    .trades-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }}
    .trades-table th {{
        padding: 10px 12px;
        text-align: left;
        border: 1px solid {colors["grid"]};
        font-weight: 600;
    }}
    .trades-table td {{
        padding: 8px 12px;
        border: 1px solid {colors["grid"]};
    }}
    .note {{
        margin-top: 10px;
        font-size: 0.85rem;
        opacity: 0.7;
    }}
    .report-footer {{
        text-align: center;
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px solid {colors["grid"]};
        opacity: 0.6;
        font-size: 0.85rem;
    }}
    @media (max-width: 768px) {{
        .chart-grid {{
            grid-template-columns: 1fr;
        }}
        .report-meta {{
            flex-direction: column;
            gap: 5px;
        }}
    }}
    """


def generate_report_from_dict(
    data: dict[str, Any],
    config: ReportConfig | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate an HTML report from a dictionary (e.g., loaded from JSON).

    Args:
        data: Dictionary with backtest result data (from BacktestResult.to_dict()).
        config: Optional ReportConfig for customization.
        output_path: Optional path to write the HTML file.

    Returns:
        HTML string of the report.
    """
    result = BacktestResult.from_dict(data)
    return generate_html_report(result, config, output_path)


def _create_comparison_equity_chart(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
    dpi: int,
) -> str:
    """Create comparison equity curve chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 4), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    # Use a color palette for multiple strategies
    palette = [
        colors["neutral"],
        colors["positive"],
        colors["negative"],
        colors["accent"],
        "#9c27b0",
        "#00bcd4",
        "#ff5722",
        "#795548",
    ]

    for i, (name, result) in enumerate(results):
        equity = result.equity_curve
        if len(equity) > 0:
            color = palette[i % len(palette)]
            ax.plot(
                equity.index,
                equity.values,
                color=color,
                linewidth=1.5,
                label=name,
                alpha=0.8,
            )

    ax.set_title("Equity Curves Comparison", color=colors["fg"], fontsize=14, fontweight="bold")
    ax.set_ylabel("Portfolio Value ($)", color=colors["fg"])
    ax.set_xlabel("Date", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"], fontsize=8)

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_comparison_drawdown_chart(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
    dpi: int,
) -> str:
    """Create comparison drawdown chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 3), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    palette = [
        colors["neutral"],
        colors["positive"],
        colors["negative"],
        colors["accent"],
        "#9c27b0",
        "#00bcd4",
        "#ff5722",
        "#795548",
    ]

    for i, (name, result) in enumerate(results):
        equity = result.equity_curve
        if len(equity) > 0:
            color = palette[i % len(palette)]
            peak = equity.expanding().max()
            drawdown = (equity - peak) / peak * 100
            ax.plot(
                drawdown.index,
                drawdown.values,
                color=color,
                linewidth=1,
                label=name,
                alpha=0.8,
            )

    ax.axhline(y=0, color=colors["fg"], linewidth=0.5)
    ax.set_title("Drawdown Comparison (%)", color=colors["fg"], fontsize=14, fontweight="bold")
    ax.set_ylabel("Drawdown (%)", color=colors["fg"])
    ax.set_xlabel("Date", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"], fontsize=8)

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_comparison_monthly_returns_heatmap(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
    dpi: int,
) -> str:
    """Create comparison monthly returns heatmap and return as base64 string."""
    _check_matplotlib()
    n_results = len(results)
    if n_results == 0:
        return ""

    fig, axes = plt.subplots(
        1,
        n_results,
        figsize=(8 * n_results, 4),
        dpi=dpi,
        facecolor=colors["bg"],
        squeeze=False,
        constrained_layout=True,
    )
    axes = axes[0]

    for i, (name, result) in enumerate(results):
        ax = axes[i]
        ax.set_facecolor(colors["bg"])
        equity = result.equity_curve

        if len(equity) < 2:
            ax.text(
                0.5,
                0.5,
                "Insufficient data",
                ha="center",
                va="center",
                color=colors["fg"],
                transform=ax.transAxes,
            )
            ax.set_title(
                f"{name} - Monthly Returns", color=colors["fg"], fontsize=12, fontweight="bold"
            )
            ax.axis("off")
            continue

        monthly = equity.resample("ME").last()
        monthly_returns = monthly.pct_change().dropna() * 100

        if len(monthly_returns) == 0:
            ax.text(
                0.5,
                0.5,
                "Insufficient data",
                ha="center",
                va="center",
                color=colors["fg"],
                transform=ax.transAxes,
            )
            ax.set_title(
                f"{name} - Monthly Returns", color=colors["fg"], fontsize=12, fontweight="bold"
            )
            ax.axis("off")
            continue

        monthly_returns.index = pd.to_datetime(monthly_returns.index)
        pivot = monthly_returns.groupby(
            [monthly_returns.index.year, monthly_returns.index.month]
        ).first()
        pivot = pivot.unstack(level=1)

        all_months = range(1, 13)
        pivot = pivot.reindex(columns=all_months)
        pivot.columns = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        vmin = -max(abs(pivot.min().min()), abs(pivot.max().max())) if not pivot.empty else -1
        vmax = max(abs(pivot.min().min()), abs(pivot.max().max())) if not pivot.empty else 1

        im = ax.imshow(
            pivot.values,
            cmap="RdYlGn",
            aspect="auto",
            vmin=vmin,
            vmax=vmax,
        )

        ax.set_xticks(range(12))
        ax.set_xticklabels(pivot.columns, color=colors["fg"], fontsize=8)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels([str(y) for y in pivot.index], color=colors["fg"], fontsize=8)

        for row_idx in range(len(pivot.index)):
            for col_idx in range(12):
                val = pivot.iloc[row_idx, col_idx]
                if not np.isnan(val):
                    text_color = "white" if abs(val) > (pivot.max().max() * 0.5) else colors["fg"]
                    ax.text(
                        col_idx,
                        row_idx,
                        f"{val:.1f}%",
                        ha="center",
                        va="center",
                        color=text_color,
                        fontsize=7,
                        fontweight="bold",
                    )

        ax.set_title(
            f"{name} - Monthly Returns (%)", color=colors["fg"], fontsize=12, fontweight="bold"
        )

        for spine in ax.spines.values():
            spine.set_color(colors["grid"])

    cbar = fig.colorbar(im, ax=axes, shrink=0.6)
    cbar.ax.tick_params(colors=colors["fg"])
    cbar.outline.set_edgecolor(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_comparison_trade_distribution_chart(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
    dpi: int,
) -> str:
    """Create comparison trade PnL distribution chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 4), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    palette = [
        colors["neutral"],
        colors["positive"],
        colors["negative"],
        colors["accent"],
        "#9c27b0",
        "#00bcd4",
        "#ff5722",
        "#795548",
    ]

    any_data = False
    for i, (name, result) in enumerate(results):
        trades_df = result.trades
        if trades_df.empty or "pnl" not in trades_df.columns:
            continue

        pnls = trades_df["pnl"].dropna()
        if len(pnls) == 0:
            continue

        winners = pnls[pnls > 0]
        losers = pnls[pnls <= 0]

        color = palette[i % len(palette)]
        alpha = 0.5 if len(results) > 1 else 0.7

        bins = 30
        ax.hist(
            winners,
            bins=bins,
            alpha=alpha,
            color=color,
            label=f"{name} Winners ({len(winners)})",
            edgecolor=colors["bg"],
            linewidth=0.5,
            histtype="stepfilled",
        )
        ax.hist(
            losers,
            bins=bins,
            alpha=alpha,
            color=color,
            label=f"{name} Losers ({len(losers)})",
            edgecolor=colors["bg"],
            linewidth=0.5,
            histtype="step",
            linestyle="--",
        )
        any_data = True

    if not any_data:
        ax.text(
            0.5,
            0.5,
            "No trade PnL data to display",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title(
            "Trade PnL Distribution Comparison", color=colors["fg"], fontsize=14, fontweight="bold"
        )
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    ax.axvline(x=0, color=colors["fg"], linewidth=1, linestyle="-")
    ax.set_title(
        "Trade PnL Distribution Comparison", color=colors["fg"], fontsize=14, fontweight="bold"
    )
    ax.set_xlabel("PnL ($)", color=colors["fg"])
    ax.set_ylabel("Frequency", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"], fontsize=7)

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_comparison_rolling_sharpe_chart(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
    dpi: int,
) -> str:
    """Create comparison rolling Sharpe ratio chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 3), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    palette = [
        colors["neutral"],
        colors["positive"],
        colors["negative"],
        colors["accent"],
        "#9c27b0",
        "#00bcd4",
        "#ff5722",
        "#795548",
    ]

    any_data = False
    for i, (name, result) in enumerate(results):
        equity = result.equity_curve
        if len(equity) < 60:
            continue

        returns = equity.pct_change().dropna()
        rolling_sharpe = (
            returns.rolling(window=60).mean() / returns.rolling(window=60).std() * np.sqrt(252)
        )

        if rolling_sharpe.dropna().empty:
            continue

        color = palette[i % len(palette)]
        ax.plot(
            rolling_sharpe.index,
            rolling_sharpe.values,
            color=color,
            linewidth=1,
            label=name,
            alpha=0.8,
        )
        any_data = True

    if not any_data:
        ax.text(
            0.5,
            0.5,
            "Insufficient data for rolling Sharpe (need 60+ bars)",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title(
            "Rolling Sharpe Ratio (60-period) Comparison",
            color=colors["fg"],
            fontsize=14,
            fontweight="bold",
        )
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    ax.axhline(y=0, color=colors["fg"], linewidth=0.5)
    ax.axhline(y=1, color=colors["positive"], linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axhline(y=-1, color=colors["negative"], linewidth=0.5, linestyle="--", alpha=0.5)
    ax.set_title(
        "Rolling Sharpe Ratio (60-period) Comparison",
        color=colors["fg"],
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Sharpe Ratio", color=colors["fg"])
    ax.set_xlabel("Date", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"], fontsize=8)

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _create_comparison_rolling_volatility_chart(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
    dpi: int,
) -> str:
    """Create comparison rolling volatility chart and return as base64 string."""
    _check_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 3), dpi=dpi, facecolor=colors["bg"])
    ax.set_facecolor(colors["bg"])

    palette = [
        colors["neutral"],
        colors["positive"],
        colors["negative"],
        colors["accent"],
        "#9c27b0",
        "#00bcd4",
        "#ff5722",
        "#795548",
    ]

    any_data = False
    for i, (name, result) in enumerate(results):
        equity = result.equity_curve
        if len(equity) < 60:
            continue

        returns = equity.pct_change().dropna()
        rolling_vol = returns.rolling(window=60).std() * np.sqrt(252) * 100

        if rolling_vol.dropna().empty:
            continue

        color = palette[i % len(palette)]
        ax.plot(
            rolling_vol.index,
            rolling_vol.values,
            color=color,
            linewidth=1,
            label=name,
            alpha=0.8,
        )
        any_data = True

    if not any_data:
        ax.text(
            0.5,
            0.5,
            "Insufficient data for rolling volatility (need 60+ bars)",
            ha="center",
            va="center",
            color=colors["fg"],
            transform=ax.transAxes,
        )
        ax.set_title(
            "Rolling Volatility (60-period, Annualized %) Comparison",
            color=colors["fg"],
            fontsize=14,
            fontweight="bold",
        )
        ax.axis("off")
        return _fig_to_base64(fig, dpi)

    ax.set_title(
        "Rolling Volatility (60-period, Annualized %) Comparison",
        color=colors["fg"],
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Volatility (%)", color=colors["fg"])
    ax.set_xlabel("Date", color=colors["fg"])
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(facecolor=colors["bg"], edgecolor=colors["grid"], labelcolor=colors["fg"], fontsize=8)

    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _build_comparison_table(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
) -> str:
    """Build HTML comparison table for multiple strategies."""
    rows = [
        ("Initial Capital", lambda r: f"${r.initial_capital:,.2f}"),
        ("Final Value", lambda r: f"${r.final_value:,.2f}"),
        ("Total Return", lambda r: f"{r.total_return_pct:.2f}%"),
        ("Total Return ($)", lambda r: f"${r.total_return:,.2f}"),
        (
            "Annualized Return",
            lambda r: _format_metric(getattr(r.metrics, "annual_return", None), "{:.2f}%"),
        ),
        (
            "Volatility (Ann.)",
            lambda r: _format_metric(getattr(r.metrics, "volatility", None), "{:.2f}%"),
        ),
        ("Sharpe Ratio", lambda r: _format_metric(getattr(r.metrics, "sharpe_ratio", None))),
        ("Sortino Ratio", lambda r: _format_metric(getattr(r.metrics, "sortino_ratio", None))),
        ("Calmar Ratio", lambda r: _format_metric(getattr(r.metrics, "calmar_ratio", None))),
        (
            "Max Drawdown",
            lambda r: _format_metric(getattr(r.metrics, "max_drawdown_pct", None), "{:.2f}%"),
        ),
        (
            "Max Drawdown ($)",
            lambda r: _format_metric(getattr(r.metrics, "max_drawdown", None), "${:,.2f}"),
        ),
        ("Profit Factor", lambda r: _format_metric(getattr(r.metrics, "profit_factor", None))),
        ("Win Rate", lambda r: _format_metric(getattr(r.metrics, "win_rate", None), "{:.2%}")),
        (
            "Total Trades",
            lambda r: _format_metric(getattr(r.metrics, "num_trades", None), "{:.0f}"),
        ),
        ("Avg Win", lambda r: _format_metric(getattr(r.metrics, "avg_win", None), "${:,.2f}")),
        ("Avg Loss", lambda r: _format_metric(getattr(r.metrics, "avg_loss", None), "${:,.2f}")),
        (
            "Best Trade",
            lambda r: _format_metric(getattr(r.metrics, "best_trade", None), "${:,.2f}"),
        ),
        (
            "Worst Trade",
            lambda r: _format_metric(getattr(r.metrics, "worst_trade", None), "${:,.2f}"),
        ),
        (
            "Avg Trade Duration",
            lambda r: _format_metric(getattr(r.metrics, "avg_trade_duration", None), "{:.1f} bars"),
        ),
        ("Total Costs", lambda r: f"${r.total_costs:,.2f}"),
    ]

    header = [f'<thead><tr><th style="background:{colors["table_header"]}">Metric</th>']
    for name, _ in results:
        header.append(f'<th style="background:{colors["table_header"]}">{name}</th>')
    header.append("</tr></thead>")

    html = ['<table class="metrics-table comparison-table">']
    html.extend(header)
    html.append("<tbody>")
    for i, (metric_name, metric_fn) in enumerate(rows):
        bg = colors["table_row_even"] if i % 2 == 0 else colors["table_row_odd"]
        html.append(f'<tr><td style="background:{bg}">{metric_name}</td>')
        for name, result in results:
            try:
                value = metric_fn(result)
            except (AttributeError, TypeError, ValueError):
                value = "N/A"
            html.append(f'<td style="background:{bg}">{value}</td>')
        html.append("</tr>")
    html.append("</tbody></table>")
    return "\n".join(html)


def _build_comparison_risk_attribution(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
    dpi: int | None = None,
) -> str:
    """Build HTML risk attribution comparison section for multiple strategies."""
    has_attribution = any(getattr(result, "risk_attribution", None) for _, result in results)
    if not has_attribution:
        return ""

    palette = [
        colors["neutral"],
        colors["positive"],
        colors["negative"],
        colors["accent"],
        "#9c27b0",
        "#00bcd4",
        "#ff5722",
        "#795548",
    ]

    html = ['<section class="section">', "<h2>Risk Attribution Comparison</h2>"]

    # Summary metrics table
    summary_rows = [
        ("Confidence", lambda d: _format_metric(d.get("confidence"), "{:.2%}")),
        ("Positions Value", lambda d: _format_metric(d.get("positions_value"), "${:,.2f}")),
        ("Portfolio Value", lambda d: _format_metric(d.get("portfolio_value"), "${:,.2f}")),
        ("Portfolio VaR", lambda d: _format_metric(d.get("portfolio_var"), "{:.4f}")),
        ("Portfolio Volatility", lambda d: _format_metric(d.get("portfolio_volatility"), "{:.4f}")),
    ]

    html.append('<table class="metrics-table comparison-table">')
    header = [f'<thead><tr><th style="background:{colors["table_header"]}">Metric</th>']
    for name, _ in results:
        header.append(f'<th style="background:{colors["table_header"]}">{name}</th>')
    header.append("</tr></thead>")
    html.extend(header)
    html.append("<tbody>")
    for i, (metric_name, metric_fn) in enumerate(summary_rows):
        bg = colors["table_row_even"] if i % 2 == 0 else colors["table_row_odd"]
        html.append(f'<tr><td style="background:{bg}">{metric_name}</td>')
        for _, result in results:
            attr = getattr(result, "risk_attribution", None)
            if attr is not None:
                data = attr.to_dict() if hasattr(attr, "to_dict") else attr
                if isinstance(data, dict):
                    try:
                        value = metric_fn(data)
                    except (TypeError, ValueError, KeyError):
                        value = "N/A"
                else:
                    value = "N/A"
            else:
                value = "N/A"
            html.append(f'<td style="background:{bg}">{value}</td>')
        html.append("</tr>")
    html.append("</tbody></table>")

    # Per-symbol breakdown for each strategy
    for idx, (name, result) in enumerate(results):
        attr = getattr(result, "risk_attribution", None)
        if attr is None:
            continue

        data = attr.to_dict() if hasattr(attr, "to_dict") else attr
        if not isinstance(data, dict):
            continue

        symbols = sorted(
            set(
                list((data.get("weights") or {}).keys())
                + list((data.get("marginal_var") or {}).keys())
                + list((data.get("component_var") or {}).keys())
                + list((data.get("volatility_contributions") or {}).keys())
            )
        )

        if not symbols:
            continue

        color = palette[idx % len(palette)]
        html.append(
            f'<h3 style="color:{color}; margin-top:20px;">{name} - Position Breakdown</h3>'
        )
        headers = ["Symbol", "Weight", "Marginal VaR", "Component VaR", "Volatility Contribution"]
        html.append('<div class="table-container"><table class="trades-table">')
        html.append("<thead><tr>")
        for h in headers:
            html.append(f'<th style="background:{colors["table_header"]}">{h}</th>')
        html.append("</tr></thead><tbody>")
        for i, symbol in enumerate(symbols):
            bg = colors["table_row_even"] if i % 2 == 0 else colors["table_row_odd"]
            weight = (data.get("weights") or {}).get(symbol)
            mvar = (data.get("marginal_var") or {}).get(symbol)
            cvar = (data.get("component_var") or {}).get(symbol)
            volc = (data.get("volatility_contributions") or {}).get(symbol)
            html.append(f'<tr style="background:{bg}">')
            html.append(f"<td>{symbol}</td>")
            html.append(f"<td>{_format_metric(weight, '{:.4f}')}</td>")
            html.append(f"<td>{_format_metric(mvar, '{:.6f}')}</td>")
            html.append(f"<td>{_format_metric(cvar, '{:.6f}')}</td>")
            html.append(f"<td>{_format_metric(volc, '{:.6f}')}</td>")
            html.append("</tr>")
        html.append("</tbody></table></div>")

    if dpi is not None:
        chart = _create_comparison_risk_attribution_chart(results, colors, dpi)
        if chart:
            html.extend(
                [
                    '<div class="chart-card full-width">',
                    '<h3 style="margin-top:24px;">Risk Attribution: Portfolio VaR &amp; Volatility</h3>',
                    f'<img src="data:image/png;base64,{chart}" alt="Risk Attribution Comparison Chart">',
                    "</div>",
                ]
            )

    html.append("</section>")
    return "\n".join(html)


def _create_comparison_risk_attribution_chart(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
    dpi: int,
) -> str:
    """Create comparison risk attribution chart and return as base64 string."""
    _check_matplotlib()
    strategy_names: list[str] = []
    var_values: list[float] = []
    vol_values: list[float] = []
    for name, result in results:
        attr = getattr(result, "risk_attribution", None)
        if attr is None:
            continue
        data = attr.to_dict() if hasattr(attr, "to_dict") else attr
        if not isinstance(data, dict):
            continue
        strategy_names.append(name)
        var_values.append(float(data.get("portfolio_var", 0) or 0))
        vol_values.append(float(data.get("portfolio_volatility", 0) or 0))
    if not strategy_names:
        return ""

    fig, ax = plt.subplots(
        figsize=(10, 4), dpi=dpi, facecolor=colors["bg"], constrained_layout=True
    )
    ax.set_facecolor(colors["bg"])

    x = np.arange(len(strategy_names))
    width = 0.35
    ax.bar(
        x - width / 2,
        var_values,
        width,
        label="Portfolio VaR",
        color=colors["negative"],
        alpha=0.8,
    )
    ax.bar(
        x + width / 2,
        vol_values,
        width,
        label="Portfolio Volatility",
        color=colors["neutral"],
        alpha=0.8,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(strategy_names, color=colors["fg"], fontsize=9)
    ax.set_ylabel("Value", color=colors["fg"])
    ax.set_title(
        "Risk Attribution Comparison", color=colors["fg"], fontsize=14, fontweight="bold"
    )
    ax.tick_params(colors=colors["fg"])
    ax.grid(True, axis="y", color=colors["grid"], alpha=0.3, linestyle="-", linewidth=0.5)
    ax.legend(
        facecolor=colors["bg"],
        edgecolor=colors["grid"],
        labelcolor=colors["fg"],
        fontsize=9,
    )
    for spine in ax.spines.values():
        spine.set_color(colors["grid"])

    return _fig_to_base64(fig, dpi)


def _build_comparison_summary_cards(
    results: list[tuple[str, BacktestResult]],
    colors: dict[str, str],
) -> str:
    """Build summary cards for each strategy."""
    html = ['<div class="summary-cards">']
    for name, result in results:
        metrics = result.metrics
        html.append(f"""
        <div class="summary-card" style="background:{colors["table_row_even"]}; border:1px solid {colors["grid"]}; border-radius:8px; padding:15px; margin:10px 0;">
            <h3 style="margin:0 0 10px 0; color:{colors["fg"]};">{name}</h3>
            <div style="display:flex; flex-wrap:wrap; gap:20px;">
                <div><strong>Return:</strong> {result.total_return_pct:.2f}%</div>
                <div><strong>Sharpe:</strong> {getattr(metrics, "sharpe_ratio", 0):.2f}</div>
                <div><strong>Max DD:</strong> {getattr(metrics, "max_drawdown_pct", 0):.2f}%</div>
                <div><strong>Win Rate:</strong> {getattr(metrics, "win_rate", 0):.1%}</div>
                <div><strong>Trades:</strong> {getattr(metrics, "num_trades", 0)}</div>
                <div><strong>Costs:</strong> ${result.total_costs:,.2f}</div>
            </div>
        </div>
        """)
    html.append("</div>")
    return "\n".join(html)


def generate_comparison_report(
    results: list[tuple[str, BacktestResult]],
    config: ReportConfig | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Generate an HTML comparison report from multiple backtest results.

    Args:
        results: List of (strategy_name, BacktestResult) tuples.
        config: Optional ReportConfig for customization.
        output_path: Optional path to write the HTML file.

    Returns:
        HTML string of the report.

    Raises:
        ImportError: If matplotlib is required but not installed.
        ValueError: If results list is empty.
    """
    if not results:
        raise ValueError("At least one result is required for comparison report")

    if config is None:
        config = ReportConfig()

    if config.include_charts:
        _check_matplotlib()

    colors = _get_theme_colors(config.theme)

    # Generate charts if enabled
    equity_chart = ""
    drawdown_chart = ""
    monthly_heatmap = ""
    trade_dist_chart = ""
    rolling_sharpe_chart = ""
    rolling_vol_chart = ""

    if config.include_charts:
        equity_chart = _create_comparison_equity_chart(results, colors, config.dpi)
        drawdown_chart = _create_comparison_drawdown_chart(results, colors, config.dpi)

        if config.include_monthly_heatmap:
            monthly_heatmap = _create_comparison_monthly_returns_heatmap(
                results, colors, config.dpi
            )

        trade_dist_chart = _create_comparison_trade_distribution_chart(results, colors, config.dpi)

        if config.include_rolling_metrics:
            rolling_sharpe_chart = _create_comparison_rolling_sharpe_chart(
                results, colors, config.dpi
            )
            rolling_vol_chart = _create_comparison_rolling_volatility_chart(
                results, colors, config.dpi
            )

    # Build comparison table
    comparison_table = _build_comparison_table(results, colors)

    # Build summary cards
    summary_cards = _build_comparison_summary_cards(results, colors)

    # Build risk attribution comparison
    risk_attribution_comparison = _build_comparison_risk_attribution(
        results, colors, config.dpi if config.include_charts else None
    )

    # Build HTML
    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>{config.title}</title>",
        f"<style>{_get_css(colors)}</style>",
        "<style>.summary-cards {display:flex; flex-wrap:wrap; gap:15px; justify-content:center;} .summary-card {flex:1 1 300px; min-width:280px;}</style>",
        "</head>",
        "<body>",
        '<div class="container">',
        '<header class="report-header">',
        f"<h1>{config.title}</h1>",
        '<div class="report-meta">',
        f'<span>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>',
        f'<span>Strategies: {", ".join(name for name, _ in results)}</span>',
        "</div>",
        "</header>",
    ]

    if config.include_charts:
        html_parts.extend(
            [
                '<section class="section">',
                "<h2>Charts</h2>",
                '<div class="chart-grid">',
                f'<div class="chart-card full-width"><h3>Equity Curves</h3><img src="data:image/png;base64,{equity_chart}" alt="Equity Curves Comparison"></div>',
                f'<div class="chart-card full-width"><h3>Drawdown Comparison</h3><img src="data:image/png;base64,{drawdown_chart}" alt="Drawdown Comparison"></div>',
            ]
        )
        if monthly_heatmap:
            html_parts.append(
                f'<div class="chart-card full-width"><h3>Monthly Returns Comparison</h3><img src="data:image/png;base64,{monthly_heatmap}" alt="Monthly Returns Comparison"></div>'
            )
        html_parts.extend(
            [
                f'<div class="chart-card full-width"><h3>Trade PnL Distribution Comparison</h3><img src="data:image/png;base64,{trade_dist_chart}" alt="Trade PnL Distribution Comparison"></div>',
            ]
        )
        if rolling_sharpe_chart:
            html_parts.append(
                f'<div class="chart-card full-width"><h3>Rolling Sharpe (60) Comparison</h3><img src="data:image/png;base64,{rolling_sharpe_chart}" alt="Rolling Sharpe Comparison"></div>'
            )
        if rolling_vol_chart:
            html_parts.append(
                f'<div class="chart-card full-width"><h3>Rolling Volatility (60) Comparison</h3><img src="data:image/png;base64,{rolling_vol_chart}" alt="Rolling Volatility Comparison"></div>'
            )
        html_parts.extend(["</div>", "</section>"])

    html_parts.extend(
        [
            '<section class="section">',
            "<h2>Strategy Comparison</h2>",
            summary_cards,
            comparison_table,
            "</section>",
        ]
    )

    if risk_attribution_comparison:
        html_parts.append(risk_attribution_comparison)

    html_parts.extend(
        [
            '<footer class="report-footer">',
            "<p>Generated by Quantitative Trading Framework</p>",
            "</footer>",
            "</div>",
            "</body>",
            "</html>",
        ]
    )

    html = "\n".join(html_parts)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

    return html


__all__ = [
    "MATPLOTLIB_AVAILABLE",
    "ReportConfig",
    "generate_comparison_report",
    "generate_html_report",
    "generate_report_from_dict",
]
