"""End-to-end tests that the CLI example commands documented in the README
actually run.

The README's "Command Line Interface" section is a set of copy-pasteable
invocations. :class:`TestReadmeCliFlags` guards that every individual flag
advertised there exists on the parser; this module guards that the documented
*invocations* themselves execute end-to-end (exit code 0) or, for the
documented error-reporting examples, exit with code 1 and a one-line message
instead of a traceback.

Only commands that need no network are executed directly: offline runs (``--offline``
or ``--provider synthetic``) and the info commands (``--list-strategies``,
``--list-providers``, ``--init-config``, ``--validate-config``). Commands that
default to Yahoo Finance or Alpha Vantage are executed too, with the providers
mocked to return deterministic synthetic OHLCV data, so every documented CLI
invocation runs without network access.

Commands are extracted from the README's ``## Command Line Interface`` bash
code blocks, so a newly documented command is covered automatically and a
documented command that breaks at runtime is caught immediately.
"""

import contextlib
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from examples.cli import main
from quant_trading.data.providers import DataProvider, FetchResult, MarketData
from quant_trading.data.yfinance_provider import AlphaVantageProvider, YFinanceProvider

README_PATH = Path(__file__).resolve().parent.parent / "README.md"

_CODE_BLOCK = re.compile(r"```bash\n(?P<body>.*?)```", re.DOTALL)
_COMMAND = re.compile(r"^python\s+examples/cli\.py(?P<args>.*)$")


def _cli_section() -> str:
    """Return the body of the README "Command Line Interface" section."""
    text = README_PATH.read_text(encoding="utf-8")
    start = text.index("## Command Line Interface")
    remainder = text[start + 1 :]
    end = remainder.find("\n## ")
    return remainder if end == -1 else remainder[:end]


def _readme_commands() -> list[pytest.param]:
    """Extract the ``examples/cli.py`` argument lists documented in the README.

    Backslash-continued command lines are joined into a single command.
    Comment lines (``# ...``) are ignored.

    Commands that run every builtin strategy (``--combined``) are slow; they are
    marked ``slow`` so they are deselected by default (``-m "not slow"``) and
    excluded from the default coverage run, which otherwise exceeds the session
    timeout on these long-running invocations.
    """
    params: list[pytest.param] = []
    section = _cli_section()
    for block in _CODE_BLOCK.finditer(section):
        logical_lines: list[str] = []
        for raw_line in block.group("body").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("\\"):
                logical_lines.append(line[:-1].rstrip())
                continue
            if logical_lines:
                logical_lines[-1] += " " + line
                line = logical_lines.pop()
            else:
                line = raw_line.strip()
            match = _COMMAND.match(line)
            if match:
                args = match.group("args").strip().split()
                test_id = " ".join(args)[:70]
                marks = [pytest.mark.slow] if "--combined" in args else []
                params.append(pytest.param(args, marks=marks, id=test_id))
    return params


def _expects_failure(args: list[str]) -> bool:
    """Whether a documented command is one of the error-reporting examples."""
    text = " ".join(args)
    return (
        "nosuchstrategy" in text
        or "--mc-simulations 0" in text
        or "--ma-fast-range 5,20,0" in text
        or "--config missing.yaml" in text
    )


def _make_ohlcv_frame(symbol: str, start: datetime | None, end: datetime | None) -> pd.DataFrame:
    """Return deterministic daily OHLCV data covering ``[start, end]``.

    The window defaults to ~400 days ending today when bounds are omitted, so
    any documented ``--days`` span is covered. Columns mirror the synthetic
    provider (lowercase OHLCV) so strategies compute without error.
    """
    start_ts = pd.Timestamp(start) if start else pd.Timestamp.now() - pd.Timedelta(days=400)
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.now()
    idx = pd.date_range(start=start_ts, end=end_ts, freq="D")
    n = len(idx)
    base = [100.0 + i * 0.25 for i in range(n)]
    return pd.DataFrame(
        {
            "open": base,
            "high": [b + 1.0 for b in base],
            "low": [b - 1.0 for b in base],
            "close": [b + 0.5 for b in base],
            "volume": [1000] * n,
        },
        index=idx,
    )


