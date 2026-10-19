"""Risk metrics calculation utilities.

This module provides functions for calculating common portfolio risk metrics
such as Sharpe ratio, Sortino ratio, maximum drawdown, volatility, Value at
Risk (VaR), beta, alpha, and Calmar ratio. It also includes the
``RiskMetrics`` dataclass for convenient storage and serialization of these
metrics.

Examples:
    >>> import pandas as pd
    >>> prices = pd.Series([100, 101, 102, 101, 103, 102, 104])
    >>> equity = (1 + prices.pct_change().fillna(0)).cumprod() * 100
    >>> from quant_trading.risk.metrics import calculate_all_metrics
    >>> metrics = calculate_all_metrics(equity)
    >>> metrics.sharpe_ratio  # doctest: +ELLIPSIS
    ...

"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RiskMetrics:
    """Container for portfolio risk metrics.

    Attributes:
        sharpe_ratio: Sharpe ratio of the portfolio (annualized by default).
        sortino_ratio: Sortino ratio using downside deviation (annualized).
        max_drawdown: Maximum drawdown as a negative (or most negative)
            decimal (e.g., -0.1 for 10% drawdown).
        volatility: Annualized volatility of returns.
        var_95: Value at Risk at 95% confidence (historical method).
        var_99: Value at Risk at 99% confidence (historical method).
        beta: Beta relative to the market benchmark.
        alpha: Jensen's alpha (annualized) relative to the market benchmark.
        calmar_ratio: Calmar ratio (annual return / |max drawdown|).

    Examples:
        >>> metrics = RiskMetrics(sharpe_ratio=1.2, max_drawdown=-0.05)
        >>> metrics.to_dict()["sharpe_ratio"]
        1.2

    """

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    volatility: float = 0.0
    var_95: float = 0.0  # Value at Risk (95% confidence)
    var_99: float = 0.0  # Value at Risk (99% confidence)
    beta: float = 0.0
    alpha: float = 0.0
    calmar_ratio: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Convert metrics to a dictionary.

        Returns:
            Dictionary containing all risk metric values with keys
            corresponding to attribute names.

        """
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
    """Calculate simple returns from price series.

    Args:
        prices: Price series indexed by time.

    Returns:
        Series of simple returns (percentage changes), with NaN dropped.

    Examples:
        >>> import pandas as pd
        >>> prices = pd.Series([100, 102, 101, 104])
        >>> calculate_returns(prices).round(3).tolist()
        [0.02, -0.0098, 0.0297]

    """
    return prices.pct_change().dropna()


def calculate_volatility(
    returns: pd.Series,
    annualize: bool = True,
    periods_per_year: int = 252,
) -> float:
    """Calculate volatility of returns.

    Args:
        returns: Return series.
        annualize: Whether to annualize volatility using sqrt(periods_per_year).
        periods_per_year: Number of periods per year used for annualization
            (default 252 for daily data).

    Returns:
        Volatility (annualized if requested), or 0.0 if insufficient data.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, -0.005, 0.015, -0.002, 0.01])
        >>> round(calculate_volatility(returns, annualize=False), 5)
        0.00862

    """
    returns = returns.dropna()
    if len(returns) < 2:
        return 0.0
    vol = returns.std()
    if annualize:
        vol *= np.sqrt(periods_per_year)
    return float(vol)


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """Calculate maximum drawdown from equity curve.

    Drawdown is defined as (current - peak) / peak. The maximum drawdown
    is the minimum value of this ratio over time (most negative).

    Args:
        equity_curve: Equity curve series (cumulative value).

    Returns:
        Maximum drawdown as a decimal (e.g., -0.05 for 5% drawdown), or
        0.0 if insufficient data.

    Examples:
        >>> import pandas as pd
        >>> equity = pd.Series([100, 110, 105, 90, 95])
        >>> calculate_max_drawdown(equity)
        -0.181818...

    """
    equity_curve = equity_curve.dropna()
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
    periods_per_year: int = 252,
) -> float:
    """Calculate Sharpe ratio.

    Sharpe ratio = (mean(excess returns)) / std(excess returns), where
    excess returns are returns minus risk-free rate per period.

    Args:
        returns: Return series.
        risk_free_rate: Annual risk-free rate (default 0.02).
        annualize: Whether to annualize using sqrt(periods_per_year).
        periods_per_year: Number of periods per year used to annualize the
            risk-free rate and the ratio (default 252 for daily data).

    Returns:
        Sharpe ratio, or 0.0 if insufficient data or zero volatility. A
        single observation has an undefined standard deviation and yields
        0.0 rather than NaN.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> round(calculate_sharpe_ratio(returns, annualize=False), 2)
        2.06

    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0
    std = returns.std()
    if not np.isfinite(std) or std == 0:
        return 0.0
    excess = returns.mean() - risk_free_rate / periods_per_year
    sharpe = excess / std
    if annualize:
        sharpe *= np.sqrt(periods_per_year)
    return float(sharpe)


def calculate_sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    annualize: bool = True,
    periods_per_year: int = 252,
) -> float:
    """Calculate Sortino ratio (uses downside deviation).

    Sortino ratio = (mean(excess returns)) / downside_std, where
    downside_std is the standard deviation of returns below zero.

    Args:
        returns: Return series.
        risk_free_rate: Annual risk-free rate (default 0.02).
        annualize: Whether to annualize using sqrt(periods_per_year).
        periods_per_year: Number of periods per year used to annualize the
            risk-free rate and the ratio (default 252 for daily data).

    Returns:
        Sortino ratio, or 0.0 if insufficient data or zero downside
        deviation.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> round(calculate_sortino_ratio(returns, annualize=False), 2)
        1.98

    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) < 2:
        return 0.0
    downside_std = downside.std()
    if not np.isfinite(downside_std) or downside_std == 0:
        return 0.0
    excess = returns.mean() - risk_free_rate / periods_per_year
    sortino = excess / downside_std
    if annualize:
        sortino *= np.sqrt(periods_per_year)
    return float(sortino)


