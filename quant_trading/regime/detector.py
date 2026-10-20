"""Market regime detection for backtest analysis.

This module classifies a price or equity series into a sequence of market
regimes. Each regime is a combination of a direction signal
(bull/bear/sideways) and a volatility signal (high/low) computed relative to
rolling reference statistics. The classification is performed by
:class:`RegimeDetector`, with :func:`detect_regimes` providing a convenient
convenience wrapper around it.

Examples:
    >>> import pandas as pd
    >>> prices = pd.Series(
    ...     [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
    ...     index=pd.date_range("2024-01-01", periods=6, freq="D"),
    ... )
    >>> from quant_trading.regime.detector import detect_regimes
    >>> result = detect_regimes(prices, window=2, vol_threshold=10.0, return_threshold=10.0)
    >>> result.n_segments
    1
    >>> result.current_regime.value
    'sideways_low_vol'

"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


class Regime(Enum):
    """Market regime labels.

    Regimes combine a direction (bull/bear/sideways) with a volatility level
    (high/low). The :attr:`UNKNOWN` label is used when a regime cannot be
    determined, for example when the input series is too short or contains
    non-finite values.

    Attributes:
        BULL_LOW_VOL: Rising prices with below-threshold volatility.
        BULL_HIGH_VOL: Rising prices with above-threshold volatility.
        BEAR_LOW_VOL: Falling prices with below-threshold volatility.
        BEAR_HIGH_VOL: Falling prices with above-threshold volatility.
        SIDEWAYS_LOW_VOL: Flat prices with below-threshold volatility.
        SIDEWAYS_HIGH_VOL: Flat prices with above-threshold volatility.
        UNKNOWN: Regime could not be determined.

    Examples:
        >>> from quant_trading.regime import Regime
        >>> Regime.BULL_LOW_VOL.value
        'bull_low_vol'
        >>> Regime.UNKNOWN.value
        'unknown'

    """

    BULL_LOW_VOL = "bull_low_vol"
    BULL_HIGH_VOL = "bull_high_vol"
    BEAR_LOW_VOL = "bear_low_vol"
    BEAR_HIGH_VOL = "bear_high_vol"
    SIDEWAYS_LOW_VOL = "sideways_low_vol"
    SIDEWAYS_HIGH_VOL = "sideways_high_vol"
    UNKNOWN = "unknown"


@dataclass
class RegimeSegment:
    """A single labeled regime segment.

    A segment is a maximal contiguous run of price bars that share the same
    :class:`Regime` label. Segments are produced by merging consecutive
    identical labels emitted by the rolling classifier.

    Attributes:
        regime: The :class:`Regime` label assigned to every bar in the segment.
        start: Timestamp of the segment's first labeled price bar.
        end: Timestamp of the segment's last labeled price bar.
        start_index: Position of the segment's first label within the label
            series (0-based index into the rolling-statistics series, which is
            ``prices.index[1:]`` after ``pct_change``).
        end_index: Exclusive end position of the segment within the label
            series.
        volatility: Mean annualized volatility over the segment's labeled
            bars.
        return_pct: Percentage price change across the segment's labeled
            bars (end price relative to start price).

    Examples:
        >>> import pandas as pd
        >>> from quant_trading.regime import Regime, RegimeSegment
        >>> seg = RegimeSegment(
        ...     regime=Regime.BULL_LOW_VOL,
        ...     start=pd.Timestamp("2024-01-01"),
        ...     end=pd.Timestamp("2024-01-31"),
        ...     start_index=0,
        ...     end_index=20,
        ...     volatility=0.1,
        ...     return_pct=5.0,
        ... )
        >>> seg.to_dict()["regime"]
        'bull_low_vol'
        >>> seg.to_dict()["return_pct"]
        5.0

    """

    regime: Regime
    start: Any
    end: Any
    start_index: int
    end_index: int
    volatility: float = 0.0
    return_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert the segment to a plain dictionary.

        Returns:
            Dictionary with keys ``regime`` (the label's string value),
            ``start``, ``end``, ``start_index``, ``end_index``,
            ``volatility``, and ``return_pct``.

        """
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
    """Result of a regime detection run.

    Aggregates the labeled segments produced by :class:`RegimeDetector`
    along with summary statistics for the whole series.

    Attributes:
        segments: Ordered list of :class:`RegimeSegment` objects.
        regimes: Ordered list of :class:`Regime` labels, one per segment.
        n_segments: Number of detected segments (``len(segments)``).
        current_regime: The regime of the last segment, or
            :attr:`Regime.UNKNOWN` when no segment was detected.
        total_volatility: Annualized volatility of the last labeled bar
            (0.0 when not computable).
        total_return_pct: Percentage change from the first to the last price
            bar of the full input series.

    Examples:
        >>> import pandas as pd
        >>> from quant_trading.regime.detector import detect_regimes
        >>> prices = pd.Series(
        ...     [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        ...     index=pd.date_range("2024-01-01", periods=6, freq="D"),
        ... )
        >>> result = detect_regimes(prices, window=2, vol_threshold=10.0, return_threshold=10.0)
        >>> result.n_segments
        1
        >>> result.current_regime.value
        'sideways_low_vol'
        >>> result.to_dict()["n_segments"]
        1

    """

    segments: list[RegimeSegment] = field(default_factory=list)
    regimes: list[Regime] = field(default_factory=list)
    n_segments: int = 0
    current_regime: Regime = Regime.UNKNOWN
    total_volatility: float = 0.0
    total_return_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a plain dictionary.

        Returns:
            Dictionary with keys ``segments`` (list of segment dicts),
            ``regimes`` (list of regime string values), ``n_segments``,
            ``current_regime``, ``total_volatility``, and
            ``total_return_pct``.

        """
        return {
            "segments": [s.to_dict() for s in self.segments],
            "regimes": [r.value for r in self.regimes],
            "n_segments": self.n_segments,
            "current_regime": self.current_regime.value,
            "total_volatility": self.total_volatility,
            "total_return_pct": self.total_return_pct,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the segments to a DataFrame.

        Returns:
            DataFrame with one row per segment and columns ``regime``,
            ``start``, ``end``, ``start_index``, ``end_index``,
            ``volatility``, and ``return_pct``. An empty DataFrame is
            returned when there are no segments.

        Examples:
            >>> import pandas as pd
            >>> from quant_trading.regime.detector import detect_regimes
            >>> prices = pd.Series(
            ...     [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            ...     index=pd.date_range("2024-01-01", periods=6, freq="D"),
            ... )
            >>> result = detect_regimes(prices, window=2, vol_threshold=10.0, return_threshold=10.0)
            >>> df = result.to_dataframe()
            >>> len(df)
            1
            >>> "regime" in df.columns
            True

        """
        if not self.segments:
            empty: pd.DataFrame = pd.DataFrame()
            return empty
        frame: pd.DataFrame = pd.DataFrame([s.to_dict() for s in self.segments])
        return frame

    def summary(self) -> dict[str, Any]:
        """Return a compact summary of the detection result.

        Returns:
            Dictionary with keys ``n_segments``, ``current_regime``,
            ``total_volatility``, ``total_return_pct``, and
            ``regime_counts`` (a mapping from regime string value to the
            number of segments with that label).

        Examples:
            >>> import pandas as pd
            >>> from quant_trading.regime.detector import detect_regimes
            >>> prices = pd.Series(
            ...     [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            ...     index=pd.date_range("2024-01-01", periods=6, freq="D"),
            ... )
            >>> result = detect_regimes(prices, window=2, vol_threshold=10.0, return_threshold=10.0)
            >>> summary = result.summary()
            >>> summary["n_segments"]
            1
            >>> "regime_counts" in summary
            True

        """
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
    Rolling volatility and rolling mean return are computed over a trailing
    ``window`` of returns, then compared against thresholds. When a threshold
    is left at its default (``0.0`` or below), it is derived from the series
    itself (the mean of the rolling statistics).

    Attributes:
        window: Number of trailing returns used for the rolling statistics.
        vol_threshold: Annualized volatility threshold separating low and
            high volatility. Defaults to the mean rolling volatility when
            ``<= 0``.
        return_threshold: Annualized return threshold separating sideways
            from trending markets. Defaults to the mean rolling return when
            ``<= 0``.
        periods_per_year: Number of trading periods per year used to
            annualize volatility and return (default 252 for daily data).

    Examples:
        >>> from quant_trading.regime.detector import RegimeDetector
        >>> detector = RegimeDetector()
        >>> detector.window
        20
        >>> detector.periods_per_year
        252

    """

    def __init__(
        self,
        window: int = 20,
        vol_threshold: float = 0.0,
        return_threshold: float = 0.0,
        periods_per_year: int = 252,
    ):
        """Configure the regime detector.

        Args:
            window: Number of trailing returns used for the rolling
                statistics (default 20).
            vol_threshold: Annualized volatility threshold separating low
                and high volatility. A non-positive value triggers automatic
                derivation from the mean rolling volatility.
            return_threshold: Annualized return threshold separating
                sideways from trending markets. A non-positive value triggers
                automatic derivation from the mean rolling return.
            periods_per_year: Trading periods per year used to annualize
                volatility and return (default 252 for daily data).

        """
        self.window = window
        self.vol_threshold = vol_threshold
        self.return_threshold = return_threshold
        self.periods_per_year = periods_per_year

    def detect(self, prices: pd.Series) -> RegimeResult:
        """Classify regimes over a price or equity series.

        The input may be any iterable convertible to a :class:`pandas.Series`.
        When the series is too short to compute returns (fewer than two
        points) or when the returns are entirely non-finite, an empty
        :class:`RegimeResult` is returned with ``current_regime`` set to
        :attr:`Regime.UNKNOWN`.

        Args:
            prices: Price or equity curve series indexed by time. Any
                non-Series input is converted to a ``pd.Series``.

        Returns:
            A :class:`RegimeResult` containing the labeled segments and
            summary statistics.

        Examples:
            >>> import pandas as pd
            >>> from quant_trading.regime.detector import RegimeDetector
            >>> prices = pd.Series(
            ...     [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            ...     index=pd.date_range("2024-01-01", periods=6, freq="D"),
            ... )
            >>> result = RegimeDetector(window=2, vol_threshold=10.0, return_threshold=10.0).detect(prices)
            >>> result.n_segments
            1
            >>> result.current_regime.value
            'sideways_low_vol'

        """
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
        """Build regime segments from rolling statistics and thresholds.

        First labels every bar with a :class:`Regime` (or ``None`` for bars
        where the rolling statistics are non-finite), then merges consecutive
        identical labels into :class:`RegimeSegment` objects.

        Args:
            prices: Full price series indexed by time.
            returns: Daily returns derived from ``prices``.
            rolling_vol: Rolling annualized volatility series.
            rolling_mean: Rolling annualized mean return series.
            vol_threshold: Volatility threshold separating low/high vol.
            ret_threshold: Return threshold separating sideways/trending.

        Returns:
            Ordered list of :class:`RegimeSegment` objects.

        """
        labels = self._label_series(rolling_vol, rolling_mean, vol_threshold, ret_threshold)
        return self._merge_segments(labels, prices, returns, rolling_vol)

    def _label_series(
        self,
        rolling_vol: pd.Series,
        rolling_mean: pd.Series,
        vol_threshold: float,
        ret_threshold: float,
    ) -> list[Regime | None]:
        """Classify each bar into a :class:`Regime` label.

        For every position in the rolling statistics, the volatility and mean
        return are compared against the configured thresholds to derive a
        direction (bull/bear/sideways) and a volatility level (high/low).
        Bars whose rolling statistics are non-finite are labeled ``None`` so
        they are skipped during segment merging.

        Args:
            rolling_vol: Rolling annualized volatility series.
            rolling_mean: Rolling annualized mean return series.
            vol_threshold: Volatility threshold separating low/high vol.
            ret_threshold: Return threshold separating sideways/trending.

        Returns:
            Ordered list of :class:`Regime` labels (or ``None`` for bars that
            could not be classified), one entry per bar in the rolling series.

        """
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
        """Merge consecutive identical labels into :class:`RegimeSegment` objects.

        Runs of ``None`` labels are skipped, so a segment only spans bars that
        received a concrete :class:`Regime`. Each maximal run of the same
        label becomes a single segment; the segment's start/end positions and
        volatility/return statistics are computed by :meth:`_make_segment`.

        Args:
            labels: Ordered per-bar labels (or ``None``) from
                :meth:`_label_series`.
            prices: Full price series indexed by time.
            returns: Daily returns derived from ``prices``.
            rolling_vol: Rolling annualized volatility series.

        Returns:
            Ordered list of :class:`RegimeSegment` objects.

        """
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
        """Build a single :class:`RegimeSegment` from a label range.

        Labels are indexed into the rolling-statistics series, which corresponds
        to ``prices.index[1:]`` (since ``pct_change`` drops the first bar). A
        segment spanning labels ``[start_idx, end_idx)`` therefore covers price
        bars ``[start_idx + 1, end_idx]``. The segment's start/end timestamps,
        mean volatility, and percentage return are derived from those bars.

        Args:
            regime: The :class:`Regime` label assigned to the segment.
            start_idx: Inclusive start index of the label range.
            end_idx: Exclusive end index of the label range.
            prices: Full price series indexed by time.
            returns: Daily returns derived from ``prices``.
            rolling_vol: Rolling annualized volatility series.

        Returns:
            A :class:`RegimeSegment` describing the labeled span.

        """
        # Label i corresponds to rolling stats computed on returns, whose index
        # is prices.index[1:] (pct_change drops the first bar). So label i is the
        # regime of price bar (i + 1). A segment spanning labels [start_idx, end_idx)
        # therefore covers price bars [start_idx + 1, end_idx].
        n_prices = len(prices)
        seg_start_idx = min(start_idx + 1, n_prices - 1)
        seg_end_idx = min(end_idx, n_prices - 1)
        price_start = prices.index[seg_start_idx]
        price_end = prices.index[seg_end_idx]
        seg_vol = rolling_vol.iloc[start_idx:end_idx]
        ret_pct = (
            float((prices.iloc[seg_end_idx] / prices.iloc[seg_start_idx] - 1) * 100)
            if seg_end_idx > seg_start_idx and seg_end_idx < n_prices
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
    """Detect market regimes over a price series using default thresholds.

    Convenience wrapper around :class:`RegimeDetector` that constructs a
    detector with the given parameters and runs :meth:`RegimeDetector.detect`.

    Args:
        prices: Price or equity curve series indexed by time. Any
            non-Series input is converted to a ``pd.Series``.
        window: Number of trailing returns used for the rolling
            statistics (default 20).
        vol_threshold: Annualized volatility threshold separating low and
            high volatility. A non-positive value triggers automatic
            derivation from the mean rolling volatility.
        return_threshold: Annualized return threshold separating sideways
            from trending markets. A non-positive value triggers automatic
            derivation from the mean rolling return.

    Returns:
        A :class:`RegimeResult` containing the labeled segments and summary
        statistics.

    Examples:
        >>> import pandas as pd
        >>> from quant_trading.regime.detector import detect_regimes
        >>> prices = pd.Series(
        ...     [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        ...     index=pd.date_range("2024-01-01", periods=6, freq="D"),
        ... )
        >>> result = detect_regimes(prices, window=2, vol_threshold=10.0, return_threshold=10.0)
        >>> result.n_segments
        1
        >>> result.current_regime.value
        'sideways_low_vol'

    """
    detector = RegimeDetector(
        window=window, vol_threshold=vol_threshold, return_threshold=return_threshold
    )
    return detector.detect(prices)
