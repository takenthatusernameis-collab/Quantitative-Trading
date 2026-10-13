"""CLI entry point for running backtests with configurable data providers."""

import argparse
from datetime import datetime, timedelta

from quant_trading.backtest.engine import run_backtest
from quant_trading.config.settings import Config
from quant_trading.monte_carlo import run_monte_carlo
from quant_trading.optimization import (
    BayesianOptimizer,
    GridSearch,
    ParameterGrid,
    RandomSearch,
    WalkForwardOptimizer,
    maximize_calmar,
    maximize_profit_factor,
    maximize_sharpe,
    maximize_total_return,
    maximize_win_rate,
    minimize_max_drawdown,
)
from quant_trading.strategies import (
    create_strategy as factory_create_strategy,
)
from quant_trading.strategies import (
    get_registry,
    get_strategy,
)
from quant_trading.strategies import (
    list_strategies as factory_list_strategies,
)

# Built-in strategy keys for argparse choices (preserves existing behavior)
BUILTIN_STRATEGY_KEYS = ["ma", "rsi", "bb", "macd", "supertrend", "donchian"]

PROVIDERS = {
    "yfinance": ("YFinanceProvider", "Yahoo Finance (requires network)"),
    "alphavantage": ("AlphaVantageProvider", "Alpha Vantage (requires API key)"),
    "synthetic": ("SyntheticDataProvider", "Synthetic data generator (offline, deterministic)"),
}

OBJECTIVES = {
    "sharpe": maximize_sharpe,
    "return": maximize_total_return,
    "calmar": maximize_calmar,
    "drawdown": minimize_max_drawdown,
    "profit_factor": maximize_profit_factor,
    "win_rate": maximize_win_rate,
}

