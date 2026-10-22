"""Backtest analysis helpers built on top of a completed BacktestResult.

The :mod:`quant_trading.regime` module labels an equity curve into market
regimes (bull/bear/sideways x low/high vol).  This module wires that
capability into the backtest package so a finished ``BacktestResult`` can be
inspected for the regimes it traversed, without requiring the caller to
reach into ``quant_trading.regime`` directly.

Examples:
    >>> from quant_trading.backtest.engine import BacktestResult
    >>> from quant_trading.backtest.metrics import BacktestMetrics
    >>> from quant_trading.backtest.analysis import analyze_regimes
    >>> import pandas as pd
    >>> metrics = BacktestMetrics()
    >>> eq = pd.Series(
    ...     [100000, 105000],
    ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
    ... )
    >>> res = BacktestResult(
    ...     equity_curve=eq,
    ...     trades=pd.DataFrame(),
    ...     positions={},
    ...     metrics=metrics,
    ...     start_date=pd.Timestamp("2024-01-01"),
    ...     end_date=pd.Timestamp("2024-01-31"),
    ...     initial_capital=100000,
    ...     final_value=105000,
    ...     total_return=5000,
    ...     total_return_pct=5.0,
    ... )
    >>> analysis = analyze_regimes(res)
    >>> analysis.n_segments
    0
    >>> analysis.current_regime.value
    'unknown'

"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant_trading.backtest.engine import BacktestResult
from quant_trading.regime import (
    Regime,
    RegimeDetector,
    RegimeResult,
    RegimeSegment,
    detect_regimes,
)


@dataclass
class BacktestRegimeAnalysis:
    """Regime analysis attached to a single ``BacktestResult``.

    Wraps a :class:`RegimeResult` together with the equity curve it was
    derived from so callers can correlate regime transitions with the
    backtest's trades and equity drawdowns.

    Attributes:
        result: The underlying :class:`RegimeResult` from detection.
        equity_curve: The equity curve the regimes were derived from.
        window: Rolling-window size used by the regime detector.
        vol_threshold: Optional explicit volatility threshold (<= 0 auto).
        return_threshold: Optional explicit return threshold (<= 0 auto).
        periods_per_year: Trading periods per year the rolling volatility and
            rolling mean return were annualized with.

    Examples:
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> from quant_trading.backtest.analysis import analyze_regimes
        >>> import pandas as pd
        >>> metrics = BacktestMetrics()
        >>> eq = pd.Series(
        ...     [100000, 105000],
        ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
        ... )
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> analysis = analyze_regimes(res)
        >>> analysis.window
        20
        >>> analysis.to_dict()["current_regime"]
        'unknown'

    """

    result: RegimeResult
    equity_curve: pd.Series
    window: int = 20
    vol_threshold: float = 0.0
    return_threshold: float = 0.0
    periods_per_year: int = 252

    @property
    def n_segments(self) -> int:
        """Number of detected regime segments.

        Examples:
            >>> from quant_trading.backtest.engine import BacktestResult
            >>> from quant_trading.backtest.metrics import BacktestMetrics
            >>> from quant_trading.backtest.analysis import analyze_regimes
            >>> import pandas as pd
            >>> metrics = BacktestMetrics()
            >>> eq = pd.Series(
            ...     [100000, 105000],
            ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
            ... )
            >>> res = BacktestResult(
            ...     equity_curve=eq,
            ...     trades=pd.DataFrame(),
            ...     positions={},
            ...     metrics=metrics,
            ...     start_date=pd.Timestamp("2024-01-01"),
            ...     end_date=pd.Timestamp("2024-01-31"),
            ...     initial_capital=100000,
            ...     final_value=105000,
            ...     total_return=5000,
            ...     total_return_pct=5.0,
            ... )
            >>> analyze_regimes(res).n_segments
            0

        """
        return self.result.n_segments

    @property
    def current_regime(self) -> Regime:
        """Regime of the most recent segment.

        Examples:
            >>> from quant_trading.backtest.engine import BacktestResult
            >>> from quant_trading.backtest.metrics import BacktestMetrics
            >>> from quant_trading.backtest.analysis import analyze_regimes
            >>> import pandas as pd
            >>> metrics = BacktestMetrics()
            >>> eq = pd.Series(
            ...     [100000, 105000],
            ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
            ... )
            >>> res = BacktestResult(
            ...     equity_curve=eq,
            ...     trades=pd.DataFrame(),
            ...     positions={},
            ...     metrics=metrics,
            ...     start_date=pd.Timestamp("2024-01-01"),
            ...     end_date=pd.Timestamp("2024-01-31"),
            ...     initial_capital=100000,
            ...     final_value=105000,
            ...     total_return=5000,
            ...     total_return_pct=5.0,
            ... )
            >>> analyze_regimes(res).current_regime.value
            'unknown'

        """
        return self.result.current_regime

    @property
    def segments(self) -> list[RegimeSegment]:
        """Detected regime segments in chronological order.

        Examples:
            >>> from quant_trading.backtest.engine import BacktestResult
            >>> from quant_trading.backtest.metrics import BacktestMetrics
            >>> from quant_trading.backtest.analysis import analyze_regimes
            >>> import pandas as pd
            >>> metrics = BacktestMetrics()
            >>> eq = pd.Series(
            ...     [100000, 105000],
            ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
            ... )
            >>> res = BacktestResult(
            ...     equity_curve=eq,
            ...     trades=pd.DataFrame(),
            ...     positions={},
            ...     metrics=metrics,
            ...     start_date=pd.Timestamp("2024-01-01"),
            ...     end_date=pd.Timestamp("2024-01-31"),
            ...     initial_capital=100000,
            ...     final_value=105000,
            ...     total_return=5000,
            ...     total_return_pct=5.0,
            ... )
            >>> analyze_regimes(res).segments
            []

        """
        return self.result.segments

    def to_dict(self) -> dict[str, Any]:
        """Serialize the analysis to a JSON-friendly dictionary.

        Returns:
            Dictionary with window thresholds, current regime, volatility,
            return percentage, the annualization factor, and serialized
            segments.

        Examples:
            >>> from quant_trading.backtest.engine import BacktestResult
            >>> from quant_trading.backtest.metrics import BacktestMetrics
            >>> from quant_trading.backtest.analysis import analyze_regimes
            >>> import pandas as pd
            >>> metrics = BacktestMetrics()
            >>> eq = pd.Series(
            ...     [100000, 105000],
            ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
            ... )
            >>> res = BacktestResult(
            ...     equity_curve=eq,
            ...     trades=pd.DataFrame(),
            ...     positions={},
            ...     metrics=metrics,
            ...     start_date=pd.Timestamp("2024-01-01"),
            ...     end_date=pd.Timestamp("2024-01-31"),
            ...     initial_capital=100000,
            ...     final_value=105000,
            ...     total_return=5000,
            ...     total_return_pct=5.0,
            ... )
            >>> analysis = analyze_regimes(res)
            >>> analysis.to_dict()["window"]
            20
            >>> analysis.to_dict()["current_regime"]
            'unknown'
            >>> analysis.to_dict()["periods_per_year"]
            252

        """
        return {
            "window": self.window,
            "vol_threshold": self.vol_threshold,
            "return_threshold": self.return_threshold,
            "periods_per_year": self.periods_per_year,
            "current_regime": self.result.current_regime.value,
            "total_volatility": self.result.total_volatility,
            "total_return_pct": self.result.total_return_pct,
            "segments": [s.to_dict() for s in self.result.segments],
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Return regime segments as a DataFrame.

        Returns:
            DataFrame produced by the underlying :class:`RegimeResult`.

        Examples:
            >>> from quant_trading.backtest.engine import BacktestResult
            >>> from quant_trading.backtest.metrics import BacktestMetrics
            >>> from quant_trading.backtest.analysis import analyze_regimes
            >>> import pandas as pd
            >>> metrics = BacktestMetrics()
            >>> eq = pd.Series(
            ...     [100000, 105000],
            ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
            ... )
            >>> res = BacktestResult(
            ...     equity_curve=eq,
            ...     trades=pd.DataFrame(),
            ...     positions={},
            ...     metrics=metrics,
            ...     start_date=pd.Timestamp("2024-01-01"),
            ...     end_date=pd.Timestamp("2024-01-31"),
            ...     initial_capital=100000,
            ...     final_value=105000,
            ...     total_return=5000,
            ...     total_return_pct=5.0,
            ... )
            >>> analysis = analyze_regimes(res)
            >>> len(analysis.to_dataframe())
            0

        """
        return self.result.to_dataframe()

    def summary(self) -> dict[str, Any]:
        """Return a summary of the regime analysis.

        Returns:
            Summary dictionary augmented with window, threshold and
            annualization settings.

        Examples:
            >>> from quant_trading.backtest.engine import BacktestResult
            >>> from quant_trading.backtest.metrics import BacktestMetrics
            >>> from quant_trading.backtest.analysis import analyze_regimes
            >>> import pandas as pd
            >>> metrics = BacktestMetrics()
            >>> eq = pd.Series(
            ...     [100000, 105000],
            ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
            ... )
            >>> res = BacktestResult(
            ...     equity_curve=eq,
            ...     trades=pd.DataFrame(),
            ...     positions={},
            ...     metrics=metrics,
            ...     start_date=pd.Timestamp("2024-01-01"),
            ...     end_date=pd.Timestamp("2024-01-31"),
            ...     initial_capital=100000,
            ...     final_value=105000,
            ...     total_return=5000,
            ...     total_return_pct=5.0,
            ... )
            >>> analysis = analyze_regimes(res)
            >>> analysis.summary()["window"]
            20
            >>> analysis.summary()["current_regime"]
            'unknown'

        """
        summary = self.result.summary()
        summary["window"] = self.window
        summary["vol_threshold"] = self.vol_threshold
        summary["return_threshold"] = self.return_threshold
        summary["periods_per_year"] = self.periods_per_year
        return summary


