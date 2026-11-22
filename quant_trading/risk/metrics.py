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

import math
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import pandas as pd


def _drop_non_finite(values: pd.Series) -> pd.Series:
    """Drop NaN and infinite observations from a return or value series.

    Args:
        values: Series to clean.

    Returns:
        The finite observations from ``values``.

    Examples:
        >>> import pandas as pd
        >>> _drop_non_finite(pd.Series([1.0, float("nan"), float("inf")])).tolist()
        [1.0]

    """
    return cast(pd.Series, values.replace([np.inf, -np.inf], np.nan).dropna())


def _drop_non_finite_rows(returns: pd.DataFrame) -> pd.DataFrame:
    """Drop rows containing NaN or infinite observations.

    Args:
        returns: DataFrame of asset returns.

    Returns:
        The rows whose values are all finite.

    Examples:
        >>> import pandas as pd
        >>> frame = pd.DataFrame({"a": [1.0, float("nan"), float("inf")]})
        >>> _drop_non_finite_rows(frame).shape
        (1, 1)

    """
    return cast(pd.DataFrame, returns.replace([np.inf, -np.inf], np.nan).dropna())


def _validate_confidence(confidence: float) -> float:
    """Validate a Value-at-Risk / Expected-Shortfall confidence level.

    A confidence level must be a finite number strictly between 0 and 1 so the
    tail probability ``1 - confidence`` is a valid probability. Values outside
    that range (including ``0`` and ``1``) previously produced an opaque
    third-party error or a silently wrong percentile, so they are rejected with
    a clear message.

    Args:
        confidence: Confidence level to validate.

    Returns:
        The validated confidence level as a float.

    Raises:
        ValueError: If ``confidence`` is not a finite number strictly between
            0 and 1.

    Examples:
        >>> _validate_confidence(0.95)
        0.95
        >>> _validate_confidence(0)
        Traceback (most recent call last):
            ...
        ValueError: invalid confidence: the value must be in the range (0, 1) (got 0)
        >>> _validate_confidence(float("nan"))
        Traceback (most recent call last):
            ...
        ValueError: invalid confidence: the value must be in the range (0, 1) (got nan)

    """
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not (0.0 < confidence < 1.0)
    ):
        raise ValueError(
            f"invalid confidence: the value must be in the range (0, 1) " f"(got {confidence})"
        )
    return float(confidence)


def _validate_risk_free_rate(risk_free_rate: float) -> float:
    """Validate the risk-free rate used by Sharpe / Sortino / Treynor ratios.

    A non-finite (NaN/±inf) or non-numeric rate would silently turn every
    risk-adjusted ratio into NaN (or a wrong value), mirroring the defect
    previously fixed for the VaR confidence level. Only finiteness is
    required: negative rates are allowed, matching :class:`BacktestConfig`.

    Args:
        risk_free_rate: Annual risk-free rate to validate.

    Returns:
        The validated risk-free rate as a float.

    Raises:
        ValueError: If ``risk_free_rate`` is not a finite number.

    Examples:
        >>> _validate_risk_free_rate(0.02)
        0.02
        >>> _validate_risk_free_rate(-0.01)
        -0.01
        >>> _validate_risk_free_rate(float("nan"))
        Traceback (most recent call last):
            ...
        ValueError: invalid risk_free_rate: the value must be finite (got nan)
        >>> _validate_risk_free_rate(True)
        Traceback (most recent call last):
            ...
        ValueError: invalid risk_free_rate: the value must be finite (got True)
    """
    if (
        isinstance(risk_free_rate, bool)
        or not isinstance(risk_free_rate, (int, float))
        or not math.isfinite(risk_free_rate)
    ):
        raise ValueError(
            f"invalid risk_free_rate: the value must be finite " f"(got {risk_free_rate})"
        )
    return float(risk_free_rate)