def _mock_fetch(self, symbols, start=None, end=None, interval="1d"):
    """Stand-in for provider.fetch that returns synthetic OHLCV for every symbol."""
    result = FetchResult()
    for symbol in symbols:
        df = _make_ohlcv_frame(symbol, start, end)
        result.data[symbol] = MarketData(
            symbol=symbol,
            data=df,
            source="mock",
            fetched_at=end if end else pd.Timestamp.now(),
        )
    return result


def _mock_fetch_many(self, requests):
    """Stand-in for provider.fetch_many that delegates to ``_mock_fetch``."""
    out: dict[str, FetchResult] = {}
    for req in requests:
        symbols = req.get("symbols", [])
        start = req.get("start")
        end = req.get("end")
        interval = req.get("interval", "1d")
        key = DataProvider._request_key(symbols, start, end, interval)
        out[key] = _mock_fetch(self, symbols, start, end, interval)
    return out


@pytest.fixture(autouse=True)
def mocked_network_providers(monkeypatch: pytest.MonkeyPatch):
    """Mock YFinance/AlphaVantage fetch so network README commands run offline."""
    monkeypatch.setattr(YFinanceProvider, "fetch", _mock_fetch)
    monkeypatch.setattr(YFinanceProvider, "fetch_many", _mock_fetch_many)
    monkeypatch.setattr(AlphaVantageProvider, "fetch", _mock_fetch)
    monkeypatch.setattr(AlphaVantageProvider, "fetch_many", _mock_fetch_many)


def _run_cli(args: list[str], tmp_path: Path) -> tuple[int, str]:
    """Run ``main()`` with ``args`` inside ``tmp_path`` and return (rc, output).

    The working directory is temporarily moved to ``tmp_path`` so commands that
    write files (``--init-config``, ``--output-strategy-config``) do not
    pollute the repository, and a valid ``config.yaml`` is created ahead of a
    ``--validate-config`` command.
    """
    for index, arg in enumerate(args):
        if arg == "--config" and index + 1 < len(args):
            target_path = tmp_path / args[index + 1]
            if not target_path.exists() and Path(args[index + 1]).name != "missing.yaml":
                # The README ``--config config.yaml`` example assumes a config
                # file exists in the working directory; create a valid one so
                # the command runs offline in the temporary directory.
                target_path.write_text(
                    "data:\n  provider: synthetic\n  offline: true\n",
                    encoding="utf-8",
                )
        if arg in {"--validate-config", "--strategy-config"} and index + 1 < len(args):
            target_path = tmp_path / args[index + 1]
            if not target_path.exists():
                if arg == "--validate-config":
                    target_path.write_text(
                        "data:\n  provider: synthetic\n  offline: true\n",
                        encoding="utf-8",
                    )
                else:
                    target_path.write_text(
                        "type: rsi\nname: MyRSI\nparameters:\n  period: 21\n  oversold: 25\n  overbought: 75\n",
                        encoding="utf-8",
                    )

    old_cwd = Path.cwd()
    old_argv = sys.argv
    output = io.StringIO()
    try:
        os.chdir(tmp_path)
        sys.argv = ["cli.py"] + args
        with contextlib.redirect_stdout(output):
            try:
                rc = main()
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 1
    finally:
        os.chdir(old_cwd)
        sys.argv = old_argv
    return rc, output.getvalue()


_COMMANDS = _readme_commands()


@pytest.mark.parametrize("args", _COMMANDS)
class TestReadmeCliCommands:
    """Every documented README CLI command runs end-to-end.

    Offline/error commands execute as documented (exit 0 / exit 1). Network
    commands (Yahoo Finance / Alpha Vantage defaults) run with the providers
    mocked to deterministic synthetic OHLCV data, so they also exit 0 without
    any network access.
    """

    def test_command_runs_with_documented_exit_code(self, args, tmp_path):
        """Every README CLI command exits with the documented code, no traceback."""
        expected_rc = 1 if _expects_failure(args) else 0

        rc, output = _run_cli(args, tmp_path)
        assert rc == expected_rc, (
            f"expected exit code {expected_rc} for `python examples/cli.py "
            + " ".join(args)
            + f"`, got {rc}\noutput:\n{output}"
        )
        if expected_rc == 1:
            command = "python examples/cli.py " + " ".join(args)
            assert "Traceback" not in output, (
                "error-reporting command produced a traceback: `"
                + command
                + "`\noutput:\n"
                + output
            )
            assert "Error:" in output or "error" in output.lower(), (
                "error-reporting command did not report an error: `"
                + command
                + "`\noutput:\n"
                + output
            )


