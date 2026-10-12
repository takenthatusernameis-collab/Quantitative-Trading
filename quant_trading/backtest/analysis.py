"""Backtest analysis helpers built on top of a completed BacktestResult.

The :mod:`quant_trading.regime` module labels an equity curve into market
regimes (bull/bear/sideways x low/high vol).  This module wires that
capability into the backtest package so a finished ``BacktestResult`` can be
inspected for the regimes it traversed, without requiring the caller to
reach into ``quant_trading.regime`` directly.
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
    """

    result: RegimeResult
    equity_curve: pd.Series
    window: int = 20
    vol_threshold: float = 0.0
    return_threshold: float = 0.0

    @property
    def n_segments(self) -> int:
        return self.result.n_segments

    @property
    def current_regime(self) -> Regime:
        return self.result.current_regime

    @property
    def segments(self) -> list[RegimeSegment]:
        return self.result.segments

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "vol_threshold": self.vol_threshold,
            "return_threshold": self.return_threshold,
            "current_regime": self.result.current_regime.value,
            "total_volatility": self.result.total_volatility,
            "total_return_pct": self.result.total_return_pct,
            "segments": [s.to_dict() for s in self.result.segments],
        }

    def to_dataframe(self) -> pd.DataFrame:
        return self.result.to_dataframe()

    def summary(self) -> dict[str, Any]:
        summary = self.result.summary()
        summary["window"] = self.window
        summary["vol_threshold"] = self.vol_threshold
        summary["return_threshold"] = self.return_threshold
        return summary


def analyze_regimes(
    result: BacktestResult,
    window: int = 20,
    vol_threshold: float = 0.0,
    return_threshold: float = 0.0,
) -> BacktestRegimeAnalysis:
    """Run regime detection on a backtest's equity curve.

    Args:
        result: A finished ``BacktestResult``.
        window: Rolling-window size used by the regime detector.
        vol_threshold: Optional explicit volatility threshold (<= 0 auto).
        return_threshold: Optional explicit return threshold (<= 0 auto).

    Returns:
        A :class:`BacktestRegimeAnalysis` wrapping the detection result.
    """
    equity = result.equity_curve
    regime_result = detect_regimes(
        equity,
        window=window,
        vol_threshold=vol_threshold,
        return_threshold=return_threshold,
    )
    return BacktestRegimeAnalysis(
        result=regime_result,
        equity_curve=equity,
        window=window,
        vol_threshold=vol_threshold,
        return_threshold=return_threshold,
    )


def regime_for_backtest(
    result: BacktestResult,
    window: int = 20,
    vol_threshold: float = 0.0,
    return_threshold: float = 0.0,
) -> RegimeResult:
    """Convenience wrapper returning just the :class:`RegimeResult`.

    Equivalent to ``analyze_regimes(...).result`` but cheaper to call when
    only the raw regime data is needed.
    """
    return detect_regimes(
        result.equity_curve,
        window=window,
        vol_threshold=vol_threshold,
        return_threshold=return_threshold,
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