def _validate_periods_per_year(periods_per_year: int) -> None:
    """Validate the annualization factor used by volatility and risk ratios.

    ``periods_per_year`` must be a finite number of at least 1. A value below
    1 (including 0, negatives, NaN and ±inf) cannot annualize returns and
    previously produced an opaque ``ZeroDivisionError`` (Sharpe / Sortino), a
    silent zero volatility, or ``NaN`` from ``sqrt`` of a negative number.

    Args:
        periods_per_year: Periods per year to validate (default 252).

    Returns:
        None.

    Raises:
        ValueError: If ``periods_per_year`` is not a finite number of at
            least 1.

    Examples:
        >>> _validate_periods_per_year(252)
        >>> _validate_periods_per_year(1)
        >>> _validate_periods_per_year(0)
        Traceback (most recent call last):
            ...
        ValueError: invalid periods_per_year: the value must be at least 1 (got 0)
        >>> _validate_periods_per_year(float("nan"))
        Traceback (most recent call last):
            ...
        ValueError: invalid periods_per_year: the value must be at least 1 (got nan)
        >>> _validate_periods_per_year(True)
        Traceback (most recent call last):
            ...
        ValueError: invalid periods_per_year: the value must be at least 1 (got True)
    """
    if (
        isinstance(periods_per_year, bool)
        or not isinstance(periods_per_year, (int, float))
        or not math.isfinite(periods_per_year)
        or periods_per_year < 1
    ):
        raise ValueError(
            f"invalid periods_per_year: the value must be at least 1 " f"(got {periods_per_year})"
        )


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
        ulcer_index: Ulcer Index (root-mean-square of percentage drawdowns).

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
    ulcer_index: float = 0.0

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
            "ulcer_index": self.ulcer_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "RiskMetrics":
        """Deserialize risk metrics from a dictionary.

        Non-finite values are replaced with ``0.0`` so a reconstructed result
        never carries NaN/inf into downstream reporting.

        Missing optional keys fall back to the field defaults. Extra keys are
        ignored.

        Args:
            data: Dictionary previously produced by :meth:`to_dict`.

        Returns:
            A reconstructed :class:`RiskMetrics` whose every metric is finite.

        Examples:
            >>> from quant_trading.risk.metrics import RiskMetrics
            >>> metrics = RiskMetrics.from_dict({
            ...     "sharpe_ratio": float("nan"),
            ...     "max_drawdown": float("inf"),
            ...     "beta": -float("inf"),
            ... })
            >>> metrics.sharpe_ratio, metrics.max_drawdown, metrics.beta
            (0.0, 0.0, 0.0)
            >>> normal = RiskMetrics.from_dict({"sharpe_ratio": 1.25})
            >>> normal.sharpe_ratio
            1.25
        """

        def _finite(value: Any, default: float = 0.0) -> float:
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            ):
                return float(value)
            try:
                result = float(value)
            except (TypeError, ValueError):
                return default
            return result if math.isfinite(result) else default

        return cls(
            sharpe_ratio=_finite(data.get("sharpe_ratio", 0.0)),
            sortino_ratio=_finite(data.get("sortino_ratio", 0.0)),
            max_drawdown=_finite(data.get("max_drawdown", 0.0)),
            volatility=_finite(data.get("volatility", 0.0)),
            var_95=_finite(data.get("var_95", 0.0)),
            var_99=_finite(data.get("var_99", 0.0)),
            cvar_95=_finite(data.get("cvar_95", 0.0)),
            cvar_99=_finite(data.get("cvar_99", 0.0)),
            beta=_finite(data.get("beta", 0.0)),
            alpha=_finite(data.get("alpha", 0.0)),
            calmar_ratio=_finite(data.get("calmar_ratio", 0.0)),
            treynor_ratio=_finite(data.get("treynor_ratio", 0.0)),
            information_ratio=_finite(data.get("information_ratio", 0.0)),
            omega_ratio=_finite(data.get("omega_ratio", 0.0)),
            ulcer_index=_finite(data.get("ulcer_index", 0.0)),
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

    Raises:
        ValueError: If ``periods_per_year`` is not a finite number of at
            least 1.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, -0.005, 0.015, -0.002, 0.01])
        >>> round(calculate_volatility(returns, annualize=False), 5)
        0.00862

    """
    _validate_periods_per_year(periods_per_year)
    returns = _drop_non_finite(returns)
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
        0.0 if insufficient data or if the running peak is never strictly
        positive (an all-zero or all-negative equity curve), in which case
        the drawdown ratio is undefined and is reported as neutral.
        Drawdowns measured against a zero running peak are undefined and
        are ignored, so an equity curve that dips below zero while its peak
        is still zero reports a finite value instead of ``-inf``.

    Examples:
        >>> import pandas as pd
        >>> equity = pd.Series([100, 110, 105, 90, 95])
        >>> calculate_max_drawdown(equity)
        -0.181818...
        >>> calculate_max_drawdown(pd.Series([0.0, -5.0, 10.0]))
        0.0

    """
    equity_curve = _drop_non_finite(equity_curve)
    if len(equity_curve) == 0:
        return 0.0
    running_max = equity_curve.cummax()
    if running_max.max() <= 0:
        return 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = (equity_curve - running_max) / running_max
    # A zero running peak (an equity curve that starts at or drops to zero)
    # makes the ratio undefined for that point. Ignore those observations
    # instead of letting an infinite drawdown dominate the minimum.
    drawdown = drawdown.replace([np.inf, -np.inf], np.nan).dropna()
    if len(drawdown) == 0:
        return 0.0
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

    Raises:
        ValueError: If ``periods_per_year`` is not a finite number of at
            least 1, or if ``risk_free_rate`` is not finite.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> round(calculate_sharpe_ratio(returns, annualize=False), 2)
        1.06

    """
    risk_free_rate = _validate_risk_free_rate(risk_free_rate)
    _validate_periods_per_year(periods_per_year)
    returns = _drop_non_finite(returns)
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

    Raises:
        ValueError: If ``periods_per_year`` is not a finite number of at
            least 1, or if ``risk_free_rate`` is not finite.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> round(calculate_sortino_ratio(returns, annualize=False), 2)
        4.37

    """
    risk_free_rate = _validate_risk_free_rate(risk_free_rate)
    _validate_periods_per_year(periods_per_year)
    returns = _drop_non_finite(returns)
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

    Raises:
        ValueError: If ``confidence`` is not a finite number strictly between
            0 and 1.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([-0.02, 0.01, -0.01, 0.005, -0.03])
        >>> round(calculate_var(returns, 0.95), 3)
        -0.028
        >>> calculate_var(returns, 0.0)
        Traceback (most recent call last):
            ...
        ValueError: invalid confidence: the value must be in the range (0, 1) (got 0.0)

    """
    confidence = _validate_confidence(confidence)
    returns = _drop_non_finite(returns)
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
    # Attempt label alignment first. Only fall back to positional alignment
    # when label alignment would produce a cartesian expansion (more rows than
    # either input) or insufficient overlap; duplicate labels alone do not
    # force positional alignment when they do not cause such expansion.
    try:
        aligned: pd.DataFrame = pd.concat([returns, market_returns], axis=1, sort=False).dropna()
    except ValueError:
        aligned = pd.DataFrame()
    if (
        len(aligned) == 0
        or len(aligned) > min(len(returns), len(market_returns))
        or (len(aligned) < 2 and len(returns) >= 2 and len(market_returns) >= 2)
    ):
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
    if np.isinf(returns).any() or np.isinf(market_returns).any():
        return 0.0
    if len(returns) < 2 or len(market_returns) < 2:
        return 0.0
    aligned = _align_series(returns, market_returns)
    if len(aligned) < 2:
        return 0.0
    market = aligned.iloc[:, 1]
    if market.nunique() <= 1:
        return 0.0
    cov = aligned.iloc[:, 0].cov(market)
    var = market.var()
    if not np.isfinite(var) or var == 0:
        return 0.0
    beta = cov / var
    return float(beta) if np.isfinite(beta) else 0.0


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

    Raises:
        ValueError: If ``periods_per_year`` is not a finite number of at
            least 1.

    """
    _validate_periods_per_year(periods_per_year)
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

    The annualized return and the drawdown are computed from the same
    aligned sample: the two series are matched on their shared index (falling
    back to positional alignment when they do not overlap), so a caller that
    passes series with different indices or NaN rows cannot mix the numerator
    from one period with the denominator from another.

    Args:
        returns: Return series.
        equity_curve: Equity curve series.
        periods_per_year: Number of periods per year used to annualize the
            return (default 252 for daily data).

    Returns:
        Calmar ratio, or 0.0 if fewer than two aligned observations remain or
        the drawdown over the aligned sample is zero.

    Raises:
        ValueError: If ``periods_per_year`` is not a finite number of at
            least 1.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015])
        >>> equity = (1 + returns).cumprod() * 100
        >>> round(calculate_max_drawdown(equity), 4)
        -0.005
        >>> round(calculate_calmar_ratio(returns, equity), 2)
        504.0

    """
    _validate_periods_per_year(periods_per_year)
    returns = _drop_non_finite(returns)
    aligned = _align_series(returns, equity_curve)
    if len(aligned) < 2:
        return 0.0
    annual_return = aligned.iloc[:, 0].mean() * periods_per_year
    aligned_equity = aligned.iloc[:, 1]
    # Include the equity bar that seeds the first aligned return so a peak at
    # the start of the curve is not dropped from the drawdown sample.
    drawdown_equity = aligned_equity
    if (
        len(aligned_equity) > 0
    ):  # pragma: no cover  (aligned always has >= 2 rows; see the len(aligned) < 2 guard above)
        try:
            pos = equity_curve.index.get_loc(aligned_equity.index[0])
            if isinstance(pos, (slice, np.ndarray)):
                pos = int(np.asarray(pos).ravel()[0]) if np.asarray(pos).size else 0
            if pos > 0:
                seed = equity_curve.iloc[[pos - 1]]
                drawdown_equity = pd.concat([seed, aligned_equity], sort=False)
        except (KeyError, TypeError, ValueError):
            drawdown_equity = equity_curve
    max_dd = calculate_max_drawdown(drawdown_equity)
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

    Treynor ratio = (annualized mean excess return) / beta, where beta is the
    portfolio's sensitivity to market returns. The excess return is computed
    over the same aligned (overlapping-index) sample that ``calculate_beta``
    uses, so the numerator and denominator always describe the same
    observations, as they do for :func:`calculate_alpha`.

    Args:
        returns: Portfolio return series.
        market_returns: Benchmark return series.
        risk_free_rate: Annual risk-free rate (default 0.02).
        periods_per_year: Number of periods per year used to annualize the
            risk-free rate (default 252 for daily data).

    Returns:
        Treynor ratio, or 0.0 if insufficient data or beta is zero/undefined.

    Raises:
        ValueError: If ``periods_per_year`` is not a finite number of at
            least 1, or if ``risk_free_rate`` is not finite.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> market = pd.Series([0.008, 0.015, -0.003, 0.01, 0.008])
        >>> round(calculate_treynor_ratio(returns, market, risk_free_rate=0.02), 2)
        1.77

    """
    risk_free_rate = _validate_risk_free_rate(risk_free_rate)
    _validate_periods_per_year(periods_per_year)
    beta = calculate_beta(returns, market_returns)
    if beta == 0:
        return 0.0

    # Use the same aligned sample as calculate_beta so the average return and
    # the beta describe the same observations (mirrors calculate_alpha).
    aligned = _align_series(returns, market_returns)
    if len(aligned) < 2:  # pragma: no cover  (beta != 0 implies >= 2 aligned points)
        return 0.0

    excess_return = float(aligned.iloc[:, 0].mean() * periods_per_year - risk_free_rate)
    return float(excess_return / beta)


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

    Raises:
        ValueError: If ``periods_per_year`` is not a finite number of at
            least 1.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, 0.01])
        >>> benchmark = pd.Series([0.008, 0.015, -0.003, 0.01, 0.008])
        >>> round(calculate_information_ratio(returns, benchmark), 2)
        13.22

    """
    _validate_periods_per_year(periods_per_year)
    if np.isinf(returns).any() or np.isinf(benchmark_returns).any():
        return 0.0
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

    Raises:
        ValueError: If ``confidence`` is not a finite number strictly between
            0 and 1.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([-0.02, 0.01, -0.01, 0.005, -0.03, -0.025])
        >>> round(calculate_cvar(returns, 0.95), 3)
        -0.03
        >>> calculate_cvar(returns, 1.5)
        Traceback (most recent call last):
            ...
        ValueError: invalid confidence: the value must be in the range (0, 1) (got 1.5)

    """
    confidence = _validate_confidence(confidence)
    returns = _drop_non_finite(returns)
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
            A non-finite (NaN/inf) or non-numeric threshold is treated as
            ``0.0`` so it cannot poison the ratio with NaN.
        periods_per_year: Number of periods per year (not used in calculation
            but kept for API consistency).

    Returns:
        Omega ratio, or 0.0 if insufficient data or no losses below threshold.

    Examples:
        >>> import pandas as pd
        >>> returns = pd.Series([0.01, 0.02, -0.005, 0.015, -0.01])
        >>> round(calculate_omega_ratio(returns, threshold=0.0), 2)
        3.0
        >>> calculate_omega_ratio(returns, threshold=float("nan")) == calculate_omega_ratio(returns, threshold=0.0)
        True

    """
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
    ):
        threshold = 0.0
    returns = _drop_non_finite(returns)
    if len(returns) == 0:
        return 0.0

    gains = np.sum(np.maximum(returns.to_numpy(dtype=float) - threshold, 0.0))
    losses = np.sum(np.maximum(threshold - returns.to_numpy(dtype=float), 0.0))

    if losses == 0:
        return 0.0

    return float(gains / losses)


def _weights_array(weights: np.ndarray | pd.Series, columns: pd.Index) -> np.ndarray:
    """Return ``weights`` as a float array ordered like ``columns``.

    A labeled ``pd.Series`` is reindexed to the asset columns first, so the
    caller's Series order cannot silently pair one asset's weight with a
    different column. A plain array is assumed to already follow ``columns``
    order.

    Args:
        weights: Portfolio weights, either labeled by asset or positional.
        columns: Asset columns the weights must line up with.

    Returns:
        The weights as a float array in ``columns`` order.

    Examples:
        >>> import pandas as pd
        >>> _weights_array(pd.Series({"b": 0.3, "a": 0.7}), pd.Index(["a", "b"]))
        array([0.7, 0.3])

    """
    if isinstance(weights, pd.Series):
        weights = weights.reindex(columns)
    return np.asarray(weights, dtype=float)


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
    Sum of Component VaRs = Portfolio CVaR (Expected Shortfall)

    Because the tail statistic is a mean rather than a quantile, the
    component sum reproduces the portfolio expected shortfall (CVaR), not the
    quantile-based ``calculate_var``.

    Args:
        returns: DataFrame of asset returns (columns = assets, rows = periods).
        weights: Current portfolio weights (must sum to 1.0).
        confidence: VaR confidence level (default 0.95).

    Returns:
        Series of marginal VaR values indexed by asset name.

    Raises:
        ValueError: If ``confidence`` is not a finite number strictly between
            0 and 1.

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
        >>> calculate_marginal_var(returns, weights, confidence=1.5)
        Traceback (most recent call last):
            ...
        ValueError: invalid confidence: the value must be in the range (0, 1) (got 1.5)

    """
    confidence = _validate_confidence(confidence)
    returns = _drop_non_finite_rows(returns)
    if len(returns) < 2:
        return cast(pd.Series, pd.Series(0.0, index=returns.columns))

    weights = _weights_array(weights, returns.columns)
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
        return cast(pd.Series, pd.Series(0.0, index=returns.columns))

    tail_returns = returns.values[tail_mask]
    marginal_vars = tail_returns.mean(axis=0)

    return cast(pd.Series, pd.Series(marginal_vars, index=returns.columns))


