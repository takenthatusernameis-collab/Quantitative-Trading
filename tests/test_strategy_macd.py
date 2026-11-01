"""Tests for MACD strategy validation branches."""

from quant_trading.strategies.examples import MACDStrategy


class TestMACDValidation:
    def test_validate_fast_period_must_be_positive(self):
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        strategy.fast_period = 0
        try:
            strategy.validate_parameters()
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "fast_period must be positive" in str(exc)

        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        strategy.fast_period = -1
        try:
            strategy.validate_parameters()
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "fast_period must be positive" in str(exc)

    def test_validate_slow_period_must_be_positive(self):
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        strategy.slow_period = 0
        try:
            strategy.validate_parameters()
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "slow_period must be positive" in str(exc)

        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        strategy.slow_period = -5
        try:
            strategy.validate_parameters()
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "slow_period must be positive" in str(exc)

    def test_validate_signal_period_must_be_positive(self):
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        strategy.signal_period = 0
        try:
            strategy.validate_parameters()
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "signal_period must be positive" in str(exc)

        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        strategy.signal_period = -2
        try:
            strategy.validate_parameters()
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "signal_period must be positive" in str(exc)

    def test_validate_fast_period_must_be_less_than_slow_period(self):
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        strategy.fast_period = 26
        strategy.slow_period = 26
        try:
            strategy.validate_parameters()
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "fast_period must be less than slow_period" in str(exc)

        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        strategy.fast_period = 30
        strategy.slow_period = 26
        try:
            strategy.validate_parameters()
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "fast_period must be less than slow_period" in str(exc)
