"""Market regime detection for backtest analysis."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


class Regime(Enum):
    """Market regime labels."""

    BULL_LOW_VOL = "bull_low_vol"
    BULL_HIGH_VOL = "bull_high_vol"
    BEAR_LOW_VOL = "bear_low_vol"
    BEAR_HIGH_VOL = "bear_high_vol"
    SIDEWAYS_LOW_VOL = "sideways_low_vol"
    SIDEWAYS_HIGH_VOL = "sideways_high_vol"
    UNKNOWN = "unknown"


@dataclass
class RegimeSegment:
    """A single labeled regime segment."""

    regime: Regime
    start: Any
    end: Any
    start_index: int
    end_index: int
    volatility: float = 0.0
    return_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "start": str(self.start),
            "end": str(self.end),
            "start_index": self.start_index,
            "end_index": self.end_index,
            "volatility": self.volatility,
            "return_pct": self.return_pct,
        }


@dataclass
class RegimeResult:
    """Result of regime detection."""

    segments: list[RegimeSegment] = field(default_factory=list)
    regimes: list[Regime] = field(default_factory=list)
    n_segments: int = 0
    current_regime: Regime = Regime.UNKNOWN
    total_volatility: float = 0.0
    total_return_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "regimes": [r.value for r in self.regimes],
            "n_segments": self.n_segments,
            "current_regime": self.current_regime.value,
            "total_volatility": self.total_volatility,
            "total_return_pct": self.total_return_pct,
        }

    def to_dataframe(self) -> pd.DataFrame:
        if not self.segments:
            return pd.DataFrame()  # type: ignore[no-any-return]
        return pd.DataFrame([s.to_dict() for s in self.segments])  # type: ignore[no-any-return]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for r in self.regimes:
            counts[r.value] = counts.get(r.value, 0) + 1
        return {
            "n_segments": self.n_segments,
            "current_regime": self.current_regime.value,
            "total_volatility": self.total_volatility,
            "total_return_pct": self.total_return_pct,
            "regime_counts": counts,
        }


class RegimeDetector:
    """Detector that classifies market regimes over a price or equity series.

    Regimes are determined by combining a direction signal (bull/bear/sideways)
    with a volatility signal (high/low) relative to rolling reference statistics.
    """

    def __init__(
        self,
        window: int = 20,
        vol_threshold: float = 0.0,
        return_threshold: float = 0.0,
        periods_per_year: int = 252,
    ):
        self.window = window
        self.vol_threshold = vol_threshold
        self.return_threshold = return_threshold
        self.periods_per_year = periods_per_year

    def detect(self, prices: pd.Series) -> RegimeResult:
        if not isinstance(prices, pd.Series):
            prices = pd.Series(prices)
        if len(prices) < 2:
            return RegimeResult()

        returns = prices.pct_change().dropna()
        if len(returns) < 1:
            return RegimeResult()

        rolling_vol = returns.rolling(self.window).std() * np.sqrt(self.periods_per_year)
        rolling_mean = returns.rolling(self.window).mean() * self.periods_per_year

        vol_threshold = self.vol_threshold
        if vol_threshold <= 0:
            vol_threshold = float(rolling_vol.mean())

        ret_threshold = self.return_threshold
        if ret_threshold <= 0:
            ret_threshold = float(rolling_mean.mean()) if not np.isnan(rolling_mean.mean()) else 0.0

        segments = self._build_segments(
            prices, returns, rolling_vol, rolling_mean, vol_threshold, ret_threshold
        )

        regimes = [s.regime for s in segments]
        current = segments[-1].regime if segments else Regime.UNKNOWN
        total_vol = float(rolling_vol.iloc[-1]) if not np.isnan(rolling_vol.iloc[-1]) else 0.0
        total_ret = float((prices.iloc[-1] / prices.iloc[0] - 1) * 100)

        return RegimeResult(
            segments=segments,
            regimes=regimes,
            n_segments=len(segments),
            current_regime=current,
            total_volatility=total_vol,
            total_return_pct=total_ret,
        )

    def _build_segments(
        self,
        prices: pd.Series,
        returns: pd.Series,
        rolling_vol: pd.Series,
        rolling_mean: pd.Series,
        vol_threshold: float,
        ret_threshold: float,
    ) -> list[RegimeSegment]:
        labels = self._label_series(rolling_vol, rolling_mean, vol_threshold, ret_threshold)
        return self._merge_segments(labels, prices, returns, rolling_vol)

    def _label_series(
        self,
        rolling_vol: pd.Series,
        rolling_mean: pd.Series,
        vol_threshold: float,
        ret_threshold: float,
    ) -> list[Regime | None]:
        labels: list[Regime | None] = []
        for i in range(len(rolling_vol)):
            vol = rolling_vol.iloc[i]
            mean = rolling_mean.iloc[i]
            if np.isnan(vol) or np.isnan(mean):
                labels.append(None)
                continue
            high_vol = vol > vol_threshold
            if mean > ret_threshold:
                regime: Regime = Regime.BULL_HIGH_VOL if high_vol else Regime.BULL_LOW_VOL
            elif mean < -ret_threshold:
                regime = Regime.BEAR_HIGH_VOL if high_vol else Regime.BEAR_LOW_VOL
            else:
                regime = Regime.SIDEWAYS_HIGH_VOL if high_vol else Regime.SIDEWAYS_LOW_VOL
            labels.append(regime)
        return labels

    def _merge_segments(
        self,
        labels: list[Regime | None],
        prices: pd.Series,
        returns: pd.Series,
        rolling_vol: pd.Series,
    ) -> list[RegimeSegment]:
        segments: list[RegimeSegment] = []
        current: Regime | None = None
        start_idx = 0
        for i, label in enumerate(labels):
            if label is None:
                continue
            if current is None:
                current = label
                start_idx = i
            elif label != current:
                segments.append(
                    self._make_segment(current, start_idx, i, prices, returns, rolling_vol)
                )
                current = label
                start_idx = i
        if current is not None:
            segments.append(
                self._make_segment(current, start_idx, len(labels), prices, returns, rolling_vol)
            )
        return segments

    def _make_segment(
        self,
        regime: Regime,
        start_idx: int,
        end_idx: int,
        prices: pd.Series,
        returns: pd.Series,
        rolling_vol: pd.Series,
    ) -> RegimeSegment:
        price_start = prices.index[start_idx]
        price_end = prices.index[end_idx - 1] if end_idx > 0 else prices.index[start_idx]
        seg_vol = rolling_vol.iloc[start_idx:end_idx]
        ret_pct = (
            float((prices.iloc[end_idx] / prices.iloc[start_idx] - 1) * 100)
            if end_idx < len(prices)
            else 0.0
        )
        vol = float(seg_vol.mean()) if len(seg_vol) > 0 and not np.isnan(seg_vol.mean()) else 0.0
        return RegimeSegment(
            regime=regime,
            start=price_start,
            end=price_end,
            start_index=start_idx,
            end_index=end_idx,
            volatility=vol,
            return_pct=ret_pct,
        )


def detect_regimes(
    prices: pd.Series,
    window: int = 20,
    vol_threshold: float = 0.0,
    return_threshold: float = 0.0,
) -> RegimeResult:
    detector = RegimeDetector(
        window=window, vol_threshold=vol_threshold, return_threshold=return_threshold
    )
    return detector.detect(prices)