def calculate_component_var(
    returns: pd.DataFrame,
    weights: np.ndarray | pd.Series,
    confidence: float = 0.95,
) -> pd.Series:
    """Calculate component VaR for each position using historical simulation.

    Component VaR = weight * Marginal VaR. Because the marginal statistics are
    tail means, the component VaRs sum to the portfolio Expected Shortfall
    (CVaR) exactly (Euler's theorem for homogeneous functions), not to the
    quantile-based ``calculate_var``.

    Args:
        returns: DataFrame of asset returns (columns = assets, rows = periods).
        weights: Current portfolio weights (must sum to 1.0).
        confidence: VaR confidence level (default 0.95).

    Returns:
        Series of component VaR values indexed by asset name.

    Raises:
        ValueError: If ``confidence`` is not a finite number strictly between
            0 and 1 (propagated from :func:`calculate_marginal_var`).

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
    weights = _weights_array(weights, returns.columns)
    marginal_var = calculate_marginal_var(returns, weights, confidence)
    component_var = weights * marginal_var
    return cast(pd.Series, pd.Series(component_var, index=returns.columns))


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
        >>> bool(round(contrib.sum(), 6) == round(calculate_volatility(pd.Series(returns.values @ weights.values), annualize=False), 6))
        True

    """
    returns = _drop_non_finite_rows(returns)
    if len(returns) < 2:
        return cast(pd.Series, pd.Series(0.0, index=returns.columns))

    weights = _weights_array(weights, returns.columns)
    if not np.isfinite(weights).all() or abs(weights.sum() - 1.0) > 1e-6:
        raise ValueError("weights must be finite and sum to 1.0")

    cov = returns.cov().values.copy()
    if annualize:
        cov *= periods_per_year

    portfolio_variance = weights @ cov @ weights
    if portfolio_variance <= 0:
        return cast(pd.Series, pd.Series(0.0, index=returns.columns))

    portfolio_vol = np.sqrt(portfolio_variance)
    marginal_contrib = cov @ weights / portfolio_vol
    contributions = weights * marginal_contrib

    return cast(pd.Series, pd.Series(contributions, index=returns.columns))


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
        long_only: If True, constrain weights to be non-negative (default False).

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
        >>> bool(abs(weights.sum() - 1.0) < 1e-6)
        True
        >>> len(weights) == 2
        True

    """
    returns = _drop_non_finite_rows(returns)
    if len(returns) < 2:
        n = len(returns.columns) if len(returns.columns) > 0 else 1
        return cast(pd.Series, pd.Series(1.0 / n, index=returns.columns))

    n = len(returns.columns)
    weights = np.ones(n) / n

    for _ in range(max_iter):
        contrib = np.asarray(
            calculate_volatility_contributions(
                returns,
                pd.Series(weights, index=returns.columns),
                annualize=annualize,
                periods_per_year=periods_per_year,
            ).values,
            dtype=float,
        )

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

    return cast(pd.Series, pd.Series(weights, index=returns.columns))


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
        long_only: If True, constrain weights to be non-negative (default False).

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
        >>> bool(abs(weights.sum() - 1.0) < 1e-6)
        True

    """
    returns = _drop_non_finite_rows(returns)
    if len(returns) < 2:
        n = len(returns.columns) if len(returns.columns) > 0 else 1
        return cast(pd.Series, pd.Series(1.0 / n, index=returns.columns))

    budget = _weights_array(risk_budget, returns.columns)
    if not np.isfinite(budget).all() or abs(budget.sum() - 1.0) > 1e-6:
        raise ValueError("risk_budget must be finite and sum to 1.0")

    n = len(returns.columns)
    weights = budget.copy()

    for _ in range(max_iter):
        contrib = np.asarray(
            calculate_volatility_contributions(
                returns,
                pd.Series(weights, index=returns.columns),
                annualize=annualize,
                periods_per_year=periods_per_year,
            ).values,
            dtype=float,
        )

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

    return cast(pd.Series, pd.Series(weights, index=returns.columns))


