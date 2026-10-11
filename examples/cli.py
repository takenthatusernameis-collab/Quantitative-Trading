"""CLI entry point for running backtests with configurable data providers."""

import argparse
from datetime import datetime, timedelta

from quant_trading.backtest.engine import run_backtest
from quant_trading.config.settings import Config
from quant_trading.strategies.examples import (
    BollingerBandsStrategy,
    MovingAverageCrossover,
    RSIStrategy,
)

STRATEGIES = {
    "ma": MovingAverageCrossover,
    "rsi": RSIStrategy,
    "bb": BollingerBandsStrategy,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run backtests with the Quantitative Trading framework",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["AAPL", "MSFT", "GOOGL"],
        help="Symbols to trade",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days of historical data",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD), overrides --days",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD), defaults to today",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000.0,
        help="Initial capital",
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.001,
        help="Commission rate",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.0005,
        help="Slippage rate",
    )
    parser.add_argument(
        "--interval",
        default="1d",
        help="Data interval",
    )

    parser.add_argument(
        "--strategy",
        choices=list(STRATEGIES.keys()),
        default="ma",
        help="Strategy to run",
    )
    parser.add_argument(
        "--fast-period",
        type=int,
        default=10,
        help="Fast period for MA crossover",
    )
    parser.add_argument(
        "--slow-period",
        type=int,
        default=30,
        help="Slow period for MA crossover",
    )
    parser.add_argument(
        "--rsi-period",
        type=int,
        default=14,
        help="RSI period",
    )
    parser.add_argument(
        "--rsi-oversold",
        type=int,
        default=30,
        help="RSI oversold threshold",
    )
    parser.add_argument(
        "--rsi-overbought",
        type=int,
        default=70,
        help="RSI overbought threshold",
    )
    parser.add_argument(
        "--bb-period",
        type=int,
        default=20,
        help="Bollinger Bands period",
    )
    parser.add_argument(
        "--bb-std",
        type=float,
        default=2.0,
        help="Bollinger Bands standard deviations",
    )

    parser.add_argument(
        "--provider",
        choices=["yfinance", "alphavantage", "synthetic"],
        default=None,
        help="Data provider to use (default: from config or yfinance)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run in offline mode using synthetic data (alias for --provider synthetic)",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Cache directory for data providers (default: from config or ./data/cache)",
    )
    parser.add_argument(
        "--alphavantage-key",
        type=str,
        default=None,
        help="Alpha Vantage API key (required for alphavantage provider)",
    )
    parser.add_argument(
        "--synthetic-days",
        type=int,
        default=None,
        help="Days of synthetic data to generate (default: from config or 365)",
    )
    parser.add_argument(
        "--synthetic-seed",
        type=int,
        default=None,
        help="Random seed for synthetic data (default: from config or 42)",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results (JSON)",
    )

    return parser.parse_args()


def create_strategy(args: argparse.Namespace):
    """Create strategy instance from args."""
    strategy_cls = STRATEGIES[args.strategy]

    if args.strategy == "ma":
        return strategy_cls(
            fast_period=args.fast_period,
            slow_period=args.slow_period,
            name=f"MA_Crossover_{args.fast_period}_{args.slow_period}",
        )
    elif args.strategy == "rsi":
        return strategy_cls(
            period=args.rsi_period,
            oversold=args.rsi_oversold,
            overbought=args.rsi_overbought,
            name=f"RSI_{args.rsi_period}",
        )
    elif args.strategy == "bb":
        return strategy_cls(
            period=args.bb_period,
            std_dev=args.bb_std,
            name=f"BB_{args.bb_period}_{args.bb_std}",
        )
    else:
        raise ValueError(f"Unknown strategy: {args.strategy}")


def create_config(args: argparse.Namespace) -> Config:
    """Create Config from args and optional YAML file."""
    config = Config()

    if args.config:
        config = Config.from_yaml(args.config)

    # Override with CLI args (only when explicitly provided)
    if args.offline:
        config.data.provider = "synthetic"
        config.data.offline = True
    elif args.provider is not None:
        config.data.provider = args.provider

    if args.cache_dir is not None:
        config.data.cache_dir = args.cache_dir

    if args.synthetic_days is not None:
        config.data.synthetic_days = args.synthetic_days

    if args.synthetic_seed is not None:
        config.data.synthetic_seed = args.synthetic_seed

    if args.alphavantage_key is not None:
        config.data.alphavantage_api_key = args.alphavantage_key

    return config


def main() -> int:
    args = parse_args()

    # Parse dates
    end_date = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start_date = end_date - timedelta(days=args.days)

    # Create strategy
    strategy = create_strategy(args)

    # Create config
    config = create_config(args)

    # Run backtest
    print(f"Running backtest for {strategy.name}")
    print(f"Symbols: {args.symbols}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Provider: {config.data.provider}")
    if config.data.offline:
        print("Mode: OFFLINE (synthetic data)")

    try:
        result = run_backtest(
            strategy=strategy,
            symbols=args.symbols,
            start=start_date,
            end=end_date,
            initial_capital=args.initial_capital,
            commission=args.commission,
            slippage=args.slippage,
            interval=args.interval,
            config=config,
        )

        print(f"\n{'=' * 60}")
        print(f"Results for: {strategy.name}")
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

        if args.output:
            import json

            output_data = {
                "strategy": strategy.name,
                "symbols": args.symbols,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "initial_capital": result.initial_capital,
                "final_value": result.final_value,
                "total_return": result.total_return,
                "total_return_pct": result.total_return_pct,
                "num_trades": result.metrics.num_trades,
                "win_rate": result.metrics.win_rate,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "max_drawdown_pct": result.metrics.max_drawdown_pct,
                "profit_factor": result.metrics.profit_factor,
            }
            with open(args.output, "w") as f:
                json.dump(output_data, f, indent=2)
            print(f"\nResults saved to {args.output}")

    except (ValueError, RuntimeError, KeyError) as e:
        print(f"Error running backtest: {e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())