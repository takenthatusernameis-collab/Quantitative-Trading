"""Tests for CLI functionality."""

import argparse
import json
import tempfile
from unittest.mock import MagicMock, patch

from examples.cli import (
    create_config,
    create_strategy,
    init_config,
    list_providers,
    list_strategies,
    main,
    parse_args,
    run_combined,
)
from quant_trading.config.settings import Config
from quant_trading.strategies.examples import (
    BollingerBandsStrategy,
    DonchianChannelStrategy,
    MACDStrategy,
    MovingAverageCrossover,
    RSIStrategy,
    SuperTrendStrategy,
)


class TestParseArgs:
    """Tests for argument parsing."""

    def test_default_args(self):
        with patch("sys.argv", ["cli.py"]):
            args = parse_args()
        assert args.symbols == ["AAPL", "MSFT", "GOOGL"]
        assert args.days == 365
        assert args.initial_capital == 100000.0
        assert args.commission == 0.001
        assert args.slippage == 0.0005
        assert args.interval == "1d"
        assert args.strategy == "ma"
        assert args.fast_period == 10
        assert args.slow_period == 30
        assert args.provider is None
        assert args.offline is False
        assert args.alphavantage_key is None
        assert args.combined is False

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
            args = ["--walk-forward", "--offline", "--strategy", "ma", "--days", "120", "--wf-windows", "2"]
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

        mock_results = []
        for name, ret in [
            ("MA_Crossover_10_30", 15.5),
            ("RSI_14", 12.3),
            ("BB_20_2.0", 18.7),
            ("MACD_12_26_9", 10.0),
            ("SuperTrend_10_3.0", 8.5),
            ("Donchian_20_20", 14.2),
            ("Aroon_25", 11.0),
            ("Keltner_20_10_2.0", 13.0),
        ]:
            m = MagicMock(
                spec=[
                    "name",
                    "total_return_pct",
                    "metrics",
                    "initial_capital",
                    "final_value",
                    "total_return",
                ]
            )
            m.name = name
            m.total_return_pct = ret
            m.metrics = mock_metrics
            m.initial_capital = 100000.0
            m.final_value = 100000.0 * (1 + ret / 100)
            m.total_return = 100000.0 * ret / 100
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

        mock_result = MagicMock(
            spec=[
                "name",
                "total_return_pct",
                "metrics",
                "initial_capital",
                "final_value",
                "total_return",
            ]
        )
        mock_result.name = "MA_Crossover_10_30"
        mock_result.total_return_pct = 15.5
        mock_result.metrics = mock_metrics
        mock_result.initial_capital = 100000.0
        mock_result.final_value = 115500.0
        mock_result.total_return = 15500.0

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
                "--offline", "--regime", "--monte-carlo", "--trade-analysis",
                "--output", output_path, "--symbols", "AAPL", "--days", "120",
                "--mc-simulations", "30"
            ]
            with patch("sys.argv", ["cli.py"] + args):
                result = main()
            assert result == 0
            with open(output_path) as f:
                data = json.load(f)
            assert "regime_analysis" in data
            assert "monte_carlo" in data
            assert "trade_analysis" in data


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

            def generate_signals(self, data, symbol: str):
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

            def generate_signals(self, data, symbol: str):
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

            def generate_signals(self, data, symbol: str):
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

                mock_result = MagicMock()
                mock_result.name = "CustomStrategy"
                mock_result.total_return_pct = 5.0
                mock_result.metrics = mock_metrics
                mock_result.initial_capital = 100000.0
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


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
