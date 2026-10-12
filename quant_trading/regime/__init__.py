"""Market regime detection for backtest analysis."""

from .detector import (
    Regime,
    RegimeDetector,
    RegimeResult,
    RegimeSegment,
    detect_regimes,
)

__all__ = [
    "Regime",
    "RegimeDetector",
    "RegimeResult",
    "RegimeSegment",
    "detect_regimes",
]