OPTIMIZERS = {
    "grid": GridSearch,
    "random": RandomSearch,
    "bayesian": BayesianOptimizer,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run backtests with the Quantitative Trading framework",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--list-strategies",
        action="store_true",
        help="List available strategies and exit",
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="List available data providers and exit",
    )
    parser.add_argument(
        "--init-config",
        type=str,
        metavar="PATH",
        help="Generate a default config YAML file at PATH and exit",
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
        choices=BUILTIN_STRATEGY_KEYS,
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
        "--macd-fast",
        type=int,
        default=12,
        help="MACD fast EMA period",
    )
    parser.add_argument(
        "--macd-slow",
        type=int,
        default=26,
        help="MACD slow EMA period",
    )
    parser.add_argument(
        "--macd-signal",
        type=int,
        default=9,
        help="MACD signal period",
    )
    parser.add_argument(
        "--macd-zero-line",
        action="store_true",
        help="Enable zero-line crossover signals for MACD",
    )
    parser.add_argument(
        "--st-period",
        type=int,
        default=10,
        help="SuperTrend ATR period",
    )
    parser.add_argument(
        "--st-multiplier",
        type=float,
        default=3.0,
        help="SuperTrend multiplier",
    )
    parser.add_argument(
        "--dc-period",
        type=int,
        default=20,
        help="Donchian Channel lookback period",
    )
    parser.add_argument(
        "--dc-exit-period",
        type=int,
        default=None,
        help="Donchian Channel exit period (default: same as period)",
    )

    # Parameter ranges for optimization
    parser.add_argument(
        "--ma-fast-range",
        type=str,
        default="5,20,5",
        help="Fast MA range: min,max,step (for grid search)",
    )
    parser.add_argument(
        "--ma-slow-range",
        type=str,
        default="20,50,5",
        help="Slow MA range: min,max,step (for grid search)",
    )
    parser.add_argument(
        "--rsi-period-range",
        type=str,
        default="10,20,2",
        help="RSI period range: min,max,step",
    )
    parser.add_argument(
        "--rsi-oversold-range",
        type=str,
        default="20,35,5",
        help="RSI oversold range: min,max,step",
    )
    parser.add_argument(
        "--rsi-overbought-range",
        type=str,
        default="65,80,5",
        help="RSI overbought range: min,max,step",
    )
    parser.add_argument(
        "--bb-period-range",
        type=str,
        default="10,30,5",
        help="BB period range: min,max,step",
    )
    parser.add_argument(
        "--bb-std-range",
        type=str,
        default="1.5,3.0,0.5",
        help="BB std dev range: min,max,step",
    )
    parser.add_argument(
        "--macd-fast-range",
        type=str,
        default="8,16,2",
        help="MACD fast range: min,max,step",
    )
    parser.add_argument(
        "--macd-slow-range",
        type=str,
        default="20,30,2",
        help="MACD slow range: min,max,step",
    )
    parser.add_argument(
        "--macd-signal-range",
        type=str,
        default="7,12,1",
        help="MACD signal range: min,max,step",
    )
    parser.add_argument(
        "--st-period-range",
        type=str,
        default="7,20,1",
        help="SuperTrend period range: min,max,step",
    )
    parser.add_argument(
        "--st-multiplier-range",
        type=str,
        default="2.0,4.0,0.5",
        help="SuperTrend multiplier range: min,max,step",
    )
    parser.add_argument(
        "--dc-period-range",
        type=str,
        default="10,40,5",
        help="Donchian Channel period range: min,max,step",
    )
    parser.add_argument(
        "--dc-exit-period-range",
        type=str,
        default="5,20,5",
        help="Donchian Channel exit period range: min,max,step",
    )

    parser.add_argument(
        "--combined",
        action="store_true",
        help="Run all available strategies together and compare results",
    )

    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run parameter optimization for the selected strategy",
    )
    parser.add_argument(
        "--optimizer",
        choices=list(OPTIMIZERS.keys()),
        default="grid",
        help="Optimization method to use",
    )
    parser.add_argument(
        "--objective",
        choices=list(OBJECTIVES.keys()),
        default="sharpe",
        help="Objective function to optimize",
    )
    parser.add_argument(
        "--n-iter",
        type=int,
        default=50,
        help="Number of iterations for random search",
    )
    parser.add_argument(
        "--bayesian-n-initial",
        type=int,
        default=10,
        help="Number of initial random points for Bayesian optimization",
    )
    parser.add_argument(
        "--bayesian-acq-func",
        choices=["EI", "PI", "LCB", "gp_hedge"],
        default="EI",
        help="Acquisition function for Bayesian optimization",
    )
    parser.add_argument(
        "--bayesian-acq-optimizer",
        choices=["auto", "sampling", "lbfgs"],
        default="auto",
        help="Acquisition function optimizer for Bayesian optimization",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward optimization",
    )
    parser.add_argument(
        "--wf-windows",
        type=int,
        default=5,
        help="Number of walk-forward windows",
    )
    parser.add_argument(
        "--wf-train-size",
        type=float,
        default=0.7,
        help="Training fraction for walk-forward (0-1)",
    )
    parser.add_argument(
        "--wf-anchored",
        action="store_true",
        default=True,
        help="Use anchored (expanding) walk-forward windows",
    )
    parser.add_argument(
        "--wf-rolling",
        action="store_false",
        dest="wf_anchored",
        help="Use rolling (sliding) walk-forward windows",
    )
    parser.add_argument(
        "--wf-optimizer",
        choices=["grid", "random", "bayesian"],
        default="grid",
        help="Optimizer to use within each walk-forward window",
    )

    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS.keys()),
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
    parser.add_argument(
        "--regime",
        action="store_true",
        help="Run market-regime detection on the backtest equity curve",
    )
    parser.add_argument(
        "--regime-window",
        type=int,
        default=20,
        help="Rolling window size for regime detection",
    )
    parser.add_argument(
        "--regime-vol-threshold",
        type=float,
        default=0.0,
        help="Explicit volatility threshold (<=0 auto-derives)",
    )
    parser.add_argument(
        "--regime-return-threshold",
        type=float,
        default=0.0,
        help="Explicit return threshold (<=0 auto-derives)",
    )

    parser.add_argument(
        "--monte-carlo",
        action="store_true",
        help="Run Monte Carlo simulation on the backtest equity curve",
    )
    parser.add_argument(
        "--mc-simulations",
        type=int,
        default=1000,
        help="Number of Monte Carlo simulations to run",
    )
    parser.add_argument(
        "--mc-confidence",
        type=float,
        default=0.95,
        help="Confidence level for Monte Carlo intervals (0-1)",
    )
    parser.add_argument(
        "--mc-method",
        choices=["bootstrap", "parametric"],
        default="bootstrap",
        help="Monte Carlo simulation method",
    )
    parser.add_argument(
        "--mc-seed",
        type=int,
        default=None,
        help="Random seed for Monte Carlo reproducibility",
    )

    parser.add_argument(
        "--trade-analysis",
        action="store_true",
        help="Run detailed trade analysis on the backtest results",
    )

    return parser.parse_args()


