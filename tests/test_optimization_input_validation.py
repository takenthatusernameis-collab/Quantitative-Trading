"""Regression tests for per-call input validation in the optimization API.

These tests lock in the contract that the public optimization entry points
surface a clear ``ValueError``/``TypeError`` (never an opaque third-party
error such as ``AttributeError``) when fed a corrupted or wrong-typed
per-call argument:

* :func:`quant_trading.optimization.sensitivity.prepare_sensitivity_data`
  (and :func:`~quant_trading.optimization.sensitivity.generate_sensitivity_report_html`,
  which delegates to it) must reject a non-dict result entry or a non-dict
  ``params`` value with a clear ``TypeError`` instead of leaking an
  ``AttributeError`` from ``.items()``/``in`` on the wrong type.
* :meth:`quant_trading.optimization.base.OptimizationResult.get_top_n` must
  reject a negative ``n`` with ``ValueError`` (previously it silently dropped
  results from the end of the sorted list) and a non-integer ``n`` with
  ``TypeError``.
"""

from __future__ import annotations

from typing import Any

import pytest

from quant_trading.optimization.base import OptimizationResult
from quant_trading.optimization.sensitivity import (
    generate_sensitivity_report_html,
    prepare_sensitivity_data,
)


class TestPrepareSensitivityDataMalformed:
    """prepare_sensitivity_data rejects corrupted results with clear errors."""

    @pytest.mark.parametrize(
        "bad_params",
        [5, None, [1, 2], "ab", 3.5, True, object()],
        ids=["int", "none", "list", "str", "float", "bool", "object"],
    )
    def test_non_dict_params_raises_type_error(self, bad_params: Any) -> None:
        """A result whose ``params`` is not a dict raises TypeError, not AttributeError."""
        with pytest.raises(TypeError):
            prepare_sensitivity_data([{"params": bad_params, "score": 1.0}])

    @pytest.mark.parametrize(
        "bad_result",
        [5, 3.5, "x", None, True, [1, 2]],
        ids=["int", "float", "str", "none", "bool", "list"],
    )
    def test_non_dict_result_raises_type_error(self, bad_result: Any) -> None:
        """A non-dict entry in ``all_results`` raises TypeError, not AttributeError."""
        with pytest.raises(TypeError):
            prepare_sensitivity_data([bad_result])

    def test_dict_without_params_is_skipped(self) -> None:
        """A dict entry without a ``params`` key is still skipped (unchanged)."""
        df = prepare_sensitivity_data([{"score": 1.0}, {"params": {"a": 1}, "score": 2.0}])
        assert len(df) == 1
        assert df["a"].tolist() == [1]

    def test_valid_results_still_work(self) -> None:
        """Well-formed results are unaffected by the new validation."""
        df = prepare_sensitivity_data(
            [
                {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
                {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
            ]
        )
        assert len(df) == 2
        assert df["score"].tolist() == [1.5, 2.0]

    def test_empty_results_return_empty_frame(self) -> None:
        """An empty result list still short-circuits to an empty DataFrame."""
        assert prepare_sensitivity_data([]).empty


class TestGenerateSensitivityReportHtmlMalformed:
    """generate_sensitivity_report_html surfaces the same clear error."""

    def test_non_dict_params_raises_type_error(self) -> None:
        """A corrupted ``params`` propagates a clear TypeError, not AttributeError."""
        with pytest.raises(TypeError):
            generate_sensitivity_report_html([{"params": 5, "score": 1.0}])

    def test_non_dict_result_raises_type_error(self) -> None:
        """A non-dict result entry propagates a clear TypeError, not AttributeError."""
        bad_results: Any = [5]
        with pytest.raises(TypeError):
            generate_sensitivity_report_html(bad_results)


class TestGetTopNValidation:
    """OptimizationResult.get_top_n validates its per-call count argument."""

    @pytest.fixture
    def result(self) -> OptimizationResult:
        return OptimizationResult(
            best_params={},
            best_score=3.0,
            all_results=[{"score": 1.0}, {"score": 3.0}, {"score": 2.0}],
        )

    def test_negative_n_raises_value_error(self, result: OptimizationResult) -> None:
        """A negative ``n`` raises ValueError instead of silently slicing."""
        with pytest.raises(ValueError):
            result.get_top_n(-1)

    @pytest.mark.parametrize("bad_n", ["x", 1.5, True, None], ids=["str", "float", "bool", "none"])
    def test_non_integer_n_raises_type_error(self, result: OptimizationResult, bad_n: Any) -> None:
        """A non-integer ``n`` raises a clear TypeError."""
        with pytest.raises(TypeError):
            result.get_top_n(bad_n)

    def test_zero_returns_empty_list(self, result: OptimizationResult) -> None:
        """``n == 0`` returns an empty list (valid boundary)."""
        assert result.get_top_n(0) == []

    def test_valid_n_returns_top_scores(self, result: OptimizationResult) -> None:
        """A valid ``n`` returns the highest-scoring results in order."""
        top = result.get_top_n(2)
        assert [entry["score"] for entry in top] == [3.0, 2.0]

    def test_n_larger_than_results_returns_all(self, result: OptimizationResult) -> None:
        """An ``n`` beyond the number of results returns every result."""
        assert len(result.get_top_n(99)) == 3
