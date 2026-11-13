"""Portfolio rebalancing example using synthetic data.

Runs a backtest against deterministic synthetic price data and then uses
:class:`~quant_trading.portfolio.rebalancer.Rebalancer` to bring the
portfolio back to a target allocation. It needs no network access and
produces the same output on every run.

The rebalancer compares the portfolio's current allocation against a set of
target allocations and emits :class:`~quant_trading.portfolio.rebalancer.RebalanceAction`
objects describing the trades required to close the gap. The emitted actions
are then applied to the portfolio with
:meth:`~quant_trading.portfolio.rebalancer.Rebalancer.execute_actions`, which
reports what each action actually traded.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta

from quant_trading.backtest.engine import BacktestEngine
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager
from quant_trading.data.synthetic import create_synthetic_provider
from quant_trading.portfolio.rebalancer import Rebalancer
from quant_trading.strategies.examples import MovingAverageCrossover


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


def _print_allocation(portfolio) -> None:
    allocation = portfolio.get_allocation()
    print("Current allocation:")
    if not allocation:
        print("  (none)")
    for symbol, weight in sorted(allocation.items()):
        print(f"  {symbol:<8} {weight:>8.2%}")


def _print_actions(actions) -> None:
    print(f"\nRebalance actions ({len(actions)}):")
    if not actions:
        print("  (none)")
    for action in actions:
        print(
            f"  {action.symbol:<8} {action.action:<5} "
            f"quantity={action.quantity:>10.4f}  reason={action.reason}"
        )


def _print_executions(executions) -> None:
    print(f"\nExecutions ({len(executions)}):")
    if not executions:
        print("  (none)")
    for execution in executions:
        print(
            f"  {execution.symbol:<8} {execution.action:<5} "
            f"requested={execution.requested_quantity:>10.4f} "
            f"executed={execution.executed_quantity:>10.4f} "
            f"price={execution.price:>10.2f} "
            f"cash_effect={execution.cash_effect:>12.2f}"
        )


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

    strategy = MovingAverageCrossover(fast_period=10, slow_period=30, name="MA_10_30")

    _print_section("Backtest")
    engine = BacktestEngine(config=config, data_manager=data_manager)
    engine.add_strategy(strategy)
    result = engine.run(symbols, start_date, end_date, "1d")
    print(f"Initial Capital: ${result.initial_capital:,.2f}")
    print(f"Final Value:     ${result.final_value:,.2f}")
    print(f"Total Return:    ${result.total_return:,.2f} ({result.total_return_pct:.2f}%)")
    print(f"Total Trades:    {result.metrics.num_trades}")
    print(f"Sharpe Ratio:    {result.metrics.sharpe_ratio:.2f}")

    # The rebalancer manages the portfolio the engine just ran, so the
    # actions it plans are sized against the post-run portfolio state.
    target_allocation = {symbol: 1.0 / len(symbols) for symbol in symbols}
    rebalancer = Rebalancer(
        engine.portfolio,
        frequency="monthly",
        target_allocation=target_allocation,
    )

    _print_section("Target Allocation")
    for symbol, weight in sorted(target_allocation.items()):
        print(f"  {symbol:<8} {weight:>8.2%}")

    _print_section("Portfolio Before Rebalance")
    _print_allocation(engine.portfolio)
    print(f"Cash:            ${engine.portfolio.cash:>12,.2f}")
    print(f"Total Value:     ${engine.portfolio.total_value:>12,.2f}")

    # Resolve a real mark per symbol from the last bar of the backtest data,
    # so the rebalancer plans and executes at the same prices. The engine
    # already fetched this data, so reuse the manager instead of re-fetching
    # per symbol.
    last_bars = data_manager.fetch(
        symbols=symbols, start=start_date, end=end_date, interval="1d"
    ).data
    prices = {symbol: float(md.data["close"].iloc[-1]) for symbol, md in last_bars.items()}

    actions = rebalancer.generate_rebalance_actions(prices=prices)

    _print_section("Rebalance Actions")
    _print_actions(actions)

    executions = rebalancer.execute_actions(actions, prices=prices)

    _print_section("Executions")
    _print_executions(executions)

    _print_section("Portfolio After Rebalance")
    _print_allocation(engine.portfolio)
    print(f"Cash:            ${engine.portfolio.cash:>12,.2f}")
    print(f"Total Value:     ${engine.portfolio.total_value:>12,.2f}")

    deviations = rebalancer.get_current_deviation()
    _print_section("Final Deviations")
    for symbol, deviation in sorted(deviations.items()):
        print(f"  {symbol:<8} {deviation:>+8.2%}")

    print("\nExample script completed.")


if __name__ == "__main__":
    main()