def analyze_regimes(
    result: BacktestResult,
    window: int = 20,
    vol_threshold: float = 0.0,
    return_threshold: float = 0.0,
    periods_per_year: int = 252,
) -> BacktestRegimeAnalysis:
    """Run regime detection on a backtest's equity curve.

    Args:
        result: A finished ``BacktestResult``.
        window: Rolling-window size used by the regime detector.
        vol_threshold: Optional explicit volatility threshold (<= 0 auto).
        return_threshold: Optional explicit return threshold (<= 0 auto).
        periods_per_year: Trading periods per year used to annualize
            volatility and return (default 252 for daily data).

    Returns:
        A :class:`BacktestRegimeAnalysis` wrapping the detection result.

    Examples:
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> from quant_trading.backtest.analysis import analyze_regimes
        >>> import pandas as pd
        >>> metrics = BacktestMetrics()
        >>> eq = pd.Series(
        ...     [100000, 105000],
        ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
        ... )
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> analysis = analyze_regimes(res, window=10)
        >>> analysis.window
        10
        >>> analysis.n_segments
        0

    """
    equity = result.equity_curve
    regime_result = detect_regimes(
        equity,
        window=window,
        vol_threshold=vol_threshold,
        return_threshold=return_threshold,
        periods_per_year=periods_per_year,
    )
    return BacktestRegimeAnalysis(
        result=regime_result,
        equity_curve=equity,
        window=window,
        vol_threshold=vol_threshold,
        return_threshold=return_threshold,
        periods_per_year=periods_per_year,
    )