def create_strategy(args: argparse.Namespace):
    """Create strategy instance from args using the factory registry."""
    kwargs = {}

    if args.strategy == "ma":
        kwargs = {
            "fast_period": args.fast_period,
            "slow_period": args.slow_period,
            "name": f"MA_Crossover_{args.fast_period}_{args.slow_period}",
        }
    elif args.strategy == "rsi":
        kwargs = {
            "period": args.rsi_period,
            "oversold": args.rsi_oversold,
            "overbought": args.rsi_overbought,
            "name": f"RSI_{args.rsi_period}",
        }
    elif args.strategy == "bb":
        kwargs = {
            "period": args.bb_period,
            "std_dev": args.bb_std,
            "name": f"BB_{args.bb_period}_{args.bb_std}",
        }
    elif args.strategy == "macd":
        kwargs = {
            "fast_period": getattr(args, "macd_fast", 12),
            "slow_period": getattr(args, "macd_slow", 26),
            "signal_period": getattr(args, "macd_signal", 9),
            "use_zero_line": getattr(args, "macd_zero_line", False),
            "name": f"MACD_{getattr(args, 'macd_fast', 12)}_{getattr(args, 'macd_slow', 26)}_{getattr(args, 'macd_signal', 9)}",
        }
    elif args.strategy == "supertrend":
        kwargs = {
            "period": args.st_period,
            "multiplier": args.st_multiplier,
            "name": f"SuperTrend_{args.st_period}_{args.st_multiplier}",
        }
    elif args.strategy == "donchian":
        kwargs = {
            "period": args.dc_period,
            "exit_period": args.dc_exit_period,
            "name": f"Donchian_{args.dc_period}_{args.dc_exit_period if args.dc_exit_period else args.dc_period}",
        }

    return factory_create_strategy(args.strategy, **kwargs)


def list_strategies() -> int:
    """Print available strategies and exit."""
    strategies = factory_list_strategies()
    print("Available strategies:")
    for key, cls in strategies.items():
        instance = cls()
        params = instance.get_parameters()
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        print(f"  {key}: {cls.__name__} ({param_str})")
    return 0


def list_providers() -> int:
    """Print available data providers and exit."""
    print("Available data providers:")
    for key, (cls_name, description) in PROVIDERS.items():
        print(f"  {key}: {cls_name} - {description}")
    return 0


def init_config(path: str) -> int:
    """Generate a default config YAML file at the given path."""
    config = Config()
    config.to_yaml(path)
    print(f"Default config written to {path}")
    return 0


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


def parse_range(range_str: str) -> tuple[float, float, float]:
    """Parse a range string 'min,max,step' into a tuple."""
    parts = range_str.split(",")
    if len(parts) != 3:
        raise ValueError(f"Invalid range format: {range_str}. Expected 'min,max,step'")
    return float(parts[0]), float(parts[1]), float(parts[2])


