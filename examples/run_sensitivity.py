"""Offline parameter sensitivity analysis example using synthetic data.

This script demonstrates how to use the parameter sensitivity analysis
module to explore how strategy performance varies with different parameter
values. It runs a small grid search over the fast/slow MA periods of the
``MovingAverageCrossover`` strategy against deterministic synthetic data,
then feeds the resulting scores into the sensitivity analysis functions:

* :func:`prepare_sensitivity_data` turns the grid results into a tidy
  DataFrame,
* :func:`generate_sensitivity_report_html` renders 1D sensitivity plots,
  2D parameter-interaction heatmaps, a parameter-interaction heatmap, and a
  summary statistics table into a standalone HTML report,
* :func:`create_1d_sensitivity_plot` and :func:`create_2d_sensitivity_heatmap`
  are also exercised individually so their individual return values are
  covered.

The script needs no network access and produces the same output on every
run because the synthetic data is seeded.
"""

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from datetime import datetime, timedelta

from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager
from quant_trading.data.synthetic import create_synthetic_provider
from quant_trading.optimization import (
    GridSearch,
    ParameterGrid,
    ParameterSpace,
    maximize_sharpe,
)
from quant_trading.optimization.sensitivity import (
    SensitivityConfig,
    create_1d_sensitivity_plot,
    create_2d_sensitivity_heatmap,
    generate_sensitivity_report_html,
    prepare_sensitivity_data,
)
from quant_trading.strategies.examples import MovingAverageCrossover


def _print_summary_table(df) -> None:
    print("\nSensitivity Summary:")
    print(f"{'Parameter':<15} {'Mean':>10} {'Std':>10} {'Range':>10} {'N':>6}")
    print("-" * 60)
    for row in df.itertuples(index=False):
        print(
            f"{row.parameter:<15} {row.mean_score:>10.4f} {row.score_std:>10.4f} "
            f"{row.sensitivity_range:>10.4f} {row.n_values:>6}"
        )


def main() -> None:
    start = time.monotonic()
    symbols = ["AAPL", "MSFT", "GOOGL"]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    provider = create_synthetic_provider(symbols, days=365, seed=42, end_date=end_date)
    data_manager = DataManager([provider])

    config = BacktestConfig(
        initial_capital=100000.0,
        commission=0.001,
        slippage=0.0005,
    )

    print("=" * 60)
    print("Parameter Optimization (grid search) for Sensitivity Analysis")
    print("=" * 60)

    param_grid = ParameterGrid()
    param_grid.add(
        ParameterSpace(
            name="fast_period",
            min_val=5,
            max_val=20,
            step=5,
            param_type=int,
        )
    )
    param_grid.add(
        ParameterSpace(
            name="slow_period",
            min_val=20,
            max_val=50,
            step=5,
            param_type=int,
        )
    )
    param_grid.set_validator(lambda p: p["fast_period"] < p["slow_period"])

    optimizer = GridSearch(
        strategy_cls=MovingAverageCrossover,
        param_grid=param_grid,
        objective=maximize_sharpe,
        symbols=symbols,
        start=start_date,
        end=end_date,
        initial_capital=config.initial_capital,
        commission=config.commission,
        slippage=config.slippage,
        interval="1d",
        data_manager=data_manager,
        config=config,
        verbose=False,
    )

    result = optimizer.run()
    print(f"Evaluated {len(result.all_results)} combinations.")
    print(f"Best Sharpe: {result.best_score:.4f} -> {result.best_params}")

    print("\n" + "=" * 60)
    print("Sensitivity Analysis")
    print("=" * 60)

    # Build the tidy DataFrame the sensitivity functions consume.
    df = prepare_sensitivity_data(result.all_results)
    print(f"Prepared sensitivity DataFrame with {len(df)} rows " f"and columns {list(df.columns)}.")

    # Exercise the individual chart builders so their return values are
    # covered in addition to the all-in-one HTML report.
    sensitivity_config = SensitivityConfig(dpi=80, figure_size=(8, 5))
    chart_1d = create_1d_sensitivity_plot(df, "fast_period", config=sensitivity_config)
    chart_2d = create_2d_sensitivity_heatmap(
        df, "fast_period", "slow_period", config=sensitivity_config
    )
    print(
        f"Built 1D sensitivity plot ({len(chart_1d)} base64 chars) and "
        f"2D heatmap ({len(chart_2d)} base64 chars)."
    )

    # Render the standalone HTML report.
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "sensitivity_report.html"
    html = generate_sensitivity_report_html(
        result.all_results,
        param_names=["fast_period", "slow_period"],
        score_key="score",
        config=sensitivity_config,
        output_path=str(html_path),
    )
    print(f"Wrote sensitivity report to {html_path} ({len(html)} chars).")

    # Print a text summary table derived from the same data.
    summary_rows = []
    for param in ("fast_period", "slow_period"):
        grouped = df.groupby(param)["score"].agg(["mean", "std", "min", "max"]).reset_index()
        summary_rows.append(
            {
                "parameter": param,
                "mean_score": grouped["mean"].mean(),
                "score_std": grouped["mean"].std(),
                "sensitivity_range": grouped["mean"].max() - grouped["mean"].min(),
                "n_values": len(grouped),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    _print_summary_table(summary_df)

    print(f"\nExample script completed in {time.monotonic() - start:.2f}s")


if __name__ == "__main__":
    main()
