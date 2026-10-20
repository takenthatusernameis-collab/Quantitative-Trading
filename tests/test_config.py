"""Tests for configuration management."""

import os
import tempfile

from quant_trading.config.settings import (
    BacktestConfig,
    Config,
    DataConfig,
    PortfolioConfig,
    RiskConfig,
)


class TestBacktestConfig:
    """Tests for BacktestConfig."""

    def test_defaults(self):
        config = BacktestConfig()
        assert config.initial_capital == 100000.0
        assert config.commission == 0.001
        assert config.slippage == 0.0005
        assert config.risk_free_rate == 0.02
        assert config.periods_per_year == 252

    def test_custom(self):
        config = BacktestConfig(initial_capital=50000.0, commission=0.002)
        assert config.initial_capital == 50000.0
        assert config.commission == 0.002

    def test_periods_per_year_is_configurable(self):
        """Non-daily annualization periods must be configurable."""
        config = BacktestConfig(periods_per_year=12)
        assert config.periods_per_year == 12


class TestRiskConfig:
    """Tests for RiskConfig."""

    def test_defaults(self):
        config = RiskConfig()
        assert config.max_position_size == 0.1
        assert config.max_drawdown == 0.20
        assert config.max_leverage == 1.0


class TestPortfolioConfig:
    """Tests for PortfolioConfig."""

    def test_defaults(self):
        config = PortfolioConfig()
        assert config.rebalance_frequency == "monthly"
        assert config.max_positions == 20


class TestDataConfig:
    """Tests for DataConfig."""

    def test_defaults(self):
        config = DataConfig()
        assert config.provider == "yfinance"
        assert config.default_interval == "1d"


class TestConfig:
    """Tests for the main Config class."""

    def test_default_initialization(self):
        config = Config()
        assert isinstance(config.backtest, BacktestConfig)
        assert isinstance(config.risk, RiskConfig)
        assert isinstance(config.portfolio, PortfolioConfig)
        assert isinstance(config.data, DataConfig)
        assert config.logging_level == "INFO"

    def test_update(self):
        config = Config()
        config.update(logging_level="DEBUG")
        assert config.logging_level == "DEBUG"

    def test_update_unknown_key_ignored(self):
        config = Config()
        config.update(nonexistent_attr="value")  # should not raise
        assert not hasattr(config, "nonexistent_attr")

    def test_yaml_round_trip(self):
        """to_yaml followed by from_yaml must reproduce the configuration."""
        config = Config(
            data=DataConfig(provider="yfinance", cache_dir="./cache"),
            backtest=BacktestConfig(initial_capital=50000.0, commission=0.002),
            risk=RiskConfig(max_position_size=0.15, max_drawdown=0.10),
            portfolio=PortfolioConfig(rebalance_frequency="weekly", max_positions=10),
            logging_level="DEBUG",
            output_dir="./out",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "config.yaml")
            config.to_yaml(path)
            assert os.path.exists(path)

            loaded = Config.from_yaml(path)

        assert loaded.data == config.data
        assert loaded.backtest == config.backtest
        assert loaded.risk == config.risk
        assert loaded.portfolio == config.portfolio
        assert loaded.logging_level == config.logging_level
        assert loaded.output_dir == config.output_dir

    def test_yaml_output_is_plain_mapping(self):
        """Serialized YAML must not contain python/object tags."""
        config = Config()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.yaml")
            config.to_yaml(path)
            with open(path) as f:
                content = f.read()
        assert "!!python/object" not in content
        assert "backtest:" in content

    def test_from_yaml_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "missing.yaml")
            try:
                Config.from_yaml(path)
            except FileNotFoundError:
                return
            raise AssertionError("Expected FileNotFoundError")

    def test_from_yaml_invalid_content_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.yaml")
            with open(path, "w") as f:
                f.write("just: a\n  bad: [indent\n")
            try:
                Config.from_yaml(path)
            except (ValueError, TypeError, OSError):
                return
            raise AssertionError("Expected an error for malformed YAML")

    def test_from_yaml_unknown_keys_ignored(self):
        """Unknown top-level keys should not crash deserialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.yaml")
            with open(path, "w") as f:
                f.write(
                    "backtest:\n"
                    "  initial_capital: 100000.0\n"
                    "  commission: 0.001\n"
                    "  slippage: 0.0005\n"
                    "  risk_free_rate: 0.02\n"
                    "data:\n"
                    "  provider: yfinance\n"
                    "  cache_dir: ./data/cache\n"
                    "  default_interval: 1d\n"
                    "  default_period: 1y\n"
                    "risk:\n"
                    "  max_position_size: 0.1\n"
                    "  max_portfolio_risk: 0.02\n"
                    "  stop_loss_pct: 0.05\n"
                    "  take_profit_pct: 0.15\n"
                    "  max_drawdown: 0.2\n"
                    "portfolio:\n"
                    "  rebalance_frequency: monthly\n"
                    "  max_positions: 20\n"
                    "  min_position_size: 0.01\n"
                    "logging_level: INFO\n"
                    "output_dir: ./output\n"
                    "extra_unknown_key: ignored\n"
                )
            config = Config.from_yaml(path)
        assert config.backtest.initial_capital == 100000.0

    def test_from_yaml_non_mapping_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.yaml")
            with open(path, "w") as f:
                f.write("- item1\n- item2\n")
            try:
                Config.from_yaml(path)
            except ValueError:
                return
            raise AssertionError("Expected ValueError for non-mapping YAML")

    def test_filter_fields_non_dict_returns_empty(self):
        from quant_trading.config import settings

        result = settings._filter_fields(DataConfig, None)
        assert result == {}
        result = settings._filter_fields(DataConfig, "not_a_dict")
        assert result == {}

    def test_to_yaml_bare_filename(self, tmp_path, monkeypatch):
        """to_yaml with a bare filename skips directory creation (settings.py:96->98)."""
        config = Config()
        monkeypatch.chdir(tmp_path)
        config.to_yaml("bare_config.yaml")
        assert os.path.exists("bare_config.yaml")


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
