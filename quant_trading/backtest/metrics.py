"""Backtest metrics calculation."""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant_trading.risk.metrics import (
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_var,
    calculate_volatility,
)


@dataclass
class BacktestMetrics:
    """Comprehensive backtest performance metrics."""

    # Returns
    total_return: float = 0.0
    total_return_pct: float = 0.0
    annual_return: float = 0.0
    annual_return_pct: float = 0.0

    # Risk
    volatility: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0

    # Ratios
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Other
    win_rate: float = 0.0
    profit_factor: float = 0.0
    num_trades: int = 0
    num_winning_trades: int = 0
    num_losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    var_95: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_return": self.total_return,
            "total_return_pct": self.total_return_pct,
            "annual_return": self.annual_return,
            "annual_return_pct": self.annual_return_pct,
            "volatility": self.volatility,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "num_trades": self.num_trades,
            "num_winning_trades": self.num_winning_trades,
            "num_losing_trades": self.num_losing_trades,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "var_95": self.var_95,
        }


def calculate_backtest_metrics(
    equity_curve: pd.Series,
    trades: pd.DataFrame | None = None,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> BacktestMetrics:
    """Calculate comprehensive backtest metrics."""
    metrics = BacktestMetrics()

    if len(equity_curve) < 2:
        return metrics

    initial_value = equity_curve.iloc[0]
    final_value = equity_curve.iloc[-1]

    metrics.total_return = final_value - initial_value
    metrics.total_return_pct = (final_value / initial_value - 1) * 100

    returns = calculate_returns(equity_curve)
    if len(returns) > 0:
        metrics.annual_return = returns.mean() * periods_per_year
        metrics.annual_return_pct = metrics.annual_return * 100
        metrics.volatility = calculate_volatility(returns)
        metrics.max_drawdown = calculate_max_drawdown(equity_curve)
        metrics.max_drawdown_pct = metrics.max_drawdown * 100
        metrics.sharpe_ratio = calculate_sharpe_ratio(returns, risk_free_rate)
        metrics.sortino_ratio = calculate_sortino_ratio(returns, risk_free_rate)
        metrics.calmar_ratio = calculate_calmar_ratio(returns, equity_curve)
        metrics.var_95 = calculate_var(returns, 0.95)

    # Trade statistics
    if trades is not None and len(trades) > 0 and "pnl" in trades.columns:
        winning = trades[trades["pnl"] > 0]
        losing = trades[trades["pnl"] < 0]

        metrics.num_trades = len(trades)
        metrics.num_winning_trades = len(winning)
        metrics.num_losing_trades = len(losing)
        metrics.win_rate = len(winning) / len(trades) if len(trades) > 0 else 0

        metrics.avg_win = winning["pnl"].mean() if len(winning) > 0 else 0
        metrics.avg_loss = losing["pnl"].mean() if len(losing) > 0 else 0
        metrics.largest_win = winning["pnl"].max() if len(winning) > 0 else 0
        metrics.largest_loss = losing["pnl"].min() if len(losing) > 0 else 0

        gross_profit = winning["pnl"].sum() if len(winning) > 0 else 0
        gross_loss = abs(losing["pnl"].sum()) if len(losing) > 0 else 0
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    return metrics
