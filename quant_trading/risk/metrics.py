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
    >>> round(metrics.sharpe_ratio, 2)
    7.75

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
        cvar_95: Conditional Value at Risk (Expected Shortfall) at 95% confidence.
        cvar_99: Conditional Value at Risk (Expected Shortfall) at 99% confidence.
        beta: Beta relative to the market benchmark.
        alpha: Jensen's alpha (annualized) relative to the market benchmark.
        calmar_ratio: Calmar ratio (annual return / |max drawdown|).
        treynor_ratio: Treynor ratio (excess return / beta).
        information_ratio: Information ratio (active return / tracking error).
        omega_ratio: Omega ratio (probability-weighted gains/losses vs threshold).

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
    cvar_95: float = 0.0  # Conditional VaR / Expected Shortfall (95%)
    cvar_99: float = 0.0  # Conditional VaR / Expected Shortfall (99%)
    beta: float = 0.0
    alpha: float = 0.0
    calmar_ratio: float = 0.0
    treynor_ratio: float = 0.0
    information_ratio: float = 0.0
    omega_ratio: float = 0.0

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
            "cvar_95": self.cvar_95,
            "cvar_99": self.cvar_99,
            "beta": self.beta,
            "alpha": self.alpha,
            "calmar_ratio": self.calmar_ratio,
            "treynor_ratio": self.treynor_ratio,
            "information_ratio": self.information_ratio,
            "omega_ratio": self.omega_ratio,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "RiskMetrics":
        """Deserialize risk metrics from a dictionary."""
        return cls(
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            sortino_ratio=data.get("sortino_ratio", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            volatility=data.get("volatility", 0.0),
            var_95=data.get("var_95", 0.0),
            var_99=data.get("var_99", 0.0),
            cvar_95=data.get("cvar_95", 0.0),
            cvar_99=data.get("cvar_99", 0.0),
            beta=data.get("beta", 0.0),
            alpha=data.get("alpha", 0.0),
            calmar_ratio=data.get("calmar_ratio", 0.0),
            treynor_ratio=data.get("treynor_ratio", 0.0),
            information_ratio=data.get("information_ratio", 0.0),
            omega_ratio=data.get("omega_ratio", 0.0),
        )


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
        [0.02, -0.01, 0.03]

    """
    previous = prices.shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = (prices - previous) / previous
    # A previous price of zero makes the return undefined (inf); drop those
    # observations so downstream metrics stay finite instead of NaN/inf.
    cleaned: pd.Series = returns.replace([np.inf, -np.inf], np.nan)
    return cleaned.dropna()


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
        1.06

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

    Sortino ratio = (mean(excess returns)) / downside deviation, where
    excess returns are returns minus the risk-free rate per period (the
    minimum acceptable return, MAR) and the downside deviation is

        sqrt(sum(min(0, r - MAR) ** 2) / N)

    over the full sample: every observation counts towards the divisor,
    but only returns below the MAR contribute their squared shortfall.
    This is the standard downside deviation. Unlike the standard
    deviation of the losing subset it stays defined for a single losing
    period, and a strategy that only loses money keeps a negative ratio
    instead of collapsing to zero.

    Args:
        returns: Return series.
        risk_free_rate: Annual risk-free rate (default 0.02).
        annualize: Whether to annualize using sqrt(periods_per_year).
        periods_per_year: Number of periods per year used to annualize the
            risk-free rate and the ratio (default 252 for daily data).

    Returns:
        Sortino ratio, or 0.0 if insufficient data or zero downside
        deviation (no return below the minimum acceptable return).

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> round(calculate_sortino_ratio(returns, annualize=False), 2)
        4.37

    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0
    # A constant or undefined-variance return series has no downside to
    # measure: with every observation on the same side of the MAR (or with
    # fewer than two observations, so std is NaN), the downside deviation is
    # non-zero and the ratio collapses to a degenerate annualized value.
    # Guard the same way calculate_sharpe_ratio does, so a flat/single-
    # observation portfolio reports 0.0 instead of a spurious ratio.
    std = returns.std()
    if not np.isfinite(std) or std == 0:
        return 0.0
    mar = risk_free_rate / periods_per_year
    excess = float(returns.mean()) - mar
    shortfalls = np.minimum(returns.to_numpy(dtype=float) - mar, 0.0)
    downside_deviation = float(np.sqrt(np.mean(shortfalls**2)))
    if not np.isfinite(downside_deviation) or downside_deviation == 0:
        return 0.0
    sortino = excess / downside_deviation
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


def _align_series(returns: pd.Series, market_returns: pd.Series) -> pd.DataFrame:
    """Align two return series on their shared index.

    Index alignment is preferred so observations are matched by their labels
    (for example dates). When the two series carry incompatible indices and
    index alignment leaves fewer than two overlapping points, the series fall
    back to positional alignment: each observation is paired with the
    observation at the same position in the other series.

    This keeps ``beta``/``alpha`` defined when one side is a RangeIndex (the
    equity curve built inside :meth:`RiskManager.calculate_metrics` carries no
    dates) and the other is date-indexed, instead of silently returning 0.0.

    Args:
        returns: Portfolio return series.
        market_returns: Benchmark return series.

    Returns:
        The two series aligned on a common index (or positionally), with any
        NaN rows dropped.

    """
    aligned: pd.DataFrame = pd.concat([returns, market_returns], axis=1).dropna()
    if len(aligned) < 2 and len(returns) >= 2 and len(market_returns) >= 2:
        aligned = pd.concat(
            [returns.reset_index(drop=True), market_returns.reset_index(drop=True)],
            axis=1,
        ).dropna()
    return aligned


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
    aligned = _align_series(returns, market_returns)
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
    aligned = _align_series(returns, market_returns)
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
        >>> round(calculate_max_drawdown(equity), 4)
        -0.005
        >>> round(calculate_calmar_ratio(returns, equity), 2)
        504.0

    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0
    annual_return = returns.mean() * periods_per_year
    max_dd = calculate_max_drawdown(equity_curve)
    if max_dd == 0:
        return 0.0
    return float(annual_return / abs(max_dd))


def calculate_treynor_ratio(
    returns: pd.Series,
    market_returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> float:
    """Calculate Treynor ratio.

    Treynor ratio = (mean(returns) - risk_free_rate / periods_per_year) / beta,
    where beta is the portfolio's sensitivity to market returns.

    Args:
        returns: Portfolio return series.
        market_returns: Benchmark return series.
        risk_free_rate: Annual risk-free rate (default 0.02).
        periods_per_year: Number of periods per year used to annualize the
            risk-free rate (default 252 for daily data).

    Returns:
        Treynor ratio, or 0.0 if insufficient data or beta is zero/undefined.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> market = pd.Series([0.008, 0.015, -0.003, 0.01, 0.008])
        >>> round(calculate_treynor_ratio(returns, market, risk_free_rate=0.02), 2)
        1.77

    """
    beta = calculate_beta(returns, market_returns)
    if beta == 0:
        return 0.0

    returns = returns.dropna()
    if len(returns) == 0:  # pragma: no cover  (beta != 0 implies non-empty after dropna)
        return 0.0

    excess_return = returns.mean() - risk_free_rate / periods_per_year
    return float(excess_return / beta * periods_per_year)


def calculate_information_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """Calculate Information ratio.

    Information ratio = mean(active returns) / std(active returns), where
    active returns are portfolio returns minus benchmark returns.

    Args:
        returns: Portfolio return series.
        benchmark_returns: Benchmark return series.
        periods_per_year: Number of periods per year used for annualization
            (default 252 for daily data).

    Returns:
        Annualized Information ratio, or 0.0 if insufficient data or
        zero tracking error.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> benchmark = pd.Series([0.008, 0.015, -0.003, 0.01, 0.008])
        >>> round(calculate_information_ratio(returns, benchmark), 2)
        13.22

    """
    aligned = _align_series(returns, benchmark_returns)
    if len(aligned) < 2:
        return 0.0

    active_returns = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    tracking_error = active_returns.std()

    if not np.isfinite(tracking_error) or tracking_error == 0:
        return 0.0

    info_ratio = active_returns.mean() / tracking_error
    return float(info_ratio * np.sqrt(periods_per_year))


def calculate_cvar(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """Calculate Conditional Value at Risk (Expected Shortfall).

    CVaR is the expected loss given that the loss exceeds the VaR threshold.
    For a confidence level of 95%, CVaR is the average of the worst 5% of returns.

    Args:
        returns: Return series.
        confidence: Confidence level (default 0.95).

    Returns:
        Conditional VaR (negative value indicates expected loss), or 0.0 if
        insufficient data.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([-0.02, 0.01, -0.01, 0.005, -0.03, -0.025])
        >>> round(calculate_cvar(returns, 0.95), 3)
        -0.03

    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0

    var_threshold = np.percentile(returns, (1 - confidence) * 100)
    tail_returns = returns[returns <= var_threshold]

    if len(tail_returns) == 0:  # pragma: no cover  (percentile guarantees non-empty tail)
        return float(var_threshold)

    return float(tail_returns.mean())


def calculate_omega_ratio(
    returns: pd.Series,
    threshold: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculate Omega ratio.

    Omega ratio = sum(max(0, r - threshold)) / sum(max(0, threshold - r))
    It measures the probability-weighted ratio of gains vs losses relative to
    a threshold return.

    Args:
        returns: Return series.
        threshold: Threshold return (default 0.0 for zero return threshold).
        periods_per_year: Number of periods per year (not used in calculation
            but kept for API consistency).

    Returns:
        Omega ratio, or 0.0 if insufficient data or no losses below threshold.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, -0.01])
        >>> round(calculate_omega_ratio(returns, threshold=0.0), 2)
        3.0

    """
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0

    gains = np.sum(np.maximum(returns.to_numpy(dtype=float) - threshold, 0.0))
    losses = np.sum(np.maximum(threshold - returns.to_numpy(dtype=float), 0.0))

    if losses == 0:
        return 0.0

    return float(gains / losses)


def calculate_marginal_var(
    returns: pd.DataFrame,
    weights: np.ndarray | pd.Series,
    confidence: float = 0.95,
) -> pd.Series:
    """Calculate marginal VaR for each position using historical simulation.

    Marginal VaR is computed as the average asset return in the tail of the
    portfolio return distribution (the worst (1-confidence) fraction of
    observations). This is the standard historical simulation approach and
    naturally satisfies the Euler decomposition:
    Component VaR_i = weight_i * Marginal VaR_i
    Sum of Component VaRs = Portfolio VaR

    Args:
        returns: DataFrame of asset returns (columns = assets, rows = periods).
        weights: Current portfolio weights (must sum to 1.0).
        confidence: VaR confidence level (default 0.95).

    Returns:
        Series of marginal VaR values indexed by asset name.

    Examples:
        >>> import pandas as pd
        >>> import numpy as np
        >>> np.random.seed(42)
        >>> returns = pd.DataFrame({
        ...     "A": np.random.normal(0.001, 0.02, 100),
        ...     "B": np.random.normal(0.001, 0.02, 100),
        ... })
        >>> weights = pd.Series([0.5, 0.5], index=["A", "B"])
        >>> mvar = calculate_marginal_var(returns, weights, confidence=0.95)
        >>> len(mvar) == 2
        True

    """
    returns = returns.dropna()
    if len(returns) < 2:
        return pd.Series(0.0, index=weights.index)

    weights = np.asarray(weights, dtype=float)
    if not np.isfinite(weights).all() or abs(weights.sum() - 1.0) > 1e-6:
        raise ValueError("weights must be finite and sum to 1.0")

    portfolio_returns = returns.values @ weights
    # VaR is the negative of the (1-confidence) quantile
    var_threshold = -np.percentile(portfolio_returns, (1 - confidence) * 100)

    # Marginal VaR for each asset is the average return in the tail
    # where portfolio return <= -VaR
    tail_mask = portfolio_returns <= -var_threshold
    if not tail_mask.any():
        # If no observations in tail (e.g., single observation), return zeros
        return pd.Series(0.0, index=returns.columns)

    tail_returns = returns.values[tail_mask]
    marginal_vars = tail_returns.mean(axis=0)

    return pd.Series(marginal_vars, index=returns.columns)


def calculate_component_var(
    returns: pd.DataFrame,
    weights: np.ndarray | pd.Series,
    confidence: float = 0.95,
) -> pd.Series:
    """Calculate component VaR for each position using historical simulation.

    Component VaR = weight * Marginal VaR. The sum of component VaRs equals
    the total portfolio VaR exactly (Euler's theorem for homogeneous functions).

    Args:
        returns: DataFrame of asset returns (columns = assets, rows = periods).
        weights: Current portfolio weights (must sum to 1.0).
        confidence: VaR confidence level (default 0.95).

    Returns:
        Series of component VaR values indexed by asset name.

    Examples:
        >>> import pandas as pd
        >>> import numpy as np
        >>> np.random.seed(42)
        >>> returns = pd.DataFrame({
        ...     "A": np.random.normal(0.001, 0.02, 100),
        ...     "B": np.random.normal(0.001, 0.02, 100),
        ... })
        >>> weights = pd.Series([0.5, 0.5], index=["A", "B"])
        >>> cvar = calculate_component_var(returns, weights, confidence=0.95)
        >>> len(cvar) == 2
        True

    """
    weights = np.asarray(weights, dtype=float)
    marginal_var = calculate_marginal_var(returns, weights, confidence)
    component_var = weights * marginal_var
    return pd.Series(component_var, index=returns.columns)


def calculate_volatility_contributions(
    returns: pd.DataFrame,
    weights: np.ndarray | pd.Series,
    annualize: bool = True,
    periods_per_year: int = 252,
) -> pd.Series:
    """Calculate each position's contribution to portfolio volatility.

    Contribution_i = weight_i * (Cov_i * weights) / portfolio_volatility,
    where Cov_i is the i-th row of the covariance matrix.

    The sum of contributions equals the total portfolio volatility.

    Args:
        returns: DataFrame of asset returns (columns = assets, rows = periods).
        weights: Current portfolio weights (must sum to 1.0).
        annualize: Whether to annualize the volatility (default True).
        periods_per_year: Periods per year for annualization (default 252).

    Returns:
        Series of volatility contributions indexed by asset name.

    Examples:
        >>> import pandas as pd
        >>> import numpy as np
        >>> np.random.seed(42)
        >>> returns = pd.DataFrame({
        ...     "A": np.random.normal(0.001, 0.02, 100),
        ...     "B": np.random.normal(0.001, 0.02, 100),
        ... })
        >>> weights = pd.Series([0.5, 0.5], index=["A", "B"])
        >>> contrib = calculate_volatility_contributions(returns, weights, annualize=False)
        >>> round(contrib.sum(), 6) == round(calculate_volatility(pd.Series(returns.values @ weights.values), annualize=False), 6)
        True

    """
    returns = returns.dropna()
    if len(returns) < 2:
        return pd.Series(0.0, index=weights.index)

    weights = np.asarray(weights, dtype=float)
    if not np.isfinite(weights).all() or abs(weights.sum() - 1.0) > 1e-6:
        raise ValueError("weights must be finite and sum to 1.0")

    cov = returns.cov().values.copy()
    if annualize:
        cov *= periods_per_year

    portfolio_variance = weights @ cov @ weights
    if portfolio_variance <= 0:
        return pd.Series(0.0, index=returns.columns)

    portfolio_vol = np.sqrt(portfolio_variance)
    marginal_contrib = cov @ weights / portfolio_vol
    contributions = weights * marginal_contrib

    return pd.Series(contributions, index=returns.columns)


def calculate_equal_risk_contribution_weights(
    returns: pd.DataFrame,
    max_iter: int = 1000,
    tol: float = 1e-8,
    annualize: bool = True,
    periods_per_year: int = 252,
    long_only: bool = False,
) -> pd.Series:
    """Calculate portfolio weights for equal risk contribution (ERC).

    ERC portfolio assigns weights such that each asset contributes equally to
    total portfolio volatility. Solved via iterative scaling:
    w_i = w_i * (target_contribution / actual_contribution)

    Args:
        returns: DataFrame of asset returns (columns = assets, rows = periods).
        max_iter: Maximum iterations for convergence (default 1000).
        tol: Convergence tolerance for weight changes (default 1e-8).
        annualize: Whether to annualize volatility (default True).
        periods_per_year: Periods per year for annualization (default 252).
        long_only: If True, constrain weights to be non-negative (default True).

    Returns:
        Series of ERC weights indexed by asset name, summing to 1.0.

    Examples:
        >>> import pandas as pd
        >>> import numpy as np
        >>> np.random.seed(42)
        >>> returns = pd.DataFrame({
        ...     "A": np.random.normal(0.001, 0.02, 100),
        ...     "B": np.random.normal(0.001, 0.02, 100),
        ... })
        >>> weights = calculate_equal_risk_contribution_weights(returns, annualize=False)
        >>> abs(weights.sum() - 1.0) < 1e-6
        True
        >>> len(weights) == 2
        True

    """
    returns = returns.dropna()
    if len(returns) < 2:
        n = len(returns.columns) if len(returns.columns) > 0 else 1
        return pd.Series(1.0 / n, index=returns.columns)

    n = len(returns.columns)
    weights = np.ones(n) / n

    for _ in range(max_iter):
        contrib = calculate_volatility_contributions(
            returns,
            pd.Series(weights, index=returns.columns),
            annualize=annualize,
            periods_per_year=periods_per_year,
        ).values

        target = contrib.sum() / n
        if target == 0:
            break

        # Avoid division by zero
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(contrib != 0, target / contrib, 1.0)
        new_weights = weights * ratio

        if long_only:
            new_weights = np.maximum(new_weights, 0.0)

        weight_sum = new_weights.sum()
        if weight_sum == 0:
            break
        new_weights = new_weights / weight_sum

        if np.max(np.abs(new_weights - weights)) < tol:
            weights = new_weights
            break

        weights = new_weights

    return pd.Series(weights, index=returns.columns)


def calculate_risk_budget_weights(
    returns: pd.DataFrame,
    risk_budget: np.ndarray | pd.Series,
    max_iter: int = 1000,
    tol: float = 1e-8,
    annualize: bool = True,
    periods_per_year: int = 252,
    long_only: bool = False,
) -> pd.Series:
    """Calculate portfolio weights for a given risk budget.

    Risk budgeting assigns each asset a target risk contribution. The weights
    are solved iteratively so that actual contributions match the budget.

    Args:
        returns: DataFrame of asset returns (columns = assets, rows = periods).
        risk_budget: Target risk contribution for each asset (must sum to 1.0).
        max_iter: Maximum iterations for convergence (default 1000).
        tol: Convergence tolerance for weight changes (default 1e-8).
        annualize: Whether to annualize volatility (default True).
        periods_per_year: Periods per year for annualization (default 252).
        long_only: If True, constrain weights to be non-negative (default True).

    Returns:
        Series of risk budget weights indexed by asset name, summing to 1.0.

    Examples:
        >>> import pandas as pd
        >>> import numpy as np
        >>> np.random.seed(42)
        >>> returns = pd.DataFrame({
        ...     "A": np.random.normal(0.001, 0.02, 100),
        ...     "B": np.random.normal(0.001, 0.02, 100),
        ... })
        >>> budget = pd.Series([0.7, 0.3], index=["A", "B"])
        >>> weights = calculate_risk_budget_weights(returns, budget, annualize=False)
        >>> abs(weights.sum() - 1.0) < 1e-6
        True

    """
    returns = returns.dropna()
    if len(returns) < 2:
        n = len(returns.columns) if len(returns.columns) > 0 else 1
        return pd.Series(1.0 / n, index=returns.columns)

    budget = np.asarray(risk_budget, dtype=float)
    if not np.isfinite(budget).all() or abs(budget.sum() - 1.0) > 1e-6:
        raise ValueError("risk_budget must be finite and sum to 1.0")

    n = len(returns.columns)
    weights = budget.copy()

    for _ in range(max_iter):
        contrib = calculate_volatility_contributions(
            returns,
            pd.Series(weights, index=returns.columns),
            annualize=annualize,
            periods_per_year=periods_per_year,
        ).values

        total_contrib = contrib.sum()
        if total_contrib == 0:
            break

        actual_contrib = contrib / total_contrib
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(actual_contrib != 0, budget / actual_contrib, 1.0)
        new_weights = weights * ratio

        if long_only:
            new_weights = np.maximum(new_weights, 0.0)

        weight_sum = new_weights.sum()
        if weight_sum == 0:
            break
        new_weights = new_weights / weight_sum

        if np.max(np.abs(new_weights - weights)) < tol:
            weights = new_weights
            break

        weights = new_weights

    return pd.Series(weights, index=returns.columns)


def calculate_all_metrics(
    equity_curve: pd.Series,
    market_returns: pd.Series | None = None,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> RiskMetrics:
    """Calculate all risk metrics from an equity curve.

    Calculates Sharpe ratio, Sortino ratio, max drawdown, volatility,
    VaR (95% and 99%), CVaR (95% and 99%), Calmar ratio, and optionally
    beta, alpha, Treynor ratio, Information ratio, and Omega ratio if
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
        >>> round(metrics.sharpe_ratio, 2)
        11.9
        >>> round(metrics.max_drawdown, 4)
        -0.005

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
        cvar_95=calculate_cvar(returns, 0.95),
        cvar_99=calculate_cvar(returns, 0.99),
        calmar_ratio=calculate_calmar_ratio(
            returns, equity_curve, periods_per_year=periods_per_year
        ),
        omega_ratio=calculate_omega_ratio(returns, periods_per_year=periods_per_year),
    )

    if market_returns is not None:
        metrics.beta = calculate_beta(returns, market_returns)
        metrics.alpha = calculate_alpha(
            returns, market_returns, risk_free_rate, periods_per_year=periods_per_year
        )
        metrics.treynor_ratio = calculate_treynor_ratio(
            returns, market_returns, risk_free_rate, periods_per_year=periods_per_year
        )
        metrics.information_ratio = calculate_information_ratio(
            returns, market_returns, periods_per_year=periods_per_year
        )

    return metrics


__all__ = [
    "RiskMetrics",
    "calculate_all_metrics",
    "calculate_alpha",
    "calculate_beta",
    "calculate_calmar_ratio",
    "calculate_component_var",
    "calculate_cvar",
    "calculate_equal_risk_contribution_weights",
    "calculate_information_ratio",
    "calculate_marginal_var",
    "calculate_max_drawdown",
    "calculate_omega_ratio",
    "calculate_risk_budget_weights",
    "calculate_returns",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "calculate_treynor_ratio",
    "calculate_var",
    "calculate_volatility",
    "calculate_volatility_contributions",
]
