"""Risk metrics calculation utilities."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RiskMetrics:
    """Container for portfolio risk metrics."""

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    volatility: float = 0.0
    var_95: float = 0.0  # Value at Risk (95% confidence)
    var_99: float = 0.0  # Value at Risk (99% confidence)
    beta: float = 0.0
    alpha: float = 0.0
    calmar_ratio: float = 0.0

    def to_dict(self) -> dict:
        return {
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "volatility": self.volatility,
            "var_95": self.var_95,
            "var_99": self.var_99,
            "beta": self.beta,
            "alpha": self.alpha,
            "calmar_ratio": self.calmar_ratio,
        }


def calculate_returns(prices: pd.Series) -> pd.Series:
    """Calculate simple returns from price series."""
    return prices.pct_change().dropna()


def calculate_volatility(returns: pd.Series, annualize: bool = True) -> float:
    """Calculate volatility of returns."""
    if len(returns) < 2:
        return 0.0
    vol = returns.std()
    if annualize:
        vol *= np.sqrt(252)
    return float(vol)


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """Calculate maximum drawdown from equity curve."""
    if len(equity_curve) == 0:
        return 0.0
    running_max = equity_curve.cummax()
    if running_max.eq(0).all():
        return 0.0
    drawdown = (equity_curve - running_max) / running_max
    return float(drawdown.min())


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    annualize: bool = True,
) -> float:
    """Calculate Sharpe ratio."""
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    excess = returns.mean() - risk_free_rate / 252
    sharpe = excess / returns.std()
    if annualize:
        sharpe *= np.sqrt(252)
    return float(sharpe)


def calculate_sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    annualize: bool = True,
) -> float:
    """Calculate Sortino ratio (uses downside deviation)."""
    if len(returns) == 0:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) < 2:
        return 0.0
    downside_std = downside.std()
    if downside_std == 0:
        return 0.0
    excess = returns.mean() - risk_free_rate / 252
    sortino = excess / downside_std
    if annualize:
        sortino *= np.sqrt(252)
    return float(sortino)


def calculate_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Calculate Value at Risk using historical method."""
    if len(returns) == 0:
        return 0.0
    return float(np.percentile(returns, (1 - confidence) * 100))


def calculate_beta(returns: pd.Series, market_returns: pd.Series) -> float:
    """Calculate portfolio beta relative to market."""
    if len(returns) < 2 or len(market_returns) < 2:
        return 0.0
    aligned = pd.concat([returns, market_returns], axis=1).dropna()
    if len(aligned) < 2:
        return 0.0
    cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
    var = aligned.iloc[:, 1].var()
    if var == 0:
        return 0.0
    return float(cov / var)


def calculate_alpha(
    returns: pd.Series,
    market_returns: pd.Series,
    risk_free_rate: float = 0.02,
) -> float:
    """Calculate Jensen's alpha."""
    beta = calculate_beta(returns, market_returns)
    if beta == 0:
        return 0.0
    avg_return = returns.mean() * 252
    avg_market = market_returns.mean() * 252
    return float(avg_return - (risk_free_rate + beta * (avg_market - risk_free_rate)))


def calculate_calmar_ratio(returns: pd.Series, equity_curve: pd.Series) -> float:
    """Calculate Calmar ratio (annual return / max drawdown)."""
    if len(returns) == 0:
        return 0.0
    annual_return = returns.mean() * 252
    max_dd = calculate_max_drawdown(equity_curve)
    if max_dd == 0:
        return 0.0
    return float(annual_return / abs(max_dd))


def calculate_all_metrics(
    equity_curve: pd.Series,
    market_returns: pd.Series | None = None,
    risk_free_rate: float = 0.02,
) -> RiskMetrics:
    """Calculate all risk metrics from an equity curve."""
    returns = calculate_returns(equity_curve)

    metrics = RiskMetrics(
        sharpe_ratio=calculate_sharpe_ratio(returns, risk_free_rate),
        sortino_ratio=calculate_sortino_ratio(returns, risk_free_rate),
        max_drawdown=calculate_max_drawdown(equity_curve),
        volatility=calculate_volatility(returns),
        var_95=calculate_var(returns, 0.95),
        var_99=calculate_var(returns, 0.99),
        calmar_ratio=calculate_calmar_ratio(returns, equity_curve),
    )

    if market_returns is not None:
        metrics.beta = calculate_beta(returns, market_returns)
        metrics.alpha = calculate_alpha(returns, market_returns, risk_free_rate)

    return metrics
