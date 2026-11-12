"""Tests for ParabolicSARStrategy validation branches."""

import pytest

from quant_trading.strategies.examples import ParabolicSARStrategy


def _valid_sar():
    return ParabolicSARStrategy(step=0.02, max_step=0.2)


def test_validate_step_must_be_positive():
    s = _valid_sar()
    s.step = 0
    with pytest.raises(ValueError, match="step must be positive"):
        s.validate_parameters()


def test_validate_max_step_must_be_positive():
    s = _valid_sar()
    s.max_step = 0
    with pytest.raises(ValueError, match="max_step must be positive"):
        s.validate_parameters()


def test_validate_step_non_finite_rejected():
    s = _valid_sar()
    s.step = float("nan")
    with pytest.raises(ValueError, match="step must be positive"):
        s.validate_parameters()

    s = _valid_sar()
    s.step = float("inf")
    with pytest.raises(ValueError, match="step must be positive"):
        s.validate_parameters()

    s = _valid_sar()
    s.step = float("-inf")
    with pytest.raises(ValueError, match="step must be positive"):
        s.validate_parameters()


def test_validate_max_step_non_finite_rejected():
    s = _valid_sar()
    s.max_step = float("nan")
    with pytest.raises(ValueError, match="max_step must be positive"):
        s.validate_parameters()

    s = _valid_sar()
    s.max_step = float("inf")
    with pytest.raises(ValueError, match="max_step must be positive"):
        s.validate_parameters()

    s = _valid_sar()
    s.max_step = float("-inf")
    with pytest.raises(ValueError, match="max_step must be positive"):
        s.validate_parameters()


def test_validate_step_must_be_lte_max_step():
    s = _valid_sar()
    s.step = 0.3
    s.max_step = 0.2
    with pytest.raises(ValueError, match="step must be less than or equal to max_step"):
        s.validate_parameters()


def test_constructor_calls_validate():
    # nan values should be rejected at construction time
    with pytest.raises(ValueError, match="step must be positive"):
        ParabolicSARStrategy(step=float("nan"), max_step=0.2)

    with pytest.raises(ValueError, match="step must be positive"):
        ParabolicSARStrategy(step=float("inf"), max_step=0.2)

    with pytest.raises(ValueError, match="step must be positive"):
        ParabolicSARStrategy(step=-0.01, max_step=0.2)

    with pytest.raises(ValueError, match="max_step must be positive"):
        ParabolicSARStrategy(step=0.02, max_step=float("nan"))

    with pytest.raises(ValueError, match="max_step must be positive"):
        ParabolicSARStrategy(step=0.02, max_step=float("inf"))

    with pytest.raises(ValueError, match="max_step must be positive"):
        ParabolicSARStrategy(step=0.02, max_step=-0.1)

    with pytest.raises(ValueError, match="step must be less than or equal to max_step"):
        ParabolicSARStrategy(step=0.3, max_step=0.2)

    # Valid construction should succeed
    s = ParabolicSARStrategy(step=0.02, max_step=0.2)
    assert s.step == 0.02
    assert s.max_step == 0.2


def test_validate_accepts_valid_values():
    s = _valid_sar()
    s.validate_parameters()  # Should not raise

    s = ParabolicSARStrategy(step=0.01, max_step=0.2)
    s.validate_parameters()  # Should not raise

    s = ParabolicSARStrategy(step=0.02, max_step=0.02)
    s.validate_parameters()  # Should not raise (equal is ok)