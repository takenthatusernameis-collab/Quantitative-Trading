"""Market regime detection and regime-specific backtesting."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import numpy as np
import pandas as pd


class MarketRegime(StrEnum):
    BULL_TRENDING = "bull_trending"
    BEAR_TRENDING = "bear_trending"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    VOLATILITY_BREAKOUT = "volatility_breakout"
    UNKNOWN = "unknown"


@dataclass
class RegimeLabel:
    regime: MarketRegime
    confidence: float
    timestamp: datetime
    indicators: dict[str, float] = field(default_factory=dict)


@dataclass
class RegimeAnalysis:
    symbol: str
    start_date: datetime
    end_date: datetime
    regimes: list[RegimeLabel]
    regime_counts: dict[str, int]
    dominant_regime: MarketRegime
    avg_volatility: float
    avg_trend_strength: float


class RegimeDetector:
    """Detects market regimes based on volatility, trend strength, and price action."""

    def __init__(
        self,
        vol_window: int = 20,
        trend_window: int = 50,
        high_vol_threshold: float = 0.02,
        low_vol_threshold: float = 0.005,
        trend_threshold: float = 0.001,
    ):
        self.vol_window = vol_window
        self.trend_window = trend_window
        self.high_vol_threshold = high_vol_threshold
        self.low_vol_threshold = low_vol_threshold
        self.trend_threshold = trend_threshold

    def detect(
        self,
        data: pd.DataFrame,
        symbol: str = "BTC/USDT",
    ) -> RegimeAnalysis:
        if data.empty or len(data) < self.trend_window:
            raise ValueError("Insufficient data for regime detection")

        close = data["close"].astype(float)
        high = data["high"].astype(float)
        low = data["low"].astype(float)

        returns = close.pct_change()
        volatility = returns.rolling(self.vol_window).std()

        sma_short = close.rolling(20).mean()
        sma_long = close.rolling(self.trend_window).mean()
        trend_strength = (sma_short - sma_long) / sma_long

        atr = (high - low).rolling(self.vol_window).mean()
        atr_pct = atr / close

        regimes: list[RegimeLabel] = []
        regime_counts: dict[str, int] = {}

        for i in range(self.trend_window, len(data)):
            ts = data.index[i]
            vol = volatility.iloc[i]
            trend = trend_strength.iloc[i]
            atr_val = atr_pct.iloc[i]

            if pd.isna(vol) or pd.isna(trend):
                continue

            indicators = {
                "volatility": float(vol),
                "trend_strength": float(trend),
                "atr_pct": float(atr_val) if not pd.isna(atr_val) else 0.0,
            }

            regime, confidence = self._classify(vol, trend, atr_val)
            regimes.append(
                RegimeLabel(
                    regime=regime,
                    confidence=confidence,
                    timestamp=ts,
                    indicators=indicators,
                )
            )
            regime_counts[regime.value] = regime_counts.get(regime.value, 0) + 1

        if not regimes:
            raise ValueError("No valid regime labels generated")

        dominant = max(regime_counts, key=regime_counts.get)  # type: ignore[arg-type]
        avg_vol = float(np.nanmean([r.indicators["volatility"] for r in regimes]))
        avg_trend = float(np.nanmean([r.indicators["trend_strength"] for r in regimes]))

        return RegimeAnalysis(
            symbol=symbol,
            start_date=regimes[0].timestamp,
            end_date=regimes[-1].timestamp,
            regimes=regimes,
            regime_counts=regime_counts,
            dominant_regime=MarketRegime(dominant),
            avg_volatility=avg_vol,
            avg_trend_strength=avg_trend,
        )

    def _classify(self, vol: float, trend: float, atr_pct: float) -> tuple[MarketRegime, float]:
        if vol >= self.high_vol_threshold * 2:
            return MarketRegime.VOLATILITY_BREAKOUT, min(vol / (self.high_vol_threshold * 2), 1.0)
        if vol >= self.high_vol_threshold:
            if abs(trend) >= self.trend_threshold:
                regime = MarketRegime.BULL_TRENDING if trend > 0 else MarketRegime.BEAR_TRENDING
                return regime, min(abs(trend) / self.trend_threshold, 1.0)
            return MarketRegime.HIGH_VOLATILITY, min(vol / self.high_vol_threshold, 1.0)
        if vol <= self.low_vol_threshold:
            if abs(trend) >= self.trend_threshold * 2:
                regime = MarketRegime.BULL_TRENDING if trend > 0 else MarketRegime.BEAR_TRENDING
                return regime, min(abs(trend) / (self.trend_threshold * 2), 1.0)
            return MarketRegime.LOW_VOLATILITY, min(self.low_vol_threshold / max(vol, 1e-10), 1.0)
        if abs(trend) >= self.trend_threshold:
            regime = MarketRegime.BULL_TRENDING if trend > 0 else MarketRegime.BEAR_TRENDING
            return regime, min(abs(trend) / self.trend_threshold, 1.0)
        return MarketRegime.RANGING, 0.5


class RegimeAwareBacktest:
    """Runs backtests with regime-aware position sizing and strategy selection."""

    def __init__(self, detector: RegimeDetector | None = None):
        self.detector = detector or RegimeDetector()

    def analyze_regimes(
        self,
        market_data: dict[str, pd.DataFrame],
    ) -> dict[str, RegimeAnalysis]:
        results = {}
        for symbol, df in market_data.items():
            try:
                results[symbol] = self.detector.detect(df, symbol)
            except ValueError:
                continue
        return results


__all__ = [
    "MarketRegime",
    "RegimeLabel",
    "RegimeAnalysis",
    "RegimeDetector",
    "RegimeAwareBacktest",
]
