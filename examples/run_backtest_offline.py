"""Offline backtest example using synthetic data.

Runs the built-in strategies against deterministic synthetic price
data, so it needs no network access and produces the same output on
every run.
"""

from datetime import datetime, timedelta

from quant_trading.backtest.engine import BacktestEngine
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager
from quant_trading.data.synthetic import create_synthetic_provider
from quant_trading.strategies.examples import (
    BollingerBandsStrategy,
    MovingAverageCrossover,
    RSIStrategy,
)


def _print_summary(name: str, result) -> None:
    print(f"\n{'=' * 60}")
    print(f"Results for: {name}")
    print(f"{'=' * 60}")
    print(f"Initial Capital: ${result.initial_capital:,.2f}")
    print(f"Final Value:     ${result.final_value:,.2f}")
    print(
        f"Total Return:    ${result.total_return:,.2f} "
        f"({result.total_return_pct:.2f}%)"
    )
    print(f"Total Trades:    {result.metrics.num_trades}")
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

    strategies = [
        MovingAverageCrossover(fast_period=10, slow_period=30, name="MA_Crossover_10_30"),
        RSIStrategy(period=14, oversold=30, overbought=70, name="RSI_14"),
        BollingerBandsStrategy(period=20, std_dev=2.0, name="BB_20_2"),
    ]

    # Run each strategy on its own engine
    for strategy in strategies:
        engine = BacktestEngine(config=config, data_manager=data_manager)
        engine.add_strategy(strategy)
        result = engine.run(symbols, start_date, end_date, "1d")
        _print_summary(strategy.name, result)

    # Run all strategies together on a single engine
    print(f"\n{'=' * 60}")
    print("Running combined strategy backtest")
    print(f"{'=' * 60}")

    combined_engine = BacktestEngine(config=config, data_manager=data_manager)
    for strategy in strategies:
        combined_engine.add_strategy(strategy)

    combined_result = combined_engine.run(symbols, start_date, end_date, "1d")
    _print_summary("Combined", combined_result)


if __name__ == "__main__":
    main()
