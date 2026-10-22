"""CLI entry point for running backtests with configurable data providers.

Additional feature:
  --strategy-config: Specify a YAML file containing strategy configuration
                     (type, name, parameters) to create the strategy.
                     This overrides the --strategy argument and individual
                     strategy parameters.
"""

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from quant_trading.backtest.engine import run_backtest
from quant_trading.config.settings import Config
from quant_trading.data.yfinance_provider import AlphaVantageProvider
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
BUILTIN_STRATEGY_KEYS = [
    "ma",
    "rsi",
    "bb",
    "macd",
    "supertrend",
    "donchian",
    "aroon",
    "keltner",
    "stoch",
    "ichimoku",
    "sar",
    "vwap",
    "ema",
    "momentum",
]

PROVIDERS = {
    "yfinance": ("YFinanceProvider", "Yahoo Finance (requires network)"),
    "alphavantage": ("AlphaVantageProvider", "Alpha Vantage (requires API key)"),
    "synthetic": ("SyntheticDataProvider", "Synthetic data generator (offline, deterministic)"),
}

# Trading periods per year for each supported bar frequency. Used to
# annualize return, volatility, Sharpe, Sortino and Calmar metrics.
INTERVAL_PERIODS_PER_YEAR = {
    "1d": 252,
    "d": 252,
    "day": 252,
    "daily": 252,
    "1w": 52,
    "1wk": 52,
    "w": 52,
    "wk": 52,
    "week": 52,
    "weekly": 52,
    "1mo": 12,
    "mo": 12,
    "month": 12,
    "monthly": 12,
    "monthly_adjusted": 12,
}

# Minutes in a standard US equity trading session (6.5 hours), used to
# annualize intraday intervals.
MINUTES_PER_TRADING_DAY = 390

# Every interval alias the Alpha Vantage provider accepts, so the CLI does not
# reject values the README documents as valid (e.g. ``monthly_adjusted``,
# ``quote``, ``fx_daily``, ``crypto_daily``, ``sector``, ``sma``). Non-bar
# intervals (quotes, market status, technical indicators, sector performance)
# have no annualization meaning and fall back to the default 252 periods per
# year. The set is derived from ``AlphaVantageProvider`` so it stays in sync
# with the provider instead of drifting out of date.
ALPHAVANTAGE_INTERVALS: frozenset[str] = frozenset(
    {
        *AlphaVantageProvider.INTRADAY_INTERVALS,
        *AlphaVantageProvider.WEEKLY_INTERVALS,
        *AlphaVantageProvider.MONTHLY_INTERVALS,
        *AlphaVantageProvider.QUOTE_INTERVALS,
        *AlphaVantageProvider.MARKET_STATUS_INTERVALS,
        *AlphaVantageProvider.FX_DAILY_INTERVALS,
        *AlphaVantageProvider.FX_INTRADAY_INTERVALS,
        *AlphaVantageProvider.CRYPTO_INTERVALS,
        *AlphaVantageProvider.DIGITAL_CURRENCY_INTERVALS,
        *AlphaVantageProvider.CURRENCY_EXCHANGE_RATE_INTERVALS,
        *AlphaVantageProvider.SYMBOL_SEARCH_INTERVALS,
        *AlphaVantageProvider.TECHNICAL_INDICATORS,
        *AlphaVantageProvider.SECTOR_INTERVALS,
        *AlphaVantageProvider.COMMODITIES_INTERVALS,
        *AlphaVantageProvider.GOLD_INTERVALS,
    }
)