def create_param_grid(args: argparse.Namespace) -> "ParameterGrid":
    """Create parameter grid for optimization based on strategy and args."""
    from quant_trading.optimization import ParameterGrid, ParameterSpace

    grid = ParameterGrid()

    if args.strategy == "ma":
        fast_min, fast_max, fast_step = parse_range(args.ma_fast_range)
        slow_min, slow_max, slow_step = parse_range(args.ma_slow_range)
        grid.add(ParameterSpace("fast_period", min_val=fast_min, max_val=fast_max, step=fast_step, param_type=int))
        grid.add(ParameterSpace("slow_period", min_val=slow_min, max_val=slow_max, step=slow_step, param_type=int))
        grid.set_validator(lambda p: p["fast_period"] < p["slow_period"])
    elif args.strategy == "rsi":
        period_min, period_max, period_step = parse_range(args.rsi_period_range)
        oversold_min, oversold_max, oversold_step = parse_range(args.rsi_oversold_range)
        overbought_min, overbought_max, overbought_step = parse_range(args.rsi_overbought_range)
        grid.add(ParameterSpace("period", min_val=period_min, max_val=period_max, step=period_step, param_type=int))
        grid.add(ParameterSpace("oversold", min_val=oversold_min, max_val=oversold_max, step=oversold_step, param_type=int))
        grid.add(ParameterSpace("overbought", min_val=overbought_min, max_val=overbought_max, step=overbought_step, param_type=int))
        grid.set_validator(lambda p: p["oversold"] < p["overbought"])
    elif args.strategy == "bb":
        period_min, period_max, period_step = parse_range(args.bb_period_range)
        std_min, std_max, std_step = parse_range(args.bb_std_range)
        grid.add(ParameterSpace("period", min_val=period_min, max_val=period_max, step=period_step, param_type=int))
        grid.add(ParameterSpace("std_dev", min_val=std_min, max_val=std_max, step=std_step, param_type=float))
    elif args.strategy == "macd":
        fast_min, fast_max, fast_step = parse_range(args.macd_fast_range)
        slow_min, slow_max, slow_step = parse_range(args.macd_slow_range)
        signal_min, signal_max, signal_step = parse_range(args.macd_signal_range)
        grid.add(ParameterSpace("fast_period", min_val=fast_min, max_val=fast_max, step=fast_step, param_type=int))
        grid.add(ParameterSpace("slow_period", min_val=slow_min, max_val=slow_max, step=slow_step, param_type=int))
        grid.add(ParameterSpace("signal_period", min_val=signal_min, max_val=signal_max, step=signal_step, param_type=int))
        grid.add(ParameterSpace("use_zero_line", values=[False, True], param_type=bool))
        grid.set_validator(lambda p: p["fast_period"] < p["slow_period"])
    elif args.strategy == "supertrend":
        period_min, period_max, period_step = parse_range(args.st_period_range)
        mult_min, mult_max, mult_step = parse_range(args.st_multiplier_range)
        grid.add(ParameterSpace("period", min_val=period_min, max_val=period_max, step=period_step, param_type=int))
        grid.add(ParameterSpace("multiplier", min_val=mult_min, max_val=mult_max, step=mult_step, param_type=float))
    elif args.strategy == "donchian":
        period_min, period_max, period_step = parse_range(args.dc_period_range)
        exit_min, exit_max, exit_step = parse_range(args.dc_exit_period_range)
        grid.add(ParameterSpace("period", min_val=period_min, max_val=period_max, step=period_step, param_type=int))
        grid.add(ParameterSpace("exit_period", min_val=exit_min, max_val=exit_max, step=exit_step, param_type=int))

    return grid