def calculate_all_metrics(
    equity_curve: pd.Series,
    market_returns: pd.Series | None = None,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> RiskMetrics:
    """Calculate all risk metrics from an equity curve.

    Calculates Sharpe ratio, Sortino ratio, max drawdown, Ulcer Index,
    volatility, VaR (95% and 99%), CVaR (95% and 99%), Calmar ratio, and
    optionally beta, alpha, Treynor ratio, Information ratio, and Omega
    ratio if market returns are provided.

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
        ulcer_index=calculate_ulcer_index(equity_curve),
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


def calculate_ulcer_index(equity_curve: pd.Series) -> float:
    """Calculate the Ulcer Index from an equity curve.

    The Ulcer Index measures downside risk as the root-mean-square of the
    percentage drawdowns from the running peak of the equity curve. It grows
    with both the depth and the duration of drawdowns, so a curve that stays
    far below its peak for a long time scores higher (worse) than one with the
    same maximum drawdown that recovers quickly. Unlike
    :func:`calculate_max_drawdown`, which reports only the single deepest
    point, the Ulcer Index accounts for the whole drawdown path.

    Args:
        equity_curve: Equity curve series (cumulative value).

    Returns:
        The Ulcer Index as a non-negative decimal (``0.0`` for a curve that
        only rises or is flat), or ``0.0`` if the curve is empty or its
        running peak is never strictly positive (an all-zero, all-negative,
        or zero-and-negative equity curve), in which case the drawdown ratio
        is undefined and is reported as neutral.

    Examples:
        >>> import pandas as pd
        >>> equity = pd.Series([100, 110, 105, 90, 95])
        >>> round(calculate_ulcer_index(equity), 5)
        0.10365
        >>> calculate_ulcer_index(pd.Series([100, 101, 102]))
        0.0
        >>> calculate_ulcer_index(pd.Series([-5.0, -10.0, -3.0]))
        0.0

    """
    equity_curve = _drop_non_finite(equity_curve)
    if len(equity_curve) == 0:
        return 0.0
    running_max = equity_curve.cummax()
    if running_max.max() <= 0:
        return 0.0
    # Drawdown from the running peak as a non-positive fraction. A zero peak
    # (an equity curve that starts at or drops to zero) makes the ratio
    # undefined for that point, so it contributes no drawdown.
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = (equity_curve - running_max) / running_max
    drawdown = drawdown.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    ulcer = float(np.sqrt(np.mean(drawdown**2)))
    if not np.isfinite(ulcer):
        return 0.0
    return ulcer


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
    "calculate_returns",
    "calculate_risk_budget_weights",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "calculate_treynor_ratio",
    "calculate_ulcer_index",
    "calculate_var",
    "calculate_volatility",
    "calculate_volatility_contributions",
]