def resolve_periods_per_year(interval: str, override: int | None = None) -> int:
    """Resolve the number of trading periods per year for a data interval.

    Args:
        interval: Data interval string (e.g. ``"1d"``, ``"1wk"``, ``"5m"``).
        override: Explicit value that takes precedence when not ``None``.

    Returns:
        Number of periods per year to use for annualization. Falls back to
        252 (daily) for unrecognized intervals.

    Examples:
        >>> resolve_periods_per_year("1d")
        252
        >>> resolve_periods_per_year("1wk")
        52
        >>> resolve_periods_per_year("1d", override=12)
        12

    """
    if override is not None:
        return override

    key = (interval or "").strip().lower()
    if key in INTERVAL_PERIODS_PER_YEAR:
        return INTERVAL_PERIODS_PER_YEAR[key]

    match = re.fullmatch(r"(\d+)\s*(m|min|mins|minute|minutes)", key)
    if match:
        minutes = int(match.group(1))
        if minutes > 0:
            return max(1, MINUTES_PER_TRADING_DAY * 252 // minutes)

    match = re.fullmatch(r"(\d+)\s*(h|hr|hrs|hour|hours)", key)
    if match:
        hours = int(match.group(1))
        if hours > 0:
            return max(1, MINUTES_PER_TRADING_DAY * 252 // (hours * 60))

    return 252


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

# Default values for CLI arguments (matching the argparser defaults)
CLI_ARG_DEFAULTS = {
    "fast_period": 10,
    "slow_period": 30,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "bb_period": 20,
    "bb_std": 2.0,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "macd_zero_line": False,
    "st_period": 10,
    "st_multiplier": 3.0,
    "dc_period": 20,
    "dc_exit_period": None,
    "aroon_period": 25,
    "kc_ema_period": 20,
    "kc_atr_period": 10,
    "kc_multiplier": 2.0,
    "kc_use_middle_cross": False,
    "stoch_k_period": 14,
    "stoch_d_period": 3,
    "stoch_oversold": 20,
    "stoch_overbought": 80,
    "stoch_use_midline": False,
    "tenkan_period": 9,
    "kijun_period": 26,
    "senkou_b_period": 52,
    "sar_step": 0.02,
    "sar_max_step": 0.20,
}


def _is_supported_interval(interval: str) -> bool:
    """Return whether ``interval`` is a recognized annualization interval."""
    key = (interval or "").strip().lower()
    if key in INTERVAL_PERIODS_PER_YEAR:
        return True
    if key in ALPHAVANTAGE_INTERVALS:
        return True
    minutes_match = re.fullmatch(r"(\d+)\s*(m|min|mins|minute|minutes)", key)
    if minutes_match:
        return int(minutes_match.group(1)) > 0
    hours_match = re.fullmatch(r"(\d+)\s*(h|hr|hrs|hour|hours)", key)
    if hours_match:
        return int(hours_match.group(1)) > 0
    return False


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
        default=None,
        help=(
            "Initial capital (default: the value in the config file, or 100000.0 when no "
            "config file is given)"
        ),
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=None,
        help=(
            "Commission rate (default: the value in the config file, or 0.001 when no config "
            "file is given)"
        ),
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=None,
        help=(
            "Slippage rate (default: the value in the config file, or 0.0005 when no config "
            "file is given)"
        ),
    )
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=None,
        help=(
            "Risk-free rate for Sharpe ratio calculations, e.g. 0.02 for 2%% (default: the value "
            "in the config file, or 0.02 when no config file is given)"
        ),
    )
    parser.add_argument(
        "--interval",
        default=None,
        help=(
            'Data interval (e.g. "1d", "1wk", "5m"). Defaults to the value '
            'of the config file\'s data.default_interval, or to "1d" when no '
            "config file is given."
        ),
    )
    parser.add_argument(
        "--periods-per-year",
        type=int,
        default=None,
        help=(
            "Trading periods per year used to annualize return, volatility, "
            "Sharpe, Sortino and Calmar metrics. Defaults to a value derived "
            "from --interval (252 daily, 52 weekly, 12 monthly, and "
            "252 * 390 / bar-minutes for intraday intervals)."
        ),
    )

    parser.add_argument(
        "--strategy",
        default="ma",
        help="Strategy to run (use --list-strategies to see available options). Ignored if --strategy-config is provided.",
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
    parser.add_argument(
        "--aroon-period",
        type=int,
        default=25,
        help="Aroon period",
    )
    parser.add_argument(
        "--kc-ema-period",
        type=int,
        default=20,
        help="EMA period for Keltner Channel middle line",
    )
    parser.add_argument(
        "--kc-atr-period",
        type=int,
        default=10,
        help="ATR period for Keltner Channel",
    )
    parser.add_argument(
        "--kc-multiplier",
        type=float,
        default=2.0,
        help="Multiplier for ATR to set channel width",
    )
    parser.add_argument(
        "--kc-use-middle-cross",
        action="store_true",
        help="Enable middle line (EMA) crossover signals for Keltner Channel",
    )
    parser.add_argument(
        "--stoch-k-period",
        type=int,
        default=14,
        help="Stochastic %%K period",
    )
    parser.add_argument(
        "--stoch-d-period",
        type=int,
        default=3,
        help="Stochastic %%D period",
    )
    parser.add_argument(
        "--stoch-oversold",
        type=int,
        default=20,
        help="Stochastic oversold threshold",
    )
    parser.add_argument(
        "--stoch-overbought",
        type=int,
        default=80,
        help="Stochastic overbought threshold",
    )
    parser.add_argument(
        "--stoch-use-midline",
        action="store_true",
        help="Enable midline (50) crossover signals for Stochastic",
    )
    parser.add_argument(
        "--tenkan-period",
        type=int,
        default=9,
        help="Tenkan-sen (Conversion Line) period",
    )
    parser.add_argument(
        "--kijun-period",
        type=int,
        default=26,
        help="Kijun-sen (Base Line) period",
    )
    parser.add_argument(
        "--senkou-b-period",
        type=int,
        default=52,
        help="Senkou Span B period",
    )
    parser.add_argument(
        "--sar-step",
        type=float,
        default=0.02,
        help="Parabolic SAR initial acceleration factor (step)",
    )
    parser.add_argument(
        "--sar-max-step",
        type=float,
        default=0.20,
        help="Parabolic SAR maximum acceleration factor",
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
        "--aroon-period-range",
        type=str,
        default="10,50,5",
        help="Aroon period range: min,max,step",
    )
    parser.add_argument(
        "--kc-ema-period-range",
        type=str,
        default="10,30,5",
        help="Keltner EMA period range: min,max,step",
    )
    parser.add_argument(
        "--kc-atr-period-range",
        type=str,
        default="5,20,2",
        help="Keltner ATR period range: min,max,step",
    )
    parser.add_argument(
        "--kc-multiplier-range",
        type=str,
        default="1.0,3.0,0.5",
        help="Keltner multiplier range: min,max,step",
    )
    parser.add_argument(
        "--stoch-k-period-range",
        type=str,
        default="10,20,2",
        help="Stochastic %%K period range: min,max,step",
    )
    parser.add_argument(
        "--stoch-d-period-range",
        type=str,
        default="2,5,1",
        help="Stochastic %%D period range: min,max,step",
    )
    parser.add_argument(
        "--stoch-oversold-range",
        type=str,
        default="10,30,5",
        help="Stochastic oversold range: min,max,step",
    )
    parser.add_argument(
        "--stoch-overbought-range",
        type=str,
        default="70,90,5",
        help="Stochastic overbought range: min,max,step",
    )
    parser.add_argument(
        "--ichimoku-tenkan-period-range",
        type=str,
        default="5,30,2",
        help="Ichimoku Tenkan-sen period range: min,max,step",
    )
    parser.add_argument(
        "--ichimoku-kijun-period-range",
        type=str,
        default="10,60,5",
        help="Ichimoku Kijun-sen period range: min,max,step",
    )
    parser.add_argument(
        "--ichimoku-senkou-b-period-range",
        type=str,
        default="20,120,10",
        help="Ichimoku Senkou Span B period range: min,max,step",
    )
    parser.add_argument(
        "--sar-step-range",
        type=str,
        default="0.01,0.10,0.01",
        help="Parabolic SAR step range: min,max,step",
    )
    parser.add_argument(
        "--sar-max-step-range",
        type=str,
        default="0.10,0.30,0.05",
        help="Parabolic SAR max step range: min,max,step",
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
        "--n-jobs",
        type=int,
        default=1,
        help="Number of parallel jobs for grid/random search (default: 1)",
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
    parser.add_argument(
        "--strategy-config",
        type=str,
        help="Path to YAML file containing strategy configuration (type, name, parameters)",
    )
    parser.add_argument(
        "--output-strategy-config",
        type=str,
        help="Path to YAML file to save the strategy configuration used",
    )

    args = parser.parse_args()
    _validate_range_arguments(args)
    if args.mc_simulations < 1:
        raise ValueError(
            f"invalid --mc-simulations: the value must be at least 1 (got {args.mc_simulations})"
        )
    interval = getattr(args, "interval", None)
    if interval is not None and not _is_supported_interval(interval):
        raise ValueError(
            f"invalid --interval: unrecognized interval {interval!r} "
            f"(expected one of {sorted(INTERVAL_PERIODS_PER_YEAR)} or an "
            f"intraday form like '5m'/'1h')"
        )
    if not (0.0 < args.mc_confidence <= 1.0):
        raise ValueError(
            f"invalid --mc-confidence: the value must be in the range (0, 1] "
            f"(got {args.mc_confidence})"
        )
    if not (0.0 < args.wf_train_size < 1.0):
        raise ValueError(
            f"invalid --wf-train-size: the value must be in the range (0, 1) "
            f"(got {args.wf_train_size})"
        )
    if args.initial_capital is not None and args.initial_capital <= 0:
        raise ValueError(
            f"invalid --initial-capital: the value must be greater than 0 "
            f"(got {args.initial_capital})"
        )
    if args.commission is not None and args.commission < 0:
        raise ValueError(
            f"invalid --commission: the value must be non-negative " f"(got {args.commission})"
        )
    if args.slippage is not None and args.slippage < 0:
        raise ValueError(
            f"invalid --slippage: the value must be non-negative " f"(got {args.slippage})"
        )
    return args


def _validate_range_arguments(args: argparse.Namespace) -> None:
    """Reject malformed ``--*-range`` arguments before the run starts.

    A range argument is 'min,max,step'. A step of zero would make the grid
    search loop forever, so it is reported here instead of hanging later.

    Args:
        args: The parsed command line arguments.

    Raises:
        ValueError: If a range argument is malformed or has a step that is
            not greater than zero.

    """
    for name, value in sorted(vars(args).items()):
        if not name.endswith("_range") or not isinstance(value, str):
            continue
        try:
            parse_range(value)
        except ValueError as e:
            raise ValueError(f"invalid --{name.replace('_', '-')}: {e}") from e


def create_strategy(args: argparse.Namespace):
    """Create strategy instance from args using the factory registry."""
    # If strategy config file is provided, use it
    strategy_config_path = getattr(args, "strategy_config", None)
    if strategy_config_path:
        import yaml

        try:
            with open(strategy_config_path, "r") as f:
                strategy_config = yaml.safe_load(f)
        except OSError as e:
            raise ValueError(
                f"could not read strategy config '{strategy_config_path}': {e.strerror or e}"
            ) from e
        except yaml.YAMLError as e:
            raise ValueError(
                f"invalid YAML in strategy config '{strategy_config_path}': {e}"
            ) from e

        if not isinstance(strategy_config, dict):
            raise ValueError(
                f"invalid strategy config '{strategy_config_path}': expected a mapping, "
                f"got {type(strategy_config).__name__}"
            )
        parameters = strategy_config.get("parameters")
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError(
                f"invalid strategy config '{strategy_config_path}': 'parameters' must be "
                f"a mapping, got {type(parameters).__name__}"
            )

        from quant_trading.strategies.base import Strategy

        try:
            return Strategy.from_config(strategy_config)
        except (TypeError, AttributeError) as e:
            # A malformed file reaches the strategy constructor as a bad
            # argument, which is a user error and not a defect in the library.
            raise ValueError(f"invalid strategy config '{strategy_config_path}': {e}") from e

    # Map strategy keys to lists of (cli_arg, param_name) tuples for built-in strategies
    strategy_param_map = {
        "ma": [("fast_period", "fast_period"), ("slow_period", "slow_period")],
        "ema": [("fast_period", "fast_period"), ("slow_period", "slow_period")],
        "rsi": [
            ("rsi_period", "period"),
            ("rsi_oversold", "oversold"),
            ("rsi_overbought", "overbought"),
        ],
        "bb": [("bb_period", "period"), ("bb_std", "std_dev")],
        "macd": [
            ("macd_fast", "fast_period"),
            ("macd_slow", "slow_period"),
            ("macd_signal", "signal_period"),
            ("macd_zero_line", "use_zero_line"),
        ],
        "supertrend": [("st_period", "period"), ("st_multiplier", "multiplier")],
        "donchian": [("dc_period", "period"), ("dc_exit_period", "exit_period")],
        "aroon": [("aroon_period", "period")],
        "keltner": [
            ("kc_ema_period", "ema_period"),
            ("kc_atr_period", "atr_period"),
            ("kc_multiplier", "multiplier"),
            ("kc_use_middle_cross", "use_middle_cross"),
        ],
        "stoch": [
            ("stoch_k_period", "k_period"),
            ("stoch_d_period", "d_period"),
            ("stoch_oversold", "oversold"),
            ("stoch_overbought", "overbought"),
            ("stoch_use_midline", "use_midline"),
        ],
        "ichimoku": [
            ("tenkan_period", "tenkan_period"),
            ("kijun_period", "kijun_period"),
            ("senkou_b_period", "senkou_b_period"),
        ],
        "sar": [("sar_step", "step"), ("sar_max_step", "max_step")],
        "vwap": [],
    }

    if args.strategy in strategy_param_map:
        # Handle built-in strategies with custom naming
        kwargs = {}
        for cli_arg, param_name in strategy_param_map[args.strategy]:
            value = getattr(args, cli_arg, CLI_ARG_DEFAULTS.get(cli_arg))
            kwargs[param_name] = value

        # Generate the strategy name based on the strategy and parameters
        if args.strategy == "ma":
            kwargs["name"] = f"MA_Crossover_{args.fast_period}_{args.slow_period}"
        elif args.strategy == "ema":
            kwargs["name"] = f"EMA_Crossover_{args.fast_period}_{args.slow_period}"
        elif args.strategy == "rsi":
            kwargs["name"] = f"RSI_{args.rsi_period}"
        elif args.strategy == "bb":
            kwargs["name"] = f"BB_{args.bb_period}_{args.bb_std}"
        elif args.strategy == "macd":
            kwargs["name"] = (
                f"MACD_{getattr(args, 'macd_fast', 12)}_{getattr(args, 'macd_slow', 26)}_{getattr(args, 'macd_signal', 9)}"
            )
        elif args.strategy == "supertrend":
            kwargs["name"] = f"SuperTrend_{args.st_period}_{args.st_multiplier}"
        elif args.strategy == "donchian":
            exit_period = args.dc_exit_period if args.dc_exit_period else args.dc_period
            kwargs["name"] = f"Donchian_{args.dc_period}_{exit_period}"
        elif args.strategy == "aroon":
            kwargs["name"] = f"Aroon_{args.aroon_period}"
        elif args.strategy == "keltner":
            kwargs["name"] = (
                f"Keltner_{args.kc_ema_period}_{args.kc_atr_period}_{args.kc_multiplier}"
            )
        elif args.strategy == "stoch":
            kwargs["name"] = (
                f"Stoch_{args.stoch_k_period}_{args.stoch_d_period}_{args.stoch_oversold}_{args.stoch_overbought}"
            )
        elif args.strategy == "sar":
            kwargs["name"] = f"Parabolic_SAR_{args.sar_step}_{args.sar_max_step}"
        elif args.strategy == "vwap":
            kwargs["name"] = "VWAP"

        return factory_create_strategy(args.strategy, **kwargs)
    else:
        # For non-built-in strategies, use the factory with default parameters
        # and let the strategy use its default name.
        return factory_create_strategy(args.strategy)


def _save_strategy_config(path: str, strategy_cls: type, parameters: dict) -> None:
    """Write the winning strategy configuration to a YAML file.

    Args:
        path: Destination YAML path.
        strategy_cls: The strategy class that produced the winning parameters.
        parameters: The winning parameter dict (may include a 'name' key).
    """
    import yaml

    from quant_trading.strategies.factory import get_registry

    # Resolve the registry key for this class, falling back to the class name.
    registry = get_registry()
    strategy_key = None
    for key, cls in registry.get_all().items():
        if cls is strategy_cls:
            strategy_key = key
            break
    if strategy_key is None:
        strategy_key = strategy_cls.__name__.lower().replace("strategy", "")

    config = {
        "type": strategy_key,
        "name": parameters.get("name", strategy_key),
        "parameters": {k: v for k, v in parameters.items() if k != "name"},
    }

    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f"Strategy configuration saved to {path}")


def _save_json_output(path: str, output_data: dict) -> bool:
    """Write ``output_data`` as JSON to ``path``.

    Args:
        path: Destination path of the JSON file.
        output_data: The data to serialize.

    Returns:
        True when the file was written. False when it could not be written,
        in which case a one-line error message has been printed.
    """
    import json

    try:
        with open(path, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
    except OSError as e:
        print(f"Error: could not write output file '{path}': {e.strerror or e}")
        return False
    print(f"\nResults saved to {path}")
    return True


def list_strategies() -> int:
    """Print available strategies and exit."""
    strategies = factory_list_strategies()
    print("Available strategies:")
    for key, cls in strategies.items():
        try:
            instance = cls()  # type: ignore[call-arg]
        except (TypeError, ValueError):
            try:
                instance = cls(name=f"{key}_dummy")
            except (TypeError, ValueError):
                instance = cls(name="dummy")  # type: ignore
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
        try:
            config = Config.from_yaml(args.config)
        except OSError as e:
            raise ValueError(
                f"could not read config file '{args.config}': {e.strerror or e}"
            ) from e

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

    if args.risk_free_rate is not None:
        config.backtest.risk_free_rate = args.risk_free_rate

    if getattr(args, "initial_capital", None) is not None:
        config.backtest.initial_capital = args.initial_capital

    if getattr(args, "commission", None) is not None:
        config.backtest.commission = args.commission

    if getattr(args, "slippage", None) is not None:
        config.backtest.slippage = args.slippage

    # The --interval flag configures the data layer: it is applied to the
    # configured default_interval so the rule stays in one place. When the
    # flag is not given, the value of the config file (or the built-in
    # default) is kept.
    if getattr(args, "interval", None) is not None:
        config.data.default_interval = args.interval

    # The synthetic provider always emits daily bars regardless of --interval,
    # so daily annualization is the only correct choice for offline runs.
    interval = "1d" if config.data.provider == "synthetic" else config.data.default_interval
    config.backtest.periods_per_year = resolve_periods_per_year(
        interval, getattr(args, "periods_per_year", None)
    )

    return config


def parse_range(range_str: str) -> tuple[float, float, float]:
    """Parse a range string 'min,max,step' into a tuple.

    Args:
        range_str: The range in the 'min,max,step' form.

    Returns:
        The minimum, the maximum and the step of the range.

    Raises:
        ValueError: If the string is not in the 'min,max,step' form, if a part
            is not a number, or if the step is not greater than zero. A step of
            zero would make the grid search loop forever.

    """
    parts = range_str.split(",")
    if len(parts) != 3:
        raise ValueError(f"Invalid range format: {range_str}. Expected 'min,max,step'")
    try:
        minimum, maximum, step = (float(part) for part in parts)
    except ValueError as e:
        raise ValueError(
            f"Invalid range format: {range_str}. Expected three numbers 'min,max,step'"
        ) from e
    if step <= 0:
        raise ValueError(f"Invalid range {range_str}: the step must be greater than 0")
    if minimum > maximum:
        raise ValueError(
            f"Invalid range {range_str}: the minimum ({minimum}) is greater "
            f"than the maximum ({maximum})"
        )
    return minimum, maximum, step


def create_param_grid(args: argparse.Namespace) -> "ParameterGrid":
    """Create parameter grid for optimization based on strategy and args."""
    from quant_trading.optimization import ParameterGrid, ParameterSpace

    grid = ParameterGrid()

    if args.strategy == "ma":
        fast_min, fast_max, fast_step = parse_range(args.ma_fast_range)
        slow_min, slow_max, slow_step = parse_range(args.ma_slow_range)
        grid.add(
            ParameterSpace(
                "fast_period", min_val=fast_min, max_val=fast_max, step=fast_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "slow_period", min_val=slow_min, max_val=slow_max, step=slow_step, param_type=int
            )
        )
        grid.set_validator(lambda p: p["fast_period"] < p["slow_period"])
    elif args.strategy == "rsi":
        period_min, period_max, period_step = parse_range(args.rsi_period_range)
        oversold_min, oversold_max, oversold_step = parse_range(args.rsi_oversold_range)
        overbought_min, overbought_max, overbought_step = parse_range(args.rsi_overbought_range)
        grid.add(
            ParameterSpace(
                "period", min_val=period_min, max_val=period_max, step=period_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "oversold",
                min_val=oversold_min,
                max_val=oversold_max,
                step=oversold_step,
                param_type=int,
            )
        )
        grid.add(
            ParameterSpace(
                "overbought",
                min_val=overbought_min,
                max_val=overbought_max,
                step=overbought_step,
                param_type=int,
            )
        )
        grid.set_validator(lambda p: p["oversold"] < p["overbought"])
    elif args.strategy == "bb":
        period_min, period_max, period_step = parse_range(args.bb_period_range)
        std_min, std_max, std_step = parse_range(args.bb_std_range)
        grid.add(
            ParameterSpace(
                "period", min_val=period_min, max_val=period_max, step=period_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "std_dev", min_val=std_min, max_val=std_max, step=std_step, param_type=float
            )
        )
    elif args.strategy == "macd":
        fast_min, fast_max, fast_step = parse_range(args.macd_fast_range)
        slow_min, slow_max, slow_step = parse_range(args.macd_slow_range)
        signal_min, signal_max, signal_step = parse_range(args.macd_signal_range)
        grid.add(
            ParameterSpace(
                "fast_period", min_val=fast_min, max_val=fast_max, step=fast_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "slow_period", min_val=slow_min, max_val=slow_max, step=slow_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "signal_period",
                min_val=signal_min,
                max_val=signal_max,
                step=signal_step,
                param_type=int,
            )
        )
        grid.add(ParameterSpace("use_zero_line", values=[False, True], param_type=bool))
        grid.set_validator(lambda p: p["fast_period"] < p["slow_period"])
    elif args.strategy == "supertrend":
        period_min, period_max, period_step = parse_range(args.st_period_range)
        mult_min, mult_max, mult_step = parse_range(args.st_multiplier_range)
        grid.add(
            ParameterSpace(
                "period", min_val=period_min, max_val=period_max, step=period_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "multiplier", min_val=mult_min, max_val=mult_max, step=mult_step, param_type=float
            )
        )
    elif args.strategy == "donchian":
        period_min, period_max, period_step = parse_range(args.dc_period_range)
        exit_min, exit_max, exit_step = parse_range(args.dc_exit_period_range)
        grid.add(
            ParameterSpace(
                "period", min_val=period_min, max_val=period_max, step=period_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "exit_period", min_val=exit_min, max_val=exit_max, step=exit_step, param_type=int
            )
        )
    elif args.strategy == "aroon":
        period_min, period_max, period_step = parse_range(args.aroon_period_range)
        grid.add(
            ParameterSpace(
                "period", min_val=period_min, max_val=period_max, step=period_step, param_type=int
            )
        )
    elif args.strategy == "keltner":
        ema_min, ema_max, ema_step = parse_range(args.kc_ema_period_range)
        atr_min, atr_max, atr_step = parse_range(args.kc_atr_period_range)
        mult_min, mult_max, mult_step = parse_range(args.kc_multiplier_range)
        grid.add(
            ParameterSpace(
                "ema_period", min_val=ema_min, max_val=ema_max, step=ema_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "atr_period", min_val=atr_min, max_val=atr_max, step=atr_step, param_type=int
            )
        )
        grid.add(
            ParameterSpace(
                "multiplier", min_val=mult_min, max_val=mult_max, step=mult_step, param_type=float
            )
        )
        grid.add(ParameterSpace("use_middle_cross", values=[False, True], param_type=bool))
    elif args.strategy == "stoch":
        k_min, k_max, k_step = parse_range(args.stoch_k_period_range)
        d_min, d_max, d_step = parse_range(args.stoch_d_period_range)
        oversold_min, oversold_max, oversold_step = parse_range(args.stoch_oversold_range)
        overbought_min, overbought_max, overbought_step = parse_range(args.stoch_overbought_range)
        grid.add(
            ParameterSpace("k_period", min_val=k_min, max_val=k_max, step=k_step, param_type=int)
        )
        grid.add(
            ParameterSpace("d_period", min_val=d_min, max_val=d_max, step=d_step, param_type=int)
        )
        grid.add(
            ParameterSpace(
                "oversold",
                min_val=oversold_min,
                max_val=oversold_max,
                step=oversold_step,
                param_type=int,
            )
        )
        grid.add(
            ParameterSpace(
                "overbought",
                min_val=overbought_min,
                max_val=overbought_max,
                step=overbought_step,
                param_type=int,
            )
        )
        grid.add(ParameterSpace("use_midline", values=[False, True], param_type=bool))
        grid.set_validator(lambda p: p["oversold"] < p["overbought"])
    elif args.strategy == "ichimoku":
        tenkan_min, tenkan_max, tenkan_step = parse_range(args.ichimoku_tenkan_period_range)
        kijun_min, kijun_max, kijun_step = parse_range(args.ichimoku_kijun_period_range)
        senkou_b_min, senkou_b_max, senkou_b_step = parse_range(args.ichimoku_senkou_b_period_range)
        grid.add(
            ParameterSpace(
                "tenkan_period",
                min_val=tenkan_min,
                max_val=tenkan_max,
                step=tenkan_step,
                param_type=int,
            )
        )
        grid.add(
            ParameterSpace(
                "kijun_period",
                min_val=kijun_min,
                max_val=kijun_max,
                step=kijun_step,
                param_type=int,
            )
        )
        grid.add(
            ParameterSpace(
                "senkou_b_period",
                min_val=senkou_b_min,
                max_val=senkou_b_max,
                step=senkou_b_step,
                param_type=int,
            )
        )
        grid.set_validator(
            lambda p: p["tenkan_period"] < p["kijun_period"]
            and p["senkou_b_period"] > p["kijun_period"]
        )
    elif args.strategy == "sar":
        step_min, step_max, step_step = parse_range(args.sar_step_range)
        max_step_min, max_step_max, max_step_step = parse_range(args.sar_max_step_range)
        grid.add(
            ParameterSpace(
                "step",
                min_val=step_min,
                max_val=step_max,
                step=step_step,
                param_type=float,
            )
        )
        grid.add(
            ParameterSpace(
                "max_step",
                min_val=max_step_min,
                max_val=max_step_max,
                step=max_step_step,
                param_type=float,
            )
        )
        grid.set_validator(lambda p: p["step"] <= p["max_step"])

    elif args.strategy == "vwap":
        # VWAP has no configurable parameters
        pass

    return grid


def run_optimization(
    args: argparse.Namespace, config: Config, start_date: datetime, end_date: datetime
) -> int:
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
            initial_capital=config.backtest.initial_capital,
            commission=config.backtest.commission,
            slippage=config.backtest.slippage,
            interval=args.interval,
            config=config,
            n_iter=args.n_iter,
            n_jobs=args.n_jobs,
            periods_per_year=config.backtest.periods_per_year,
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
            initial_capital=config.backtest.initial_capital,
            commission=config.backtest.commission,
            slippage=config.backtest.slippage,
            interval=args.interval,
            config=config,
            n_initial_points=args.bayesian_n_initial,
            n_calls=args.n_iter,
            acq_func=args.bayesian_acq_func,
            acq_optimizer=args.bayesian_acq_optimizer,
            periods_per_year=config.backtest.periods_per_year,
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
            initial_capital=config.backtest.initial_capital,
            commission=config.backtest.commission,
            slippage=config.backtest.slippage,
            interval=args.interval,
            config=config,
            n_jobs=args.n_jobs,
            periods_per_year=config.backtest.periods_per_year,
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
        print(f"Total Costs:     ${result.best_result.total_costs:,.2f}")
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
        print(
            f"{i+1:<5} {params_str:<50} {r['score']:>10.4f} {r['total_return_pct']:>10.2f} {r['sharpe_ratio']:>8.4f} {r['max_drawdown_pct']:>10.2f}"
        )

    if args.output:
        output_data = {
            "strategy": strategy_cls.__name__,
            "symbols": args.symbols,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "optimizer": args.optimizer,
            "objective": args.objective,
            "best_params": result.best_params,
            "best_score": result.best_score,
            "best_result": (
                {
                    "total_return_pct": (
                        result.best_result.total_return_pct if result.best_result else None
                    ),
                    "total_costs": (result.best_result.total_costs if result.best_result else None),
                    "sharpe_ratio": (
                        result.best_result.metrics.sharpe_ratio if result.best_result else None
                    ),
                    "max_drawdown_pct": (
                        result.best_result.metrics.max_drawdown_pct if result.best_result else None
                    ),
                    "win_rate": result.best_result.metrics.win_rate if result.best_result else None,
                    "profit_factor": (
                        result.best_result.metrics.profit_factor if result.best_result else None
                    ),
                    "num_trades": (
                        result.best_result.metrics.num_trades if result.best_result else None
                    ),
                }
                if result.best_result
                else None
            ),
            "all_results": result.all_results,
        }
        if not _save_json_output(args.output, output_data):
            return 1

    # Persist the winning strategy configuration when requested
    if args.output_strategy_config:
        _save_strategy_config(args.output_strategy_config, strategy_cls, result.best_params)

    return 0


def run_walk_forward(
    args: argparse.Namespace, config: Config, start_date: datetime, end_date: datetime
) -> int:
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
        optimizer_kwargs = {"n_iter": args.n_iter, "n_jobs": args.n_jobs}
    elif args.wf_optimizer == "bayesian":
        optimizer_kwargs = {
            "n_initial_points": args.bayesian_n_initial,
            "n_calls": args.n_iter,
            "acq_func": args.bayesian_acq_func,
            "acq_optimizer": args.bayesian_acq_optimizer,
        }
    else:
        optimizer_kwargs = {"n_jobs": args.n_jobs}

    optimizer = WalkForwardOptimizer(
        strategy_cls=strategy_cls,
        param_grid=param_grid,
        objective=objective,
        symbols=args.symbols,
        start=start_date,
        end=end_date,
        initial_capital=config.backtest.initial_capital,
        commission=config.backtest.commission,
        slippage=config.backtest.slippage,
        interval=args.interval,
        data_manager=None,
        config=config,
        n_windows=args.wf_windows,
        train_size=args.wf_train_size,
        anchored=args.wf_anchored,
        optimizer=args.wf_optimizer,
        optimizer_kwargs=optimizer_kwargs,
        periods_per_year=config.backtest.periods_per_year,
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
        print(
            f"{'Window':<7} {'Train Return%':>14} {'Train Sharpe':>13} {'Test Return%':>13} {'Test Sharpe':>12} {'Test MaxDD%':>13}"
        )
        print(f"{'-' * 75}")
        for _, row in df.iterrows():
            print(
                f"{int(row['window']):<7} {row['train_return_pct']:>14.2f} {row['train_sharpe']:>13.4f} "
                f"{row['test_return_pct']:>13.2f} {row['test_sharpe']:>12.4f} {row['test_max_dd']:>13.2f}"
            )

    summary = result.summary()
    print("\nSummary:")
    print(f"  Windows:           {summary['n_windows']}")
    print(f"  Avg Test Return:   {summary['avg_test_return_pct']:.2f}%")
    print(f"  Avg Test Sharpe:   {summary['avg_test_sharpe']:.4f}")
    print(f"  Avg Test Max DD:   {summary['avg_test_max_dd_pct']:.2f}%")
    print(f"  Window Win Rate:   {summary['win_rate_windows']:.2%}")

    if result.combined_test_result:
        print(f"  Combined Test Return: {summary['combined_test_return_pct']:.2f}%")
        print(f"  Combined Test Costs:  ${result.combined_test_result.total_costs:,.2f}")
        print(f"  Combined Test Sharpe: {summary['combined_test_sharpe']:.4f}")

    if args.output:
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
        if not _save_json_output(args.output, output_data):
            return 1

    # Persist the most recent window's winning strategy configuration when
    # requested. The last window's params are the most current calibration and
    # the natural choice for continuing the walk-forward series.
    if args.output_strategy_config:
        last_params = None
        for window in reversed(result.windows):
            if window.best_params:
                last_params = dict(window.best_params)
                break
        if last_params is None:
            last_params = {}
        _save_strategy_config(args.output_strategy_config, strategy_cls, last_params)

    return 0


def _get_regime_analysis(result, args: argparse.Namespace, periods_per_year: int = 252):
    """Get regime detection results for a backtest's equity curve.

    Args:
        result: Backtest result whose equity curve is labelled.
        args: Parsed CLI arguments.
        periods_per_year: Trading periods per year the regime volatility and
            return were annualized with.

    """
    from quant_trading.backtest import analyze_regimes

    analysis = analyze_regimes(
        result,
        window=args.regime_window,
        vol_threshold=args.regime_vol_threshold,
        return_threshold=args.regime_return_threshold,
        periods_per_year=periods_per_year,
    )
    return analysis


def _print_regime_analysis(analysis) -> None:
    """Print regime detection results for a backtest's equity curve."""
    summary = analysis.summary()

    print(f"\n{'=' * 60}")
    print("Market Regime Analysis")
    print(f"{'=' * 60}")
    print(f"Current Regime:   {summary['current_regime']}")
    print(f"Total Volatility: {summary['total_volatility']:.4f}")
    print(f"Total Return:      {summary['total_return_pct']:.2f}%")
    print(f"Regime Segments:   {summary['n_segments']}")
    print(f"Periods per Year:  {summary['periods_per_year']}")

    if summary["n_segments"] > 0:
        print(f"\n{'Regime':<22} {'Start':<12} {'End':<12} {'Vol':>8} {'Ret %':>8}")
        print(f"{'-' * 62}")
        for seg in analysis.segments:
            print(
                f"{seg.regime.value:<22} {str(seg.start)[:10]:<12} {str(seg.end)[:10]:<12} "
                f"{seg.volatility:>8.4f} {seg.return_pct:>8.2f}"
            )


def _get_monte_carlo_analysis(result, args: argparse.Namespace, periods_per_year: int = 252):
    """Get Monte Carlo simulation results for a backtest's equity curve.

    Args:
        result: Backtest result whose equity curve is resampled.
        args: Parsed CLI arguments.
        periods_per_year: Trading periods per year of the resampled returns,
            used to annualize the simulated metrics.

    """
    mc = run_monte_carlo(
        result,
        n_simulations=args.mc_simulations,
        confidence_level=args.mc_confidence,
        method=args.mc_method,
        random_state=args.mc_seed,
        periods_per_year=periods_per_year,
    )
    # Store method for printing
    try:
        mc._method = args.mc_method  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        pass
    return mc


def _print_monte_carlo_analysis(mc) -> None:
    """Print Monte Carlo simulation results for a backtest's equity curve."""
    summary = mc.summary()

    print(f"\n{'=' * 60}")
    print("Monte Carlo Simulation")
    print(f"{'=' * 60}")
    method_str = getattr(mc, "_method", "bootstrap")
    print(f"Method:            {method_str}")
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


def _get_trade_analysis(result, args: argparse.Namespace, risk_free_rate: float = 0.02):
    """Get detailed trade analysis for a backtest result.

    Args:
        result: Backtest result whose trade log is analysed.
        args: Parsed CLI arguments.
        risk_free_rate: Annual risk-free rate of the run, used for the
            trade-level Sharpe and Sortino ratios.

    """
    from quant_trading.backtest import analyze_trades

    analysis = analyze_trades(result, risk_free_rate=risk_free_rate)
    return analysis


def _print_trade_analysis(analysis) -> None:
    """Print detailed trade analysis for a backtest result."""
    from quant_trading.backtest import print_trade_analysis

    print_trade_analysis(analysis)


def main() -> int:
    """Run the command line interface.

    A user error -- an unknown strategy, a missing file, malformed input --
    is reported as a one-line message with exit code 1 instead of a
    traceback.

    Returns:
        The exit code of the run: 0 on success, 1 on a user error.
    """
    try:
        return _run_cli()
    except (OSError, ValueError) as e:
        print(f"Error: {e}")
        return 1


def _run_cli() -> int:
    """Parse the arguments and run the requested mode.

    Returns:
        The exit code of the run: 0 on success, 1 on a failed run.
    """
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

    # Save strategy configuration if requested
    if args.output_strategy_config:
        import yaml

        from quant_trading.strategies.factory import get_registry

        # Determine strategy type key from registry
        registry = get_registry()
        strategy_key = None
        for key, cls in registry.get_all().items():
            if cls == strategy.__class__:
                strategy_key = key
                break
        if strategy_key is None:
            # Fallback to a generic key based on class name
            strategy_key = strategy.__class__.__name__.lower().replace("strategy", "")

        strategy_config = {
            "type": strategy_key,
            "name": strategy.name,
            "parameters": strategy.get_parameters(),
        }

        with open(args.output_strategy_config, "w") as f:
            yaml.dump(strategy_config, f, default_flow_style=False)
        print(f"Strategy configuration saved to {args.output_strategy_config}")

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
            initial_capital=config.backtest.initial_capital,
            commission=config.backtest.commission,
            slippage=config.backtest.slippage,
            interval=config.data.default_interval,
            config=config,
            periods_per_year=config.backtest.periods_per_year,
        )

        print(f"\n{'=' * 60}")
        print(f"Results for: {strategy.name}")
        print(f"{'=' * 60}")
        print(f"Initial Capital: ${result.initial_capital:,.2f}")
        print(f"Final Value:     ${result.final_value:,.2f}")
        print(f"Total Return:    ${result.total_return:,.2f} " f"({result.total_return_pct:.2f}%)")
        print(f"Realized PnL:    ${result.metrics.total_pnl:,.2f}")
        print(f"Unrealized PnL:  ${result.metrics.unrealized_pnl:,.2f}")
        print(f"Total Costs:     ${result.total_costs:,.2f}")
        print(f"Total Trades:    {result.metrics.num_trades}")
        print(f"Win Rate:        {result.metrics.win_rate:.2%}")
        print(f"Sharpe Ratio:    {result.metrics.sharpe_ratio:.2f}")
        print(f"Max Drawdown:    {result.metrics.max_drawdown_pct:.2f}%")
        print(f"Profit Factor:   {result.metrics.profit_factor:.2f}")
        print(f"Sortino Ratio:   {result.metrics.sortino_ratio:.2f}")
        print(f"Volatility:      {result.metrics.volatility:.2%}")
        print(f"VaR (95%):       {result.metrics.var_95:.2%}")
        print(f"Calmar Ratio:    {result.metrics.calmar_ratio:.2f}")

        if args.regime:
            regime_analysis = _get_regime_analysis(
                result, args, periods_per_year=config.backtest.periods_per_year
            )
            _print_regime_analysis(regime_analysis)

        if args.monte_carlo:
            mc_analysis = _get_monte_carlo_analysis(
                result, args, periods_per_year=config.backtest.periods_per_year
            )
            _print_monte_carlo_analysis(mc_analysis)

        if args.trade_analysis:
            trade_analysis = _get_trade_analysis(
                result, args, risk_free_rate=config.backtest.risk_free_rate
            )
            _print_trade_analysis(trade_analysis)

        if args.output:
            output_data = {
                "strategy": strategy.name,
                "symbols": args.symbols,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "initial_capital": result.initial_capital,
                "final_value": result.final_value,
                "total_return": result.total_return,
                "total_return_pct": result.total_return_pct,
                "total_pnl": result.metrics.total_pnl,
                "unrealized_pnl": result.metrics.unrealized_pnl,
                "total_costs": result.total_costs,
                "num_trades": result.metrics.num_trades,
                "win_rate": result.metrics.win_rate,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "max_drawdown_pct": result.metrics.max_drawdown_pct,
                "profit_factor": result.metrics.profit_factor,
                "sortino_ratio": result.metrics.sortino_ratio,
                "volatility": result.metrics.volatility,
                "var_95": result.metrics.var_95,
                "calmar_ratio": result.metrics.calmar_ratio,
            }
            if args.regime:
                output_data["regime_analysis"] = regime_analysis.to_dict()
            if args.monte_carlo:
                output_data["monte_carlo"] = mc_analysis.summary()
            if args.trade_analysis:
                output_data["trade_analysis"] = trade_analysis.to_dict()
            if not _save_json_output(args.output, output_data):
                return 1

    except (ValueError, RuntimeError, KeyError) as e:
        print(f"Error running backtest: {e}")
        return 1

    return 0


def run_combined(
    args: argparse.Namespace, config: Config, start_date: datetime, end_date: datetime
) -> int:
    """Run all strategies and compare results."""
    print("Running combined backtest for all strategies")
    print(f"Symbols: {args.symbols}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Provider: {config.data.provider}")
    if config.data.offline:
        print("Mode: OFFLINE (synthetic data)")

    registry = get_registry()
    # Use canonical builtin strategies for compatibility, but also include any
    # additional registered strategies (e.g., custom ones added in tests).
    strategy_keys_to_run = list(BUILTIN_STRATEGY_KEYS)
    for k in registry.primary_keys():
        if k not in strategy_keys_to_run:
            strategy_keys_to_run.append(k)
    results = []
    for strategy_key in strategy_keys_to_run:
        # Create a copy of args with the current strategy
        strategy_args = argparse.Namespace(**vars(args))
        strategy_args.strategy = strategy_key
        # Set defaults for strategy-specific args
        if strategy_key == "donchian":
            strategy_args.dc_period = getattr(args, "dc_period", 20)
            strategy_args.dc_exit_period = getattr(args, "dc_exit_period", None)
        elif strategy_key == "aroon":
            strategy_args.aroon_period = getattr(args, "aroon_period", 25)
        elif strategy_key == "keltner":
            strategy_args.kc_ema_period = getattr(args, "kc_ema_period", 20)
            strategy_args.kc_atr_period = getattr(args, "kc_atr_period", 10)
            strategy_args.kc_multiplier = getattr(args, "kc_multiplier", 2.0)
            strategy_args.kc_use_middle_cross = getattr(args, "kc_use_middle_cross", False)
        elif strategy_key == "stoch":
            strategy_args.stoch_k_period = getattr(args, "stoch_k_period", 14)
            strategy_args.stoch_d_period = getattr(args, "stoch_d_period", 3)
            strategy_args.stoch_oversold = getattr(args, "stoch_oversold", 20)
            strategy_args.stoch_overbought = getattr(args, "stoch_overbought", 80)
            strategy_args.stoch_use_midline = getattr(args, "stoch_use_midline", False)
        elif strategy_key == "sar":
            strategy_args.sar_step = getattr(args, "sar_step", 0.02)
            strategy_args.sar_max_step = getattr(args, "sar_max_step", 0.20)
        strategy = create_strategy(strategy_args)

        try:
            result = run_backtest(
                strategy=strategy,
                symbols=args.symbols,
                start=start_date,
                end=end_date,
                initial_capital=config.backtest.initial_capital,
                commission=config.backtest.commission,
                slippage=config.backtest.slippage,
                interval=args.interval,
                config=config,
                periods_per_year=config.backtest.periods_per_year,
            )
            results.append((strategy.name, result))
            print(
                f"  ✓ {strategy.name}: {result.total_return_pct:.2f}% return, Sharpe {result.metrics.sharpe_ratio:.2f}"
            )
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
    print(
        f"{'Strategy':<30} {'Return %':>10} {'Sharpe':>8} {'Max DD %':>10} {'Win Rate':>10} {'Trades':>8} {'Costs':>12}"
    )
    print(f"{'-' * 80}")
    for name, result in results:
        print(
            f"{name:<30} {result.total_return_pct:>10.2f} "
            f"{result.metrics.sharpe_ratio:>8.2f} "
            f"{result.metrics.max_drawdown_pct:>10.2f} "
            f"{result.metrics.win_rate:>9.2%} "
            f"{result.metrics.num_trades:>8} "
            f"${result.total_costs:>11,.2f}"
        )

    # Find best by Sharpe ratio
    best = max(results, key=lambda x: x[1].metrics.sharpe_ratio)
    print(f"\nBest strategy (by Sharpe): {best[0]} (Sharpe: {best[1].metrics.sharpe_ratio:.2f})")

    # The analysis modules work on a single equity curve, so in combined mode
    # they are reported for the best strategy. Without them the flags would be
    # silently ignored, because combined mode runs one backtest per strategy
    # and there is no combined curve to analyse.
    regime_analysis = None
    mc_analysis = None
    trade_analysis = None
    wants_regime = getattr(args, "regime", False)
    wants_monte_carlo = getattr(args, "monte_carlo", False)
    wants_trade_analysis = getattr(args, "trade_analysis", False)
    if wants_regime or wants_monte_carlo or wants_trade_analysis:
        best_result = best[1]
        print(f"\nAnalysis of the best strategy: {best[0]}")
        if wants_regime:
            regime_analysis = _get_regime_analysis(
                best_result, args, periods_per_year=config.backtest.periods_per_year
            )
            _print_regime_analysis(regime_analysis)
        if wants_monte_carlo:
            mc_analysis = _get_monte_carlo_analysis(
                best_result, args, periods_per_year=config.backtest.periods_per_year
            )
            _print_monte_carlo_analysis(mc_analysis)
        if wants_trade_analysis:
            trade_analysis = _get_trade_analysis(
                best_result, args, risk_free_rate=config.backtest.risk_free_rate
            )
            _print_trade_analysis(trade_analysis)

    if args.output:
        output_data = {
            "comparison": [
                {
                    "strategy": name,
                    "total_return_pct": result.total_return_pct,
                    "total_return": result.total_return,
                    "total_costs": result.total_costs,
                    "total_pnl": result.metrics.total_pnl,
                    "unrealized_pnl": result.metrics.unrealized_pnl,
                    "sharpe_ratio": result.metrics.sharpe_ratio,
                    "max_drawdown_pct": result.metrics.max_drawdown_pct,
                    "win_rate": result.metrics.win_rate,
                    "num_trades": result.metrics.num_trades,
                }
                for name, result in results
            ],
            "best_strategy": best[0],
        }
        if regime_analysis is not None:
            output_data["regime_analysis"] = regime_analysis.to_dict()
        if mc_analysis is not None:
            output_data["monte_carlo"] = mc_analysis.summary()
        if trade_analysis is not None:
            output_data["trade_analysis"] = trade_analysis.to_dict()
        if not _save_json_output(args.output, output_data):
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