def run_optimization(args: argparse.Namespace, config: Config, start_date: datetime, end_date: datetime) -> int:
    """Run parameter optimization for a strategy."""

    strategy_cls = get_strategy(args.strategy)
    if strategy_cls is None:
        raise ValueError(f"Unknown strategy: {args.strategy}. Available: {BUILTIN_STRATEGY_KEYS}")
    param_grid = create_param_grid(args)
    objective = OBJECTIVES[args.objective]

    print(f"Running parameter optimization for {strategy_cls.__name__}")
    print(f"Symbols: {args.symbols}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Provider: {config.data.provider}")
    print(f"Optimizer: {args.optimizer}")
    print(f"Objective: {args.objective}")
    if config.data.offline:
        print("Mode: OFFLINE (synthetic data)")
    print(f"Parameter grid: {param_grid.generate_combinations().__len__()} combinations")

    optimizer_cls = OPTIMIZERS[args.optimizer]
    if args.optimizer == "random":
        optimizer = optimizer_cls(
            strategy_cls=strategy_cls,
            param_grid=param_grid,
            objective=objective,
            symbols=args.symbols,
            start=start_date,
            end=end_date,
            initial_capital=args.initial_capital,
            commission=args.commission,
            slippage=args.slippage,
            interval=args.interval,
            config=config,
            n_iter=args.n_iter,
            verbose=True,
        )
    elif args.optimizer == "bayesian":
        optimizer = optimizer_cls(
            strategy_cls=strategy_cls,
            param_grid=param_grid,
            objective=objective,
            symbols=args.symbols,
            start=start_date,
            end=end_date,
            initial_capital=args.initial_capital,
            commission=args.commission,
            slippage=args.slippage,
            interval=args.interval,
            config=config,
            n_initial_points=args.bayesian_n_initial,
            n_calls=args.n_iter,
            acq_func=args.bayesian_acq_func,
            acq_optimizer=args.bayesian_acq_optimizer,
            verbose=True,
        )
    else:
        optimizer = optimizer_cls(
            strategy_cls=strategy_cls,
            param_grid=param_grid,
            objective=objective,
            symbols=args.symbols,
            start=start_date,
            end=end_date,
            initial_capital=args.initial_capital,
            commission=args.commission,
            slippage=args.slippage,
            interval=args.interval,
            config=config,
            verbose=True,
        )

    result = optimizer.run()

    print(f"\n{'=' * 60}")
    print("Optimization Complete")
    print(f"{'=' * 60}")
    print(f"Best Parameters: {result.best_params}")
    print(f"Best Score ({args.objective}): {result.best_score:.4f}")

    if result.best_result:
        print(f"Total Return:    {result.best_result.total_return_pct:.2f}%")
        print(f"Sharpe Ratio:    {result.best_result.metrics.sharpe_ratio:.4f}")
        print(f"Max Drawdown:    {result.best_result.metrics.max_drawdown_pct:.2f}%")
        print(f"Win Rate:        {result.best_result.metrics.win_rate:.2%}")
        print(f"Profit Factor:   {result.best_result.metrics.profit_factor:.4f}")
        print(f"Total Trades:    {result.best_result.metrics.num_trades}")

    # Print top 10
    print("\nTop 10 Results:")
    print(f"{'Rank':<5} {'Params':<50} {'Score':>10} {'Return%':>10} {'Sharpe':>8} {'MaxDD%':>10}")
    print(f"{'-' * 90}")
    for i, r in enumerate(result.get_top_n(10)):
        params_str = str(r["params"])[:48]
        print(f"{i+1:<5} {params_str:<50} {r['score']:>10.4f} {r['total_return_pct']:>10.2f} {r['sharpe_ratio']:>8.4f} {r['max_drawdown_pct']:>10.2f}")

    if args.output:
        import json

        output_data = {
            "strategy": strategy_cls.__name__,
            "symbols": args.symbols,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "optimizer": args.optimizer,
            "objective": args.objective,
            "best_params": result.best_params,
            "best_score": result.best_score,
            "best_result": {
                "total_return_pct": result.best_result.total_return_pct if result.best_result else None,
                "sharpe_ratio": result.best_result.metrics.sharpe_ratio if result.best_result else None,
                "max_drawdown_pct": result.best_result.metrics.max_drawdown_pct if result.best_result else None,
                "win_rate": result.best_result.metrics.win_rate if result.best_result else None,
                "profit_factor": result.best_result.metrics.profit_factor if result.best_result else None,
                "num_trades": result.best_result.metrics.num_trades if result.best_result else None,
            } if result.best_result else None,
            "all_results": result.all_results,
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"\nResults saved to {args.output}")

    return 0