class TestExplicitCombinedAndStrategyConfigErrors:
    def test_combined_mc_simulations_zero(self, tmp_path):
        rc, output = _run_cli(["--combined", "--offline", "--mc-simulations", "0"], tmp_path)
        assert rc == 1
        assert "Traceback" not in output
        assert "error" in output.lower()

    def test_combined_missing_strategy_config_file(self, tmp_path):
        import contextlib
        import io
        import os
        import sys
        from pathlib import Path

        old_cwd = Path.cwd()
        old_argv = sys.argv
        output = io.StringIO()
        try:
            os.chdir(tmp_path)
            sys.argv = ["cli.py", "--combined", "--offline", "--strategy-config", "missing.yaml"]
            with contextlib.redirect_stdout(output):
                try:
                    rc = main()
                except SystemExit as exc:
                    rc = exc.code if isinstance(exc.code, int) else 1
        finally:
            os.chdir(old_cwd)
            sys.argv = old_argv
        assert rc == 1
        assert "Traceback" not in output.getvalue()
        assert "could not read strategy config" in output.getvalue()

    def test_missing_strategy_config_file(self, tmp_path):
        import contextlib
        import io
        import os
        import sys
        from pathlib import Path

        old_cwd = Path.cwd()
        old_argv = sys.argv
        output = io.StringIO()
        try:
            os.chdir(tmp_path)
            sys.argv = ["cli.py", "--offline", "--strategy-config", "missing.yaml"]
            with contextlib.redirect_stdout(output):
                try:
                    rc = main()
                except SystemExit as exc:
                    rc = exc.code if isinstance(exc.code, int) else 1
        finally:
            os.chdir(old_cwd)
            sys.argv = old_argv
        assert rc == 1
        assert "Traceback" not in output.getvalue()
        assert "could not read strategy config" in output.getvalue()

    def test_invalid_yaml_config_file_reported(self, tmp_path):
        """A config file that is not valid YAML is reported as a one-line error.

        The README's "Error Reporting" section documents that a configuration
        file that is not valid YAML is reported the same way as a missing one
        (exit code 1, no traceback). This test keeps that documentation in sync
        with the CLI behavior.
        """
        import contextlib
        import io
        import os
        import sys
        from pathlib import Path

        broken = tmp_path / "broken.yaml"
        broken.write_text("backtest: {initial_capital: 100.0\n")
        old_cwd = Path.cwd()
        old_argv = sys.argv
        output = io.StringIO()
        try:
            os.chdir(tmp_path)
            sys.argv = [
                "cli.py",
                "--config",
                str(broken),
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ]
            with contextlib.redirect_stdout(output):
                try:
                    rc = main()
                except SystemExit as exc:
                    rc = exc.code if isinstance(exc.code, int) else 1
        finally:
            os.chdir(old_cwd)
            sys.argv = old_argv
        out = output.getvalue()
        assert rc == 1
        assert "Traceback" not in out
        assert "Invalid YAML" in out

    def test_invalid_yaml_strategy_config_file_reported(self, tmp_path):
        """A strategy config file that is not valid YAML is reported as a one-line error."""
        import contextlib
        import io
        import os
        import sys
        from pathlib import Path

        broken = tmp_path / "broken.yaml"
        broken.write_text("type: [unclosed\n  bad: : :\n")
        old_cwd = Path.cwd()
        old_argv = sys.argv
        output = io.StringIO()
        try:
            os.chdir(tmp_path)
            sys.argv = [
                "cli.py",
                "--strategy-config",
                str(broken),
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ]
            with contextlib.redirect_stdout(output):
                try:
                    rc = main()
                except SystemExit as exc:
                    rc = exc.code if isinstance(exc.code, int) else 1
        finally:
            os.chdir(old_cwd)
            sys.argv = old_argv
        out = output.getvalue()
        assert rc == 1
        assert "Traceback" not in out
        assert "invalid YAML in strategy config" in out