def regime_for_backtest(
    result: BacktestResult,
    window: int = 20,
    vol_threshold: float = 0.0,
    return_threshold: float = 0.0,
    periods_per_year: int = 252,
) -> RegimeResult:
    """Return just the :class:`RegimeResult` from a backtest.

    Equivalent to ``analyze_regimes(...).result`` but cheaper to call when
    only the raw regime data is needed.

    Args:
        result: A finished ``BacktestResult``.
        window: Rolling-window size used by the regime detector.
        vol_threshold: Optional explicit volatility threshold (<= 0 auto).
        return_threshold: Optional explicit return threshold (<= 0 auto).
        periods_per_year: Trading periods per year used to annualize
            volatility and return (default 252 for daily data).

    Returns:
        The raw :class:`RegimeResult` from detection.

    Examples:
        >>> from quant_trading.backtest.engine import BacktestResult
        >>> from quant_trading.backtest.metrics import BacktestMetrics
        >>> from quant_trading.backtest.analysis import regime_for_backtest
        >>> import pandas as pd
        >>> metrics = BacktestMetrics()
        >>> eq = pd.Series(
        ...     [100000, 105000],
        ...     index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31")],
        ... )
        >>> res = BacktestResult(
        ...     equity_curve=eq,
        ...     trades=pd.DataFrame(),
        ...     positions={},
        ...     metrics=metrics,
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     end_date=pd.Timestamp("2024-01-31"),
        ...     initial_capital=100000,
        ...     final_value=105000,
        ...     total_return=5000,
        ...     total_return_pct=5.0,
        ... )
        >>> regime_for_backtest(res).n_segments
        0
        >>> regime_for_backtest(res).current_regime.value
        'unknown'

    """
    equity = result.equity_curve
    return detect_regimes(
        equity,
        window=window,
        vol_threshold=vol_threshold,
        return_threshold=return_threshold,
        periods_per_year=periods_per_year,
    )


__all__ = [
    "BacktestRegimeAnalysis",
    "Regime",
    "RegimeDetector",
    "RegimeResult",
    "RegimeSegment",
    "analyze_regimes",
    "detect_regimes",
    "regime_for_backtest",
]
