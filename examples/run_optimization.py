"""Example optimization script demonstrating parameter optimization and walk-forward optimization.

This script demonstrates how to use the optimization modules to find optimal
parameters for a strategy and how to run walk-forward optimization to assess
parameter stability over time.

It uses synthetic data to ensure deterministic results and no network dependency.
"""
from datetime import datetime, timedelta

from quant_trading.backtest.engine import BacktestEngine
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager
from quant_trading.data.synthetic import create_synthetic_provider
from quant_trading.optimization import (
    BayesianOptimizer,
    GridSearch,
    ParameterGrid,
    ParameterSpace,
    RandomSearch,
    WalkForwardOptimizer,
    maximize_sharpe,
    maximize_total_return,
)
from quant_trading.strategies.examples import MovingAverageCrossover


def main() -> None:
    """Run optimization and walk-forward optimization examples."""
    symbols = ["AAPL", "MSFT", "GOOGL"]
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    # Create synthetic data provider (deterministic, no network)
    provider = create_synthetic_provider(symbols, days=365, seed=42)
    data_manager = DataManager([provider])

    config = BacktestConfig(
        initial_capital=100000.0,
        commission=0.001,
        slippage=0.0005,
    )

    print("=" * 60)
    print("Parameter Optimization Example: Moving Average Crossover")
    print("=" * 60)

    # Define parameter grid for optimization
    # We'll optimize fast and slow MA periods with constraint fast < slow
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
    # Add validator to ensure fast < slow
    param_grid.set_validator(lambda p: p["fast_period"] < p["slow_period"])

    # We'll use grid search for simplicity
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
        verbose=True,
    )

    result = optimizer.run()

    print(f"\nOptimization completed. Evaluated {len(result.all_results)} combinations.")
    print(f"Best Sharpe Ratio: {result.best_score:.4f}")
    print(f"Best Parameters: {result.best_params}")

    # Show top 5 results
    print("\nTop 5 Results:")
    print(f"{'Rank':<5} {'Parameters':<25} {'Sharpe':>10} {'Return%':>10}")
    print("-" * 55)
    for i, r in enumerate(result.get_top_n(5)):
        params_str = str(r["params"])
        print(
            f"{i+1:<5} {params_str:<25} {r['sharpe_ratio']:>10.4f} {r['total_return_pct']:>10.2f}"
        )

    print("\n" + "=" * 60)
    print("Walk-Forward Optimization Example")
    print("=" * 60)

    # Use the same parameter grid for walk-forward optimization
    wf_optimizer = WalkForwardOptimizer(
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
        n_windows=4,
        train_size=0.6,
        optimizer="grid",  # Use grid search within each window
        verbose=True,
    )

    wf_result = wf_optimizer.run()

    print(f"\nWalk-forward optimization completed over {wf_result.summary()['n_windows']} windows.")
    print(f"Average Out-of-Sample Sharpe: {wf_result.summary()['avg_test_sharpe']:.4f}")
    print(f"Average Out-of-Sample Return: {wf_result.summary()['avg_test_return_pct']:.2f}%")

    # Show window results
    print("\nWindow Results:")
    print(
        f"{'Window':<8} {'Train Sharpe':>12} {'Test Sharpe':>12} {'Train Return%':>14} {'Test Return%':>14}"
    )
    print("-" * 70)
    for _, row in wf_result.to_dataframe().iterrows():
        print(
            f"{int(row['window']):<8} {row['train_sharpe']:>12.4f} {row['test_sharpe']:>12.4f} "
            f"{row['train_return_pct']:>14.2f} {row['test_return_pct']:>14.2f}"
        )

    print("\nExample script completed.")


if __name__ == "__main__":
    main()