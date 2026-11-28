"""Robustness contract for ``from_dict`` against malformed payloads.

A serialized cache or user-edited config can be corrupted: a value that should
be a mapping may be a scalar or list, a list of mappings may contain scalars,
a required key may be missing, or a timestamp may be garbage. ``from_dict``
must never leak an unexpected exception type (e.g. ``AttributeError`` from
calling ``.items()``/``.get()`` on a non-dict, or ``KeyError`` for a missing
required field). The only acceptable rejections are ``ValueError``/``TypeError``
(or a successful reconstruction with safe defaults).

This test deterministically feeds every serializable dataclass's ``from_dict``
a battery of wrong-typed payloads (each field poisoned in turn, plus an empty
mapping and an all-poisoned mapping) and asserts the contract holds. It
complements ``test_serialization_roundtrip.py`` (which proves the happy-path
round-trip) by guarding the corrupted-input path.
"""

import dataclasses
import importlib
import pkgutil
from typing import Any

import pytest

import quant_trading

# Values that are valid JSON/YAML scalars or containers but wrong for most
# fields. ``object()``/``bytes``/``tuple`` model in-process corruption.
_POISONS: list[Any] = [
    None,
    True,
    False,
    0,
    1,
    -1,
    3.14,
    float("nan"),
    float("inf"),
    "",
    "not-a-date",
    "2024-13-45T99:99:99",
    [],
    [1, 2, 3],
    {},
    {"nested": {"deep": [1, 2]}},
    object(),
    b"bytes",
    (1, 2),
]

_ACCEPTABLE = (ValueError, TypeError)


