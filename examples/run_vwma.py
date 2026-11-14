"""Offline VWMA crossover backtest example using synthetic data.

Runs the ``VolumeWeightedMovingAverageCrossover`` strategy against deterministic
synthetic price data, so it needs no network access and produces the same output
on every run.

The Volume Weighted Moving Average (VWMA) weights each close by the volume
traded in the same bar. The strategy generates a buy signal when the fast VWMA
crosses above the slow VWMA and a sell signal when it crosses below the slow
VWMA.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from datetime import datetime, timedelta

from quant_trading.backtest.engine import BacktestEngine
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager
from quant_trading.data.synthetic import create_synthetic_provider
from quant_trading.strategies.examples import VolumeWeightedMovingAverageCrossover


def _print_summary(name: str, result) -> None:
    print(f"\n{'=' * 60}")
    print(f"Results for: {name}")
    print(f"{'=' * 60}")
    print(f"Initial Capital: ${result.initial_capital:,.2f}")
    print(f"Final Value:     ${result.final_value:,.2f}")
    print(f"Total Return:    ${result.total_return:,.2f} ({result.total_return_pct:.2f}%)")
    print(f"Total Trades:    ${result.metrics.num_trades}")
    print(f"Win Rate:        {result.metrics.win_rate:.2%}")
    print(f"Sharpe Ratio:    {result.metrics.sharpe_ratio:.2f}")
    print(f"Max Drawdown:    {result.metrics.max_drawdown_pct:.2f}%")
    print(f"Profit Factor:   {result.metrics.profit_factor:.2f}")


def main() -> None:
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    provider = create_synthetic_provider(symbols, days=365, seed=42)
    data_manager = DataManager([provider])

    config = BacktestConfig(
        initial_capital=100000.0,
        commission=0.001,
        slippage=0.0005,
    )

    strategy = VolumeWeightedMovingAverageCrossover(
        fast_period=10, slow_period=30, name="VWMA_Crossover_10_30"
    )

    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(strategy)
    result = engine.run(symbols, start_date, end_date, "1d")
    _print_summary(strategy.name, result)


if __name__ == "__main__":
    main()
