"""Backtesting module for strategy validation."""

from .analysis import (
    BacktestRegimeAnalysis,
    analyze_regimes,
    regime_for_backtest,
)
from .engine import BacktestEngine, BacktestResult, run_backtest
from .metrics import BacktestMetrics
from .trade_analysis import TradeAnalysis, analyze_trades, print_trade_analysis
from .trade_log import TradeLog, split_trade_log

__all__ = [
    "BacktestEngine",
    "BacktestMetrics",
    "BacktestRegimeAnalysis",
    "BacktestResult",
    "TradeAnalysis",
    "TradeLog",
    "analyze_regimes",
    "analyze_trades",
    "print_trade_analysis",
    "regime_for_backtest",
    "run_backtest",
    "split_trade_log",
]
