"""Core-only import invariant.

The package's *core* functionality — importing the library and running a
backtest — must work when the optional ``reporting`` (matplotlib) and
``bayesian`` (scikit-optimize) extras are **not** installed. The README
documents these as optional extras, so a plain ``pip install -e .`` install
must never fail to import or run the core engine.

These tests exercise that guarantee in a **subprocess** that blocks
``matplotlib`` and ``skopt`` through a meta-path finder, then imports every
core subpackage and runs a deterministic offline backtest. Running in a clean
interpreter means the invariant is checked regardless of whether the optional
extras happen to be installed in the current environment, and it catches a
regression where a core module gains an unguarded top-level ``import
matplotlib`` / ``import skopt``.

This locks into the ordinary ``pytest`` run the same guarantee that a separate
"core-only" CI workflow would enforce.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The child runs in a fresh interpreter with ``matplotlib`` and ``skopt``
# blocked. It imports every core subpackage, runs a small deterministic
# backtest, and checks that chart helpers raise a clean ``ImportError`` (rather
# than crashing) when the extras are missing. It prints a single
# ``CORE_ONLY_JSON {...}`` line to stdout and exits non-zero on any failure.
_CHILD_SCRIPT = r"""
import importlib.abc
import json
import os
import sys

sys.path.insert(0, os.environ["QT_ROOT"])

BLOCKED = ("matplotlib", "skopt")


class _Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(
                "No module named %r" % fullname, name=fullname
            )
        return None


sys.meta_path.insert(0, _Blocker())
for _name in list(sys.modules):
    if _name.split(".")[0] in BLOCKED:
        del sys.modules[_name]

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


# 1. Every core subpackage imports without the optional extras.
import quant_trading  # noqa: E402,F401
import quant_trading.backtest  # noqa: E402,F401
import quant_trading.backtest.report as report  # noqa: E402
import quant_trading.config  # noqa: E402,F401
import quant_trading.data  # noqa: E402,F401
import quant_trading.monte_carlo  # noqa: E402,F401
import quant_trading.optimization as optimization  # noqa: E402
import quant_trading.optimization.sensitivity as sensitivity  # noqa: E402
import quant_trading.portfolio  # noqa: E402,F401
import quant_trading.regime  # noqa: E402,F401
import quant_trading.risk  # noqa: E402,F401
import quant_trading.utils  # noqa: E402,F401

check(
    report.MATPLOTLIB_AVAILABLE is False,
    "report.MATPLOTLIB_AVAILABLE should be False without matplotlib",
)
check(
    sensitivity.MATPLOTLIB_AVAILABLE is False,
    "sensitivity.MATPLOTLIB_AVAILABLE should be False without matplotlib",
)
check(
    "matplotlib" not in sys.modules,
    "matplotlib must not be imported as a side effect of core imports",
)
check(
    "skopt" not in sys.modules,
    "skopt must not be imported as a side effect of core imports",
)

# 2. A deterministic offline backtest runs end-to-end without the extras.
from datetime import datetime, timedelta  # noqa: E402

from quant_trading.backtest.engine import BacktestEngine  # noqa: E402
from quant_trading.config.settings import BacktestConfig  # noqa: E402
from quant_trading.data.providers import DataManager  # noqa: E402
from quant_trading.data.synthetic import create_synthetic_provider  # noqa: E402
from quant_trading.strategies.examples import MovingAverageCrossover  # noqa: E402

end = datetime(2023, 1, 1)
start = end - timedelta(days=365)
provider = create_synthetic_provider(
    ["AAPL", "MSFT", "GOOGL"], days=365, seed=42, end_date=end
)
engine = BacktestEngine(
    config=BacktestConfig(initial_capital=100000.0, commission=0.001),
    data_manager=DataManager([provider]),
)
engine.add_strategy(MovingAverageCrossover(fast_period=10, slow_period=30))
result = engine.run(["AAPL", "MSFT", "GOOGL"], start, end, "1d")

check(
    result.metrics.num_trades > 0,
    "expected the core-only backtest to place trades, got %d"
    % result.metrics.num_trades,
)
check(result.final_value > 0, "expected a positive final value")

# 3. Requesting charts without matplotlib raises a clean ImportError.
try:
    report.generate_html_report(
        result, config=report.ReportConfig(include_charts=True)
    )
    failures.append(
        "generate_html_report(include_charts=True) should raise ImportError "
        "without matplotlib"
    )
except ImportError:
    pass
except Exception as exc:  # noqa: BLE001
    failures.append(
        "generate_html_report raised %s, expected ImportError"
        % type(exc).__name__
    )

# 4. The sensitivity chart helper also raises a clean ImportError.
try:
    sensitivity._check_matplotlib()
    failures.append(
        "sensitivity._check_matplotlib() should raise ImportError without "
        "matplotlib"
    )
except ImportError:
    pass
except Exception as exc:  # noqa: BLE001
    failures.append(
        "sensitivity._check_matplotlib() raised %s, expected ImportError"
        % type(exc).__name__
    )

print("CORE_ONLY_JSON " + json.dumps({"failures": failures}))
sys.exit(1 if failures else 0)
"""


def _run_core_only_child() -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["QT_ROOT"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-c", _CHILD_SCRIPT],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(ROOT),
        env=env,
    )


def test_core_only_import_and_backtest_without_optional_extras() -> None:
    """Core import + a deterministic backtest succeed with matplotlib/skopt absent."""
    completed = _run_core_only_child()
    output = completed.stdout + completed.stderr

    failures: list[str] = []
    for line in completed.stdout.splitlines():
        if line.startswith("CORE_ONLY_JSON "):
            payload = json.loads(line[len("CORE_ONLY_JSON ") :])
            failures = payload.get("failures", [])

    assert completed.returncode == 0, (
        f"core-only subprocess failed (exit {completed.returncode})\n"
        f"failures: {failures}\n"
        f"STDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )
    assert not failures, f"core-only checks failed: {failures}"
    assert (
        "Traceback" not in output
    ), f"core-only subprocess produced a traceback\noutput:\n{output}"