def _from_dict_classes() -> list[type]:
    """Discover every dataclass defined in ``quant_trading/`` exposing ``from_dict``.

    Mirrors the discovery in ``test_serialization_roundtrip.py``: classes that
    are imported (not defined) in a module are skipped so each is checked once,
    where it is defined.
    """
    found: list[type] = []
    seen: set[type] = set()
    for module_info in pkgutil.walk_packages(quant_trading.__path__, prefix="quant_trading."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception:  # noqa: BLE001, S112 - an unimportable module is a separate failure
            continue
        for obj in vars(module).values():
            if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
                continue
            if getattr(obj, "__module__", None) != module_info.name:
                continue
            if "from_dict" not in obj.__dict__ or obj in seen:
                continue
            seen.add(obj)
            found.append(obj)
    return found


def _payloads(cls: type) -> list[tuple[str, dict[str, Any]]]:
    """Build malformed-but-top-level-dict payloads for ``cls``.

    The top level is always a dict (the realistic corruption shape for a
    JSON/YAML cache); individual fields are replaced with each poison value.
    """
    field_names = [f.name for f in dataclasses.fields(cls)]
    cases: list[tuple[str, dict[str, Any]]] = [("empty", {})]
    for name in field_names:
        for i, poison in enumerate(_POISONS):
            cases.append((f"{name}=poison{i}", {name: poison}))
    cases.append(("all-poisoned", {name: object() for name in field_names}))
    return cases


@pytest.mark.parametrize(
    "cls",
    _from_dict_classes(),
    ids=[cls.__name__ for cls in _from_dict_classes()],
)
def test_from_dict_never_leaks_unexpected_exception(cls: type) -> None:
    """``from_dict`` must reject malformed input only via ValueError/TypeError."""
    for label, payload in _payloads(cls):
        try:
            cls.from_dict(payload)  # type: ignore[attr-defined]
        except _ACCEPTABLE:
            continue
        except Exception as exc:  # noqa: BLE001 - any other type is the regression
            pytest.fail(
                f"{cls.__module__}.{cls.__name__}.from_dict({label!r}) raised "
                f"{type(exc).__name__}: {exc}"
            )


def test_config_from_dict_tolerates_non_mapping_subconfigs() -> None:
    """Config.from_dict must not crash when a sub-config value is not a mapping.

    Regression: ``data.get("data", {})`` was passed straight to
    ``DataConfig.from_dict``, which calls ``.items()`` -> ``AttributeError``
    for a scalar/list sub-config (a realistic corrupted-YAML shape). Each
    non-mapping sub-config now falls back to that sub-config's defaults.
    """
    from quant_trading.config.settings import Config

    cfg = Config.from_dict({"data": 5, "backtest": "x", "risk": [1], "portfolio": None})
    assert cfg.data.provider == Config().data.provider
    assert cfg.backtest == Config().backtest
    assert cfg.risk == Config().risk
    assert cfg.portfolio == Config().portfolio


def test_market_data_from_dict_tolerates_non_mapping_data_field() -> None:
    """MarketData.from_dict must not crash when ``data`` is not a mapping.

    Regression: ``payload = data.get("data") or {}`` kept a truthy non-dict
    (e.g. ``[1, 2, 3]``), then ``payload.get(...)`` raised ``AttributeError``.
    """
    from quant_trading.data.providers import MarketData

    md = MarketData.from_dict({"symbol": "AAPL", "data": [1, 2, 3]})
    assert md.symbol == "AAPL"
    assert md.data.empty


def test_fetch_result_from_dict_tolerates_non_mapping_containers() -> None:
    """FetchResult.from_dict must not crash on non-mapping data/errors fields."""
    from quant_trading.data.providers import FetchResult

    fr = FetchResult.from_dict({"data": [1, 2], "errors": "boom", "missing": "MSFT"})
    assert fr.data == {}
    assert fr.errors == {}
    assert fr.missing == ["M", "S", "F", "T"]


def test_holding_from_dict_requires_symbol() -> None:
    """Holding.from_dict rejects a missing symbol with ValueError, not KeyError."""
    from quant_trading.portfolio.portfolio import Holding

    with pytest.raises(ValueError):
        Holding.from_dict({})


def test_portfolio_from_dict_skips_non_mapping_holdings() -> None:
    """Portfolio.from_dict must not crash on a non-mapping holdings value."""
    from quant_trading.portfolio.portfolio import Portfolio

    p = Portfolio.from_dict({"cash": 100.0, "holdings": {"AAPL": 5, "MSFT": {"symbol": "MSFT"}}})
    assert "AAPL" not in p.holdings
    assert "MSFT" in p.holdings


def test_rebalance_plan_from_dict_tolerates_non_mapping_positions() -> None:
    """_RebalancePlan.from_dict must not crash on a non-mapping positions value."""
    from quant_trading.portfolio.rebalancer import _RebalancePlan

    plan = _RebalancePlan.from_dict({"cash": 1.0, "positions": [1, 2, 3]})
    assert plan.positions == {}


def test_regime_result_from_dict_skips_non_mapping_segments() -> None:
    """RegimeResult.from_dict must not crash on non-mapping segment entries."""
    from quant_trading.regime.detector import Regime, RegimeResult

    result = RegimeResult.from_dict({"segments": ["x", 1, {"regime": "bull_low_vol"}]})
    assert result.n_segments == 1
    assert result.current_regime is Regime.BULL_LOW_VOL


def test_monte_carlo_result_from_dict_tolerates_bad_simulations() -> None:
    """MonteCarloResult.from_dict must not crash on non-dict simulations/metrics."""
    from quant_trading.monte_carlo.simulator import MonteCarloResult

    mc = MonteCarloResult.from_dict(
        {"simulations": ["x", {"total_return_pct": 1.0}], "original_metrics": 5}
    )
    assert len(mc.simulations) == 1
    assert mc.original_metrics == mc.original_metrics.__class__()


def test_parameter_grid_from_dict_tolerates_non_mapping_spaces() -> None:
    """ParameterGrid.from_dict must not crash on a non-mapping spaces value."""
    from quant_trading.optimization.base import ParameterGrid

    grid = ParameterGrid.from_dict({"spaces": {"x": 5, "y": {"name": "y", "values": [1]}}})
    assert "x" not in grid.spaces
    assert "y" in grid.spaces
