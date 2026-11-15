"""Parameter sensitivity analysis for optimization results.

This module provides functions for analyzing how strategy performance
varies with different parameter values, including heatmaps for 2D
parameter interactions and line plots for 1D sensitivity analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


@dataclass
class SensitivityConfig:
    """Configuration for sensitivity analysis plots.

    Attributes:
        include_charts: Whether to generate matplotlib charts.
        dpi: DPI for chart images.
        colormap: Colormap for heatmaps.
        figure_size: Figure size as (width, height) in inches.
    """

    include_charts: bool = True
    dpi: int = 150
    colormap: str = "RdYlGn"
    figure_size: tuple[int, int] = (10, 6)


def _check_matplotlib() -> None:
    """Raise ImportError if matplotlib is not available."""
    if not MATPLOTLIB_AVAILABLE:
        raise ImportError(
            "matplotlib is required for sensitivity analysis charts. "
            "Install with: pip install quant-trading[reporting]"
        )


def _fig_to_base64(fig: Any, dpi: int = 150) -> str:
    """Convert a matplotlib figure to a base64-encoded PNG string."""
    import base64
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return img_base64


def prepare_sensitivity_data(
    all_results: list[dict[str, Any]],
    param_names: list[str] | None = None,
    score_key: str = "score",
) -> pd.DataFrame:
    """Prepare a DataFrame from optimization results for sensitivity analysis.

    Args:
        all_results: List of result dicts from grid search (each with 'params' and score_key).
        param_names: List of parameter names to include. If None, all parameters found in results are used.
        score_key: Key in result dict to use as the score (default: 'score').

    Returns:
        DataFrame with columns for each parameter and the score.
    """
    if not all_results:
        return pd.DataFrame()  # type: ignore[no-any-return]

    rows: list[dict[str, Any]] = []
    for result in all_results:
        if "params" not in result:
            continue
        params = result["params"]
        score = result.get(score_key, np.nan)
        row: dict[str, Any] = {"score": score}
        if param_names is None:
            for k, v in params.items():
                row[k] = v
        else:
            for k in param_names:
                row[k] = params.get(k, np.nan)
        rows.append(row)

    return pd.DataFrame(rows)  # type: ignore[no-any-return]


def create_2d_sensitivity_heatmap(
    df: pd.DataFrame,
    param_x: str,
    param_y: str,
    score_col: str = "score",
    config: SensitivityConfig | None = None,
) -> str:
    """Create a 2D sensitivity heatmap for two parameters.

    Args:
        df: DataFrame with parameter columns and score column.
        param_x: Parameter name for x-axis.
        param_y: Parameter name for y-axis.
        score_col: Column name for the score values.
        config: Optional SensitivityConfig for customization.

    Returns:
        Base64-encoded PNG string of the heatmap.

    Raises:
        ValueError: If required columns are missing or insufficient data.
    """
    _check_matplotlib()
    if config is None:
        config = SensitivityConfig()

    if param_x not in df.columns or param_y not in df.columns or score_col not in df.columns:
        raise ValueError(f"Required columns not found: {param_x}, {param_y}, {score_col}")

    # Pivot to create 2D grid
    pivot = df.pivot_table(index=param_y, columns=param_x, values=score_col, aggfunc="mean")
    pivot = pivot.sort_index(ascending=False)  # y-axis ascending from bottom

    fig, ax = plt.subplots(
        figsize=config.figure_size,
        dpi=config.dpi,
        facecolor="white",
        constrained_layout=True,
    )
    ax.set_facecolor("white")

    # Create heatmap
    im = ax.imshow(
        pivot.values,
        cmap=config.colormap,
        aspect="auto",
        origin="lower",
    )

    # Set ticks and labels
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([str(c) for c in pivot.columns], rotation=45, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(r) for r in pivot.index])

    # Add text annotations
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.iloc[i, j]
            if not np.isnan(val):
                text_color = "white" if abs(val) > (np.nanmax(np.abs(pivot.values)) * 0.5) else "black"
                ax.text(
                    j,
                    i,
                    f"{val:.3f}",
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=8,
                    fontweight="bold",
                )

    ax.set_xlabel(param_x, fontsize=12)
    ax.set_ylabel(param_y, fontsize=12)
    ax.set_title(f"Sensitivity: {param_x} vs {param_y}", fontsize=14, fontweight="bold")

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label(score_col, fontsize=10)

    return _fig_to_base64(fig, config.dpi)


def create_1d_sensitivity_plot(
    df: pd.DataFrame,
    param: str,
    score_col: str = "score",
    config: SensitivityConfig | None = None,
) -> str:
    """Create a 1D sensitivity line plot for a single parameter.

    Shows the mean score for each parameter value, with error bars
    representing the standard deviation across other parameters.

    Args:
        df: DataFrame with parameter columns and score column.
        param: Parameter name for x-axis.
        score_col: Column name for the score values.
        config: Optional SensitivityConfig for customization.

    Returns:
        Base64-encoded PNG string of the line plot.

    Raises:
        ValueError: If required columns are missing or insufficient data.
    """
    _check_matplotlib()
    if config is None:
        config = SensitivityConfig()

    if param not in df.columns or score_col not in df.columns:
        raise ValueError(f"Required columns not found: {param}, {score_col}")

    # Group by parameter value and compute statistics
    grouped = df.groupby(param)[score_col].agg(["mean", "std", "count"]).reset_index()
    grouped = grouped.sort_values(param)

    fig, ax = plt.subplots(
        figsize=config.figure_size,
        dpi=config.dpi,
        facecolor="white",
        constrained_layout=True,
    )
    ax.set_facecolor("white")

    x = grouped[param].values
    y_mean = grouped["mean"].values
    y_std = grouped["std"].values

    ax.plot(x, y_mean, "o-", color="#1565c0", linewidth=2, markersize=6, label="Mean Score")
    ax.fill_between(
        x,
        y_mean - y_std,
        y_mean + y_std,
        color="#1565c0",
        alpha=0.2,
        label="±1 Std Dev",
    )

    ax.set_xlabel(param, fontsize=12)
    ax.set_ylabel(score_col, fontsize=12)
    ax.set_title(f"1D Sensitivity: {param}", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend()

    return _fig_to_base64(fig, config.dpi)


def create_parameter_interaction_heatmap(
    df: pd.DataFrame,
    param_names: list[str],
    score_col: str = "score",
    config: SensitivityConfig | None = None,
) -> str:
    """Create a heatmap showing all pairwise parameter interactions.

    Args:
        df: DataFrame with parameter columns and score column.
        param_names: List of parameter names to include.
        score_col: Column name for the score values.
        config: Optional SensitivityConfig for customization.

    Returns:
        Base64-encoded PNG string of the interaction heatmap.

    Raises:
        ValueError: If fewer than 2 parameters provided or insufficient data.
    """
    _check_matplotlib()
    if config is None:
        config = SensitivityConfig()

    if len(param_names) < 2:
        raise ValueError("At least 2 parameters required for interaction heatmap")

    n = len(param_names)
    interaction_matrix = np.zeros((n, n))
    interaction_matrix[:] = np.nan

    for i, param_i in enumerate(param_names):
        for j, param_j in enumerate(param_names):
            if i == j:
                # Diagonal: variance of score when varying this parameter
                grouped = df.groupby(param_i)[score_col].mean()
                interaction_matrix[i, j] = grouped.std() if len(grouped) > 1 else 0
            else:
                # Off-diagonal: interaction effect
                # Compute 2D pivot and measure how much the score varies
                # when both parameters change together vs independently
                try:
                    pivot = df.pivot_table(
                        index=param_i, columns=param_j, values=score_col, aggfunc="mean"
                    )
                    if not pivot.empty:
                        # Interaction strength = std of row means - mean of row stds
                        # (captures how much the effect of one param depends on the other)
                        row_means = pivot.mean(axis=1)
                        interaction_matrix[i, j] = row_means.std()
                except (ValueError, KeyError, IndexError):
                    interaction_matrix[i, j] = np.nan

    fig, ax = plt.subplots(
        figsize=(max(8, n * 0.8), max(6, n * 0.6)),
        dpi=config.dpi,
        facecolor="white",
        constrained_layout=True,
    )
    ax.set_facecolor("white")

    # Mask NaN values
    mask = np.isnan(interaction_matrix)
    plot_matrix = np.ma.masked_array(interaction_matrix, mask=mask)

    im = ax.imshow(
        plot_matrix,
        cmap=config.colormap,
        aspect="auto",
        origin="lower",
    )

    ax.set_xticks(range(n))
    ax.set_xticklabels(param_names, rotation=45, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels(param_names)

    # Add text annotations
    for i in range(n):
        for j in range(n):
            val = interaction_matrix[i, j]
            if not np.isnan(val):
                text_color = "white" if abs(val) > (np.nanmax(np.abs(interaction_matrix)) * 0.5) else "black"
                ax.text(
                    j,
                    i,
                    f"{val:.3f}",
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=8,
                    fontweight="bold",
                )

    ax.set_title("Parameter Interaction Strength", fontsize=14, fontweight="bold")
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Interaction Effect (std of conditional means)", fontsize=10)

    return _fig_to_base64(fig, config.dpi)


def generate_sensitivity_report_html(
    all_results: list[dict[str, Any]],
    param_names: list[str] | None = None,
    score_key: str = "score",
    config: SensitivityConfig | None = None,
    output_path: str | None = None,
) -> str:
    """Generate an HTML report for parameter sensitivity analysis.

    Args:
        all_results: List of result dicts from grid search.
        param_names: List of parameter names to analyze. If None, all parameters found in results.
        score_key: Key in result dict to use as the score.
        config: Optional SensitivityConfig for customization.
        output_path: Optional path to write the HTML file.

    Returns:
        HTML string of the report.
    """
    if config is None:
        config = SensitivityConfig()

    df = prepare_sensitivity_data(all_results, param_names, score_key)

    if df.empty:
        return "<html><body><h1>No data for sensitivity analysis</h1></body></html>"

    if param_names is None:
        param_names = [c for c in df.columns if c != score_key]

    # Generate charts
    charts = []
    if config.include_charts and MATPLOTLIB_AVAILABLE:
        # 1D sensitivity plots
        for param in param_names:
            try:
                chart = create_1d_sensitivity_plot(df, param, score_key, config)
                charts.append((f"1D Sensitivity: {param}", chart))
            except (ValueError, KeyError, IndexError):
                pass

        # 2D sensitivity heatmaps for all pairs
        for i, param_x in enumerate(param_names):
            for param_y in param_names[i + 1:]:
                try:
                    chart = create_2d_sensitivity_heatmap(df, param_x, param_y, score_key, config)
                    charts.append((f"2D Sensitivity: {param_x} vs {param_y}", chart))
                except (ValueError, KeyError, IndexError):
                    pass

        # Parameter interaction heatmap
        if len(param_names) >= 2:
            try:
                chart = create_parameter_interaction_heatmap(df, param_names, score_key, config)
                charts.append(("Parameter Interactions", chart))
            except (ValueError, KeyError, IndexError):
                pass

    # Build summary table
    summary_rows = []
    for param in param_names:
        grouped = df.groupby(param)[score_key].agg(["mean", "std", "min", "max"]).reset_index()
        sensitivity_range = grouped["mean"].max() - grouped["mean"].min()
        summary_rows.append({
            "parameter": param,
            "mean_score": grouped["mean"].mean(),
            "score_std": grouped["mean"].std(),
            "sensitivity_range": sensitivity_range,
            "n_values": len(grouped),
        })

    summary_df = pd.DataFrame(summary_rows)

    # Build HTML
    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<title>Parameter Sensitivity Analysis</title>",
        "<style>",
        "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }",
        ".container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
        "h1 { color: #333; border-bottom: 2px solid #1565c0; padding-bottom: 10px; }",
        "h2 { color: #555; margin-top: 30px; }",
        "h3 { color: #666; }",
        "table { width: 100%; border-collapse: collapse; margin: 20px 0; }",
        "th, td { padding: 12px; text-align: left; border: 1px solid #ddd; }",
        "th { background: #1565c0; color: white; }",
        "tr:nth-child(even) { background: #fafafa; }",
        ".chart { margin: 20px 0; text-align: center; }",
        ".chart img { max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; }",
        ".chart h3 { margin-bottom: 10px; }",
        "</style>",
        "</head>",
        "<body>",
        '<div class="container">',
        "<h1>Parameter Sensitivity Analysis</h1>",
        f"<p>Generated from {len(all_results)} optimization results</p>",
        "<h2>Summary Statistics</h2>",
        summary_df.to_html(index=False, float_format=lambda x: f"{x:.4f}"),
        "<h2>Charts</h2>",
    ]

    for title, chart in charts:
        html_parts.append(f'<div class="chart"><h3>{title}</h3><img src="data:image/png;base64,{chart}" alt="{title}"></div>')

    html_parts.extend([
        "</div>",
        "</body>",
        "</html>",
    ])

    html = "\n".join(html_parts)

    if output_path:
        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(html, encoding="utf-8")

    return html


__all__ = [
    "SensitivityConfig",
    "create_1d_sensitivity_plot",
    "create_2d_sensitivity_heatmap",
    "create_parameter_interaction_heatmap",
    "generate_sensitivity_report_html",
    "prepare_sensitivity_data",
]