def run_walk_forward(args: argparse.Namespace, config: Config, start_date: datetime, end_date: datetime) -> int:
    """Run walk-forward optimization for a strategy."""

    strategy_cls = get_strategy(args.strategy)
    if strategy_cls is None:
        raise ValueError(f"Unknown strategy: {args.strategy}. Available: {BUILTIN_STRATEGY_KEYS}")
    param_grid = create_param_grid(args)
    objective = OBJECTIVES[args.objective]

    print(f"Running walk-forward optimization for {strategy_cls.__name__}")
    print(f"Symbols: {args.symbols}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Provider: {config.data.provider}")
    print(f"Windows: {args.wf_windows}")
    print(f"Train size: {args.wf_train_size:.0%}")
    print(f"Anchored: {args.wf_anchored}")
    print(f"Inner optimizer: {args.wf_optimizer}")
    print(f"Objective: {args.objective}")
    if config.data.offline:
        print("Mode: OFFLINE (synthetic data)")

    if args.wf_optimizer == "random":
        optimizer_kwargs = {"n_iter": args.n_iter}
    elif args.wf_optimizer == "bayesian":
        optimizer_kwargs = {
            "n_initial_points": args.bayesian_n_initial,
            "n_calls": args.n_iter,
            "acq_func": args.bayesian_acq_func,
            "acq_optimizer": args.bayesian_acq_optimizer,
        }
    else:
        optimizer_kwargs = {}

    optimizer = WalkForwardOptimizer(
        strategy_cls=strategy_cls,
        param_grid=param_grid,
        objective=objective,
        symbols=args.symbols,
        start=start_date,
        end=end_date,
        initial_capital=args.initial_capital,
        commission=args.commission,
        slippage=args.slippage,
        interval=args.interval,
        data_manager=None,
        config=config,
        n_windows=args.wf_windows,
        train_size=args.wf_train_size,
        anchored=args.wf_anchored,
        optimizer=args.wf_optimizer,
        optimizer_kwargs=optimizer_kwargs,
        verbose=True,
    )

    result = optimizer.run()

    print(f"\n{'=' * 60}")
    print("Walk-Forward Optimization Complete")
    print(f"{'=' * 60}")

    # Print window results
    df = result.to_dataframe()
    if not df.empty:
        print("\nWindow Results:")
        print(f"{'Window':<7} {'Train Return%':>14} {'Train Sharpe':>13} {'Test Return%':>13} {'Test Sharpe':>12} {'Test MaxDD%':>13}")
        print(f"{'-' * 75}")
        for _, row in df.iterrows():
            print(f"{int(row['window']):<7} {row['train_return_pct']:>14.2f} {row['train_sharpe']:>13.4f} "
                  f"{row['test_return_pct']:>13.2f} {row['test_sharpe']:>12.4f} {row['test_max_dd']:>13.2f}")

    summary = result.summary()
    print("\nSummary:")
    print(f"  Windows:           {summary['n_windows']}")
    print(f"  Avg Test Return:   {summary['avg_test_return_pct']:.2f}%")
    print(f"  Avg Test Sharpe:   {summary['avg_test_sharpe']:.4f}")
    print(f"  Avg Test Max DD:   {summary['avg_test_max_dd_pct']:.2f}%")
    print(f"  Window Win Rate:   {summary['win_rate_windows']:.2%}")

    if result.combined_test_result:
        print(f"  Combined Test Return: {summary['combined_test_return_pct']:.2f}%")
        print(f"  Combined Test Sharpe: {summary['combined_test_sharpe']:.4f}")

    if args.output:
        import json

        output_data = {
            "strategy": strategy_cls.__name__,
            "symbols": args.symbols,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "walk_forward": {
                "n_windows": args.wf_windows,
                "train_size": args.wf_train_size,
                "anchored": args.wf_anchored,
            },
            "objective": args.objective,
            "optimizer": args.optimizer,
            "window_results": result.to_dataframe().to_dict(orient="records"),
            "summary": summary,
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"\nResults saved to {args.output}")

    return 0


def _print_regime_analysis(result, args: argparse.Namespace) -> None:
    """Print regime detection results for a backtest's equity curve."""
    from quant_trading.backtest import analyze_regimes

    analysis = analyze_regimes(
        result,
        window=args.regime_window,
        vol_threshold=args.regime_vol_threshold,
        return_threshold=args.regime_return_threshold,
    )
    summary = analysis.summary()

    print(f"\n{'=' * 60}")
    print("Market Regime Analysis")
    print(f"{'=' * 60}")
    print(f"Current Regime:   {summary['current_regime']}")
    print(f"Total Volatility: {summary['total_volatility']:.4f}")
    print(f"Total Return:      {summary['total_return_pct']:.2f}%")
    print(f"Regime Segments:   {summary['n_segments']}")

    if summary["n_segments"] > 0:
        print(f"\n{'Regime':<22} {'Start':<12} {'End':<12} {'Vol':>8} {'Ret %':>8}")
        print(f"{'-' * 62}")
        for seg in analysis.segments:
            print(
                f"{seg.regime.value:<22} {str(seg.start)[:10]:<12} {str(seg.end)[:10]:<12} "
                f"{seg.volatility:>8.4f} {seg.return_pct:>8.2f}"
            )


def _print_monte_carlo_analysis(result, args: argparse.Namespace) -> None:
    """Print Monte Carlo simulation results for a backtest's equity curve."""
    mc = run_monte_carlo(
        result,
        n_simulations=args.mc_simulations,
        confidence_level=args.mc_confidence,
        method=args.mc_method,
        random_state=args.mc_seed,
    )
    summary = mc.summary()

    print(f"\n{'=' * 60}")
    print("Monte Carlo Simulation")
    print(f"{'=' * 60}")
    print(f"Method:            {args.mc_method}")
    print(f"Simulations:       {mc.n_simulations}")
    print(f"Confidence Level:  {mc.confidence_level:.0%}")
    print(f"Duration (s):      {mc.duration_seconds:.2f}")
    print(f"Probability of Profit: {summary['probability_of_profit']:.2%}")

    print(f"\n{'Metric':<22} {'Mean':>12} {'Median':>12} {'Std':>12}")
    print(f"{'-' * 58}")
    for metric in [
        "total_return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "volatility",
    ]:
        print(
            f"{metric:<22} {summary[f'{metric}_mean']:>12.4f} "
            f"{summary[f'{metric}_median']:>12.4f} {summary[f'{metric}_std']:>12.4f}"
        )

    print("\n95% Confidence Intervals:")
    for metric in ["total_return_pct", "sharpe_ratio", "max_drawdown_pct"]:
        lower = summary[f"{metric}_ci_lower"]
        upper = summary[f"{metric}_ci_upper"]
        print(f"  {metric:<20} [{lower:>10.4f}, {upper:>10.4f}]")

    print(f"\nExpected Shortfall (95%): {summary['total_return_pct_ci_lower']:.4f}")


