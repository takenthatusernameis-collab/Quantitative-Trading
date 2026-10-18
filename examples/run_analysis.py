"""Backtest analysis example: regime, Monte Carlo, and trade analysis.

This script runs a single backtest against deterministic synthetic data and
then exercises all three built-in analysis modules:

  * Market regime detection (bull/bear/sideways x low/high volatility)
  * Monte Carlo simulation (bootstrap resampling of daily returns)
  * Trade-level analysis (PnL, holding periods, streaks, per-symbol stats)

It uses synthetic data so it is fully deterministic and requires no network
access.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from datetime import datetime, timedelta

from quant_trading.backtest import (
    analyze_regimes,
    analyze_trades,
    print_trade_analysis,
)
from quant_trading.backtest.engine import run_backtest
from quant_trading.config.settings import BacktestConfig
from quant_trading.data.providers import DataManager
from quant_trading.data.synthetic import create_synthetic_provider
from quant_trading.monte_carlo import run_monte_carlo
from quant_trading.strategies.examples import MovingAverageCrossover


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


def _print_regime_analysis(analysis) -> None:
    summary = analysis.summary()
    print(f"Current Regime:    {summary['current_regime']}")
    print(f"Total Volatility:  {summary['total_volatility']:.4f}")
    print(f"Total Return:      {summary['total_return_pct']:.2f}%")
    print(f"Number of Segments: {summary['n_segments']}")
    if analysis.segments:
        print(f"\n{'Regime':<22} {'Start':<12} {'End':<12} {'Vol':>8} {'Ret%':>8}")
        print("-" * 60)
        for seg in analysis.segments:
            print(
                f"{seg.regime.value:<22} {str(seg.start)[:10]:<12} "
                f"{str(seg.end)[:10]:<12} {seg.volatility:>8.4f} "
                f"{seg.return_pct:>8.2f}"
            )


def _print_monte_carlo_analysis(mc) -> None:
    summary = mc.summary()
    print(f"Simulations:       {summary['n_simulations']}")
    print(f"Confidence Level:  {summary['confidence_level']:.0%}")
    print(f"Prob of Profit:    {summary['probability_of_profit']:.2%}")
    print(f"Original Sharpe:   {mc.original_metrics.sharpe_ratio:.4f}")
    print(f"MC Mean Sharpe:    {summary['sharpe_ratio_mean']:.4f}")
    print(f"MC Mean Return%:   {summary['total_return_pct_mean']:.2f}")
    print(f"MC Mean Max DD%:   {summary['max_drawdown_pct_mean']:.2f}")
    lower, upper = mc.get_confidence_interval("total_return_pct")
    print(f"95% CI Return%:    [{lower:.2f}%, {upper:.2f}%]")
    es = mc.expected_shortfall("total_return_pct", confidence=0.95)
    print(f"Expected Shortfall: {es:.2f}")


def main() -> None:
    """Run a backtest and all three analysis modules against synthetic data."""
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
    result = run_backtest(
        strategy=strategy,
        symbols=symbols,
        start=start_date,
        end=end_date,
        initial_capital=config.initial_capital,
        commission=config.commission,
        slippage=config.slippage,
        interval="1d",
        data_manager=data_manager,
    )
    print(f"Initial Capital: ${result.initial_capital:,.2f}")
    print(f"Final Value:     ${result.final_value:,.2f}")
    print(f"Total Return:    ${result.total_return:,.2f} ({result.total_return_pct:.2f}%)")
    print(f"Total Trades:    {result.metrics.num_trades}")
    print(f"Win Rate:        {result.metrics.win_rate:.2%}")
    print(f"Sharpe Ratio:    {result.metrics.sharpe_ratio:.2f}")
    print(f"Max Drawdown:    {result.metrics.max_drawdown_pct:.2f}%")
    print(f"Profit Factor:   {result.metrics.profit_factor:.2f}")

    _print_section("Market Regime Analysis")
    regime_analysis = analyze_regimes(result, window=20)
    _print_regime_analysis(regime_analysis)

    _print_section("Monte Carlo Simulation")
    mc = run_monte_carlo(
        result,
        n_simulations=200,
        method="bootstrap",
        random_state=42,
    )
    _print_monte_carlo_analysis(mc)

    _print_section("Detailed Trade Analysis")
    trade_analysis = analyze_trades(result)
    print_trade_analysis(trade_analysis)

    print("\nExample script completed.")


if __name__ == "__main__":
    main()
