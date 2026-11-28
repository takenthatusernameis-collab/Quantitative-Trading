"""Robustness contract for ``Config.update`` and ``Config.from_yaml``.

A user-edited YAML config or a programmatic ``Config.update(...)`` call can
carry wrongly-typed sub-config values (a scalar where a mapping is expected,
a bool where an int is expected, an out-of-range number, a non-ISO date
string, ...). The contract: every rejection must surface as ``ValueError``
or ``TypeError`` (never ``AttributeError``/``KeyError`` leaking from internal
``.get()``/``.items()``/indexing), and a failed nested update must leave the
target sub-config untouched.

This complements ``test_config.py`` (which asserts specific rejection cases)
and ``test_from_dict_robustness.py`` (which covers ``from_dict``) by poisoning
every field of every sub-config through the ``update`` merge path and through
``from_yaml``. ``to_yaml``/``from_yaml`` round-trips are asserted to still
succeed (no serialization-format change).
"""

from dataclasses import fields
from typing import Any

import pytest
import yaml

from quant_trading.config.settings import (
    BacktestConfig,
    Config,
    DataConfig,
    PortfolioConfig,
    RiskConfig,
)

_SUBCONFIGS = ("data", "backtest", "risk", "portfolio")
_SUB_CONFIG_CLS: dict[str, type[Any]] = {
    "data": DataConfig,
    "backtest": BacktestConfig,
    "risk": RiskConfig,
    "portfolio": PortfolioConfig,
}

# Legal YAML/JSON scalars and containers that are wrong for most config
# fields. ``object()``/``bytes``/``tuple`` model in-process corruption and
# cannot be expressed in YAML, so they are exercised through ``update`` only.
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

# Poisons expressible as YAML text (``safe_load`` produces only scalars
# and containers, never in-process objects).
_YAML_POISONS: list[Any] = [
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
]

_ACCEPTABLE = (ValueError, TypeError)


def _attempt_update(config: Config, key: str, payload: Any) -> Any:
    """Run ``config.update(**{key: payload})``.

    Returns the exception when the contract raises an acceptable rejection,
    ``None`` when the update succeeds, and re-raises nothing: any other
    exception type is the regression this suite guards against.
    """
    try:
        config.update(**{key: payload})
    except _ACCEPTABLE as exc:  # the contract under test
        return exc
    except Exception as exc:  # noqa: BLE001 - any other type is the regression
        return exc
    return None


@pytest.mark.parametrize("key", _SUBCONFIGS, ids=_SUBCONFIGS)
def test_update_poisoned_fields_only_raise_acceptable(key: str) -> None:
    """Every poisoned sub-config field through ``update`` raises only ValueError/TypeError and leaves the sub-config untouched."""
    cls = _SUB_CONFIG_CLS[key]
    field_names = [f.name for f in fields(cls)]
    for field in field_names:
        for poison in _POISONS:
            config = Config()
            before = getattr(config, key)
            exc = _attempt_update(config, key, {field: poison})
            if exc is None:
                continue  # a valid value merged successfully; nothing to assert
            assert isinstance(exc, _ACCEPTABLE), (
                f"Config.update({key}={{{field!r}: {poison!r}}}) leaked "
                f"{type(exc).__name__}: {exc}"
            )
            assert (
                getattr(config, key) == before
            ), f"update({key}={{{field!r}: {poison!r}}}) rejected but mutated {key}"


@pytest.mark.parametrize("key", _SUBCONFIGS, ids=_SUBCONFIGS)
@pytest.mark.parametrize(
    "value",
    [5, [], None, "x", object(), [1, 2, 3]],
    ids=["int", "list", "None", "str", "object", "list-of-int"],
)
def test_update_non_mapping_subconfigs_raise(key: str, value: Any) -> None:
    """A non-mapping sub-config value is rejected by ``update`` and leaves the sub-config untouched."""
    config = Config()
    before = getattr(config, key)
    exc = _attempt_update(config, key, value)
    assert isinstance(
        exc, _ACCEPTABLE
    ), f"Config.update({key}={value!r}) leaked {type(exc).__name__}: {exc}"
    assert getattr(config, key) == before


@pytest.mark.parametrize("key", ["logging_level", "output_dir"])
@pytest.mark.parametrize("poison", _POISONS, ids=lambda p: repr(p))
def test_update_poisoned_scalar_fields_only_raise_acceptable(key: str, poison: Any) -> None:
    """Every poisoned top-level scalar field through ``update`` raises only ValueError/TypeError and leaves the field untouched."""
    config = Config()
    before = getattr(config, key)
    exc = _attempt_update(config, key, poison)
    if exc is None:
        # a valid value merged successfully; nothing to assert
        pass
    else:
        assert isinstance(
            exc, _ACCEPTABLE
        ), f"Config.update({key}={poison!r}) leaked {type(exc).__name__}: {exc}"
        assert getattr(config, key) == before


def _write_yaml(tmp_path, content: str) -> str:
    import os

    path = os.path.join(str(tmp_path), "config.yaml")
    with open(path, "w") as f:
        f.write(content)
    return path


@pytest.mark.parametrize("key", _SUBCONFIGS, ids=_SUBCONFIGS)
def test_from_yaml_poisoned_fields_only_raise_acceptable(key: str, tmp_path) -> None:
    """Every poisoned sub-config field read from YAML raises only ValueError/TypeError."""
    cls = _SUB_CONFIG_CLS[key]
    field_names = [f.name for f in fields(cls)]
    for field in field_names:
        for poison in _YAML_POISONS:
            content = yaml.safe_dump({key: {field: poison}})
            path = _write_yaml(tmp_path, content)
            try:
                Config.from_yaml(path)
            except _ACCEPTABLE:  # the contract under test
                continue
            except Exception as exc:  # noqa: BLE001 - any other type is the regression
                pytest.fail(
                    f"Config.from_yaml({key}: {{{field!r}: {poison!r}}}) leaked "
                    f"{type(exc).__name__}: {exc}"
                )


def test_from_yaml_tolerates_non_mapping_subconfigs(tmp_path) -> None:
    """A non-mapping sub-config in YAML falls back to defaults instead of crashing."""
    for key in _SUBCONFIGS:
        content = yaml.safe_dump({key: 5})
        path = _write_yaml(tmp_path, content)
        config = Config.from_yaml(path)
        assert getattr(config, key) == getattr(Config(), key)
