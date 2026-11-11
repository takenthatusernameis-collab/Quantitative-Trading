"""Tests for CLI functionality."""

import argparse
import importlib.util
import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from examples.cli import (
    _default_param_grid,
    _get_monte_carlo_analysis,
    _is_supported_interval,
    _print_monte_carlo_analysis,
    _print_regime_analysis,
    _print_trade_analysis,
    _save_json_output,
    create_config,
    create_strategy,
    init_config,
    list_providers,
    list_strategies,
    main,
    parse_args,
    resolve_periods_per_year,
    run_combined,
)
from quant_trading.config.settings import Config
from quant_trading.strategies.examples import (
    BollingerBandsStrategy,
    DonchianChannelStrategy,
    IchimokuCloudStrategy,
    KeltnerChannelStrategy,
    MACDStrategy,
    MovingAverageCrossover,
    ParabolicSARStrategy,
    RSIStrategy,
    StochasticOscillatorStrategy,
    SuperTrendStrategy,
    VWAPStrategy,
)


def _module_available(name: str) -> bool:
    """Return True if a top-level module can be imported."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


class TestParseArgs:
    """Tests for argument parsing."""

    def test_version_flag_exits(self):
        with patch("sys.argv", ["cli.py", "--version"]), pytest.raises(SystemExit) as exc:
            parse_args()
        assert exc.value.code == 0

    def test_default_args(self):
        with patch("sys.argv", ["cli.py"]):
            args = parse_args()
        assert args.symbols == ["AAPL", "MSFT", "GOOGL"]
        assert args.days == 365
        # The cost settings default to None so that the values of a config
        # file are used when the flag is not given.
        assert args.initial_capital is None
        assert args.commission is None
        assert args.slippage is None
        assert args.risk_free_rate is None
        assert args.interval is None
        assert args.strategy == "ma"
        assert args.fast_period == 10
        assert args.slow_period == 30
        assert args.provider is None
        assert args.offline is False
        assert args.alphavantage_key is None
        assert args.combined is False
        assert args.strategy_config is None

    def test_cost_flags_are_parsed(self):
        with patch(
            "sys.argv",
            [
                "cli.py",
                "--initial-capital",
                "50000",
                "--commission",
                "0.002",
                "--slippage",
                "0.001",
            ],
        ):
            args = parse_args()
        assert args.initial_capital == 50000.0
        assert args.commission == 0.002
        assert args.slippage == 0.001

    def test_strategy_config_flag(self):
        with patch("sys.argv", ["cli.py", "--strategy-config", "my_strat.yaml"]):
            args = parse_args()
        assert args.strategy_config == "my_strat.yaml"

    def test_list_strategies_flag(self):
        with patch("sys.argv", ["cli.py", "--list-strategies"]):
            args = parse_args()
        assert args.list_strategies is True

    def test_list_providers_flag(self):
        with patch("sys.argv", ["cli.py", "--list-providers"]):
            args = parse_args()
        assert args.list_providers is True

    def test_init_config_flag(self):
        with patch("sys.argv", ["cli.py", "--init-config", "config.yaml"]):
            args = parse_args()
        assert args.init_config == "config.yaml"

    def test_validate_config_flag(self):
        with patch("sys.argv", ["cli.py", "--validate-config", "config.yaml"]):
            args = parse_args()
        assert args.validate_config == "config.yaml"

    def test_combined_flag(self):
        with patch("sys.argv", ["cli.py", "--combined"]):
            args = parse_args()
        assert args.combined is True

    def test_custom_symbols(self):
        with patch("sys.argv", ["cli.py", "--symbols", "AAPL", "TSLA", "NVDA"]):
            args = parse_args()
        assert args.symbols == ["AAPL", "TSLA", "NVDA"]

    def test_provider_choices(self):
        with patch("sys.argv", ["cli.py", "--provider", "alphavantage"]):
            args = parse_args()
        assert args.provider == "alphavantage"

        with patch("sys.argv", ["cli.py", "--provider", "synthetic"]):
            args = parse_args()
        assert args.provider == "synthetic"

    def test_offline_flag(self):
        with patch("sys.argv", ["cli.py", "--offline"]):
            args = parse_args()
        assert args.offline is True

    def test_alphavantage_key(self):
        with patch("sys.argv", ["cli.py", "--alphavantage-key", "MY_KEY"]):
            args = parse_args()
        assert args.alphavantage_key == "MY_KEY"

    def test_strategy_params(self):
        with patch(
            "sys.argv",
            ["cli.py", "--strategy", "rsi", "--rsi-period", "21", "--rsi-oversold", "25"],
        ):
            args = parse_args()
        assert args.strategy == "rsi"
        assert args.rsi_period == 21
        assert args.rsi_oversold == 25

    def test_regime_flag_defaults(self):
        with patch("sys.argv", ["cli.py", "--regime"]):
            args = parse_args()
        assert args.regime is True
        assert args.regime_window == 20
        assert args.regime_vol_threshold == 0.0
        assert args.regime_return_threshold == 0.0

    def test_regime_flag_explicit_thresholds(self):
        with patch(
            "sys.argv",
            [
                "cli.py",
                "--regime",
                "--regime-window",
                "30",
                "--regime-vol-threshold",
                "0.15",
                "--regime-return-threshold",
                "0.05",
            ],
        ):
            args = parse_args()
        assert args.regime is True
        assert args.regime_window == 30
        assert args.regime_vol_threshold == 0.15
        assert args.regime_return_threshold == 0.05

    def test_monte_carlo_flag_defaults(self):
        with patch("sys.argv", ["cli.py", "--monte-carlo"]):
            args = parse_args()
        assert args.monte_carlo is True
        assert args.mc_simulations == 1000
        assert args.mc_confidence == 0.95
        assert args.mc_method == "bootstrap"
        assert args.mc_seed is None

    def test_monte_carlo_flag_explicit_params(self):
        with patch(
            "sys.argv",
            [
                "cli.py",
                "--monte-carlo",
                "--mc-simulations",
                "250",
                "--mc-confidence",
                "0.99",
                "--mc-method",
                "parametric",
                "--mc-seed",
                "7",
            ],
        ):
            args = parse_args()
        assert args.monte_carlo is True
        assert args.mc_simulations == 250
        assert args.mc_confidence == 0.99
        assert args.mc_method == "parametric"
        assert args.mc_seed == 7

    def test_the_help_text_renders(self, capsys):
        """``--help`` must render the help of every option.

        ``argparse`` runs the help string of each option through the
        percent-formatting operator, so a literal ``%`` in a help string
        has to be escaped as ``%%``. An unescaped one makes the whole help
        output fail with a ``ValueError``.
        """
        with patch("sys.argv", ["cli.py", "--help"]), pytest.raises(SystemExit) as excinfo:
            parse_args()
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "--risk-free-rate" in out
        assert "0.02 for 2%" in out
        # The escaped percent signs of the Stochastic options render once.
        assert "Stochastic %K period" in out
        assert "Stochastic %D period" in out

    def test_mc_simulations_below_one_is_rejected(self):
        """A ``--mc-simulations`` below 1 is a usage error, not a library failure.

        The Monte Carlo module is generic and treats a count of zero as an
        empty result; the CLI has to reject it before the run starts and name
        the offending flag so the user gets an actionable one-liner.
        """
        with (
            patch("sys.argv", ["cli.py", "--monte-carlo", "--mc-simulations", "0"]),
            pytest.raises(ValueError, match="invalid --mc-simulations"),
        ):
            parse_args()

    def test_mc_simulations_negative_is_rejected(self):
        """A negative simulation count is rejected the same way as zero."""
        with (
            patch("sys.argv", ["cli.py", "--monte-carlo", "--mc-simulations", "-5"]),
            pytest.raises(ValueError, match="invalid --mc-simulations"),
        ):
            parse_args()

    def test_mc_simulations_one_is_accepted(self):
        """The minimum accepted count is 1."""
        with patch("sys.argv", ["cli.py", "--monte-carlo", "--mc-simulations", "1"]):
            args = parse_args()
        assert args.mc_simulations == 1

    def test_mc_confidence_above_one_is_rejected(self):
        """A ``--mc-confidence`` above 1 is a usage error naming the flag.

        The Monte Carlo module derives percentile ranks from the confidence
        level, so an out-of-range value surfaces deep in NumPy as
        ``Percentiles must be in the range [0, 100]``. The check belongs in
        the CLI and has to name the offending flag instead.
        """
        with (
            patch("sys.argv", ["cli.py", "--monte-carlo", "--mc-confidence", "1.5"]),
            pytest.raises(ValueError, match="invalid --mc-confidence"),
        ):
            parse_args()

    def test_mc_confidence_zero_is_rejected(self):
        """A ``--mc-confidence`` of zero is rejected the same way as above one."""
        with (
            patch("sys.argv", ["cli.py", "--monte-carlo", "--mc-confidence", "0"]),
            pytest.raises(ValueError, match="invalid --mc-confidence"),
        ):
            parse_args()

    def test_mc_confidence_one_is_accepted(self):
        """The upper boundary ``--mc-confidence`` of 1.0 is accepted."""
        with patch("sys.argv", ["cli.py", "--monte-carlo", "--mc-confidence", "1.0"]):
            args = parse_args()
        assert args.mc_confidence == 1.0

    def test_wf_train_size_at_or_above_one_is_rejected(self):
        """A ``--wf-train-size`` at or above 1 is a usage error naming the flag.

        Walk-forward computes ``train_days = int(window_days * train_size)``,
        so a train size of one or above yields degenerate windows and wrong
        results instead of an error. The check belongs in the CLI and has to
        name the offending flag before the run starts.
        """
        with (
            patch("sys.argv", ["cli.py", "--walk-forward", "--wf-train-size", "1.5"]),
            pytest.raises(ValueError, match="invalid --wf-train-size"),
        ):
            parse_args()

    def test_wf_train_size_zero_or_negative_is_rejected(self):
        """A ``--wf-train-size`` of zero or below is a usage error naming the flag."""
        for value in ("0", "-0.1"):
            with (
                patch("sys.argv", ["cli.py", "--walk-forward", "--wf-train-size", value]),
                pytest.raises(ValueError, match="invalid --wf-train-size"),
            ):
                parse_args()

    def test_wf_step_size_non_positive_is_rejected(self):
        """A ``--wf-step-size`` of zero or below is a usage error naming the flag."""
        for value in ("0", "-1"):
            with (
                patch("sys.argv", ["cli.py", "--walk-forward", "--wf-step-size", value]),
                pytest.raises(ValueError, match="invalid --wf-step-size"),
            ):
                parse_args()

    def test_wf_windows_below_one_is_rejected(self):
        """A ``--wf-windows`` of zero or below is a usage error naming the flag."""
        for value in ("0", "-1"):
            with (
                patch("sys.argv", ["cli.py", "--walk-forward", "--wf-windows", value]),
                pytest.raises(ValueError, match="invalid --wf-windows"),
            ):
                parse_args()

    def test_wf_windows_one_is_accepted(self):
        """A ``--wf-windows`` of one is accepted."""
        with patch("sys.argv", ["cli.py", "--walk-forward", "--wf-windows", "1"]):
            args = parse_args()
        assert args.wf_windows == 1

    def test_initial_capital_non_positive_is_rejected(self):
        """A ``--initial-capital`` of zero or below is a usage error naming the flag."""
        for value in ("0", "-1"):
            with (
                patch("sys.argv", ["cli.py", "--initial-capital", value]),
                pytest.raises(ValueError, match="invalid --initial-capital"),
            ):
                parse_args()

    def test_wf_train_size_below_one_is_accepted(self):
        """A ``--wf-train-size`` just below 1.0 (valid (0,1) boundary) is accepted."""
        with patch("sys.argv", ["cli.py", "--walk-forward", "--wf-train-size", "0.99"]):
            args = parse_args()
        assert args.wf_train_size == 0.99

    def test_wf_step_size_positive_is_accepted(self):
        """A small positive ``--wf-step-size`` is accepted."""
        with patch("sys.argv", ["cli.py", "--walk-forward", "--wf-step-size", "5"]):
            args = parse_args()
        assert args.wf_step_size == 5

    def test_initial_capital_positive_is_accepted(self):
        """A positive ``--initial-capital`` is accepted."""
        with patch("sys.argv", ["cli.py", "--initial-capital", "1000"]):
            args = parse_args()
        assert args.initial_capital == 1000.0

    def test_commission_negative_is_rejected(self):
        """A negative ``--commission`` is a usage error naming the flag."""
        with (
            patch("sys.argv", ["cli.py", "--commission", "-0.1"]),
            pytest.raises(ValueError, match="invalid --commission"),
        ):
            parse_args()

    def test_commission_zero_is_accepted(self):
        """A ``--commission`` of zero (no commission) is accepted."""
        with patch("sys.argv", ["cli.py", "--commission", "0"]):
            args = parse_args()
        assert args.commission == 0.0

    def test_slippage_negative_is_rejected(self):
        """A negative ``--slippage`` is a usage error naming the flag."""
        with (
            patch("sys.argv", ["cli.py", "--slippage", "-0.1"]),
            pytest.raises(ValueError, match="invalid --slippage"),
        ):
            parse_args()

    def test_slippage_zero_is_accepted(self):
        """A ``--slippage`` of zero (no slippage) is accepted."""
        with patch("sys.argv", ["cli.py", "--slippage", "0"]):
            args = parse_args()
        assert args.slippage == 0.0

    def test_unsupported_interval_is_rejected(self):
        """An unsupported ``--interval`` is a usage error naming the flag."""
        with (
            patch("sys.argv", ["cli.py", "--interval", "3x"]),
            pytest.raises(ValueError, match="invalid --interval"),
        ):
            parse_args()

    def test_supported_interval_is_accepted(self):
        """A documented interval is accepted by the parser."""
        with patch("sys.argv", ["cli.py", "--interval", "1wk"]):
            args = parse_args()
        assert args.interval == "1wk"

    def test_optimization_range_with_a_minimum_above_the_maximum_is_rejected(self):
        """An inverted range is rejected before the run starts and names the flag."""
        with (
            patch(
                "sys.argv",
                ["cli.py", "--optimize", "--ma-fast-range", "20,5,5", "--offline"],
            ),
            pytest.raises(ValueError, match="invalid --ma-fast-range"),
        ):
            parse_args()

    def test_optimization_range_with_step_zero_is_rejected(self):
        """A range with step zero is rejected and names the flag."""
        with (
            patch(
                "sys.argv",
                ["cli.py", "--optimize", "--ma-fast-range", "1,2,0", "--offline"],
            ),
            pytest.raises(ValueError, match="invalid --ma-fast-range"),
        ):
            parse_args()

    def test_optimization_range_with_negative_step_is_rejected(self):
        """A range with negative step is rejected and names the flag."""
        with (
            patch(
                "sys.argv",
                ["cli.py", "--optimize", "--rsi-period-range", "10,20,-1", "--offline"],
            ),
            pytest.raises(ValueError, match="invalid --rsi-period-range"),
        ):
            parse_args()

    def test_n_jobs_zero_is_rejected(self):
        """A ``--n-jobs`` of zero is a usage error naming the flag.

        The library coerces ``n_jobs=0`` to ``1`` (joblib convention), so the
        value is silently accepted and the user gets a single core instead of
        the parallelism they asked for. The check belongs in the CLI and has
        to name the offending flag before the run starts.
        """
        with (
            patch("sys.argv", ["cli.py", "--n-jobs", "0"]),
            pytest.raises(ValueError, match="invalid --n-jobs"),
        ):
            parse_args()

    def test_n_jobs_below_one_except_minus_one_is_rejected(self):
        """A ``--n-jobs`` below 1 (other than -1) is a usage error.

        ``-1`` is the documented joblib shorthand for "all CPU cores". Values
        such as ``-2`` are not meaningful and would be coerced to ``1`` by the
        library, so they are rejected up front.
        """
        for value in ("-2", "-5"):
            with (
                patch("sys.argv", ["cli.py", "--n-jobs", value]),
                pytest.raises(ValueError, match="invalid --n-jobs"),
            ):
                parse_args()

    def test_n_jobs_minus_one_is_accepted(self):
        """The documented ``-1`` shorthand for all CPU cores is accepted."""
        with patch("sys.argv", ["cli.py", "--n-jobs", "-1"]):
            args = parse_args()
        assert args.n_jobs == -1

    def test_n_jobs_positive_is_accepted(self):
        """A positive ``--n-jobs`` is accepted."""
        with patch("sys.argv", ["cli.py", "--n-jobs", "4"]):
            args = parse_args()
        assert args.n_jobs == 4


class TestIsSupportedInterval:
    """Tests for ``_is_supported_interval``."""

    @pytest.mark.parametrize(
        "interval",
        [
            "1d",
            "1wk",
            "1mo",
            "monthly_adjusted",
            "weekly",
            "quote",
            "market_status",
            "fx_daily",
            "fx_5m",
            "crypto_daily",
            "sector",
            "sma",
            "5m",
            "1h",
            "gold",
        ],
    )
    def test_documented_intervals_are_supported(self, interval):
        # Intervals the README documents as valid CLI values must be accepted.
        assert _is_supported_interval(interval) is True

    def test_unknown_interval_is_not_supported(self):
        assert _is_supported_interval("3x") is False
        assert _is_supported_interval("") is False
        assert _is_supported_interval(None) is False


class TestListStrategies:
    """Tests for list_strategies function."""

    def test_list_strategies_output(self, capsys):
        result = list_strategies()
        assert result == 0
        captured = capsys.readouterr()
        assert "Available strategies:" in captured.out
        assert "ma:" in captured.out
        assert "rsi:" in captured.out
        assert "bb:" in captured.out
        assert "MovingAverageCrossover" in captured.out
        assert "RSIStrategy" in captured.out
        assert "BollingerBandsStrategy" in captured.out

    def test_list_strategies_reports_aliases(self, capsys):
        """``--list-strategies`` annotates every strategy with its aliases.

        The CLI's ``--strategy`` argument accepts every registered key,
        primary *and* alias, but the list command previously only showed
        primary keys, so users had no way to discover the aliases the
        registry and the README reference. Each strategy with aliases must
        appear exactly once, annotated with its alias list, and strategies
        without aliases (``vwap``, ``trix``) must not carry an annotation.
        """
        from quant_trading.strategies import get_registry

        result = list_strategies()
        assert result == 0
        captured = capsys.readouterr()
        out = captured.out
        registry = get_registry()

        # One line per primary key, no more.
        primary_lines = [line for line in out.splitlines() if line.startswith("  ")]
        assert len(primary_lines) == len(registry.primary_keys())

        for key in registry.primary_keys():
            aliases = registry.aliases_for(key)
            line = next(ln for ln in primary_lines if ln.startswith(f"  {key}:"))
            if aliases:
                assert f"(aliases: {', '.join(aliases)})" in line, (
                    f"{key} aliases missing from list output: {line!r}"
                )
            else:
                assert "aliases:" not in line, (
                    f"{key} should not report aliases but line says: {line!r}"
                )

    def test_list_strategies_alias_annotation_matches_registry(self, capsys):
        """The alias annotation on each line matches the live registry exactly."""
        import re

        from quant_trading.strategies import get_registry

        result = list_strategies()
        assert result == 0
        captured = capsys.readouterr()
        out = captured.out
        registry = get_registry()

        alias_re = re.compile(r"\(aliases: ([^)]*)\)")
        for line in out.splitlines():
            if not line.startswith("  "):
                continue
            key = line[2:].split(":", 1)[0]
            match = alias_re.search(line)
            reported = (
                [a.strip() for a in match.group(1).split(",")] if match else []
            )
            assert reported == registry.aliases_for(key), (
                f"{key}: list output reports {reported!r}, "
                f"registry has {registry.aliases_for(key)!r}"
            )


class TestListProviders:
    """Tests for list_providers function."""

    def test_list_providers_output(self, capsys):
        result = list_providers()
        assert result == 0
        captured = capsys.readouterr()
        assert "Available data providers:" in captured.out
        assert "yfinance:" in captured.out
        assert "alphavantage:" in captured.out
        assert "synthetic:" in captured.out
        assert "YFinanceProvider" in captured.out
        assert "AlphaVantageProvider" in captured.out
        assert "SyntheticDataProvider" in captured.out


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_validate_config_valid_file(self, capsys):
        from examples.cli import validate_config

        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/config.yaml"
            init_config(path)
            result = validate_config(path)
            assert result == 0
            captured = capsys.readouterr()
            assert f"Config is valid: {path}" in captured.out

    def test_validate_config_missing_file(self, capsys):
        from examples.cli import validate_config

        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/does_not_exist.yaml"
            result = validate_config(path)
            assert result == 1
            captured = capsys.readouterr()
            assert "Error:" in captured.out

    def test_validate_config_invalid_yaml(self, capsys):
        from examples.cli import validate_config

        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/bad.yaml"
            with open(path, "w") as f:
                f.write("backtest:\n  initial_capital: [unclosed\n")
            result = validate_config(path)
            assert result == 1
            captured = capsys.readouterr()
            assert "Error:" in captured.out

    def test_validate_config_invalid_type(self, capsys):
        from examples.cli import validate_config

        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/bad_type.yaml"
            with open(path, "w") as f:
                f.write("backtest:\n  initial_capital: abc\n")
            result = validate_config(path)
            assert result == 1
            captured = capsys.readouterr()
            assert "Error:" in captured.out


class TestInitConfig:
    """Tests for init_config function."""

    def test_init_config_creates_file(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/config.yaml"
            result = init_config(path)
            assert result == 0
            captured = capsys.readouterr()
            assert f"Default config written to {path}" in captured.out

            # Verify file exists and is valid YAML
            loaded = Config.from_yaml(path)
            assert isinstance(loaded, Config)
            assert loaded.data.provider == "yfinance"

    def test_create_aroon_strategy(self):
        from argparse import Namespace

        args = Namespace(
            strategy="aroon",
            aroon_period=25,
        )
        strategy = create_strategy(args)
        assert strategy is not None
        assert hasattr(strategy, "period")

    def test_create_aroon_strategy_with_custom_period(self):
        from argparse import Namespace

        args = Namespace(
            strategy="aroon",
            aroon_period=30,
        )
        strategy = create_strategy(args)
        assert strategy is not None

    def test_parse_range_valid(self):
        from examples.cli import parse_range

        result = parse_range("5,20,5")
        assert result == (5.0, 20.0, 5.0)

    def test_parse_range_invalid(self):
        from examples.cli import parse_range

        try:
            parse_range("5,20")
            assert False
        except ValueError:
            assert True

    def test_parse_range_rejects_a_non_positive_step(self):
        """A step of zero would make the grid search loop forever."""
        from examples.cli import parse_range

        with pytest.raises(ValueError, match="step must be greater than 0"):
            parse_range("5,20,0")

    def test_parse_range_rejects_a_part_that_is_not_a_number(self):
        """A range with a non-numeric part is a user error."""
        from examples.cli import parse_range

        with pytest.raises(ValueError, match="Invalid range format"):
            parse_range("5,20,x")

    def test_parse_range_rejects_a_minimum_greater_than_the_maximum(self):
        """A range whose minimum is above its maximum is a user error."""
        from examples.cli import parse_range

        with pytest.raises(ValueError, match="minimum.*greater than the maximum"):
            parse_range("20,5,5")

    def test_parser_accepts_every_range_flag_create_param_grid_references(self):
        """Every ``--*-range`` attribute read by ``create_param_grid`` must exist
        on the live parser, otherwise ``--optimize`` crashes for that strategy.
        """
        from examples.cli import _create_parser

        parser = _create_parser()
        parser_flags: set[str] = set()
        for action in parser._actions:
            for option in action.option_strings:
                if option.startswith("--"):
                    parser_flags.add(option.lstrip("-"))

        range_flags = [
            "ma-fast-range",
            "ma-slow-range",
            "rsi-period-range",
            "rsi-oversold-range",
            "rsi-overbought-range",
            "bb-period-range",
            "bb-std-range",
            "macd-fast-range",
            "macd-slow-range",
            "macd-signal-range",
            "st-period-range",
            "st-multiplier-range",
            "dc-period-range",
            "dc-exit-period-range",
            "aroon-period-range",
            "kc-ema-period-range",
            "kc-atr-period-range",
            "kc-multiplier-range",
            "stoch-k-period-range",
            "stoch-d-period-range",
            "stoch-oversold-range",
            "stoch-overbought-range",
            "ichimoku-tenkan-period-range",
            "ichimoku-kijun-period-range",
            "ichimoku-senkou-b-period-range",
            "sar-step-range",
            "sar-max-step-range",
            "atr-period-range",
            "atr-multiplier-range",
        ]
        missing = sorted(flag for flag in range_flags if flag not in parser_flags)
        assert (
            missing == []
        ), "create_param_grid references range flags missing from the parser: " + ", ".join(missing)

    def test_main_optimize_calls_run_optimization(self):
        with patch("examples.cli.run_optimization") as mock_opt:
            mock_opt.return_value = 0
            args = ["--optimize", "--offline", "--strategy", "ma", "--days", "60"]
            with patch("sys.argv", ["cli.py"] + args):
                from examples.cli import main

                result = main()
            assert result == 0
            mock_opt.assert_called_once()

    def test_main_walk_forward_calls_run_walk_forward(self):
        with patch("examples.cli.run_walk_forward") as mock_wf:
            mock_wf.return_value = 0
            args = [
                "--walk-forward",
                "--offline",
                "--strategy",
                "ma",
                "--days",
                "120",
                "--wf-windows",
                "2",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                from examples.cli import main

                result = main()
            assert result == 0
            mock_wf.assert_called_once()

    def test_create_config_with_yaml(self):
        import tempfile
        from argparse import Namespace

        from examples.cli import create_config, init_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            init_config(config_path)
            args = Namespace(
                config=config_path,
                offline=False,
                provider=None,
                cache_dir=None,
                synthetic_days=None,
                synthetic_seed=None,
                alphavantage_key=None,
                risk_free_rate=None,
            )
            config = create_config(args)
            assert config is not None

    def test_create_config_keeps_the_values_of_the_config_file(self):
        """A config file supplies the settings the flags do not override."""
        import tempfile
        from argparse import Namespace

        from examples.cli import create_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            with open(config_path, "w") as f:
                f.write(
                    "backtest:\n"
                    "  initial_capital: 25000.0\n"
                    "  commission: 0.002\n"
                    "  slippage: 0.001\n"
                    "risk:\n"
                    "  max_position_size: 0.05\n"
                    "portfolio:\n"
                    "  max_positions: 3\n"
                )
            args = Namespace(
                config=config_path,
                offline=False,
                provider=None,
                cache_dir=None,
                synthetic_days=None,
                synthetic_seed=None,
                alphavantage_key=None,
                risk_free_rate=None,
                initial_capital=None,
                commission=None,
                slippage=None,
            )
            config = create_config(args)

        assert config.backtest.initial_capital == 25000.0
        assert config.backtest.commission == 0.002
        assert config.backtest.slippage == 0.001
        assert config.risk.max_position_size == 0.05
        assert config.portfolio.max_positions == 3

    def test_create_config_lets_the_flags_override_the_config_file(self):
        """A flag that is given wins over the value of the config file."""
        import tempfile
        from argparse import Namespace

        from examples.cli import create_config

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            with open(config_path, "w") as f:
                f.write("backtest:\n  initial_capital: 25000.0\n  commission: 0.002\n")
            args = Namespace(
                config=config_path,
                offline=False,
                provider=None,
                cache_dir=None,
                synthetic_days=None,
                synthetic_seed=None,
                alphavantage_key=None,
                risk_free_rate=None,
                initial_capital=75000.0,
                commission=0.005,
                slippage=None,
            )
            config = create_config(args)

        assert config.backtest.initial_capital == 75000.0
        assert config.backtest.commission == 0.005
        # The slippage was not given, so the value of the config file is kept.
        assert config.backtest.slippage == 0.0005


class TestConfigFileEndToEnd:
    """A config file configures the run of the command line."""

    def test_main_with_a_config_file_uses_the_capital_of_the_file(self, capsys):
        """The starting capital of the config file is the one the run uses."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            with open(config_path, "w") as f:
                f.write(
                    "data:\n"
                    "  provider: synthetic\n"
                    "  offline: true\n"
                    "  synthetic_days: 60\n"
                    "backtest:\n"
                    "  initial_capital: 25000.0\n"
                )
            with patch(
                "sys.argv",
                ["cli.py", "--config", config_path, "--symbols", "AAPL", "--days", "60"],
            ):
                result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Initial Capital: $25,000.00" in captured.out

    def test_main_with_a_config_file_uses_the_limit_of_the_file(self):
        """The config file of the CLI reaches the run with its limits."""
        import tempfile
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            with open(config_path, "w") as f:
                f.write(
                    "data:\n"
                    "  provider: synthetic\n"
                    "  offline: true\n"
                    "  synthetic_days: 60\n"
                    "backtest:\n"
                    "  initial_capital: 25000.0\n"
                    "risk:\n"
                    "  max_position_size: 0.05\n"
                    "portfolio:\n"
                    "  max_positions: 1\n"
                )

            mock_result = MagicMock()
            mock_result.initial_capital = 25000.0
            mock_result.final_value = 25000.0
            mock_result.total_return = 0.0
            mock_result.total_return_pct = 0.0
            mock_result.total_costs = 0.0
            mock_metrics = MagicMock()
            mock_metrics.num_trades = 1
            mock_metrics.win_rate = 0.0
            mock_metrics.sharpe_ratio = 0.0
            mock_metrics.max_drawdown_pct = 0.0
            mock_metrics.profit_factor = 0.0
            mock_metrics.sortino_ratio = 0.0
            mock_metrics.volatility = 0.0
            mock_metrics.var_95 = 0.0
            mock_metrics.calmar_ratio = 0.0
            mock_metrics.total_pnl = 0.0
            mock_metrics.unrealized_pnl = 0.0
            mock_result.metrics = mock_metrics

            with (
                patch("examples.cli.run_backtest", return_value=mock_result) as mock_run,
                patch(
                    "sys.argv",
                    ["cli.py", "--config", config_path, "--symbols", "AAPL", "--days", "60"],
                ),
            ):
                main()

            kwargs = mock_run.call_args.kwargs
            assert kwargs["initial_capital"] == 25000.0
            assert kwargs["config"].risk.max_position_size == 0.05
            assert kwargs["config"].portfolio.max_positions == 1


