"""Example backtest script demonstrating the quantitative trading framework."""

from datetime import datetime, timedelta

from quant_trading.backtest.engine import BacktestEngine, run_backtest
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager
from quant_trading.data.yfinance_provider import YFinanceProvider
from quant_trading.strategies.examples import (
    BollingerBandsStrategy,
    MovingAverageCrossover,
    RSIStrategy,
)


def main():
    # Define symbols to test
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]

    # Date range for backtest
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)  # 1 year

    # Create strategies
    ma_strategy = MovingAverageCrossover(fast_period=10, slow_period=30, name="MA_Crossover_10_30")
    rsi_strategy = RSIStrategy(period=14, oversold=30, overbought=70, name="RSI_14")
    bb_strategy = BollingerBandsStrategy(period=20, std_dev=2.0, name="BB_20_2")

    # Run backtest for each strategy
    strategies = [ma_strategy, rsi_strategy, bb_strategy]

    for strategy in strategies:
        print(f"\n{'='*60}")
        print(f"Running backtest for: {strategy.name}")
        print(f"{'='*60}")

        try:
            result = run_backtest(
                strategy=strategy,
                symbols=symbols,
                start=start_date,
                end=end_date,
                initial_capital=100000.0,
                commission=0.001,
                slippage=0.0005,
                interval="1d",
            )

            print(f"Initial Capital: ${result.initial_capital:,.2f}")
            print(f"Final Value: ${result.final_value:,.2f}")
            print(f"Total Return: ${result.total_return:,.2f} ({result.total_return_pct:.2f}%)")
            print(f"Total Trades: {result.metrics.num_trades}")
            print(f"Win Rate: {result.metrics.win_rate:.2%}")
            print(f"Sharpe Ratio: {result.metrics.sharpe_ratio:.2f}")
            print(f"Max Drawdown: {result.metrics.max_drawdown_pct:.2f}%")
            print(f"Profit Factor: {result.metrics.profit_factor:.2f}")

        except (ValueError, RuntimeError, KeyError) as e:
            print(f"Error running backtest for {strategy.name}: {e}")

    # Example: Run multiple strategies together
    print(f"\n{'='*60}")
    print("Running combined strategy backtest")
    print(f"{'='*60}")

    config = BacktestConfig(initial_capital=100000.0, commission=0.001, slippage=0.0005)
    engine = BacktestEngine(config=config)

    for strategy in strategies:
        engine.add_strategy(strategy)

    # Need to set up data manager
    provider = YFinanceProvider()
    data_manager = DataManager([provider])
    engine.data_manager = data_manager

    try:
        result = engine.run(symbols, start_date, end_date, "1d")
        print(f"Initial Capital: ${result.initial_capital:,.2f}")
        print(f"Final Value: ${result.final_value:,.2f}")
        print(f"Total Return: ${result.total_return:,.2f} ({result.total_return_pct:.2f}%)")
        print(f"Total Trades: {result.metrics.num_trades}")
        print(f"Win Rate: {result.metrics.win_rate:.2%}")
        print(f"Sharpe Ratio: {result.metrics.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {result.metrics.max_drawdown_pct:.2f}%")
        print(f"Profit Factor: {result.metrics.profit_factor:.2f}")

    except (ValueError, RuntimeError, KeyError) as e:
        print(f"Error running combined backtest: {e}")


if __name__ == "__main__":
    main()
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