def calculate_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Calculate Value at Risk using historical method.

    Value at Risk is the loss at a given confidence level. For example,
    VaR at 95% confidence represents the 5th percentile loss.

    Args:
        returns: Return series.
        confidence: Confidence level (default 0.95).

    Returns:
        Value at Risk (negative value indicates loss). Returns 0.0 if
        insufficient data.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([-0.02, 0.01, -0.01, 0.005, -0.03])
        >>> round(calculate_var(returns, 0.95), 3)
        -0.028

    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0
    return float(np.percentile(returns, (1 - confidence) * 100))


def calculate_beta(returns: pd.Series, market_returns: pd.Series) -> float:
    """Calculate portfolio beta relative to market.

    Beta measures the sensitivity of portfolio returns to market returns.

    Args:
        returns: Portfolio return series.
        market_returns: Benchmark return series.

    Returns:
        Beta coefficient, or 0.0 if insufficient data or zero market
        variance.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.015, -0.005, 0.012])
        >>> market = pd.Series([0.008, 0.01, -0.003, 0.009])
        >>> round(calculate_beta(returns, market), 2)
        1.46

    """
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
    periods_per_year: int = 252,
) -> float:
    """Calculate Jensen's alpha.

    Alpha is computed from the same aligned (overlapping-index) sample that
    ``calculate_beta`` uses, so the two are always consistent even when the
    input series have non-overlapping indices or NaN values.

    Args:
        returns: Portfolio return series.
        market_returns: Benchmark return series.
        risk_free_rate: Annual risk-free rate (default 0.02).
        periods_per_year: Number of periods per year used to annualize the
            mean returns (default 252 for daily data).

    Returns:
        Annualized Jensen's alpha, or 0.0 when beta is undefined/zero.

    """
    beta = calculate_beta(returns, market_returns)
    if beta == 0:
        return 0.0

    # Align on overlapping indices, mirroring calculate_beta, so the means
    # used for alpha come from the same observations used for beta.
    aligned = pd.concat([returns, market_returns], axis=1).dropna()
    if len(aligned) < 2:  # pragma: no cover  (beta != 0 implies >= 2 aligned points)
        return 0.0

    avg_return = float(aligned.iloc[:, 0].mean() * periods_per_year)
    avg_market = float(aligned.iloc[:, 1].mean() * periods_per_year)
    return float(avg_return - (risk_free_rate + beta * (avg_market - risk_free_rate)))


def calculate_calmar_ratio(
    returns: pd.Series,
    equity_curve: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """Calculate Calmar ratio (annual return / max drawdown).

    The Calmar ratio measures risk-adjusted performance as annualized
    returns divided by the absolute maximum drawdown.

    Args:
        returns: Return series.
        equity_curve: Equity curve series.
        periods_per_year: Number of periods per year used to annualize the
            return (default 252 for daily data).

    Returns:
        Calmar ratio, or 0.0 if insufficient data or zero drawdown.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015])
        >>> equity = (1 + returns).cumprod() * 100
        >>> round(calculate_calmar_ratio(returns, equity), 2)
        1.09

    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0
    annual_return = returns.mean() * periods_per_year
    max_dd = calculate_max_drawdown(equity_curve)
    if max_dd == 0:
        return 0.0
    return float(annual_return / abs(max_dd))


def calculate_all_metrics(
    equity_curve: pd.Series,
    market_returns: pd.Series | None = None,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> RiskMetrics:
    """Calculate all risk metrics from an equity curve.

    Calculates Sharpe ratio, Sortino ratio, max drawdown, volatility,
    VaR (95% and 99%), Calmar ratio, and optionally beta and alpha if
    market returns are provided.

    Args:
        equity_curve: Equity curve series (cumulative value).
        market_returns: Optional benchmark return series for beta/alpha.
        risk_free_rate: Annual risk-free rate (default 0.02).
        periods_per_year: Number of periods per year used for annualization
            (default 252 for daily data).

    Returns:
        RiskMetrics object containing calculated values.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015])
        >>> equity = (1 + returns).cumprod() * 100
        >>> metrics = calculate_all_metrics(equity)
        >>> metrics.sharpe_ratio  # doctest: +ELLIPSIS
        ...

    """
    returns = calculate_returns(equity_curve)

    metrics = RiskMetrics(
        sharpe_ratio=calculate_sharpe_ratio(
            returns, risk_free_rate, periods_per_year=periods_per_year
        ),
        sortino_ratio=calculate_sortino_ratio(
            returns, risk_free_rate, periods_per_year=periods_per_year
        ),
        max_drawdown=calculate_max_drawdown(equity_curve),
        volatility=calculate_volatility(returns, periods_per_year=periods_per_year),
        var_95=calculate_var(returns, 0.95),
        var_99=calculate_var(returns, 0.99),
        calmar_ratio=calculate_calmar_ratio(
            returns, equity_curve, periods_per_year=periods_per_year
        ),
    )

    if market_returns is not None:
        metrics.beta = calculate_beta(returns, market_returns)
        metrics.alpha = calculate_alpha(
            returns, market_returns, risk_free_rate, periods_per_year=periods_per_year
        )

    return metrics