def _print_trade_analysis(result, args: argparse.Namespace) -> None:
    """Print detailed trade analysis for a backtest result."""
    from quant_trading.backtest import analyze_trades, print_trade_analysis

    analysis = analyze_trades(result)
    print_trade_analysis(analysis)


def main() -> int:
    args = parse_args()

    # Handle info commands that exit early
    if args.list_strategies:
        return list_strategies()
    if args.list_providers:
        return list_providers()
    if args.init_config:
        return init_config(args.init_config)

    # Parse dates
    end_date = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start_date = end_date - timedelta(days=args.days)

    # Create config
    config = create_config(args)

    if args.combined:
        return run_combined(args, config, start_date, end_date)

    if args.optimize:
        return run_optimization(args, config, start_date, end_date)

    if args.walk_forward:
        return run_walk_forward(args, config, start_date, end_date)

    # Single strategy mode
    strategy = create_strategy(args)

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

        if args.regime:
            _print_regime_analysis(result, args)

        if args.monte_carlo:
            _print_monte_carlo_analysis(result, args)

        if args.trade_analysis:
            _print_trade_analysis(result, args)

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


def run_combined(args: argparse.Namespace, config: Config, start_date: datetime, end_date: datetime) -> int:
    """Run all strategies and compare results."""
    print("Running combined backtest for all strategies")
    print(f"Symbols: {args.symbols}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Provider: {config.data.provider}")
    if config.data.offline:
        print("Mode: OFFLINE (synthetic data)")

    registry = get_registry()
    results = []
    for strategy_key in registry.primary_keys():
        # Create a copy of args with the current strategy
        strategy_args = argparse.Namespace(**vars(args))
        strategy_args.strategy = strategy_key
        # Set defaults for strategy-specific args
        if strategy_key == "donchian":
            strategy_args.dc_period = getattr(args, "dc_period", 20)
            strategy_args.dc_exit_period = getattr(args, "dc_exit_period", None)
        strategy = create_strategy(strategy_args)

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
            results.append((strategy.name, result))
            print(f"  ✓ {strategy.name}: {result.total_return_pct:.2f}% return, Sharpe {result.metrics.sharpe_ratio:.2f}")
        except (ValueError, RuntimeError, KeyError) as e:
            print(f"  ✗ {strategy.name}: Error - {e}")
            return 1

    if not results:
        print("No strategies completed successfully")
        return 1

    # Print comparison table
    print(f"\n{'=' * 80}")
    print("Strategy Comparison")
    print(f"{'=' * 80}")
    print(f"{'Strategy':<30} {'Return %':>10} {'Sharpe':>8} {'Max DD %':>10} {'Win Rate':>10} {'Trades':>8}")
    print(f"{'-' * 80}")
    for name, result in results:
        print(
            f"{name:<30} {result.total_return_pct:>10.2f} "
            f"{result.metrics.sharpe_ratio:>8.2f} "
            f"{result.metrics.max_drawdown_pct:>10.2f} "
            f"{result.metrics.win_rate:>9.2%} "
            f"{result.metrics.num_trades:>8}"
        )

    # Find best by Sharpe ratio
    best = max(results, key=lambda x: x[1].metrics.sharpe_ratio)
    print(f"\nBest strategy (by Sharpe): {best[0]} (Sharpe: {best[1].metrics.sharpe_ratio:.2f})")

    if args.output:
        import json

        output_data = {
            "comparison": [
                {
                    "strategy": name,
                    "total_return_pct": result.total_return_pct,
                    "sharpe_ratio": result.metrics.sharpe_ratio,
                    "max_drawdown_pct": result.metrics.max_drawdown_pct,
                    "win_rate": result.metrics.win_rate,
                    "num_trades": result.metrics.num_trades,
                }
                for name, result in results
            ],
            "best_strategy": best[0],
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())