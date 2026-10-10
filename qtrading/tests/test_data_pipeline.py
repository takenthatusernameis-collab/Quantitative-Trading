from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from qtrading.data import (
    OHLCV,
    DataQualityChecker,
    DataStorage,
    DataValidator,
    Exchange,
    Timeframe,
)


def make_ohlcv(
    price: Decimal = Decimal("50000"),
    volume: Decimal = Decimal("100"),
    ts_offset: int = 0,
) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=ts_offset),
        open=price,
        high=price + Decimal("100"),
        low=price - Decimal("100"),
        close=price,
        volume=volume,
        symbol="BTC/USDT",
        timeframe=Timeframe.H1,
        exchange=Exchange.BINANCE,
    )


class TestDataValidator:
    def test_valid_ohlcv(self):
        validator = DataValidator()
        ohlcv = make_ohlcv()
        result = validator.validate_ohlcv(ohlcv)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_ohlcv_negative_price(self):
        validator = DataValidator()
        ohlcv = make_ohlcv(price=Decimal("-100"))
        result = validator.validate_ohlcv(ohlcv)
        assert not result.is_valid
        assert any("positive" in e.lower() for e in result.errors)

    def test_invalid_ohlcv_high_lt_low(self):
        validator = DataValidator()
        ohlcv = OHLCV(
            timestamp=datetime.now(UTC),
            open=Decimal("100"),
            high=Decimal("50"),
            low=Decimal("200"),
            close=Decimal("100"),
            volume=Decimal("10"),
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            exchange=Exchange.BINANCE,
        )
        result = validator.validate_ohlcv(ohlcv)
        assert not result.is_valid

    def test_validate_sequence_valid(self):
        validator = DataValidator()
        ohlcvs = [make_ohlcv(ts_offset=i) for i in range(10)]
        result = validator.validate_sequence(ohlcvs)
        assert result.is_valid

    def test_validate_sequence_gap_warning(self):
        validator = DataValidator(max_gap_pct=Decimal("0.01"))
        candles = [
            make_ohlcv(price=Decimal("50000"), ts_offset=0),
            make_ohlcv(price=Decimal("60000"), ts_offset=1),
        ]
        result = validator.validate_sequence(candles)
        assert result.is_valid
        assert any("gap" in w.lower() for w in result.warnings)


class TestDataQualityChecker:
    def test_analyze_empty(self):
        checker = DataQualityChecker()
        result = checker.analyze([])
        assert result["count"] == 0
        assert result["completeness"] == 0.0

    def test_analyze_with_data(self):
        checker = DataQualityChecker()
        ohlcvs = [make_ohlcv(volume=Decimal("100"), ts_offset=i) for i in range(5)]
        result = checker.analyze(ohlcvs)
        assert result["count"] == 5
        assert result["completeness"] == 1.0
        assert result["price_range"]["min"] == 50000.0

    def test_analyze_zero_volume(self):
        checker = DataQualityChecker()
        ohlcvs = [
            make_ohlcv(volume=Decimal("100"), ts_offset=0),
            make_ohlcv(volume=Decimal("0"), ts_offset=1),
        ]
        result = checker.analyze(ohlcvs)
        assert result["zero_volume_candles"] == 1
        assert result["completeness"] == 0.5


class TestDataStorage:
    @pytest.fixture
    def storage(self, tmp_path):
        db_path = tmp_path / "test_market_data.db"
        return DataStorage(db_path=str(db_path))

    def test_save_and_load_ohlcv(self, storage):
        ohlcvs = [make_ohlcv(ts_offset=i) for i in range(5)]
        count = storage.save_ohlcv(ohlcvs)
        assert count == 5

        loaded = storage.load_ohlcv("BTC/USDT", Timeframe.H1, Exchange.BINANCE)
        assert len(loaded) == 5
        assert loaded[0].close == Decimal("50000")

    def test_load_with_limit(self, storage):
        ohlcvs = [make_ohlcv(ts_offset=i) for i in range(10)]
        storage.save_ohlcv(ohlcvs)
        loaded = storage.load_ohlcv("BTC/USDT", Timeframe.H1, Exchange.BINANCE, limit=3)
        assert len(loaded) == 3

    def test_load_with_since(self, storage):
        ohlcvs = [make_ohlcv(ts_offset=i) for i in range(10)]
        storage.save_ohlcv(ohlcvs)
        since = datetime(2024, 1, 1, 5, tzinfo=UTC)
        loaded = storage.load_ohlcv("BTC/USDT", Timeframe.H1, Exchange.BINANCE, since=since)
        assert len(loaded) == 5

    def test_delete_ohlcv(self, storage):
        ohlcvs = [make_ohlcv(ts_offset=i) for i in range(5)]
        storage.save_ohlcv(ohlcvs)
        count = storage.delete_ohlcv("BTC/USDT", Timeframe.H1, Exchange.BINANCE)
        assert count == 5
        loaded = storage.load_ohlcv("BTC/USDT", Timeframe.H1, Exchange.BINANCE)
        assert len(loaded) == 0

    def test_get_available_symbols(self, storage):
        ohlcvs = [make_ohlcv(ts_offset=i) for i in range(3)]
        storage.save_ohlcv(ohlcvs)
        symbols = storage.get_available_symbols()
        assert "BTC/USDT" in symbols

    def test_idempotent_save(self, storage):
        ohlcvs = [make_ohlcv(ts_offset=i) for i in range(3)]
        storage.save_ohlcv(ohlcvs)
        storage.save_ohlcv(ohlcvs)
        loaded = storage.load_ohlcv("BTC/USDT", Timeframe.H1, Exchange.BINANCE)
        assert len(loaded) == 3