class TestCreateStrategy:
    """Tests for create_strategy function."""

    def test_create_ma_strategy(self):
        args = argparse.Namespace(
            strategy="ma",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, MovingAverageCrossover)
        assert strategy.fast_period == 10
        assert strategy.slow_period == 30
        assert "MA_Crossover_10_30" in strategy.name

    def test_create_rsi_strategy(self):
        args = argparse.Namespace(
            strategy="rsi",
            fast_period=10,
            slow_period=30,
            rsi_period=21,
            rsi_oversold=25,
            rsi_overbought=75,
            bb_period=20,
            bb_std=2.0,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, RSIStrategy)
        assert strategy.period == 21
        assert strategy.oversold == 25
        assert strategy.overbought == 75
        assert "RSI_21" in strategy.name

    def test_create_bb_strategy(self):
        args = argparse.Namespace(
            strategy="bb",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=25,
            bb_std=2.5,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, BollingerBandsStrategy)
        assert strategy.period == 25
        assert strategy.std_dev == 2.5
        assert "BB_25_2.5" in strategy.name

    def test_create_macd_strategy(self):
        args = argparse.Namespace(
            strategy="macd",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            macd_zero_line=True,
            st_period=10,
            st_multiplier=3.0,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, MACDStrategy)
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.signal_period == 9
        assert strategy.use_zero_line is True
        assert "MACD_12_26_9" in strategy.name

    def test_create_supertrend_strategy(self):
        args = argparse.Namespace(
            strategy="supertrend",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=15,
            st_multiplier=2.5,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, SuperTrendStrategy)
        assert strategy.period == 15
        assert strategy.multiplier == 2.5
        assert "SuperTrend_15_2.5" in strategy.name

    def test_create_donchian_strategy(self):
        args = argparse.Namespace(
            strategy="donchian",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            dc_period=25,
            dc_exit_period=10,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, DonchianChannelStrategy)
        assert strategy.period == 25
        assert strategy.exit_period == 10
        assert "Donchian_25_10" in strategy.name

    def test_create_donchian_strategy_default_exit(self):
        args = argparse.Namespace(
            strategy="donchian",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=None,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, DonchianChannelStrategy)
        assert strategy.period == 20
        assert strategy.exit_period == 20
        assert "Donchian_20_20" in strategy.name

    def test_unknown_strategy_raises(self):
        args = argparse.Namespace(strategy="unknown")
        try:
            create_strategy(args)
            raise AssertionError("Expected ValueError")
        except ValueError as e:
            assert "unknown" in str(e)

    def test_create_ichimoku_strategy(self):
        args = argparse.Namespace(
            strategy="ichimoku",
            tenkan_period=9,
            kijun_period=26,
            senkou_b_period=52,
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            macd_zero_line=False,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=20,
            kc_atr_period=10,
            kc_multiplier=2.0,
            kc_use_middle_cross=False,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
        )
        strategy = create_strategy(args)
        assert strategy is not None
        assert isinstance(strategy, IchimokuCloudStrategy)
        assert strategy.tenkan_period == 9
        assert strategy.kijun_period == 26
        assert strategy.senkou_b_period == 52
        assert strategy.name == "Ichimoku_Cloud"

    def test_create_ichimoku_strategy_custom_params(self):
        args = argparse.Namespace(
            strategy="ichimoku",
            tenkan_period=5,
            kijun_period=15,
            senkou_b_period=30,
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            macd_zero_line=False,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=20,
            kc_atr_period=10,
            kc_multiplier=2.0,
            kc_use_middle_cross=False,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
        )
        strategy = create_strategy(args)
        assert strategy is not None
        assert isinstance(strategy, IchimokuCloudStrategy)
        assert strategy.tenkan_period == 5
        assert strategy.kijun_period == 15
        assert strategy.senkou_b_period == 30
        assert (
            strategy.name == "Ichimoku_Cloud"
        )  # name is not customized in create_strategy for ichimoku

    def test_create_sar_strategy(self):
        args = argparse.Namespace(
            strategy="sar",
            sar_step=0.02,
            sar_max_step=0.20,
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            macd_zero_line=False,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=20,
            kc_atr_period=10,
            kc_multiplier=2.0,
            kc_use_middle_cross=False,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
            tenkan_period=9,
            kijun_period=26,
            senkou_b_period=52,
        )
        strategy = create_strategy(args)
        assert strategy is not None
        assert isinstance(strategy, ParabolicSARStrategy)
        assert strategy.step == 0.02
        assert strategy.max_step == 0.20
        assert strategy.name == "Parabolic_SAR_0.02_0.2"

    def test_create_sar_strategy_custom_params(self):
        args = argparse.Namespace(
            strategy="sar",
            sar_step=0.05,
            sar_max_step=0.25,
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            macd_zero_line=False,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=20,
            kc_atr_period=10,
            kc_multiplier=2.0,
            kc_use_middle_cross=False,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
            tenkan_period=9,
            kijun_period=26,
            senkou_b_period=52,
        )
        strategy = create_strategy(args)
        assert strategy is not None
        assert isinstance(strategy, ParabolicSARStrategy)
        assert strategy.step == 0.05
        assert strategy.max_step == 0.25
        assert strategy.name == "Parabolic_SAR_0.05_0.25"

    def test_create_keltner_strategy(self):
        args = argparse.Namespace(
            strategy="keltner",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=20,
            kc_atr_period=10,
            kc_multiplier=2.0,
            kc_use_middle_cross=False,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, KeltnerChannelStrategy)
        assert strategy.ema_period == 20
        assert strategy.atr_period == 10
        assert strategy.multiplier == 2.0
        assert strategy.use_middle_cross is False
        assert strategy.name == "Keltner_20_10_2.0"

    def test_create_keltner_strategy_custom_params(self):
        args = argparse.Namespace(
            strategy="keltner",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=15,
            kc_atr_period=5,
            kc_multiplier=1.5,
            kc_use_middle_cross=True,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, KeltnerChannelStrategy)
        assert strategy.ema_period == 15
        assert strategy.atr_period == 5
        assert strategy.multiplier == 1.5
        assert strategy.use_middle_cross is True
        assert strategy.name == "Keltner_15_5_1.5"

    def test_create_stoch_strategy(self):
        args = argparse.Namespace(
            strategy="stoch",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=20,
            kc_atr_period=10,
            kc_multiplier=2.0,
            kc_use_middle_cross=False,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, StochasticOscillatorStrategy)
        assert strategy.k_period == 14
        assert strategy.d_period == 3
        assert strategy.oversold == 20
        assert strategy.overbought == 80
        assert strategy.use_midline is False
        assert strategy.name == "Stoch_14_3_20_80"

    def test_create_stoch_strategy_custom_params(self):
        args = argparse.Namespace(
            strategy="stoch",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=20,
            kc_atr_period=10,
            kc_multiplier=2.0,
            kc_use_middle_cross=False,
            stoch_k_period=10,
            stoch_d_period=2,
            stoch_oversold=25,
            stoch_overbought=75,
            stoch_use_midline=True,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, StochasticOscillatorStrategy)
        assert strategy.k_period == 10
        assert strategy.d_period == 2
        assert strategy.oversold == 25
        assert strategy.overbought == 75
        assert strategy.use_midline is True
        assert strategy.name == "Stoch_10_2_25_75"

    def test_create_vwap_strategy(self):
        args = argparse.Namespace(
            strategy="vwap",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            dc_period=20,
            dc_exit_period=20,
            aroon_period=25,
            kc_ema_period=20,
            kc_atr_period=10,
            kc_multiplier=2.0,
            kc_use_middle_cross=False,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
        )
        strategy = create_strategy(args)
        assert isinstance(strategy, VWAPStrategy)
        assert strategy.name == "VWAP"

    def test_create_strategy_from_config_ma(self):
        """create_strategy uses --strategy-config YAML when provided."""
        import yaml

        config = {
            "type": "ma",
            "name": "ConfigMA",
            "parameters": {"fast_period": 15, "slow_period": 40},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name

        try:
            args = argparse.Namespace(strategy="ma", strategy_config=config_path)
            strategy = create_strategy(args)
            assert isinstance(strategy, MovingAverageCrossover)
            assert strategy.fast_period == 15
            assert strategy.slow_period == 40
            assert strategy.name == "ConfigMA"
        finally:
            import os

            os.unlink(config_path)

    def test_create_strategy_from_config_rsi(self):
        """create_strategy respects parameters from YAML for RSI."""
        import yaml

        config = {
            "type": "rsi",
            "name": "ConfigRSI",
            "parameters": {"period": 21, "oversold": 25, "overbought": 75},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name

        try:
            args = argparse.Namespace(strategy="rsi", strategy_config=config_path)
            strategy = create_strategy(args)
            assert isinstance(strategy, RSIStrategy)
            assert strategy.period == 21
            assert strategy.oversold == 25
            assert strategy.overbought == 75
            assert strategy.name == "ConfigRSI"
        finally:
            import os

            os.unlink(config_path)

    def test_create_strategy_from_config_missing_type_raises(self):
        """create_strategy raises ValueError when YAML lacks 'type'."""
        import yaml

        config = {"name": "NoType", "parameters": {}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name

        try:
            args = argparse.Namespace(strategy="ma", strategy_config=config_path)
            with pytest.raises(ValueError):
                create_strategy(args)
        finally:
            import os

            os.unlink(config_path)


class TestCreateConfig:
    """Tests for create_config function."""

    def test_create_config_defaults(self):
        args = argparse.Namespace(
            config=None,
            offline=False,
            provider=None,
            cache_dir=None,
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key=None,
            risk_free_rate=None,
        )
        config = create_config(args)
        assert isinstance(config, Config)
        assert config.data.provider == "yfinance"

    def test_create_config_offline(self):
        args = argparse.Namespace(
            config=None,
            offline=True,
            provider=None,
            cache_dir=None,
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key=None,
            risk_free_rate=None,
        )
        config = create_config(args)
        assert config.data.provider == "synthetic"
        assert config.data.offline is True

    def test_create_config_provider_override(self):
        args = argparse.Namespace(
            config=None,
            offline=False,
            provider="alphavantage",
            cache_dir=None,
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key=None,
            risk_free_rate=None,
        )
        config = create_config(args)
        assert config.data.provider == "alphavantage"

    def test_create_config_alphavantage_key(self):
        args = argparse.Namespace(
            config=None,
            offline=False,
            provider="alphavantage",
            cache_dir=None,
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key="MY_API_KEY",
            risk_free_rate=None,
        )
        config = create_config(args)
        assert config.data.provider == "alphavantage"
        assert config.data.alphavantage_api_key == "MY_API_KEY"

    def test_create_config_cache_dir(self):
        args = argparse.Namespace(
            config=None,
            offline=False,
            provider=None,
            cache_dir="./custom/cache",
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key=None,
            risk_free_rate=None,
        )
        config = create_config(args)
        assert config.data.cache_dir == "./custom/cache"

    def test_create_config_synthetic_days_seed(self):
        args = argparse.Namespace(
            config=None,
            offline=True,
            provider=None,
            cache_dir=None,
            synthetic_days=500,
            synthetic_seed=123,
            alphavantage_key=None,
            risk_free_rate=None,
        )
        config = create_config(args)
        assert config.data.offline is True
        assert config.data.synthetic_days == 500
        assert config.data.synthetic_seed == 123

    def test_create_param_grid_ichimoku(self):
        from examples.cli import create_param_grid
        from quant_trading.optimization import ParameterGrid

        # Set up args with ichimoku strategy and custom ranges
        args = argparse.Namespace(
            strategy="ichimoku",
            ichimoku_tenkan_period_range="5,15,2",
            ichimoku_kijun_period_range="10,30,5",
            ichimoku_senkou_b_period_range="20,60,10",
            # Other strategy ranges (irrelevant for ichimoku but required for Namespace)
            ma_fast_range="5,20,5",
            ma_slow_range="20,50,5",
            rsi_period_range="10,20,2",
            rsi_oversold_range="20,35,5",
            rsi_overbought_range="65,80,5",
            bb_period_range="10,30,5",
            bb_std_range="1.5,3.0,0.5",
            macd_fast_range="8,16,2",
            macd_slow_range="20,30,2",
            macd_signal_range="7,12,1",
            st_period_range="7,20,1",
            st_multiplier_range="2.0,4.0,0.5",
            dc_period_range="10,40,5",
            dc_exit_period_range="5,20,5",
            aroon_period_range="10,50,5",
            kc_ema_period_range="10,30,5",
            kc_atr_period_range="5,20,2",
            kc_multiplier_range="1.0,3.0,0.5",
            stoch_k_period_range="10,20,2",
            stoch_d_period_range="2,5,1",
            stoch_oversold_range="10,30,5",
            stoch_overbought_range="70,90,5",
        )

        grid = create_param_grid(args)
        assert isinstance(grid, ParameterGrid)

        # Check that we added three parameter spaces
        assert len(grid.spaces) == 3
        # Check each space by name
        tenkan_space = grid.spaces.get("tenkan_period")
        assert tenkan_space is not None
        assert tenkan_space.min_val == 5.0
        assert tenkan_space.max_val == 15.0
        assert tenkan_space.step == 2.0
        assert tenkan_space.param_type == int

        kijun_space = grid.spaces.get("kijun_period")
        assert kijun_space is not None
        assert kijun_space.min_val == 10.0
        assert kijun_space.max_val == 30.0
        assert kijun_space.step == 5.0
        assert kijun_space.param_type == int

        senkou_b_space = grid.spaces.get("senkou_b_period")
        assert senkou_b_space is not None
        assert senkou_b_space.min_val == 20.0
        assert senkou_b_space.max_val == 60.0
        assert senkou_b_space.step == 10.0
        assert senkou_b_space.param_type == int

        # Check the validator
        assert grid.validator is not None
        # Valid parameters: tenkan < kijun and senkou_b > kijun
        assert (
            grid.validator({"tenkan_period": 5, "kijun_period": 10, "senkou_b_period": 20}) is True
        )
        assert (
            grid.validator({"tenkan_period": 5, "kijun_period": 10, "senkou_b_period": 10}) is False
        )  # senkou_b not > kijun
        assert (
            grid.validator({"tenkan_period": 15, "kijun_period": 10, "senkou_b_period": 20})
            is False
        )  # tenkan not < kijun
        assert (
            grid.validator({"tenkan_period": 5, "kijun_period": 20, "senkou_b_period": 30}) is True
        )

    def test_create_param_grid_sar(self):
        from examples.cli import create_param_grid
        from quant_trading.optimization import ParameterGrid

        args = argparse.Namespace(
            strategy="sar",
            sar_step_range="0.01,0.05,0.01",
            sar_max_step_range="0.10,0.20,0.05",
            # Other strategy ranges (irrelevant for sar but required for Namespace)
            ma_fast_range="5,20,5",
            ma_slow_range="20,50,5",
            rsi_period_range="10,20,2",
            rsi_oversold_range="20,35,5",
            rsi_overbought_range="65,80,5",
            bb_period_range="10,30,5",
            bb_std_range="1.5,3.0,0.5",
            macd_fast_range="8,16,2",
            macd_slow_range="20,30,2",
            macd_signal_range="7,12,1",
            st_period_range="7,20,1",
            st_multiplier_range="2.0,4.0,0.5",
            dc_period_range="10,40,5",
            dc_exit_period_range="5,20,5",
            aroon_period_range="10,50,5",
            kc_ema_period_range="10,30,5",
            kc_atr_period_range="5,20,2",
            kc_multiplier_range="1.0,3.0,0.5",
            stoch_k_period_range="10,20,2",
            stoch_d_period_range="2,5,1",
            stoch_oversold_range="10,30,5",
            stoch_overbought_range="70,90,5",
            ichimoku_tenkan_period_range="5,15,2",
            ichimoku_kijun_period_range="10,30,5",
            ichimoku_senkou_b_period_range="20,60,10",
        )

        grid = create_param_grid(args)
        assert isinstance(grid, ParameterGrid)

        # Check that we added two parameter spaces
        assert len(grid.spaces) == 2
        step_space = grid.spaces.get("step")
        assert step_space is not None
        assert step_space.min_val == 0.01
        assert step_space.max_val == 0.05
        assert step_space.step == 0.01
        assert step_space.param_type == float

        max_step_space = grid.spaces.get("max_step")
        assert max_step_space is not None
        assert max_step_space.min_val == 0.10
        assert max_step_space.max_val == 0.20
        assert max_step_space.step == 0.05
        assert max_step_space.param_type == float

        # Check the validator enforces step <= max_step
        assert grid.validator is not None
        assert grid.validator({"step": 0.01, "max_step": 0.10}) is True
        assert grid.validator({"step": 0.05, "max_step": 0.05}) is True  # equal is allowed
        assert grid.validator({"step": 0.05, "max_step": 0.10}) is True
        assert grid.validator({"step": 0.10, "max_step": 0.05}) is False  # step > max_step

        # Every generated combination must satisfy the validator
        combos = grid.generate_combinations()
        assert len(combos) > 0
        assert all(c["step"] <= c["max_step"] for c in combos)

    def test_create_param_grid_vwap(self):
        from examples.cli import create_param_grid
        from quant_trading.optimization import ParameterGrid

        args = argparse.Namespace(
            strategy="vwap",
            ma_fast_range="5,20,5",
            ma_slow_range="20,50,5",
            rsi_period_range="10,20,2",
            rsi_oversold_range="20,35,5",
            rsi_overbought_range="65,80,5",
            bb_period_range="10,30,5",
            bb_std_range="1.5,3.0,0.5",
            macd_fast_range="8,16,2",
            macd_slow_range="20,30,2",
            macd_signal_range="7,12,1",
            st_period_range="7,20,1",
            st_multiplier_range="2.0,4.0,0.5",
            dc_period_range="10,40,5",
            dc_exit_period_range="5,20,5",
            aroon_period_range="10,50,5",
            kc_ema_period_range="10,30,5",
            kc_atr_period_range="5,20,2",
            kc_multiplier_range="1.0,3.0,0.5",
            stoch_k_period_range="10,20,2",
            stoch_d_period_range="2,5,1",
            stoch_oversold_range="10,30,5",
            stoch_overbought_range="70,90,5",
            ichimoku_tenkan_period_range="5,15,2",
            ichimoku_kijun_period_range="10,30,5",
            ichimoku_senkou_b_period_range="20,60,10",
            sar_step_range="0.01,0.05,0.01",
            sar_max_step_range="0.10,0.20,0.05",
        )

        grid = create_param_grid(args)
        assert isinstance(grid, ParameterGrid)
        # VWAP has no parameters - should have empty or minimal grid
        assert len(grid.spaces) == 0
        combos = grid.generate_combinations()
        assert len(combos) == 1  # Single empty combination
        assert combos[0] == {}

    def test_create_param_grid_keltner(self):
        from examples.cli import create_param_grid
        from quant_trading.optimization import ParameterGrid

        args = argparse.Namespace(
            strategy="keltner",
            kc_ema_period_range="10,30,5",
            kc_atr_period_range="5,20,2",
            kc_multiplier_range="1.0,3.0,0.5",
            ma_fast_range="5,20,5",
            ma_slow_range="20,50,5",
            rsi_period_range="10,20,2",
            rsi_oversold_range="20,35,5",
            rsi_overbought_range="65,80,5",
            bb_period_range="10,30,5",
            bb_std_range="1.5,3.0,0.5",
            macd_fast_range="8,16,2",
            macd_slow_range="20,30,2",
            macd_signal_range="7,12,1",
            st_period_range="7,20,1",
            st_multiplier_range="2.0,4.0,0.5",
            dc_period_range="10,40,5",
            dc_exit_period_range="5,20,5",
            aroon_period_range="10,50,5",
            stoch_k_period_range="10,20,2",
            stoch_d_period_range="2,5,1",
            stoch_oversold_range="10,30,5",
            stoch_overbought_range="70,90,5",
            ichimoku_tenkan_period_range="5,15,2",
            ichimoku_kijun_period_range="10,30,5",
            ichimoku_senkou_b_period_range="20,60,10",
            sar_step_range="0.01,0.05,0.01",
            sar_max_step_range="0.10,0.20,0.05",
        )

        grid = create_param_grid(args)
        assert isinstance(grid, ParameterGrid)

        assert len(grid.spaces) == 4
        ema_space = grid.spaces.get("ema_period")
        assert ema_space is not None
        assert ema_space.min_val == 10.0
        assert ema_space.max_val == 30.0
        assert ema_space.step == 5.0
        assert ema_space.param_type == int

        atr_space = grid.spaces.get("atr_period")
        assert atr_space is not None
        assert atr_space.min_val == 5.0
        assert atr_space.max_val == 20.0
        assert atr_space.step == 2.0
        assert atr_space.param_type == int

        mult_space = grid.spaces.get("multiplier")
        assert mult_space is not None
        assert mult_space.min_val == 1.0
        assert mult_space.max_val == 3.0
        assert mult_space.step == 0.5
        assert mult_space.param_type == float

        use_middle_space = grid.spaces.get("use_middle_cross")
        assert use_middle_space is not None
        assert use_middle_space.param_type == bool

        combos = grid.generate_combinations()
        assert len(combos) > 0
        assert all(c["multiplier"] > 0 for c in combos)

    def test_create_param_grid_stoch(self):
        from examples.cli import create_param_grid
        from quant_trading.optimization import ParameterGrid

        args = argparse.Namespace(
            strategy="stoch",
            stoch_k_period_range="10,20,2",
            stoch_d_period_range="2,5,1",
            stoch_oversold_range="10,30,5",
            stoch_overbought_range="70,90,5",
            ma_fast_range="5,20,5",
            ma_slow_range="20,50,5",
            rsi_period_range="10,20,2",
            rsi_oversold_range="20,35,5",
            rsi_overbought_range="65,80,5",
            bb_period_range="10,30,5",
            bb_std_range="1.5,3.0,0.5",
            macd_fast_range="8,16,2",
            macd_slow_range="20,30,2",
            macd_signal_range="7,12,1",
            st_period_range="7,20,1",
            st_multiplier_range="2.0,4.0,0.5",
            dc_period_range="10,40,5",
            dc_exit_period_range="5,20,5",
            aroon_period_range="10,50,5",
            kc_ema_period_range="10,30,5",
            kc_atr_period_range="5,20,2",
            kc_multiplier_range="1.0,3.0,0.5",
            ichimoku_tenkan_period_range="5,15,2",
            ichimoku_kijun_period_range="10,30,5",
            ichimoku_senkou_b_period_range="20,60,10",
            sar_step_range="0.01,0.05,0.01",
            sar_max_step_range="0.10,0.20,0.05",
        )

        grid = create_param_grid(args)
        assert isinstance(grid, ParameterGrid)

        assert len(grid.spaces) == 5
        k_space = grid.spaces.get("k_period")
        assert k_space is not None
        assert k_space.min_val == 10.0
        assert k_space.max_val == 20.0
        assert k_space.step == 2.0
        assert k_space.param_type == int

        d_space = grid.spaces.get("d_period")
        assert d_space is not None
        assert d_space.min_val == 2.0
        assert d_space.max_val == 5.0
        assert d_space.step == 1.0
        assert d_space.param_type == int

        oversold_space = grid.spaces.get("oversold")
        assert oversold_space is not None
        assert oversold_space.min_val == 10.0
        assert oversold_space.max_val == 30.0
        assert oversold_space.step == 5.0
        assert oversold_space.param_type == int

        overbought_space = grid.spaces.get("overbought")
        assert overbought_space is not None
        assert overbought_space.min_val == 70.0
        assert overbought_space.max_val == 90.0
        assert overbought_space.step == 5.0
        assert overbought_space.param_type == int

        use_midline_space = grid.spaces.get("use_midline")
        assert use_midline_space is not None
        assert use_midline_space.param_type == bool

        # The validator enforces oversold < overbought.
        assert grid.validator is not None
        assert grid.validator({"oversold": 10, "overbought": 70}) is True
        assert grid.validator({"oversold": 30, "overbought": 70}) is True
        assert grid.validator({"oversold": 70, "overbought": 70}) is False
        assert grid.validator({"oversold": 90, "overbought": 70}) is False

        combos = grid.generate_combinations()
        assert len(combos) > 0
        assert all(c["oversold"] < c["overbought"] for c in combos)

    def test_create_param_grid_every_strategy_has_search_space(self):
        """Every registered strategy gets a non-empty optimization grid.

        Strategies with dedicated ``--*-range`` flags are covered
        individually; every other strategy falls back to
        ``_default_param_grid`` built from its constructor parameters.
        VWAP is the single exception: it has no configurable parameters,
        so its grid is empty by design and --optimize evaluates one
        default-parameter combination.
        """
        from examples.cli import create_param_grid
        from quant_trading.strategies.factory import get_registry

        range_defaults = {
            "ma_fast_range": "5,20,5",
            "ma_slow_range": "20,50,5",
            "rsi_period_range": "10,20,2",
            "rsi_oversold_range": "20,35,5",
            "rsi_overbought_range": "65,80,5",
            "bb_period_range": "10,30,5",
            "bb_std_range": "1.5,3.0,0.5",
            "macd_fast_range": "8,16,2",
            "macd_slow_range": "20,30,2",
            "macd_signal_range": "7,12,1",
            "st_period_range": "7,20,1",
            "st_multiplier_range": "2.0,4.0,0.5",
            "dc_period_range": "10,40,5",
            "dc_exit_period_range": "5,20,5",
            "aroon_period_range": "10,50,5",
            "kc_ema_period_range": "10,30,5",
            "kc_atr_period_range": "5,20,2",
            "kc_multiplier_range": "1.0,3.0,0.5",
            "stoch_k_period_range": "10,20,2",
            "stoch_d_period_range": "2,5,1",
            "stoch_oversold_range": "10,30,5",
            "stoch_overbought_range": "70,90,5",
            "ichimoku_tenkan_period_range": "5,15,2",
            "ichimoku_kijun_period_range": "10,30,5",
            "ichimoku_senkou_b_period_range": "20,60,10",
            "sar_step_range": "0.01,0.05,0.01",
            "sar_max_step_range": "0.10,0.20,0.05",
            "atr_period_range": "10,30,5",
            "atr_multiplier_range": "1.0,3.0,0.5",
        }
        registry = get_registry()
        empty = []
        for key in registry.primary_keys():
            args = argparse.Namespace(strategy=key, **range_defaults)
            grid = create_param_grid(args)
            combos = grid.generate_combinations()
            if key == "vwap":
                assert len(grid.spaces) == 0
                assert len(combos) == 1
                assert combos[0] == {}
                continue
            if len(grid.spaces) == 0 or len(combos) == 0:
                empty.append(key)
        assert not empty, (
            "strategies with no optimization search space: "
            f"{sorted(empty)}. Every strategy except vwap needs at least one "
            "tunable parameter so --optimize never runs an empty grid."
        )


class TestRunCombined:
    """Tests for run_combined function."""

    @patch("examples.cli.run_backtest")
    def test_run_combined_all_strategies(self, mock_run_backtest, capsys):
        # Mock backtest results
        from quant_trading.backtest.metrics import BacktestMetrics

        mock_metrics = MagicMock(spec=BacktestMetrics)
        mock_metrics.num_trades = 10
        mock_metrics.win_rate = 0.6
        mock_metrics.sharpe_ratio = 1.5
        mock_metrics.max_drawdown_pct = 5.0
        mock_metrics.profit_factor = 2.0
        mock_metrics.total_pnl = 0.0
        mock_metrics.unrealized_pnl = 0.0

        mock_results = []
        for name, ret in [
            ("MA_Crossover_10_30", 15.5),
            ("RSI_14", 12.3),
            ("BB_20_2.0", 18.7),
            ("Bollinger_Percent_B", 17.0),
            ("MACD_12_26_9", 10.0),
            ("SuperTrend_10_3.0", 8.5),
            ("Donchian_20_20", 14.2),
            ("Aroon_25", 11.0),
            ("Keltner_20_10_2.0", 13.0),
            ("Stoch_14_3_20_80", 12.5),
            ("StochRSI", 12.0),
            ("Ichimoku_Cloud", 9.0),
            ("Parabolic_SAR_0.02_0.2", 7.5),
            ("VWAP", 5.0),
            ("Vortex", 17.0),
            ("EMA_Crossover_10_30", 6.5),
            ("Momentum", 9.5),
            ("ADX", 11.0),
            ("CCI", 10.0),
            ("Williams %R", 12.0),
            ("OBV", 13.0),
            ("Chaikin_Money_Flow", 11.5),
            ("Force_Index", 12.5),
            ("Money_Flow_Index", 13.5),
            ("Elder_Ray", 14.0),
            ("Rate_Of_Change", 14.5),
            ("Volume_Rate_Of_Change", 15.0),
            ("Volume_Oscillator", 16.0),
            ("Volume_Price_Trend", 16.0),
            ("Hull_Moving_Average", 16.0),
            ("Negative_Volume_Index", 16.0),
            ("Positive_Volume_Index", 16.0),
            ("Stochastic_Momentum_Index", 16.5),
            ("Percentage_Volume_Oscillator", 15.8),
            ("Percentage_Price_Oscillator", 15.9),
            ("Ease_Of_Movement", 17.5),
            ("Chaikin_Oscillator", 16.5),
            ("Choppiness_Index", 16.0),
            ("Awesome_Oscillator", 12.8),
            ("Chande_Momentum_Oscillator", 15.5),
            ("TRIX", 14.0),
            ("Ultimate_Oscillator", 13.2),
            ("Klinger_Oscillator", 12.9),
            ("Detrended_Price_Oscillator", 10.0),
            ("Accumulation_Distribution", 11.0),
            ("ATR_14_2.0", 16.0),
        ]:
            m = MagicMock(
                spec=[
                    "name",
                    "total_return_pct",
                    "metrics",
                    "initial_capital",
                    "final_value",
                    "total_return",
                    "total_costs",
                ]
            )
            m.name = name
            m.total_return_pct = ret
            m.metrics = mock_metrics
            m.initial_capital = 100000.0
            m.final_value = 100000.0 * (1 + ret / 100)
            m.total_return = 100000.0 * ret / 100
            m.total_costs = 0.0
            mock_results.append(m)

        def side_effect(*args, **kwargs):
            strategy = kwargs.get("strategy")
            for result in mock_results:
                if result.name == strategy.name:
                    return result
            raise ValueError("Unknown strategy")

        mock_run_backtest.side_effect = side_effect

        args = argparse.Namespace(
            symbols=["AAPL"],
            strategy="ma",
            combined=True,
            initial_capital=100000.0,
            commission=0.001,
            slippage=0.0005,
            interval="1d",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            aroon_period=25,
            dc_period=20,
            dc_exit_period=20,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
            sar_step=0.02,
            sar_max_step=0.20,
            tenkan_period=9,
            kijun_period=26,
            senkou_b_period=52,
            output=None,
        )

        config = Config()
        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        result = run_combined(args, config, start_date, end_date)
        assert result == 0

        captured = capsys.readouterr()
        assert "Running combined backtest for all strategies" in captured.out
        assert "Strategy Comparison" in captured.out
        assert "MA_Crossover_10_30" in captured.out
        assert "RSI_14" in captured.out
        assert "BB_20_2.0" in captured.out
        assert "SuperTrend_10_3.0" in captured.out
        assert "Donchian_20_20" in captured.out
        assert "Aroon_25" in captured.out
        assert "Keltner_20_10_2.0" in captured.out
        assert "ATR_14_2.0" in captured.out
        assert "Stoch_14_3_20_80" in captured.out
        assert "Ichimoku_Cloud" in captured.out
        assert "Parabolic_SAR" in captured.out
        assert "ADX" in captured.out
        assert "CCI" in captured.out
        assert "Williams %R" in captured.out
        assert "OBV" in captured.out
        assert "Chaikin_Money_Flow" in captured.out
        assert "Force_Index" in captured.out
        assert "Money_Flow_Index" in captured.out
        assert "Volume_Rate_Of_Change" in captured.out
        assert "Ease_Of_Movement" in captured.out
        assert "Chande_Momentum_Oscillator" in captured.out
        assert "Hull_Moving_Average" in captured.out
        assert "Best strategy (by Sharpe)" in captured.out

    @patch("examples.cli.run_backtest")
    def test_run_combined_with_output(self, mock_run_backtest, capsys):
        from quant_trading.backtest.metrics import BacktestMetrics

        mock_metrics = MagicMock(spec=BacktestMetrics)
        mock_metrics.num_trades = 10
        mock_metrics.win_rate = 0.6
        mock_metrics.sharpe_ratio = 1.5
        mock_metrics.max_drawdown_pct = 5.0
        mock_metrics.profit_factor = 2.0
        mock_metrics.total_pnl = 0.0
        mock_metrics.unrealized_pnl = 0.0

        mock_result = MagicMock(
            spec=[
                "name",
                "total_return_pct",
                "metrics",
                "initial_capital",
                "final_value",
                "total_return",
                "total_costs",
            ]
        )
        mock_result.name = "MA_Crossover_10_30"
        mock_result.total_return_pct = 15.5
        mock_result.metrics = mock_metrics
        mock_result.initial_capital = 100000.0
        mock_result.final_value = 115500.0
        mock_result.total_return = 15500.0
        mock_result.total_costs = 0.0

        def side_effect(*args, **kwargs):
            return mock_result

        mock_run_backtest.side_effect = side_effect

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/results.json"
            args = argparse.Namespace(
                symbols=["AAPL"],
                strategy="ma",
                combined=True,
                initial_capital=100000.0,
                commission=0.001,
                slippage=0.0005,
                interval="1d",
                fast_period=10,
                slow_period=30,
                rsi_period=14,
                rsi_oversold=30,
                rsi_overbought=70,
                bb_period=20,
                bb_std=2.0,
                st_period=10,
                st_multiplier=3.0,
                aroon_period=25,
                output=output_path,
            )

            config = Config()
            from datetime import datetime, timedelta

            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)

            result = run_combined(args, config, start_date, end_date)
            assert result == 0

            # Verify output file
            with open(output_path) as f:
                data = json.load(f)
            assert "comparison" in data
            assert "best_strategy" in data

    def test_main_offline_combined_end_to_end(self, capsys):
        """Running offline --combined executes all strategies end-to-end (no mocks)."""
        args = [
            "--offline",
            "--combined",
            "--symbols",
            "AAPL",
            "--days",
            "120",
        ]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Running combined backtest for all strategies" in captured.out
        assert "Strategy Comparison" in captured.out
        assert "MA_Crossover_10_30" in captured.out
        assert "RSI_14" in captured.out
        assert "Ichimoku_Cloud" in captured.out
        assert "VWAP" in captured.out
        assert "Best strategy (by Sharpe)" in captured.out

    def test_main_offline_combined_with_output(self, capsys):
        """Running offline --combined with --output writes a JSON comparison file."""
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/combined.json"
            args = [
                "--offline",
                "--combined",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "120",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            assert os.path.exists(output_path)

            with open(output_path) as f:
                data = json.load(f)
            assert "comparison" in data
            assert "best_strategy" in data
            assert len(data["comparison"]) > 0
            assert all("strategy" in entry for entry in data["comparison"])
            # The combined-mode JSON carries the realized/unrealized PnL split,
            # so the reconciliation identity can be read from the file too.
            for entry in data["comparison"]:
                assert "total_pnl" in entry
                assert "unrealized_pnl" in entry
                assert "total_return" in entry

    @patch("examples.cli.run_backtest")
    def test_run_combined_strategy_error_returns_one(self, mock_run_backtest, capsys):
        """When a strategy raises an error, combined mode prints it and returns 1."""
        from quant_trading.backtest.metrics import BacktestMetrics

        mock_metrics = MagicMock(spec=BacktestMetrics)
        mock_metrics.num_trades = 10
        mock_metrics.win_rate = 0.6
        mock_metrics.sharpe_ratio = 1.5
        mock_metrics.max_drawdown_pct = 5.0
        mock_metrics.profit_factor = 2.0
        mock_metrics.total_pnl = 0.0
        mock_metrics.unrealized_pnl = 0.0

        def side_effect(*args, **kwargs):
            strategy = kwargs.get("strategy")
            if strategy.name == "RSI_14":
                raise ValueError("RSI strategy failed")
            mock_result = MagicMock(
                spec=[
                    "name",
                    "total_return_pct",
                    "metrics",
                    "initial_capital",
                    "final_value",
                    "total_return",
                    "total_costs",
                ]
            )
            mock_result.name = strategy.name
            mock_result.total_return_pct = 15.5
            mock_result.metrics = mock_metrics
            mock_result.initial_capital = 100000.0
            mock_result.final_value = 115500.0
            mock_result.total_return = 15500.0
            mock_result.total_costs = 0.0
            return mock_result

        mock_run_backtest.side_effect = side_effect

        args = argparse.Namespace(
            symbols=["AAPL"],
            strategy="ma",
            combined=True,
            initial_capital=100000.0,
            commission=0.001,
            slippage=0.0005,
            interval="1d",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            aroon_period=25,
            dc_period=20,
            dc_exit_period=20,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
            sar_step=0.02,
            sar_max_step=0.20,
            tenkan_period=9,
            kijun_period=26,
            senkou_b_period=52,
            output=None,
        )

        config = Config()
        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        result = run_combined(args, config, start_date, end_date)
        assert result == 1

        captured = capsys.readouterr()
        assert "Error - RSI strategy failed" in captured.out
        assert "✗" in captured.out

    @patch("examples.cli.run_backtest")
    def test_run_combined_all_strategies_fail_returns_one(self, mock_run_backtest, capsys):
        """When the first strategy fails, combined mode returns 1 immediately."""
        mock_run_backtest.side_effect = RuntimeError("data unavailable")

        args = argparse.Namespace(
            symbols=["AAPL"],
            strategy="ma",
            combined=True,
            initial_capital=100000.0,
            commission=0.001,
            slippage=0.0005,
            interval="1d",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            aroon_period=25,
            dc_period=20,
            dc_exit_period=20,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
            sar_step=0.02,
            sar_max_step=0.20,
            tenkan_period=9,
            kijun_period=26,
            senkou_b_period=52,
            output=None,
        )

        config = Config()
        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        result = run_combined(args, config, start_date, end_date)
        assert result == 1

        captured = capsys.readouterr()
        assert "Error - data unavailable" in captured.out
        assert "✗" in captured.out

    def test_run_combined_report_import_error_returns_one(self, capsys, tmp_path, monkeypatch):
        """Missing matplotlib in combined mode --report is a one-line error."""
        from examples.cli import run_combined

        def _raise_import_error(*args, **kwargs):
            raise ImportError(
                "matplotlib is required for chart generation. "
                "Install with: pip install quant-trading[reporting]"
            )

        monkeypatch.setattr("examples.cli.generate_comparison_report", _raise_import_error)

        report_path = tmp_path / "combined_report.html"
        args = argparse.Namespace(
            symbols=["AAPL"],
            strategy="ma",
            combined=True,
            initial_capital=100000.0,
            commission=0.001,
            slippage=0.0005,
            interval="1d",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            aroon_period=25,
            dc_period=20,
            dc_exit_period=20,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
            sar_step=0.02,
            sar_max_step=0.20,
            tenkan_period=9,
            kijun_period=26,
            senkou_b_period=52,
            output=None,
            report=str(report_path),
            report_theme="light",
            report_no_charts=False,
            report_no_trades=False,
            report_no_monthly=False,
            report_no_rolling=False,
        )

        config = Config()
        config.data.provider = "synthetic"
        config.data.offline = True
        config.data.synthetic_days = 60
        config.data.synthetic_seed = 42

        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)

        result = run_combined(args, config, start_date, end_date)
        assert result == 1

        captured = capsys.readouterr()
        assert "matplotlib" in captured.out
        assert "Traceback" not in captured.out

    def test_run_combined_report_os_error_returns_one(self, capsys, tmp_path, monkeypatch):
        """File write error in combined mode --report is a one-line error."""
        from examples.cli import run_combined

        def _raise_os_error(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr("examples.cli.generate_comparison_report", _raise_os_error)

        report_path = tmp_path / "combined_report.html"
        args = argparse.Namespace(
            symbols=["AAPL"],
            strategy="ma",
            combined=True,
            initial_capital=100000.0,
            commission=0.001,
            slippage=0.0005,
            interval="1d",
            fast_period=10,
            slow_period=30,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            bb_period=20,
            bb_std=2.0,
            st_period=10,
            st_multiplier=3.0,
            aroon_period=25,
            dc_period=20,
            dc_exit_period=20,
            stoch_k_period=14,
            stoch_d_period=3,
            stoch_oversold=20,
            stoch_overbought=80,
            stoch_use_midline=False,
            sar_step=0.02,
            sar_max_step=0.20,
            tenkan_period=9,
            kijun_period=26,
            senkou_b_period=52,
            output=None,
            report=str(report_path),
            report_theme="light",
            report_no_charts=False,
            report_no_trades=False,
            report_no_monthly=False,
            report_no_rolling=False,
        )

        config = Config()
        config.data.provider = "synthetic"
        config.data.offline = True
        config.data.synthetic_days = 60
        config.data.synthetic_seed = 42

        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)

        result = run_combined(args, config, start_date, end_date)
        assert result == 1

        captured = capsys.readouterr()
        assert "could not write report file" in captured.out
        assert "Permission denied" in captured.out
        assert "Traceback" not in captured.out


class TestMain:
    """Tests for main function."""

    @patch("examples.cli.list_strategies")
    def test_main_list_strategies(self, mock_list_strategies):
        mock_list_strategies.return_value = 0
        args = ["--list-strategies"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0
        mock_list_strategies.assert_called_once()

    @patch("examples.cli.list_providers")
    def test_main_list_providers(self, mock_list_providers):
        mock_list_providers.return_value = 0
        args = ["--list-providers"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0
        mock_list_providers.assert_called_once()

    @patch("examples.cli.init_config")
    def test_main_init_config(self, mock_init_config):
        mock_init_config.return_value = 0
        args = ["--init-config", "config.yaml"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0
        mock_init_config.assert_called_once_with("config.yaml")

    @patch("examples.cli.validate_config")
    def test_main_validate_config(self, mock_validate_config):
        mock_validate_config.return_value = 0
        args = ["--validate-config", "config.yaml"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0
        mock_validate_config.assert_called_once_with("config.yaml")

    @patch("examples.cli.run_combined")
    def test_main_combined(self, mock_run_combined):
        mock_run_combined.return_value = 0
        args = ["--combined", "--offline"]
        with patch("sys.argv", ["cli.py"] + args), patch("examples.cli.run_backtest"):
            result = main()
        assert result == 0
        mock_run_combined.assert_called_once()

    def test_main_offline_regime_analysis(self, capsys):
        """Running offline with --regime prints a Market Regime Analysis block."""
        args = ["--offline", "--regime", "--symbols", "AAPL", "--days", "120"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Market Regime Analysis" in captured.out
        assert "Current Regime:" in captured.out
        assert "Regime Segments:" in captured.out

    def test_main_offline_monte_carlo_analysis(self, capsys):
        """Running offline with --monte-carlo prints a Monte Carlo Simulation block."""
        args = [
            "--offline",
            "--monte-carlo",
            "--mc-simulations",
            "60",
            "--mc-seed",
            "42",
            "--symbols",
            "AAPL",
            "--days",
            "120",
        ]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Monte Carlo Simulation" in captured.out
        assert "Probability of Profit" in captured.out
        assert "95% Confidence Intervals" in captured.out

    def test_main_offline_trade_analysis(self, capsys):
        """Running offline with --trade-analysis prints trade analysis."""
        args = ["--offline", "--trade-analysis", "--symbols", "AAPL", "--days", "120"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Total Trades" in captured.out or "Trade Analysis" in captured.out

    def test_main_with_start_end_dates(self):
        """Main with explicit start and end dates."""
        args = ["--offline", "--start", "2023-01-01", "--end", "2023-06-01", "--symbols", "AAPL"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

    def test_main_with_output_file(self, capsys):
        """Main with output file saves results."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/results.json"
            args = ["--offline", "--output", output_path, "--symbols", "AAPL", "--days", "120"]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            # Check file was created
            import os

            assert os.path.exists(output_path)

    def test_main_offline_ichimoku(self, capsys):
        """Running offline with ichimoku strategy should work and print Ichimoku_Cloud in output."""
        args = ["--offline", "--strategy", "ichimoku", "--symbols", "AAPL", "--days", "120"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Running backtest for Ichimoku_Cloud" in captured.out
        assert "Symbols:" in captured.out
        assert "Date range:" in captured.out
        assert (
            "Provider: synthetic" in captured.out
        )  # because --offline flag sets provider to synthetic
        assert "Mode: OFFLINE (synthetic data)" in captured.out
        # Check that the results block is printed
        assert "Results for: Ichimoku_Cloud" in captured.out
        assert "Initial Capital:" in captured.out
        assert "Final Value:" in captured.out
        assert "Total Return:" in captured.out
        assert "Total Costs:" in captured.out
        assert "Total Trades:" in captured.out
        assert "Win Rate:" in captured.out
        assert "Sharpe Ratio:" in captured.out
        assert "Max Drawdown:" in captured.out
        assert "Profit Factor:" in captured.out

    def test_main_offline_ichimoku_with_custom_params(self, capsys):
        """Running offline with ichimoku strategy and custom parameters."""
        args = [
            "--offline",
            "--strategy",
            "ichimoku",
            "--tenkan-period",
            "5",
            "--kijun-period",
            "15",
            "--senkou-b-period",
            "30",
            "--symbols",
            "AAPL",
            "--days",
            "120",
        ]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert (
            "Running backtest for Ichimoku_Cloud" in captured.out
        )  # name is still default because create_strategy doesn't customize name for ichimoku
        # Note: The strategy name is not customized in create_strategy for ichimoku, so it remains "Ichimoku_Cloud"
        # But we can check that the parameters were used by looking at the generated signals? Not in the CLI output.
        # However, we can at least verify that the run succeeded.
        assert "Results for: Ichimoku_Cloud" in captured.out

    def test_main_error_handling(self, capsys):
        """Main handles errors gracefully."""
        with patch("examples.cli.run_backtest") as mock_run:
            mock_run.side_effect = ValueError("Test error")
            args = ["--offline", "--symbols", "AAPL", "--days", "60"]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 1
            captured = capsys.readouterr()
            assert "Error running backtest" in captured.out

    def test_main_with_regime_monte_carlo_trade_analysis_output(self, capsys):
        """Main with all analysis flags and output."""
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/results.json"
            args = [
                "--offline",
                "--regime",
                "--monte-carlo",
                "--trade-analysis",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--mc-simulations",
                "30",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            with open(output_path) as f:
                data = json.load(f)
            assert "regime_analysis" in data
            assert "monte_carlo" in data
            assert "trade_analysis" in data
            assert "total_costs" in data

    def test_main_offline_optimize_ichimoku_calls_run_optimization(self):
        """Running offline with --optimize and ichimoku strategy calls run_optimization."""
        with patch("examples.cli.run_optimization") as mock_opt:
            mock_opt.return_value = 0
            args = ["--optimize", "--offline", "--strategy", "ichimoku", "--days", "60"]
            with patch("sys.argv", ["cli.py"] + args):
                from examples.cli import main

                result = main()
            assert result == 0
            mock_opt.assert_called_once()

    def test_main_offline_walk_forward_ichimoku_calls_run_walk_forward(self):
        """Running offline with --walk-forward and ichimoku strategy calls run_walk_forward."""
        with patch("examples.cli.run_walk_forward") as mock_wf:
            mock_wf.return_value = 0
            args = [
                "--walk-forward",
                "--offline",
                "--strategy",
                "ichimoku",
                "--days",
                "120",
                "--wf-windows",
                "2",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                from examples.cli import main

                result = main()
            assert result == 0
            mock_wf.assert_called_once()

    def test_main_system_exit_nonzero_returns_one(self, capsys):
        """main() converts non-zero SystemExit from argparse to exit code 1."""

        from examples.cli import main

        # Simulate argparse raising SystemExit(2) for invalid argument
        with patch("examples.cli.parse_args") as mock_parse:
            mock_parse.side_effect = SystemExit(2)
            result = main()
        assert result == 1

    def test_main_system_exit_zero_returns_zero(self, capsys):
        """main() converts SystemExit(0) to exit code 0."""
        from examples.cli import main

        with patch("examples.cli.parse_args") as mock_parse:
            mock_parse.side_effect = SystemExit(0)
            result = main()
        assert result == 0


class TestFactoryIntegration:
    """Tests for CLI integration with the strategy factory registry."""

    def test_factory_registry_used_for_create_strategy(self):
        """Test that create_strategy uses the factory registry."""
        from quant_trading.strategies import get_registry, register_strategy
        from quant_trading.strategies.base import Strategy

        class CustomStrategy(Strategy):
            def __init__(self, custom_param: int = 42, **kwargs):
                super().__init__(**kwargs)
                self.custom_param = custom_param

            def generate_signals(self, data, symbol: str):  # type: ignore[override]
                return 0

            def get_parameters(self):
                return {"custom_param": self.custom_param}

        # Register custom strategy
        register_strategy("custom", CustomStrategy, aliases=["cust"])

        try:
            # Verify it's in the registry
            registry = get_registry()
            assert registry.get("custom") is CustomStrategy
            assert registry.get("cust") is CustomStrategy
            assert "custom" in registry.primary_keys()
            registered_keys = registry.keys()
            assert "cust" in registered_keys

            # Test create_strategy uses factory (for built-in strategies still works)
            args = argparse.Namespace(
                strategy="ma",
                fast_period=10,
                slow_period=30,
                rsi_period=14,
                rsi_oversold=30,
                rsi_overbought=70,
                bb_period=20,
                bb_std=2.0,
                st_period=10,
                st_multiplier=3.0,
            )
            strategy = create_strategy(args)
            assert strategy is not None
            assert hasattr(strategy, "fast_period")

        finally:
            # Cleanup
            registry.unregister("custom")

    def test_list_strategies_uses_factory(self, capsys):
        """Test that list_strategies uses factory registry."""
        from quant_trading.strategies import get_registry, register_strategy
        from quant_trading.strategies.base import Strategy

        class TestStrategy(Strategy):
            def __init__(self, **kwargs):
                super().__init__(name="TestStrategy", **kwargs)

            def generate_signals(self, data, symbol: str):  # type: ignore[override]
                return 0

            def get_parameters(self):
                return {"test_param": 1}

        register_strategy("test_strat", TestStrategy)
        try:
            result = list_strategies()
            assert result == 0
            captured = capsys.readouterr()
            assert "test_strat" in captured.out
            assert "TestStrategy" in captured.out
        finally:
            get_registry().unregister("test_strat")

    def test_run_combined_iterates_registry_primary_keys(self):
        """Test that run_combined iterates over registry primary keys."""
        from unittest.mock import MagicMock, patch

        from quant_trading.strategies import get_registry, register_strategy
        from quant_trading.strategies.base import Strategy

        # Register a custom strategy
        class CustomStrategy(Strategy):
            def __init__(self, **kwargs):
                super().__init__(name="CustomStrategy", **kwargs)

            def generate_signals(self, data, symbol: str):  # type: ignore[override]
                return 0

            def get_parameters(self):
                return {}

        register_strategy("custom_for_combined", CustomStrategy)
        registry = get_registry()

        try:
            # Verify it's in primary keys
            assert "custom_for_combined" in registry.primary_keys()

            # Mock run_backtest to succeed quickly
            with patch("examples.cli.run_backtest") as mock_run:
                from quant_trading.backtest.metrics import BacktestMetrics

                mock_metrics = MagicMock(spec=BacktestMetrics)
                mock_metrics.num_trades = 1
                mock_metrics.win_rate = 0.5
                mock_metrics.sharpe_ratio = 1.0
                mock_metrics.max_drawdown_pct = 1.0
                mock_metrics.profit_factor = 1.0
                mock_metrics.total_pnl = 0.0
                mock_metrics.unrealized_pnl = 0.0

                mock_result = MagicMock()
                mock_result.name = "CustomStrategy"
                mock_result.total_return_pct = 5.0
                mock_result.metrics = mock_metrics
                mock_result.initial_capital = 100000.0
                mock_result.final_value = 105000.0
                mock_result.total_return = 5000.0
                mock_result.total_costs = 0.0
                mock_result.final_value = 105000.0
                mock_result.total_return = 5000.0
                mock_run.return_value = mock_result

                args = argparse.Namespace(
                    symbols=["AAPL"],
                    strategy="ma",
                    combined=True,
                    initial_capital=100000.0,
                    commission=0.001,
                    slippage=0.0005,
                    interval="1d",
                    fast_period=10,
                    slow_period=30,
                    rsi_period=14,
                    rsi_oversold=30,
                    rsi_overbought=70,
                    bb_period=20,
                    bb_std=2.0,
                    st_period=10,
                    st_multiplier=3.0,
                    aroon_period=25,
                    dc_period=20,
                    dc_exit_period=20,
                    stoch_k_period=14,
                    stoch_d_period=3,
                    stoch_oversold=20,
                    stoch_overbought=80,
                    stoch_use_midline=False,
                    sar_step=0.02,
                    sar_max_step=0.20,
                    tenkan_period=9,
                    kijun_period=26,
                    senkou_b_period=52,
                    output=None,
                )

                config = Config()
                from datetime import datetime, timedelta

                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)

                # This should iterate over all primary keys including custom
                result = run_combined(args, config, start_date, end_date)
                assert result == 0

                # Verify custom strategy was called
                strategy_names = [call.kwargs["strategy"].name for call in mock_run.call_args_list]
                assert any("CustomStrategy" in name for name in strategy_names)
        finally:
            registry.unregister("custom_for_combined")


class TestSaveStrategyConfig:
    """Tests for the --output-strategy-config flag in optimization modes."""

    def _make_args(self, **overrides):
        base = {
            "symbols": ["AAPL"],
            "strategy": "ma",
            "initial_capital": 100000.0,
            "commission": 0.001,
            "slippage": 0.0005,
            "interval": "1d",
            "fast_period": 10,
            "slow_period": 30,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "bb_period": 20,
            "bb_std": 2.0,
            "st_period": 10,
            "st_multiplier": 3.0,
            "aroon_period": 25,
            "dc_period": 20,
            "dc_exit_period": 20,
            "stoch_k_period": 14,
            "stoch_d_period": 3,
            "stoch_oversold": 20,
            "stoch_overbought": 80,
            "stoch_use_midline": False,
            "sar_step": 0.02,
            "sar_max_step": 0.20,
            "tenkan_period": 9,
            "kijun_period": 26,
            "senkou_b_period": 52,
            "optimizer": "grid",
            "objective": "sharpe",
            "n_iter": 5,
            "n_jobs": 1,
            "bayesian_n_initial": 3,
            "bayesian_acq_func": "gp_hedge",
            "bayesian_acq_optimizer": "lbfgs",
            "optimize": False,
            "walk_forward": False,
            "output": None,
            "output_strategy_config": None,
            "wf_windows": 3,
            "wf_train_size": 0.6,
            "wf_anchored": False,
            "wf_optimizer": "grid",
            "wf_step_size": None,
            # parameter ranges consumed by create_param_grid
            "ma_fast_range": "5,20,5",
            "ma_slow_range": "20,50,5",
            "rsi_period_range": "10,20,2",
            "rsi_oversold_range": "20,35,5",
            "rsi_overbought_range": "65,80,5",
            "bb_period_range": "10,30,5",
            "bb_std_range": "1.5,3.0,0.5",
            "macd_fast_range": "8,16,2",
            "macd_slow_range": "20,30,2",
            "macd_signal_range": "7,12,1",
            "st_period_range": "7,20,1",
            "st_multiplier_range": "2.0,4.0,0.5",
            "dc_period_range": "10,40,5",
            "dc_exit_period_range": "5,20,5",
            "aroon_period_range": "10,50,5",
            "kc_ema_period_range": "10,30,5",
            "kc_atr_period_range": "5,20,2",
            "kc_multiplier_range": "1.0,3.0,0.5",
            "stoch_k_period_range": "10,20,2",
            "stoch_d_period_range": "2,5,1",
            "stoch_oversold_range": "10,30,5",
            "stoch_overbought_range": "70,85,5",
            "ichimoku_tenkan_period_range": "5,15,2",
            "ichimoku_kijun_period_range": "15,30,2",
            "ichimoku_senkou_b_period_range": "30,60,5",
            "sar_step_range": "0.01,0.05,0.01",
            "sar_max_step_range": "0.10,0.20,0.05",
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_optimize_saves_best_params_config(self, tmp_path):
        from examples.cli import run_optimization

        out = tmp_path / "best.yaml"
        args = self._make_args(optimize=True, output_strategy_config=str(out), days=120)
        config = Config()
        # Run offline against synthetic data so the test does not require the
        # yfinance dependency (or live network access) to be available.
        config.data.provider = "synthetic"
        config.data.offline = True
        config.data.synthetic_days = 120
        config.data.synthetic_seed = 42
        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=120)

        result = run_optimization(args, config, start_date, end_date)
        assert result == 0
        assert out.exists()

        import yaml

        with open(out) as f:
            saved = yaml.safe_load(f)
        assert saved["type"] == "ma"
        assert "fast_period" in saved["parameters"]
        assert "slow_period" in saved["parameters"]
        assert saved["name"] == "ma"

    def test_walk_forward_saves_last_window_params_config(self, tmp_path):
        from examples.cli import run_walk_forward

        out = tmp_path / "wf_best.yaml"
        args = self._make_args(
            walk_forward=True,
            output_strategy_config=str(out),
            days=120,
            wf_windows=2,
            wf_train_size=0.6,
            wf_anchored=False,
            wf_optimizer="grid",
            n_jobs=1,
        )
        config = Config()
        # Run offline against synthetic data so the test does not require the
        # yfinance dependency (or live network access) to be available.
        config.data.provider = "synthetic"
        config.data.offline = True
        config.data.synthetic_days = 120
        config.data.synthetic_seed = 42
        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=120)

        result = run_walk_forward(args, config, start_date, end_date)
        assert result == 0
        assert out.exists()

        import yaml

        with open(out) as f:
            saved = yaml.safe_load(f)
        assert saved["type"] == "ma"
        assert "fast_period" in saved["parameters"]
        assert "slow_period" in saved["parameters"]

    def test_single_strategy_saves_config(self, tmp_path, capsys):
        """``--output-strategy-config`` in a regular backtest writes the run strategy.

        The README documents ``--output-strategy-config`` for optimization,
        walk-forward, and regular backtest modes, but only the first two were
        covered. This pins the single-strategy path (``_run_cli``) so the
        documented round-trip stays alive: write the config, then reload it
        through ``Strategy.from_config``.
        """
        from examples.cli import main

        out = tmp_path / "single.yaml"
        args = [
            "--offline",
            "--strategy",
            "ma",
            "--fast-period",
            "5",
            "--slow-period",
            "25",
            "--symbols",
            "AAPL",
            "--days",
            "120",
            "--output-strategy-config",
            str(out),
        ]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0
        assert out.exists()

        import yaml

        with open(out) as f:
            saved = yaml.safe_load(f)
        assert saved["type"] == "ma"
        assert saved["parameters"]["fast_period"] == 5
        assert saved["parameters"]["slow_period"] == 25
        assert "Strategy configuration saved to" in capsys.readouterr().out

        # Round-trip: the saved config must reload into the same strategy.
        from quant_trading.strategies.base import Strategy
        from quant_trading.strategies.examples import MovingAverageCrossover

        reloaded = Strategy.from_config(saved)
        assert isinstance(reloaded, MovingAverageCrossover)
        assert reloaded.fast_period == 5
        assert reloaded.slow_period == 25

    def test_single_strategy_config_writes_to_nested_directory(self, tmp_path, capsys):
        """``--output-strategy-config`` creates missing parent directories."""
        from examples.cli import main

        out = tmp_path / "nested" / "deep" / "single.yaml"
        args = [
            "--offline",
            "--strategy",
            "rsi",
            "--symbols",
            "AAPL",
            "--days",
            "120",
            "--output-strategy-config",
            str(out),
        ]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0
        assert out.exists()
        assert out.parent.is_dir()

    def test_run_walk_forward_passes_risk_free_rate_to_optimizer(self):
        """CLI walk-forward must forward config.backtest.risk_free_rate."""
        from unittest.mock import patch

        from examples.cli import parse_args, run_walk_forward
        from quant_trading.optimization.walk_forward import WalkForwardOptimizer

        with patch(
            "sys.argv",
            [
                "cli.py",
                "--walk-forward",
                "--offline",
                "--strategy",
                "ma",
                "--days",
                "120",
                "--wf-windows",
                "2",
                "--risk-free-rate",
                "0.05",
            ],
        ):
            args = parse_args()

        config = Config()
        config.data.provider = "synthetic"
        config.data.offline = True
        config.data.synthetic_days = 120
        config.data.synthetic_seed = 42
        config.backtest.risk_free_rate = 0.05

        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=120)
        captured: dict = {}

        def spy(self, *a, **k):
            captured.update(k)
            raise RuntimeError("stop-after-init")

        with patch.object(WalkForwardOptimizer, "__init__", spy):
            try:
                run_walk_forward(args, config, start_date, end_date)
            except RuntimeError:
                pass

        assert captured.get("risk_free_rate") == 0.05

    def test_save_strategy_config_helper_round_trip(self, tmp_path):
        from examples.cli import _save_strategy_config
        from quant_trading.strategies.examples import MovingAverageCrossover

        out = tmp_path / "helper.yaml"
        params = {"fast_period": 5, "slow_period": 25, "name": "MA_Crossover_5_25"}
        _save_strategy_config(str(out), MovingAverageCrossover, params)

        import yaml

        with open(out) as f:
            saved = yaml.safe_load(f)
        assert saved["type"] == "ma"
        assert saved["name"] == "MA_Crossover_5_25"
        assert saved["parameters"] == {"fast_period": 5, "slow_period": 25}

        # The saved config must be loadable back through Strategy.from_config
        from quant_trading.strategies.base import Strategy

        strategy = Strategy.from_config(saved)
        assert isinstance(strategy, MovingAverageCrossover)
        assert strategy.fast_period == 5
        assert strategy.slow_period == 25

    def test_single_strategy_fallback_key_when_not_in_registry(self, tmp_path, capsys, monkeypatch):
        """When strategy class is not in registry, fallback key is used in saved config."""
        import pandas as pd

        from examples.cli import main
        from quant_trading.strategies.base import Signal, Strategy

        # Create a custom strategy class not in the registry
        class CustomUnregisteredStrategy(Strategy):
            def __init__(self, param_a=10, param_b=20, **kwargs):
                kwargs.setdefault("name", "CustomUnregistered")
                super().__init__(**kwargs)
                self.param_a = param_a
                self.param_b = param_b

            def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
                return []

            def get_parameters(self):
                return {"param_a": self.param_a, "param_b": self.param_b}

        # Monkeypatch create_strategy to return our custom unregistered strategy
        import examples.cli as cli_module

        def mock_create_strategy(args):
            return CustomUnregisteredStrategy(param_a=5, param_b=15)

        monkeypatch.setattr(cli_module, "create_strategy", mock_create_strategy)

        out = tmp_path / "fallback.yaml"
        args = [
            "--offline",
            "--strategy",
            "ma",  # This will be ignored by mock
            "--symbols",
            "AAPL",
            "--days",
            "120",
            "--output-strategy-config",
            str(out),
        ]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0
        assert out.exists()

        import yaml

        with open(out) as f:
            saved = yaml.safe_load(f)

        # The fallback key should be the class name without "Strategy" suffix, lowercased
        assert saved["type"] == "customunregistered"
        assert saved["name"] == "CustomUnregistered"
        assert saved["parameters"] == {"param_a": 5, "param_b": 15}

        # Round-trip should work if the fallback key is registered
        # (but it won't be since we didn't register it)
        # This test just verifies the fallback key generation


class TestResolvePeriodsPerYear:
    """Tests for the resolve_periods_per_year helper."""

    def test_daily_interval(self):
        assert resolve_periods_per_year("1d") == 252

    def test_weekly_interval(self):
        assert resolve_periods_per_year("1wk") == 52
        assert resolve_periods_per_year("1w") == 52

    def test_monthly_interval(self):
        assert resolve_periods_per_year("1mo") == 12

    def test_monthly_adjusted_annualizes_as_monthly(self):
        # The README documents ``--interval monthly_adjusted`` as a valid CLI
        # value for the Alpha Vantage provider. It must annualize as monthly
        # (12 periods per year), not fall back to the daily default of 252.
        assert resolve_periods_per_year("monthly_adjusted") == 12

    def test_intraday_interval(self):
        """Intraday intervals scale the daily count by the bar duration."""
        assert resolve_periods_per_year("5m") == 390 * 252 // 5
        assert resolve_periods_per_year("1h") == 390 * 252 // 60

    def test_unknown_interval_falls_back_to_daily(self):
        assert resolve_periods_per_year("unknown") == 252
        assert resolve_periods_per_year("") == 252

    def test_override_takes_precedence(self):
        assert resolve_periods_per_year("1d", override=12) == 12
        assert resolve_periods_per_year("5m", override=252) == 252

    def test_case_and_whitespace_insensitive(self):
        assert resolve_periods_per_year(" 1D ") == 252
        assert resolve_periods_per_year("WEEKLY") == 52


class TestPeriodsPerYearFlag:
    """Tests for the --periods-per-year CLI flag and its config wiring."""

    def test_default_flag_is_unset(self):
        with patch("sys.argv", ["cli.py"]):
            args = parse_args()
        assert args.periods_per_year is None

    def test_explicit_flag(self):
        with patch("sys.argv", ["cli.py", "--periods-per-year", "52"]):
            args = parse_args()
        assert args.periods_per_year == 52

    def test_create_config_derives_periods_from_interval(self):
        args = argparse.Namespace(
            config=None,
            offline=False,
            provider=None,
            cache_dir=None,
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key=None,
            risk_free_rate=None,
            interval="1wk",
            periods_per_year=None,
        )
        config = create_config(args)
        assert config.backtest.periods_per_year == 52

    def test_create_config_explicit_periods_win(self):
        args = argparse.Namespace(
            config=None,
            offline=False,
            provider=None,
            cache_dir=None,
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key=None,
            risk_free_rate=None,
            interval="1wk",
            periods_per_year=252,
        )
        config = create_config(args)
        assert config.backtest.periods_per_year == 252

    def test_create_config_synthetic_provider_stays_daily(self):
        """The synthetic provider always emits daily bars, so annualize daily."""
        args = argparse.Namespace(
            config=None,
            offline=True,
            provider=None,
            cache_dir=None,
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key=None,
            risk_free_rate=None,
            interval="1wk",
            periods_per_year=None,
        )
        config = create_config(args)
        assert config.data.provider == "synthetic"
        assert config.backtest.periods_per_year == 252

    def test_create_config_synthetic_provider_respects_override(self):
        """An explicit override still wins for the synthetic provider."""
        args = argparse.Namespace(
            config=None,
            offline=True,
            provider=None,
            cache_dir=None,
            synthetic_days=None,
            synthetic_seed=None,
            alphavantage_key=None,
            risk_free_rate=None,
            interval="1wk",
            periods_per_year=52,
        )
        config = create_config(args)
        assert config.backtest.periods_per_year == 52


class TestCreateConfigInterval:
    """The ``--interval`` flag configures the data layer of the run.

    ``default_interval`` was defined, documented and exported, but nothing
    read it: the interval a run actually used came from a hard-coded default,
    so a configuration that asked for weekly bars was silently ignored. The
    precedence is the same everywhere: a value that is passed explicitly wins
    over the configured one, and the configured one wins over the built-in
    default.
    """

    def _args(self, **overrides):
        base = {
            "config": None,
            "offline": False,
            "provider": None,
            "cache_dir": None,
            "synthetic_days": None,
            "synthetic_seed": None,
            "alphavantage_key": None,
            "risk_free_rate": None,
            "interval": None,
            "periods_per_year": None,
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_create_config_keeps_the_interval_of_the_file(self):
        """The interval of the config file is kept when the flag is not given."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            with open(config_path, "w") as f:
                f.write('data:\n  default_interval: "1wk"\n')
            args = self._args(config=config_path)
            config = create_config(args)

        assert config.data.default_interval == "1wk"
        assert config.backtest.periods_per_year == 52

    def test_create_config_lets_the_flag_override_the_interval(self):
        """The ``--interval`` flag wins over the value of the config file."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            with open(config_path, "w") as f:
                f.write('data:\n  default_interval: "1wk"\n')
            args = self._args(config=config_path, interval="1d")
            config = create_config(args)

        assert config.data.default_interval == "1d"
        assert config.backtest.periods_per_year == 252

    def test_create_config_applies_the_flag_when_no_file_is_given(self):
        """The flag configures the interval when there is no config file."""
        args = self._args(interval="1wk")
        config = create_config(args)

        assert config.data.default_interval == "1wk"
        assert config.backtest.periods_per_year == 52


class TestIntervalEndToEnd:
    """A config file that asks for a different interval reaches the run."""

    def test_main_uses_the_interval_of_the_config_file(self, capsys):
        """The interval of the config file is the one the run fetches with."""
        import tempfile
        from unittest.mock import MagicMock, patch

        from examples.cli import main

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            with open(config_path, "w") as f:
                f.write('data:\n  default_interval: "1wk"\n')

            mock_result = MagicMock()
            mock_result.initial_capital = 100000.0
            mock_result.final_value = 100000.0
            mock_result.total_return = 0.0
            mock_result.total_return_pct = 0.0
            mock_result.total_costs = 0.0
            mock_metrics = MagicMock()
            mock_metrics.num_trades = 0
            mock_metrics.win_rate = 0.0
            mock_metrics.sharpe_ratio = 0.0
            mock_metrics.max_drawdown_pct = 0.0
            mock_metrics.profit_factor = 0.0
            mock_metrics.sortino_ratio = 0.0
            mock_metrics.volatility = 0.0
            mock_metrics.var_95 = 0.0
            mock_metrics.calmar_ratio = 0.0
            mock_metrics.total_pnl = 0.0
            mock_metrics.unrealized_pnl = 0.0
            mock_result.metrics = mock_metrics

            with (
                patch("examples.cli.run_backtest", return_value=mock_result) as mock_run,
                patch(
                    "sys.argv",
                    ["cli.py", "--config", config_path, "--symbols", "AAPL", "--days", "60"],
                ),
            ):
                main()

            kwargs = mock_run.call_args.kwargs
            assert kwargs["interval"] == "1wk"
            assert kwargs["config"].data.default_interval == "1wk"
            assert kwargs["periods_per_year"] == 52

    def test_main_lets_the_flag_override_the_interval(self, capsys):
        """The ``--interval`` flag wins over the value of the config file."""
        import tempfile
        from unittest.mock import MagicMock, patch

        from examples.cli import main

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = f"{tmpdir}/config.yaml"
            with open(config_path, "w") as f:
                f.write('data:\n  default_interval: "1wk"\n')

            mock_result = MagicMock()
            mock_result.initial_capital = 100000.0
            mock_result.final_value = 100000.0
            mock_result.total_return = 0.0
            mock_result.total_return_pct = 0.0
            mock_result.total_costs = 0.0
            mock_metrics = MagicMock()
            mock_metrics.num_trades = 0
            mock_metrics.win_rate = 0.0
            mock_metrics.sharpe_ratio = 0.0
            mock_metrics.max_drawdown_pct = 0.0
            mock_metrics.profit_factor = 0.0
            mock_metrics.sortino_ratio = 0.0
            mock_metrics.volatility = 0.0
            mock_metrics.var_95 = 0.0
            mock_metrics.calmar_ratio = 0.0
            mock_metrics.total_pnl = 0.0
            mock_metrics.unrealized_pnl = 0.0
            mock_result.metrics = mock_metrics

            with (
                patch("examples.cli.run_backtest", return_value=mock_result) as mock_run,
                patch(
                    "sys.argv",
                    [
                        "cli.py",
                        "--config",
                        config_path,
                        "--symbols",
                        "AAPL",
                        "--days",
                        "60",
                        "--interval",
                        "1d",
                    ],
                ),
            ):
                main()

            kwargs = mock_run.call_args.kwargs
            assert kwargs["interval"] == "1d"
            assert kwargs["periods_per_year"] == 252


class TestRegimePeriodsPerYear:
    """The regime analysis is annualized with the period count of the run.

    The backtest metrics, the Monte Carlo simulation and the regime analysis
    all have to agree on how many periods make up a year, otherwise a run on
    weekly data reports a regime volatility that is off by the square root of
    the frequency ratio.
    """

    @staticmethod
    def _make_result():
        import pandas as pd

        from quant_trading.backtest.engine import BacktestResult
        from quant_trading.backtest.metrics import calculate_backtest_metrics

        equity = pd.Series(
            [100000.0 * (1.0 + 0.001 * i) for i in range(80)],
            index=pd.date_range("2024-01-01", periods=80, freq="D"),
        )
        return BacktestResult(
            equity_curve=equity,
            trades=pd.DataFrame(),
            positions={},
            metrics=calculate_backtest_metrics(equity),
            start_date=equity.index[0],
            end_date=equity.index[-1],
            initial_capital=100000.0,
            final_value=float(equity.iloc[-1]),
            total_return=float(equity.iloc[-1] - equity.iloc[0]),
            total_return_pct=float((equity.iloc[-1] / equity.iloc[0] - 1) * 100),
        )

    @staticmethod
    def _regime_args():
        return argparse.Namespace(
            regime_window=20,
            regime_vol_threshold=0.0,
            regime_return_threshold=0.0,
        )

    def test_get_regime_analysis_uses_the_given_periods_per_year(self):
        """The helper annualizes the regime with the period count it is given."""
        from examples.cli import _get_regime_analysis

        result = self._make_result()
        args = self._regime_args()

        daily = _get_regime_analysis(result, args, periods_per_year=252)
        weekly = _get_regime_analysis(result, args, periods_per_year=52)

        assert daily.result.total_volatility > 0.0
        assert daily.result.total_volatility != weekly.result.total_volatility
        assert daily.result.total_volatility == pytest.approx(
            weekly.result.total_volatility * (252 / 52) ** 0.5, rel=1e-9
        )

    def test_get_regime_analysis_defaults_to_daily(self):
        """The helper keeps the daily default when no period count is given."""
        from examples.cli import _get_regime_analysis

        result = self._make_result()
        args = self._regime_args()

        default = _get_regime_analysis(result, args)
        explicit = _get_regime_analysis(result, args, periods_per_year=252)

        assert default.periods_per_year == 252
        assert default.result.total_volatility == explicit.result.total_volatility

    def test_main_regime_uses_the_periods_per_year_of_the_run(self, capsys):
        """The printed regime block reports the annualization of the run."""
        args = [
            "--offline",
            "--regime",
            "--periods-per-year",
            "52",
            "--symbols",
            "AAPL",
            "--days",
            "120",
        ]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Periods per Year:  52" in captured.out

    def test_main_regime_output_records_the_periods_per_year(self):
        """The JSON output records the annualization the regime used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/results.json"
            args = [
                "--offline",
                "--regime",
                "--periods-per-year",
                "52",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "120",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            with open(output_path) as f:
                data = json.load(f)

        assert data["regime_analysis"]["periods_per_year"] == 52

    def test_main_regime_defaults_to_daily(self, capsys):
        """Without an override the regime is annualized with 252 periods."""
        args = ["--offline", "--regime", "--symbols", "AAPL", "--days", "120"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Periods per Year:  252" in captured.out


class TestTradeAnalysisRiskFreeRate:
    """The trade analysis is computed with the risk-free rate of the run.

    The engine annualizes the backtest Sharpe with the configured risk-free
    rate, so the trade-level Sharpe and Sortino of the same run have to use
    the same rate, otherwise one run reports two different Sharpes.
    """

    @staticmethod
    def _make_result():
        import pandas as pd

        from quant_trading.backtest.engine import BacktestResult
        from quant_trading.backtest.metrics import calculate_backtest_metrics

        equity = pd.Series(
            [100000.0 * (1.0 + 0.002 * i) for i in range(40)],
            index=pd.date_range("2024-01-01", periods=40, freq="D"),
        )
        trades = pd.DataFrame(
            {
                "symbol": ["AAPL", "AAPL", "AAPL", "AAPL"],
                "action": ["buy", "sell", "buy", "sell"],
                "quantity": [10.0, 10.0, 10.0, 10.0],
                "price": [100.0, 110.0, 105.0, 95.0],
                "timestamp": pd.to_datetime(
                    ["2024-01-02", "2024-01-05", "2024-01-10", "2024-01-15"]
                ),
                "pnl": [0.0, 100.0, 0.0, -100.0],
            }
        )
        return BacktestResult(
            equity_curve=equity,
            trades=trades,
            positions={},
            metrics=calculate_backtest_metrics(equity),
            start_date=equity.index[0],
            end_date=equity.index[-1],
            initial_capital=100000.0,
            final_value=float(equity.iloc[-1]),
            total_return=float(equity.iloc[-1] - equity.iloc[0]),
            total_return_pct=float((equity.iloc[-1] / equity.iloc[0] - 1) * 100),
        )

    def test_get_trade_analysis_uses_the_given_risk_free_rate(self):
        """The helper annualizes the trade metrics with the rate it is given."""
        from examples.cli import _get_trade_analysis

        result = self._make_result()
        args = argparse.Namespace()

        no_rate = _get_trade_analysis(result, args, risk_free_rate=0.0)
        with_rate = _get_trade_analysis(result, args, risk_free_rate=0.05)

        assert no_rate.total_trades == 2
        assert no_rate.sharpe_ratio != with_rate.sharpe_ratio

    def test_get_trade_analysis_defaults_to_the_library_default(self):
        """Without a rate the helper keeps the default of the library."""
        from examples.cli import _get_trade_analysis

        result = self._make_result()
        args = argparse.Namespace()

        default = _get_trade_analysis(result, args)
        explicit = _get_trade_analysis(result, args, risk_free_rate=0.02)

        assert default.sharpe_ratio == explicit.sharpe_ratio
        assert default.sortino_ratio == explicit.sortino_ratio

    def test_main_trade_analysis_uses_the_configured_risk_free_rate(self, capsys):
        """The printed trade Sharpe follows the risk-free rate of the run."""
        outputs = []
        for rate in ("0.0", "0.05"):
            args = [
                "--offline",
                "--trade-analysis",
                "--risk-free-rate",
                rate,
                "--symbols",
                "AAPL",
                "MSFT",
                "GOOGL",
                "--days",
                "200",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            outputs.append(capsys.readouterr().out)

        def _trade_sharpe(output: str) -> float:
            for line in output.splitlines():
                if line.startswith("Trade Sharpe:"):
                    return float(line.split(":", 1)[1].strip())
            raise AssertionError("no trade Sharpe in the output")

        # The synthetic data is seeded, so both runs trade the same round trips
        # and only the risk-free rate differs.
        assert _trade_sharpe(outputs[0]) != _trade_sharpe(outputs[1])

    def test_get_trade_analysis_uses_the_given_periods_per_year(self):
        """The helper annualizes the trade metrics with the periods it is given."""
        from examples.cli import _get_trade_analysis

        result = self._make_result()
        args = argparse.Namespace()

        daily = _get_trade_analysis(result, args, risk_free_rate=0.02, periods_per_year=252)
        weekly = _get_trade_analysis(result, args, risk_free_rate=0.02, periods_per_year=52)

        assert daily.total_trades == 2
        assert daily.sharpe_ratio != weekly.sharpe_ratio

    def test_main_trade_analysis_uses_the_configured_periods_per_year(self, capsys):
        """The printed trade Sharpe follows the annualization period of the run."""
        outputs = []
        for periods in ([], ["--periods-per-year", "52"]):
            args = [
                "--offline",
                "--trade-analysis",
                "--risk-free-rate",
                "0.02",
                "--symbols",
                "AAPL",
                "MSFT",
                "GOOGL",
                "--days",
                "200",
            ] + periods
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            outputs.append(capsys.readouterr().out)

        def _trade_sharpe(output: str) -> float:
            for line in output.splitlines():
                if line.startswith("Trade Sharpe:"):
                    return float(line.split(":", 1)[1].strip())
            raise AssertionError("no trade Sharpe in the output")

        assert _trade_sharpe(outputs[0]) != _trade_sharpe(outputs[1])


class TestCombinedAnalysis:
    """The analysis flags work in combined mode too.

    Combined mode runs one backtest per strategy, so there is no combined
    equity curve to analyse. The analysis is reported for the best strategy,
    which is the one the comparison table announces.
    """

    def test_main_combined_regime_prints_the_analysis(self, capsys):
        """--combined --regime prints the regime block instead of ignoring it."""
        args = ["--combined", "--offline", "--regime", "--symbols", "AAPL", "--days", "120"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Market Regime Analysis" in captured.out
        assert "Analysis of the best strategy:" in captured.out
        assert "Periods per Year:  252" in captured.out

    def test_main_combined_monte_carlo_and_trade_analysis(self, capsys):
        """--combined honours the Monte Carlo and trade analysis flags too."""
        args = [
            "--combined",
            "--offline",
            "--monte-carlo",
            "--trade-analysis",
            "--mc-simulations",
            "30",
            "--symbols",
            "AAPL",
            "--days",
            "120",
        ]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Monte Carlo Simulation" in captured.out
        assert "Trade Analysis" in captured.out

    def test_main_combined_without_analysis_flags_prints_no_analysis(self, capsys):
        """Without the flags the combined run stays a comparison."""
        args = ["--combined", "--offline", "--symbols", "AAPL", "--days", "120"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Market Regime Analysis" not in captured.out
        assert "Monte Carlo Simulation" not in captured.out
        assert "Trade Analysis" not in captured.out

    def test_main_combined_output_records_the_analysis(self):
        """The JSON output of a combined run carries the analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/comparison.json"
            args = [
                "--combined",
                "--offline",
                "--regime",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "120",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            with open(output_path) as f:
                data = json.load(f)

        assert "comparison" in data
        assert "regime_analysis" in data
        assert data["regime_analysis"]["periods_per_year"] == 252
        assert data["regime_analysis"]["segments"] is not None

    def test_main_combined_monte_carlo_uses_the_configured_risk_free_rate(self, capsys):
        """The combined Monte Carlo block follows the risk-free rate of the run.

        The Monte Carlo simulator computes the Sharpe/Sortino of the simulated
        curves with the rate it is given, so a run that overrides
        ``--risk-free-rate`` must reach the combined Monte Carlo block too.
        """
        outputs = []
        for rate in ("0.0", "0.05"):
            args = [
                "--combined",
                "--offline",
                "--monte-carlo",
                "--mc-simulations",
                "20",
                "--mc-seed",
                "42",
                "--risk-free-rate",
                rate,
                "--symbols",
                "AAPL",
                "--days",
                "365",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            outputs.append(capsys.readouterr().out)

        def _mc_sharpe_mean(output: str) -> float:
            """Return the Mean column of the simulated sharpe_ratio row."""
            for line in output.splitlines():
                stripped = line.strip()
                if stripped.startswith("sharpe_ratio"):
                    tokens = stripped.split()
                    if len(tokens) >= 2:
                        return float(tokens[1])
            raise AssertionError("no simulated sharpe_ratio in the output")

        assert _mc_sharpe_mean(outputs[0]) != _mc_sharpe_mean(outputs[1])

    def test_main_combined_trade_analysis_uses_the_configured_periods_per_year(self, capsys):
        """In combined mode the trade Sharpe follows the annualization period."""
        outputs = []
        for periods in ([], ["--periods-per-year", "52"]):
            args = [
                "--combined",
                "--offline",
                "--trade-analysis",
                "--risk-free-rate",
                "0.02",
                "--symbols",
                "AAPL",
                "MSFT",
                "GOOGL",
                "--days",
                "200",
            ] + periods
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            outputs.append(capsys.readouterr().out)

        def _trade_sharpe(output: str) -> float:
            for line in output.splitlines():
                if line.startswith("Trade Sharpe:"):
                    return float(line.split(":", 1)[1].strip())
            raise AssertionError("no trade Sharpe in the output")

        assert "Analysis of the best strategy:" in outputs[0]
        assert _trade_sharpe(outputs[0]) != _trade_sharpe(outputs[1])


class TestUnrealizedPnlReporting:
    """The CLI reports the realized and the unrealized PnL of the run.

    The total return of a run includes the PnL of the positions that are
    still open, so the two halves have to be visible next to it.
    """

    def test_the_output_splits_the_total_return(self, capsys):
        """The printed block reports the realized and the unrealized PnL."""
        args = ["--offline", "--symbols", "AAPL", "--days", "120"]
        with patch("sys.argv", ["cli.py"] + args):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Realized PnL:" in captured.out
        assert "Unrealized PnL:" in captured.out

    def test_the_json_output_reconciles_the_total_return(self):
        """The JSON output adds up to the total return it reports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/results.json"
            args = [
                "--offline",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "120",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            with open(output_path) as f:
                data = json.load(f)

        assert "total_pnl" in data
        assert "unrealized_pnl" in data
        assert data["total_return"] == pytest.approx(
            data["total_pnl"] + data["unrealized_pnl"], rel=1e-9, abs=1e-6
        )


class TestCsvOutput:
    """The ``--output-format csv`` flag produces a CSV file in every output mode.

    The flag was previously honoured only in single-strategy mode; combined,
    optimization and walk-forward modes always wrote JSON. These tests cover
    single-strategy and combined mode end to end.
    """

    def test_main_with_output_file_csv(self):
        """Single-strategy mode writes a CSV file with a header and a data row."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/results.csv"
            args = [
                "--offline",
                "--output-format",
                "csv",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "120",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            import os

            assert os.path.exists(output_path)
            with open(output_path) as f:
                lines = f.read().strip().splitlines()
            assert len(lines) >= 2
            header = lines[0].split(",")
            assert "strategy" in header
            assert "total_return_pct" in header
            assert "total_pnl" in header
            assert "unrealized_pnl" in header

    def test_main_combined_output_csv(self):
        """Combined mode writes a CSV comparison file with one row per strategy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/comparison.csv"
            args = [
                "--combined",
                "--offline",
                "--output-format",
                "csv",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "120",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            import os

            assert os.path.exists(output_path)
            with open(output_path) as f:
                lines = f.read().strip().splitlines()
            assert len(lines) >= 2
            header = lines[0].split(",")
            assert "comparison" in header
            assert "best_strategy" in header
            assert any("MA_Crossover" in line for line in lines[1:])

    def test_main_optimize_output_csv(self):
        """Optimization mode writes a CSV file when ``--output-format csv``."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/opt.csv"
            args = [
                "--optimize",
                "--strategy",
                "ma",
                "--offline",
                "--output-format",
                "csv",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "150",
                "--ma-fast-range",
                "5,10,1",
                "--ma-slow-range",
                "20,30,1",
                "--n-iter",
                "2",
                "--bayesian-n-initial",
                "1",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            import os

            assert os.path.exists(output_path)
            with open(output_path) as f:
                lines = f.read().strip().splitlines()
            assert len(lines) >= 2
            header = lines[0].split(",")
            assert "strategy" in header
            assert "best_params" in header

    def test_main_walk_forward_output_csv(self):
        """Walk-forward mode writes a CSV file when ``--output-format csv``."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/wf.csv"
            args = [
                "--walk-forward",
                "--strategy",
                "ma",
                "--offline",
                "--output-format",
                "csv",
                "--output",
                output_path,
                "--symbols",
                "AAPL",
                "--days",
                "200",
                "--ma-fast-range",
                "5,10,1",
                "--ma-slow-range",
                "20,30,1",
                "--wf-windows",
                "2",
                "--wf-train-size",
                "0.6",
                "--n-iter",
                "1",
                "--bayesian-n-initial",
                "1",
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            import os

            assert os.path.exists(output_path)
            with open(output_path) as f:
                lines = f.read().strip().splitlines()
            assert len(lines) >= 2
            header = lines[0].split(",")
            assert "strategy" in header
            assert "window_results" in header


class TestUserErrorReporting:
    """A user error is a one-line message, not a traceback.

    The library raises for a missing file or an unknown strategy on purpose.
    The command line interface turns those into a message and the exit code 1.
    """

    def _run(self, arguments, capsys):
        """Run the CLI with ``arguments`` and return its exit code and output."""
        with patch("sys.argv", ["cli.py", *arguments]):
            result = main()
        captured = capsys.readouterr()
        return result, captured.out + captured.err

    def test_unknown_strategy_is_reported(self, capsys):
        """An unknown strategy name is a message and the exit code 1."""
        result, output = self._run(
            ["--strategy", "nosuchstrategy", "--offline", "--symbols", "AAPL", "--days", "30"],
            capsys,
        )
        assert result == 1
        assert "invalid choice" in output or "nosuchstrategy" in output
        assert "Traceback" not in output

    def test_missing_config_file_is_reported(self, capsys, tmp_path):
        """A config file that does not exist is a message and the exit code 1."""
        missing = tmp_path / "missing" / "config.yaml"
        result, output = self._run(
            [
                "--config",
                str(missing),
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "could not read config file" in output
        assert "Traceback" not in output

    @pytest.mark.parametrize(
        ("filename", "content"),
        [
            ("invalid_indent.yaml", "just: a\n  bad: [indent\n"),
            ("unclosed_flow.yaml", "backtest: {initial_capital: 100.0\n"),
            ("tab_indent.yaml", "backtest:\n\tinitial_capital: 100.0\n"),
        ],
        ids=["invalid-indent", "unclosed-flow", "tab-indent"],
    )
    def test_an_invalid_yaml_config_file_is_reported(self, capsys, tmp_path, filename, content):
        """A config file that is not valid YAML is a message, not a traceback.

        The README's "Error Reporting" section documents that a config file
        whose YAML is broken is reported the same way as a missing one:

        ```
        $ python examples/cli.py --config /tmp/cfg.yaml --offline --symbols AAPL --days 30
        Error: ...
        ```

        The CLI catches ``yaml.YAMLError`` from ``Config.from_yaml`` and turns
        it into a one-line message. Several malformed-YAML shapes are covered
        here because the YAML parser reports different errors for different
        faults (indentation, unclosed flow, tabs), and all of them have to
        reach the user as a message instead of a traceback.
        """
        broken = tmp_path / filename
        broken.write_text(content)
        result, output = self._run(
            ["--config", str(broken), "--offline", "--symbols", "AAPL", "--days", "30"],
            capsys,
        )
        assert result == 1
        assert "Invalid YAML" in output
        assert "Traceback" not in output

    def test_missing_strategy_config_file_is_reported(self, capsys, tmp_path):
        """A strategy config that does not exist is a message and the exit code 1."""
        missing = tmp_path / "missing" / "strategy.yaml"
        result, output = self._run(
            [
                "--strategy-config",
                str(missing),
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "could not read strategy config" in output
        assert "Traceback" not in output

    def test_unwritable_output_file_is_reported(self, capsys, tmp_path):
        """An output file in a directory that does not exist is a message."""
        missing = tmp_path / "missing" / "output.json"
        result, output = self._run(
            [
                "--output",
                str(missing),
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "could not write output file" in output
        assert "Traceback" not in output

    def test_a_malformed_strategy_config_is_reported(self, capsys, tmp_path):
        """A strategy config that is not valid YAML is a message."""
        broken = tmp_path / "broken.yaml"
        broken.write_text("type: [unclosed\n  bad: : :\n")
        result, output = self._run(
            [
                "--strategy-config",
                str(broken),
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "invalid YAML in strategy config" in output
        assert "Traceback" not in output

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("- a\n- b\n", "expected a mapping"),
            ("type: rsi\nparameters: 5\n", "'parameters' must be a mapping"),
            ("type: rsi\nparameters:\n  nosuchparam: 5\n", "invalid strategy config"),
            ("type: rsi\nparameters:\n  period: abc\n", "invalid strategy config"),
        ],
        ids=[
            "not-a-mapping",
            "parameters-not-a-mapping",
            "unknown-parameter",
            "bad-parameter-value",
        ],
    )
    def test_a_malformed_strategy_config_content_is_reported(
        self, capsys, tmp_path, content, message
    ):
        """A strategy config with the wrong content is a message."""
        config = tmp_path / "strategy.yaml"
        config.write_text(content)
        result, output = self._run(
            [
                "--strategy-config",
                str(config),
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert message in output
        assert "Traceback" not in output

    def test_an_invalid_optimization_range_is_reported(self, capsys):
        """A range with a step of zero is a message, not a hang.

        A step of zero would make the grid search loop forever, so the
        argument is rejected before the run starts.
        """
        result, output = self._run(
            [
                "--optimize",
                "--ma-fast-range",
                "5,20,0",
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "--ma-fast-range" in output
        assert "step must be greater than 0" in output
        assert "Traceback" not in output

    def test_invalid_config_field_type_is_reported(self, capsys, tmp_path):
        """A config file with a wrong field type is a message and exit code 1."""
        bad = tmp_path / "bad_type.yaml"
        bad.write_text("backtest:\n  initial_capital: abc\n")
        result, output = self._run(
            ["--config", str(bad), "--offline", "--symbols", "AAPL", "--days", "30"],
            capsys,
        )
        assert result == 1
        assert "Error:" in output
        assert "Traceback" not in output

    def test_zero_mc_simulations_is_reported(self, capsys):
        """Zero mc simulations is a usage error at the CLI level."""
        result, output = self._run(
            [
                "--monte-carlo",
                "--mc-simulations",
                "0",
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "invalid --mc-simulations" in output
        assert "Traceback" not in output

    def test_n_iter_zero_is_invalid(self):
        with patch("sys.argv", ["cli.py", "--n-iter", "0"]), pytest.raises(ValueError) as exc:
            parse_args()
        assert "invalid --n-iter" in str(exc.value)

    def test_n_iter_negative_is_invalid(self):
        with patch("sys.argv", ["cli.py", "--n-iter", "-1"]), pytest.raises(ValueError) as exc:
            parse_args()
        assert "invalid --n-iter" in str(exc.value)

    def test_bayesian_n_initial_zero_is_invalid(self):
        with (
            patch("sys.argv", ["cli.py", "--bayesian-n-initial", "0"]),
            pytest.raises(ValueError) as exc,
        ):
            parse_args()
        assert "invalid --bayesian-n-initial" in str(exc.value)

    def test_bayesian_n_initial_negative_is_invalid(self):
        with (
            patch("sys.argv", ["cli.py", "--bayesian-n-initial", "-5"]),
            pytest.raises(ValueError) as exc,
        ):
            parse_args()
        assert "invalid --bayesian-n-initial" in str(exc.value)

    def test_bayesian_noise_zero_is_invalid(self):
        with (
            patch("sys.argv", ["cli.py", "--bayesian-noise", "0"]),
            pytest.raises(ValueError) as exc,
        ):
            parse_args()
        assert "invalid --bayesian-noise" in str(exc.value)

    def test_bayesian_noise_negative_is_invalid(self):
        with (
            patch("sys.argv", ["cli.py", "--bayesian-noise", "-1e-3"]),
            pytest.raises(ValueError) as exc,
        ):
            parse_args()
        assert "invalid --bayesian-noise" in str(exc.value)

    def test_bayesian_noise_default(self):
        """``--bayesian-noise`` defaults to the optimizer's default (1e-6)."""
        with patch("sys.argv", ["cli.py"]):
            args = parse_args()
        assert args.bayesian_noise == 1e-6

    def test_bayesian_noise_custom_is_accepted(self):
        """A positive ``--bayesian-noise`` value is parsed and forwarded."""
        with patch("sys.argv", ["cli.py", "--bayesian-noise", "1e-3"]):
            args = parse_args()
        assert args.bayesian_noise == 1e-3

    @pytest.mark.slow
    def test_offline_bayesian_optimize_with_custom_noise_completes(self, capsys):
        """An offline Bayesian optimization with a non-default ``--bayesian-noise``
        runs the full CLI → ``run_optimization`` → ``BayesianOptimizer`` →
        ``gp_minimize`` path and completes with exit code 0.

        The parse/constructor unit tests cover the ``--bayesian-noise`` flag in
        isolation; this is the end-to-end guard that the value actually reaches
        the Gaussian Process kernel through the optimizer and that the run
        finishes instead of raising deep in ``skopt``.
        """
        args = [
            "--offline",
            "--optimize",
            "--optimizer",
            "bayesian",
            "--bayesian-noise",
            "1e-4",
            "--ma-fast-range",
            "5,15,5",
            "--ma-slow-range",
            "20,30,10",
            "--symbols",
            "AAPL",
            "--days",
            "60",
            "--n-iter",
            "5",
            "--bayesian-n-initial",
            "2",
            "--n-jobs",
            "1",
        ]
        with patch("sys.argv", ["cli.py", *args]):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Running parameter optimization for MovingAverageCrossover" in captured.out
        assert "Optimizer: bayesian" in captured.out
        assert "Optimization Complete" in captured.out
        assert "Best Parameters:" in captured.out
        assert "Traceback" not in captured.out

    @pytest.mark.slow
    def test_offline_walk_forward_with_bayesian_inner_optimizer_completes(self, capsys):
        """An offline walk-forward run with the Bayesian inner optimizer completes.

        The walk-forward mode wires the Bayesian optimizer through
        ``WalkForwardOptimizer`` → ``optimizer_kwargs`` → ``BayesianOptimizer``
        → ``gp_minimize``. The library-level ``test_walk_forward_with_bayesian``
        covers that path with mock data; this is the end-to-end guard that the
        documented CLI invocation (``--walk-forward --wf-optimizer bayesian``)
        reaches the same path through ``run_walk_forward`` and finishes with
        exit code 0 instead of raising deep in ``skopt``.
        """
        args = [
            "--offline",
            "--walk-forward",
            "--wf-optimizer",
            "bayesian",
            "--bayesian-n-initial",
            "2",
            "--n-iter",
            "5",
            "--ma-fast-range",
            "5,15,5",
            "--ma-slow-range",
            "20,30,10",
            "--wf-windows",
            "3",
            "--wf-train-size",
            "0.7",
            "--symbols",
            "AAPL",
            "--days",
            "90",
            "--n-jobs",
            "1",
        ]
        with patch("sys.argv", ["cli.py", *args]):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Running walk-forward optimization for MovingAverageCrossover" in captured.out
        assert "Inner optimizer: bayesian" in captured.out
        assert "Walk-Forward Optimization Complete" in captured.out
        assert "Window Results:" in captured.out
        assert "Traceback" not in captured.out

    @pytest.mark.slow
    def test_offline_walk_forward_with_bayesian_inner_optimizer_and_custom_noise_completes(self, capsys):
        """An offline walk-forward run with the Bayesian inner optimizer and a
        custom ``--bayesian-noise`` completes end-to-end.

        This guards the full CLI → ``run_walk_forward`` →
        ``WalkForwardOptimizer`` → ``optimizer_kwargs`` → ``BayesianOptimizer``
        → ``gp_minimize`` path with a non-default noise value, ensuring the
        parameter is forwarded through the walk-forward layer and accepted by
        scikit-optimize's GP kernel.
        """
        args = [
            "--offline",
            "--walk-forward",
            "--wf-optimizer",
            "bayesian",
            "--bayesian-n-initial",
            "2",
            "--n-iter",
            "5",
            "--bayesian-noise",
            "1e-4",
            "--ma-fast-range",
            "5,15,5",
            "--ma-slow-range",
            "20,30,10",
            "--wf-windows",
            "3",
            "--wf-train-size",
            "0.7",
            "--symbols",
            "AAPL",
            "--days",
            "90",
            "--n-jobs",
            "1",
        ]
        with patch("sys.argv", ["cli.py", *args]):
            result = main()
        assert result == 0

        captured = capsys.readouterr()
        assert "Running walk-forward optimization for MovingAverageCrossover" in captured.out
        assert "Inner optimizer: bayesian" in captured.out
        assert "Walk-Forward Optimization Complete" in captured.out
        assert "Window Results:" in captured.out
        assert "Traceback" not in captured.out

    def test_zero_n_jobs_is_reported(self, capsys):
        """Zero ``--n-jobs`` is a usage error at the CLI level.

        The library coerces ``n_jobs=0`` to ``1`` (joblib convention), so the
        value is silently accepted and the user gets a single core instead of
        the parallelism they asked for. The check belongs in the CLI and has
        to name the offending flag before the run starts.
        """
        result, output = self._run(
            [
                "--optimize",
                "--n-jobs",
                "0",
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "invalid --n-jobs" in output
        assert "Traceback" not in output

    def test_n_jobs_below_one_except_minus_one_is_reported(self, capsys):
        """A ``--n-jobs`` below 1 (other than -1) is a usage error at the CLI level.

        ``-1`` is the documented joblib shorthand for "all CPU cores". Values
        such as ``-2`` are not meaningful and would be coerced to ``1`` by the
        library, so they are rejected up front.
        """
        result, output = self._run(
            [
                "--optimize",
                "--n-jobs",
                "-2",
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "invalid --n-jobs" in output
        assert "Traceback" not in output

    @pytest.mark.skipif(
        _module_available("skopt"),
        reason="only relevant when scikit-optimize is not installed",
    )
    def test_bayesian_optimizer_without_skopt_is_reported(self, capsys):
        """``--optimizer bayesian`` without scikit-optimize is a clean message.

        The library raises ``ImportError`` from the optimizer constructor with
        an install hint. The CLI must surface that as a one-line error and exit
        code 1 instead of a traceback, matching how every other user error is
        reported.
        """
        result, output = self._run(
            [
                "--optimize",
                "--strategy",
                "ma",
                "--optimizer",
                "bayesian",
                "--ma-fast-range",
                "5,15,5",
                "--ma-slow-range",
                "20,30,10",
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "30",
            ],
            capsys,
        )
        assert result == 1
        assert "scikit-optimize" in output
        assert "Traceback" not in output

    def test_import_error_is_reported(self, capsys):
        """An ``ImportError`` raised while running is a one-line message.

        An optional dependency that is not installed (for example
        scikit-optimize for ``--optimizer bayesian``) raises ``ImportError``
        deep in the optimizer constructor. Without this guard the user gets a
        raw traceback instead of the install hint the library already prints.
        """
        from examples import cli as cli_module

        def _raise_import_error():
            raise ImportError("BayesianOptimizer requires scikit-optimize")

        with patch.object(cli_module, "_run_cli", _raise_import_error):
            result, output = self._run(["--offline", "--symbols", "AAPL", "--days", "30"], capsys)
        assert result == 1
        assert "scikit-optimize" in output
        assert "Traceback" not in output


class TestHtmlReportFlag:
    """The ``--report`` flag writes an HTML backtest report for the run.

    The report module itself is covered by ``tests/test_backtest_report.py``;
    these tests guard the CLI wiring: the flag is accepted, the file is
    written, and a missing optional dependency is reported as a one-line
    error instead of a traceback.
    """

    def _run(self, arguments, capsys):
        with patch("sys.argv", ["cli.py", *arguments]):
            result = main()
        captured = capsys.readouterr()
        return result, captured.out + captured.err

    def test_report_writes_html_file(self, capsys, tmp_path):
        """``--report`` writes an HTML file and exits 0."""
        report_path = tmp_path / "report.html"
        result, output = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
            ],
            capsys,
        )
        assert result == 0
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Performance Summary" in content
        assert "HTML report saved to" in output

    def test_report_without_charts_writes_html_file(self, capsys, tmp_path):
        """``--report --report-no-charts`` writes a chart-free report."""
        report_path = tmp_path / "nocharts.html"
        result, _ = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
                "--report-no-charts",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "data:image/png;base64," not in content

    def test_report_dark_theme(self, capsys, tmp_path):
        """``--report-theme dark`` embeds the dark background color."""
        report_path = tmp_path / "dark.html"
        result, _ = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
                "--report-theme",
                "dark",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "#1e1e1e" in content

    def test_report_combined_writes_html_for_best_strategy(self, capsys, tmp_path):
        """In ``--combined`` mode ``--report`` writes a comparison report."""
        import multiprocessing

        report_path = tmp_path / "combined_report.html"
        result, _ = self._run(
            [
                "--combined",
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "60",
                "--report",
                str(report_path),
                "--n-jobs",
                str(min(4, multiprocessing.cpu_count() or 1)),
            ],
            capsys,
        )
        assert result == 0
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Strategy Comparison" in content

    def test_report_missing_matplotlib_is_reported(self, capsys, tmp_path, monkeypatch):
        """A missing ``matplotlib`` is a one-line error, not a traceback.

        ``matplotlib`` is an optional dependency (the ``reporting`` extra).
        When it is unavailable and charts are requested, the CLI must report
        the install hint and exit 1 rather than printing a traceback.
        """
        from examples import cli as cli_module

        def _raise_import_error(*args, **kwargs):
            raise ImportError(
                "matplotlib is required for chart generation. "
                "Install with: pip install quant-trading[reporting]"
            )

        monkeypatch.setattr(cli_module, "generate_html_report", _raise_import_error)
        report_path = tmp_path / "no_mpl.html"
        result, output = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
            ],
            capsys,
        )
        assert result == 1
        assert "matplotlib" in output
        assert "Traceback" not in output

    def test_report_os_error_is_reported(self, capsys, tmp_path, monkeypatch):
        """A file-write error in single-mode ``--report`` is a one-line error.

        ``generate_html_report`` can raise ``OSError`` when the report file
        cannot be written. The CLI must report it as a one-line message and
        exit 1 instead of printing a traceback.
        """
        from examples import cli as cli_module

        def _raise_os_error(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr(cli_module, "generate_html_report", _raise_os_error)
        report_path = tmp_path / "no_write.html"
        result, output = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
            ],
            capsys,
        )
        assert result == 1
        assert "could not write report file" in output
        assert "Traceback" not in output

    def test_report_without_trades_omits_trade_details_section(self, capsys, tmp_path):
        """``--report --report-no-trades`` omits the Trade Details section."""
        report_path = tmp_path / "notrades.html"
        result, _ = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
                "--report-no-trades",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<h2>Trade Details</h2>" not in content
        # The Performance Summary section is always present.
        assert "<h2>Performance Summary</h2>" in content

    def test_report_without_trades_keeps_charts(self, capsys, tmp_path):
        """``--report --report-no-trades`` still renders the chart sections."""
        report_path = tmp_path / "notrades_charts.html"
        result, _ = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
                "--report-no-trades",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "data:image/png;base64," in content
        assert "<h2>Charts</h2>" in content

    def test_report_without_monthly_omits_monthly_heatmap(self, capsys, tmp_path):
        """``--report --report-no-monthly`` omits the Monthly Returns chart."""
        report_path = tmp_path / "nomonthly.html"
        result, _ = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
                "--report-no-monthly",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Monthly Returns" not in content
        # Other charts are still rendered.
        assert "Equity Curve" in content

    def test_report_without_rolling_omits_rolling_charts(self, capsys, tmp_path):
        """``--report --report-no-rolling`` omits the Rolling Sharpe/Volatility charts."""
        report_path = tmp_path / "norolling.html"
        result, _ = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
                "--report-no-rolling",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Rolling Sharpe (60)" not in content
        assert "Rolling Volatility (60)" not in content
        # Other charts are still rendered.
        assert "Equity Curve" in content

    def test_report_all_sections_disabled_still_writes_html(self, capsys, tmp_path):
        """Every optional section disabled still yields a valid report."""
        report_path = tmp_path / "minimal.html"
        result, _ = self._run(
            [
                "--offline",
                "--strategy",
                "rsi",
                "--symbols",
                "AAPL",
                "--days",
                "120",
                "--report",
                str(report_path),
                "--report-no-charts",
                "--report-no-trades",
                "--report-no-monthly",
                "--report-no-rolling",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<h2>Performance Summary</h2>" in content
        assert "<h2>Trade Details</h2>" not in content
        assert "<h2>Charts</h2>" not in content

    def test_combined_report_without_charts_omits_charts_section(self, capsys, tmp_path):
        """``--combined --report --report-no-charts`` omits the Charts section."""
        import multiprocessing

        report_path = tmp_path / "combined_nocharts.html"
        result, _ = self._run(
            [
                "--combined",
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "60",
                "--report",
                str(report_path),
                "--n-jobs",
                str(min(4, multiprocessing.cpu_count() or 1)),
                "--report-no-charts",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<h2>Strategy Comparison</h2>" in content
        assert "data:image/png;base64," not in content
        assert "<h2>Charts</h2>" not in content

    def test_combined_report_all_sections_disabled_still_writes_html(
        self, capsys, tmp_path
    ):
        """Every optional section disabled still yields a valid combined report."""
        import multiprocessing

        report_path = tmp_path / "combined_minimal.html"
        result, _ = self._run(
            [
                "--combined",
                "--offline",
                "--symbols",
                "AAPL",
                "--days",
                "60",
                "--report",
                str(report_path),
                "--n-jobs",
                str(min(4, multiprocessing.cpu_count() or 1)),
                "--report-no-charts",
                "--report-no-trades",
                "--report-no-monthly",
                "--report-no-rolling",
            ],
            capsys,
        )
        assert result == 0
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<h2>Strategy Comparison</h2>" in content
        assert "data:image/png;base64," not in content
        assert "<h2>Charts</h2>" not in content


class TestCliHelpers:
    """Unit tests for the pure helper functions of examples.cli.

    These helpers take data structures (or mocks) and produce files or printed
    output, so they can be tested directly without running a backtest.
    """

    def test_save_json_output_writes_json_file(self, tmp_path):
        path = tmp_path / "out.json"
        data = {"strategy": "ma", "total_return_pct": 15.5, "params": {"fast": 10}}
        assert _save_json_output(str(path), data) is True
        import json

        with open(path) as f:
            assert json.load(f) == data

    def test_save_json_output_writes_csv_file(self, tmp_path):
        path = tmp_path / "out.csv"
        data = {"strategy": "ma", "total_return_pct": 15.5}
        assert _save_json_output(str(path), data) is True
        content = path.read_text()
        assert "strategy,total_return_pct" in content
        assert "ma,15.5" in content

    def test_save_json_output_explicit_format(self, tmp_path):
        path = tmp_path / "out.txt"
        data = {"strategy": "ma", "total_return_pct": 15.5}
        assert _save_json_output(str(path), data, output_format="json") is True
        import json

        with open(path) as f:
            assert json.load(f) == data

    def test_save_json_output_unwritable_path(self, tmp_path):
        path = tmp_path / "missing_dir" / "out.json"
        assert _save_json_output(str(path), {"a": 1}) is False

    def test_print_regime_analysis(self, capsys):
        class _Seg:
            def __init__(self):
                self.regime = type("R", (), {"value": "bull"})()
                self.start = "2024-01-01"
                self.end = "2024-06-30"
                self.volatility = 0.15
                self.return_pct = 8.25

        class _Analysis:
            def summary(self):
                return {
                    "current_regime": "bull",
                    "total_volatility": 0.15,
                    "total_return_pct": 8.25,
                    "n_segments": 1,
                    "periods_per_year": 252,
                }

            @property
            def segments(self):
                return [_Seg()]

        _print_regime_analysis(_Analysis())
        captured = capsys.readouterr()
        assert "Market Regime Analysis" in captured.out
        assert "Current Regime:   bull" in captured.out
        assert "Periods per Year:  252" in captured.out

    def test_print_regime_analysis_no_segments(self, capsys):
        class _Analysis:
            def summary(self):
                return {
                    "current_regime": "sideways",
                    "total_volatility": 0.05,
                    "total_return_pct": 1.5,
                    "n_segments": 0,
                    "periods_per_year": 252,
                }

            @property
            def segments(self):
                return []

        _print_regime_analysis(_Analysis())
        captured = capsys.readouterr()
        assert "Market Regime Analysis" in captured.out
        assert "Current Regime:   sideways" in captured.out

    def test_print_monte_carlo_analysis(self, capsys):
        class _MC:
            def __init__(self):
                self.n_simulations = 100
                self.confidence_level = 0.95
                self.duration_seconds = 1.25
                self._method = "parametric"

            def summary(self):
                return {
                    "probability_of_profit": 0.68,
                    "total_return_pct_mean": 12.5,
                    "total_return_pct_median": 11.8,
                    "total_return_pct_std": 4.2,
                    "sharpe_ratio_mean": 1.2,
                    "sharpe_ratio_median": 1.1,
                    "sharpe_ratio_std": 0.3,
                    "max_drawdown_pct_mean": -8.5,
                    "max_drawdown_pct_median": -7.9,
                    "max_drawdown_pct_std": 2.1,
                    "volatility_mean": 0.18,
                    "volatility_median": 0.17,
                    "volatility_std": 0.04,
                    "total_return_pct_ci_lower": 5.0,
                    "total_return_pct_ci_upper": 20.0,
                    "sharpe_ratio_ci_lower": 0.7,
                    "sharpe_ratio_ci_upper": 1.7,
                    "max_drawdown_pct_ci_lower": -12.0,
                    "max_drawdown_pct_ci_upper": -5.0,
                }

        _print_monte_carlo_analysis(_MC())
        captured = capsys.readouterr()
        assert "Monte Carlo Simulation" in captured.out
        assert "Method:            parametric" in captured.out
        assert "Simulations:       100" in captured.out
        assert "Probability of Profit: 68.00%" in captured.out

    def test_print_monte_carlo_analysis_default_method(self, capsys):
        class _MC:
            def __init__(self):
                self.n_simulations = 50
                self.confidence_level = 0.90
                self.duration_seconds = 0.5

            def summary(self):
                return {
                    "probability_of_profit": 0.55,
                    "total_return_pct_mean": 5.0,
                    "total_return_pct_median": 4.8,
                    "total_return_pct_std": 3.0,
                    "sharpe_ratio_mean": 0.8,
                    "sharpe_ratio_median": 0.75,
                    "sharpe_ratio_std": 0.2,
                    "max_drawdown_pct_mean": -6.0,
                    "max_drawdown_pct_median": -5.5,
                    "max_drawdown_pct_std": 1.5,
                    "volatility_mean": 0.15,
                    "volatility_median": 0.14,
                    "volatility_std": 0.03,
                    "total_return_pct_ci_lower": 1.0,
                    "total_return_pct_ci_upper": 9.0,
                    "sharpe_ratio_ci_lower": 0.4,
                    "sharpe_ratio_ci_upper": 1.2,
                    "max_drawdown_pct_ci_lower": -9.0,
                    "max_drawdown_pct_ci_upper": -3.0,
                }

        _print_monte_carlo_analysis(_MC())
        captured = capsys.readouterr()
        assert "Method:            bootstrap" in captured.out

    def test_print_trade_analysis(self, capsys):
        from unittest.mock import patch

        with patch("quant_trading.backtest.print_trade_analysis") as mock_print:
            _print_trade_analysis("fake-analysis")
            mock_print.assert_called_once_with("fake-analysis")

    def test_default_param_grid_moving_average_crossover(self):
        """``_default_param_grid`` builds one space per tunable constructor param."""
        from quant_trading.optimization import ParameterGrid, ParameterSpace
        from quant_trading.strategies.examples import MovingAverageCrossover

        grid = _default_param_grid(MovingAverageCrossover)
        assert isinstance(grid, ParameterGrid)
        assert set(grid.spaces) == {"fast_period", "slow_period"}
        fast = grid.spaces["fast_period"]
        slow = grid.spaces["slow_period"]
        assert isinstance(fast, ParameterSpace) and isinstance(slow, ParameterSpace)
        assert fast.param_type is int and slow.param_type is int
        assert fast.values == [9, 10, 11]
        assert slow.values == [29, 30, 31]

    def test_default_param_grid_skips_required_and_self_params(self):
        """Constructor params without a default, plus ``self``/``name``, are skipped."""
        from quant_trading.optimization import ParameterGrid

        class Mixed:
            def __init__(self, required: int, optional: float = 1.0, name: str = "x"):
                self.required = required
                self.optional = optional
                self.name = name

        grid = _default_param_grid(Mixed)
        assert isinstance(grid, ParameterGrid)
        assert set(grid.spaces) == {"optional"}
        assert grid.spaces["optional"].param_type is float
        assert grid.spaces["optional"].values == [0.75, 1.0, 1.25]

    def test_default_param_grid_empty_when_unintrospectable(self):
        """A constructor that cannot be introspected yields an empty grid."""
        grid = _default_param_grid(object)
        from quant_trading.optimization import ParameterGrid

        assert isinstance(grid, ParameterGrid)
        assert len(grid.spaces) == 0
        assert grid.generate_combinations() == [{}]

    def test_get_monte_carlo_analysis_forwards_args_and_sets_method(self):
        import pandas as pd

        from quant_trading.backtest.engine import BacktestResult
        from quant_trading.backtest.metrics import calculate_backtest_metrics

        equity = pd.Series(
            [100000.0 * (1.0 + 0.001 * i) for i in range(60)],
            index=pd.date_range("2024-01-01", periods=60, freq="D"),
        )
        result = BacktestResult(
            equity_curve=equity,
            trades=pd.DataFrame(),
            positions={},
            metrics=calculate_backtest_metrics(equity),
            start_date=equity.index[0],
            end_date=equity.index[-1],
            initial_capital=100000.0,
            final_value=float(equity.iloc[-1]),
            total_return=float(equity.iloc[-1] - equity.iloc[0]),
            total_return_pct=float((equity.iloc[-1] / equity.iloc[0] - 1) * 100),
        )
        args = argparse.Namespace(
            mc_simulations=20,
            mc_confidence=0.90,
            mc_method="parametric",
            mc_seed=7,
        )

        mc = _get_monte_carlo_analysis(
            result, args, periods_per_year=252, risk_free_rate=0.02
        )
        assert mc.n_simulations == 20
        assert mc.confidence_level == 0.90
        assert mc._method == "parametric"
        summary = mc.summary()
        assert summary["n_simulations"] == 20
        assert "probability_of_profit" in summary
        assert "total_return_pct_mean" in summary

    def test_default_param_grid_bool_default_param(self):
        """A constructor param with a bool default yields a [False, True] space."""
        from quant_trading.optimization import ParameterGrid, ParameterSpace

        class WithBool:
            def __init__(self, enabled: bool = True):
                self.enabled = enabled

        grid = _default_param_grid(WithBool)
        assert isinstance(grid, ParameterGrid)
        assert set(grid.spaces) == {"enabled"}
        space = grid.spaces["enabled"]
        assert isinstance(space, ParameterSpace)
        assert space.param_type is bool
        assert space.values == [False, True]

    def test_default_param_grid_string_default_param(self):
        """A constructor param with a non-numeric default yields a single-value space."""
        from quant_trading.optimization import ParameterGrid, ParameterSpace

        class WithStr:
            def __init__(self, symbol: str = "AAPL"):
                self.symbol = symbol

        grid = _default_param_grid(WithStr)
        assert isinstance(grid, ParameterGrid)
        assert set(grid.spaces) == {"symbol"}
        space = grid.spaces["symbol"]
        assert isinstance(space, ParameterSpace)
        assert space.param_type is str
        assert space.values == ["AAPL"]

    def test_default_param_grid_empty_when_signature_raises(self):
        """A constructor whose signature cannot be introspected yields an empty grid."""

        class Unintrospectable:
            __init__ = int

        grid = _default_param_grid(Unintrospectable)
        from quant_trading.optimization import ParameterGrid

        assert isinstance(grid, ParameterGrid)
        assert len(grid.spaces) == 0
        assert grid.generate_combinations() == [{}]

    def test_get_monte_carlo_analysis_swallows_method_assignment_failure(self):
        """``mc._method = ...`` failing must not break the returned analysis."""
        import pandas as pd

        from quant_trading.backtest.engine import BacktestResult
        from quant_trading.backtest.metrics import calculate_backtest_metrics

        equity = pd.Series(
            [100000.0 * (1.0 + 0.001 * i) for i in range(60)],
            index=pd.date_range("2024-01-01", periods=60, freq="D"),
        )
        result = BacktestResult(
            equity_curve=equity,
            trades=pd.DataFrame(),
            positions={},
            metrics=calculate_backtest_metrics(equity),
            start_date=equity.index[0],
            end_date=equity.index[-1],
            initial_capital=100000.0,
            final_value=float(equity.iloc[-1]),
            total_return=float(equity.iloc[-1] - equity.iloc[0]),
            total_return_pct=float((equity.iloc[-1] / equity.iloc[0] - 1) * 100),
        )
        args = argparse.Namespace(
            mc_simulations=20,
            mc_confidence=0.90,
            mc_method="parametric",
            mc_seed=7,
        )

        class _LockedMC:
            __slots__ = ("confidence_level", "n_simulations")

            def __init__(self):
                self.n_simulations = 20
                self.confidence_level = 0.90

            def summary(self):
                return {"n_simulations": 20, "probability_of_profit": 0.5}

        with patch("examples.cli.run_monte_carlo", return_value=_LockedMC()):
            mc = _get_monte_carlo_analysis(
                result, args, periods_per_year=252, risk_free_rate=0.02
            )

        assert mc.n_simulations == 20
        assert mc.confidence_level == 0.90
        assert not hasattr(mc, "_method")
        summary = mc.summary()
        assert summary["n_simulations"] == 20
        assert "probability_of_profit" in summary


class TestRunOptimizationWalkForwardEndToEnd:
    """End-to-end tests for run_optimization and run_walk_forward."""

    def _base_opt_args(self, tmp_path, **overrides):
        import argparse

        base = {
            "symbols": ["AAPL", "MSFT"],
            "days": 120,
            "strategy": "ma",
            "initial_capital": 100000.0,
            "commission": 0.001,
            "slippage": 0.0005,
            "interval": "1d",
            "optimizer": "grid",
            "objective": "sharpe",
            "n_iter": 5,
            "n_jobs": 1,
            "bayesian_n_initial": 3,
            "bayesian_acq_func": "gp_hedge",
            "bayesian_acq_optimizer": "lbfgs",
            "bayesian_noise": "gaussian",
            "output": None,
            "output_format": None,
            "output_strategy_config": None,
            # MA strategy params / ranges for grid
            "fast_period": 10,
            "slow_period": 30,
            "ma_fast_range": "5,10,5",
            "ma_slow_range": "20,30,10",
            # required by create_param_grid for other strategies (unused here)
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "bb_period": 20,
            "bb_std": 2.0,
            "st_period": 10,
            "st_multiplier": 3.0,
            "dc_period": 20,
            "dc_exit_period": None,
            "aroon_period": 25,
            "kc_ema_period": 20,
            "kc_atr_period": 10,
            "kc_multiplier": 2.0,
            "kc_use_middle_cross": False,
            "atr_period": 14,
            "atr_multiplier": 2.0,
            "stoch_k_period": 14,
            "stoch_d_period": 3,
            "stoch_oversold": 20,
            "stoch_overbought": 80,
            "stoch_use_midline": False,
            "tenkan_period": 9,
            "kijun_period": 26,
            "senkou_b_period": 52,
            "sar_step": 0.02,
            "sar_max_step": 0.2,
            # walk-forward
            "wf_windows": 2,
            "wf_train_size": 0.6,
            "wf_step_size": None,
            "wf_anchored": False,
            "wf_optimizer": "grid",
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    def _synthetic_config(self, days=120, seed=42):
        config = Config()
        config.data.provider = "synthetic"
        config.data.offline = True
        config.data.synthetic_days = days
        config.data.synthetic_seed = seed
        return config

    def test_run_optimization_offline_returns_zero_and_prints_results(self, tmp_path, capsys):
        from datetime import datetime, timedelta

        from examples.cli import run_optimization

        args = self._base_opt_args(tmp_path)
        config = self._synthetic_config(days=120, seed=42)
        end_date = datetime(2024, 12, 31)
        start_date = end_date - timedelta(days=120)

        result = run_optimization(args, config, start_date, end_date)

        assert result == 0
        out = capsys.readouterr().out
        assert "Optimization Complete" in out
        assert "Best Parameters" in out
        assert "Top 10 Results" in out

    def test_run_optimization_writes_output_json(self, tmp_path):
        import json
        from datetime import datetime, timedelta

        from examples.cli import run_optimization

        output = tmp_path / "opt.json"
        args = self._base_opt_args(tmp_path, output=str(output))
        config = self._synthetic_config(days=120, seed=42)
        end_date = datetime(2024, 12, 31)
        start_date = end_date - timedelta(days=120)

        result = run_optimization(args, config, start_date, end_date)

        assert result == 0
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["strategy"] == "MovingAverageCrossover"
        assert data["optimizer"] == "grid"
        assert "best_params" in data
        assert "best_score" in data
        assert isinstance(data.get("all_results"), list)

    def test_run_walk_forward_offline_returns_zero_and_prints_results(self, tmp_path, capsys):
        from datetime import datetime, timedelta

        from examples.cli import run_walk_forward

        args = self._base_opt_args(
            tmp_path,
            walk_forward=True,
            wf_windows=2,
            wf_train_size=0.6,
            wf_anchored=False,
            wf_optimizer="grid",
        )
        config = self._synthetic_config(days=120, seed=42)
        end_date = datetime(2024, 12, 31)
        start_date = end_date - timedelta(days=120)

        result = run_walk_forward(args, config, start_date, end_date)

        assert result == 0
        out = capsys.readouterr().out
        assert "Walk-Forward Optimization Complete" in out
        assert "Window Results" in out
        assert "Summary:" in out

    def test_run_walk_forward_writes_output_json(self, tmp_path):
        import json
        from datetime import datetime, timedelta

        from examples.cli import run_walk_forward

        output = tmp_path / "wf.json"
        args = self._base_opt_args(
            tmp_path,
            walk_forward=True,
            output=str(output),
            wf_windows=2,
            wf_train_size=0.6,
            wf_anchored=False,
            wf_optimizer="grid",
        )
        config = self._synthetic_config(days=120, seed=42)
        end_date = datetime(2024, 12, 31)
        start_date = end_date - timedelta(days=120)

        result = run_walk_forward(args, config, start_date, end_date)

        assert result == 0
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["strategy"] == "MovingAverageCrossover"
        assert "walk_forward" in data
        assert "summary" in data
        assert "window_results" in data
        assert "walk_forward_result" in data
        assert data["summary"]["n_windows"] == 2



if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
