"""Data validation and quality checks for OHLCV data."""

from dataclasses import dataclass
from decimal import Decimal

from qtrading.data.models import OHLCV, Timeframe


@dataclass
class ValidationResult:
    """Result of a data validation check."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]


class DataValidator:
    """Validates OHLCV data for quality and consistency."""

    def __init__(
        self,
        max_price_deviation: Decimal = Decimal("0.5"),
        min_volume: Decimal = Decimal("0"),
        max_gap_pct: Decimal = Decimal("0.2"),
    ):
        self.max_price_deviation = max_price_deviation
        self.min_volume = min_volume
        self.max_gap_pct = max_gap_pct

    def validate_ohlcv(self, ohlcv: OHLCV) -> ValidationResult:
        """Validate a single OHLCV candle."""
        errors = []
        warnings = []

        if ohlcv.open <= 0:
            errors.append(f"Open price must be positive, got {ohlcv.open}")
        if ohlcv.high <= 0:
            errors.append(f"High price must be positive, got {ohlcv.high}")
        if ohlcv.low <= 0:
            errors.append(f"Low price must be positive, got {ohlcv.low}")
        if ohlcv.close <= 0:
            errors.append(f"Close price must be positive, got {ohlcv.close}")

        if ohlcv.high < ohlcv.low:
            errors.append(f"High ({ohlcv.high}) cannot be less than low ({ohlcv.low})")
        if ohlcv.high < ohlcv.open:
            errors.append(f"High ({ohlcv.high}) cannot be less than open ({ohlcv.open})")
        if ohlcv.high < ohlcv.close:
            errors.append(f"High ({ohlcv.high}) cannot be less than close ({ohlcv.close})")
        if ohlcv.low > ohlcv.open:
            errors.append(f"Low ({ohlcv.low}) cannot be greater than open ({ohlcv.open})")
        if ohlcv.low > ohlcv.close:
            errors.append(f"Low ({ohlcv.low}) cannot be greater than close ({ohlcv.close})")

        if ohlcv.volume < self.min_volume:
            warnings.append(f"Volume {ohlcv.volume} below minimum {self.min_volume}")

        if ohlcv.volume == 0:
            warnings.append("Zero volume candle detected")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_sequence(self, ohlcvs: list[OHLCV]) -> ValidationResult:
        """Validate a sequence of OHLCV candles for continuity."""
        all_errors = []
        all_warnings = []

        if not ohlcvs:
            return ValidationResult(is_valid=True, errors=[], warnings=[])

        for i, candle in enumerate(ohlcvs):
            result = self.validate_ohlcv(candle)
            if result.errors:
                all_errors.extend([f"Candle {i}: {e}" for e in result.errors])
            if result.warnings:
                all_warnings.extend([f"Candle {i}: {w}" for w in result.warnings])

        for i in range(1, len(ohlcvs)):
            prev_close = ohlcvs[i - 1].close
            curr_open = ohlcvs[i].open
            gap = abs(curr_open - prev_close) / prev_close
            if gap > self.max_gap_pct:
                all_warnings.append(
                    f"Price gap between candle {i - 1} (close={prev_close}) "
                    f"and candle {i} (open={curr_open}): {gap:.2%}"
                )

            if ohlcvs[i].timestamp <= ohlcvs[i - 1].timestamp:
                all_errors.append(
                    f"Non-increasing timestamps at candle {i}: "
                    f"{ohlcvs[i].timestamp} <= {ohlcvs[i - 1].timestamp}"
                )

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings,
        )

    def check_data_quality(
        self,
        ohlcvs: list[OHLCV],
        expected_timeframe: Timeframe | None = None,
    ) -> ValidationResult:
        """Perform comprehensive data quality checks."""
        result = self.validate_sequence(ohlcvs)

        if not result.is_valid:
            return result

        duplicates = 0
        seen_timestamps = set()
        for ohlcv in ohlcvs:
            ts = ohlcv.timestamp.isoformat()
            if ts in seen_timestamps:
                duplicates += 1
            seen_timestamps.add(ts)

        if duplicates > 0:
            result.warnings.append(f"Found {duplicates} duplicate candles")

        if expected_timeframe and len(ohlcvs) > 1:
            expected_gap = expected_timeframe.to_seconds()
            for i in range(1, len(ohlcvs)):
                actual_gap = (ohlcvs[i].timestamp - ohlcvs[i - 1].timestamp).total_seconds()
                if actual_gap != expected_gap:
                    result.warnings.append(
                        f"Unexpected timeframe at candle {i}: "
                        f"expected {expected_gap}s gap, got {actual_gap}s"
                    )
                    break

        return result


class DataQualityChecker:
    """Checks data quality and reports statistics."""

    def analyze(self, ohlcvs: list[OHLCV]) -> dict:
        """Analyze OHLCV data and return quality statistics."""
        if not ohlcvs:
            return {
                "count": 0,
                "completeness": 0.0,
                "price_range": None,
                "volume_stats": None,
            }

        prices = [float(c.close) for c in ohlcvs]
        volumes = [float(c.volume) for c in ohlcvs]

        zeros = sum(1 for v in volumes if v == 0)
        completeness = (len(volumes) - zeros) / len(volumes) if volumes else 0.0

        return {
            "count": len(ohlcvs),
            "completeness": completeness,
            "price_range": {
                "min": min(prices),
                "max": max(prices),
                "mean": sum(prices) / len(prices),
            },
            "volume_stats": {
                "total": sum(volumes),
                "mean": sum(volumes) / len(volumes) if volumes else 0,
                "min": min(volumes) if volumes else 0,
                "max": max(volumes) if volumes else 0,
            },
            "zero_volume_candles": zeros,
        }
