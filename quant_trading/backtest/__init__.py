"""Backtesting module for strategy validation."""

from .analysis import (
    BacktestRegimeAnalysis,
    analyze_regimes,
    regime_for_backtest,
)
from .engine import BacktestEngine, BacktestResult, Trade, run_backtest
from .metrics import BacktestMetrics
from .report import ReportConfig, generate_html_report, generate_report_from_dict
from .trade_analysis import TradeAnalysis, analyze_trades, print_trade_analysis
from .trade_log import TradeLog, split_trade_log

__all__ = [
    "BacktestEngine",
    "BacktestMetrics",
    "BacktestRegimeAnalysis",
    "BacktestResult",
    "ReportConfig",
    "Trade",
    "TradeAnalysis",
    "TradeLog",
    "analyze_regimes",
    "analyze_trades",
    "generate_html_report",
    "generate_report_from_dict",
    "print_trade_analysis",
    "regime_for_backtest",
    "run_backtest",
    "split_trade_log",
]
