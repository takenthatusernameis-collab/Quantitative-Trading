"""Tests for configuration management."""

import os
import tempfile

import pytest

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

    @pytest.mark.parametrize("initial_capital", [0.0, -1000.0])
    def test_rejects_invalid_initial_capital(self, initial_capital):
        with pytest.raises(ValueError, match="invalid initial_capital"):
            BacktestConfig(initial_capital=initial_capital)

    @pytest.mark.parametrize("periods_per_year", [0, -1])
    def test_rejects_invalid_periods_per_year(self, periods_per_year):
        with pytest.raises(ValueError, match="invalid periods_per_year"):
            BacktestConfig(periods_per_year=periods_per_year)

    @pytest.mark.parametrize("commission", [-0.1, 1.5])
    def test_rejects_invalid_commission(self, commission):
        with pytest.raises(ValueError, match="invalid commission"):
            BacktestConfig(commission=commission)

    @pytest.mark.parametrize("slippage", [-0.1, 1.5])
    def test_rejects_invalid_slippage(self, slippage):
        with pytest.raises(ValueError, match="invalid slippage"):
            BacktestConfig(slippage=slippage)

    def test_accepts_boundary_valid_values(self):
        config = BacktestConfig(
            initial_capital=1.0,
            commission=0.0,
            slippage=1.0,
            periods_per_year=1,
        )
        assert config.initial_capital == 1.0
        assert config.commission == 0.0
        assert config.slippage == 1.0
        assert config.periods_per_year == 1

    def test_from_dict_rejects_invalid_values(self):
        with pytest.raises(ValueError, match="invalid commission"):
            BacktestConfig.from_dict({"commission": 1.5})

    def test_from_yaml_rejects_invalid_values(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("backtest:\n  slippage: -0.05\n")
        with pytest.raises(ValueError, match="invalid slippage"):
            Config.from_yaml(str(path))


class TestRiskConfig:
    """Tests for RiskConfig."""

    def test_defaults(self):
        config = RiskConfig()
        assert config.max_position_size == 0.1
        assert config.max_drawdown == 0.20
        assert config.max_leverage == 1.0
        assert config.trailing_stop_pct == 0.0
        assert config.trailing_stop_activation_pct == 0.0

    def test_trailing_stop_is_configurable(self):
        config = RiskConfig(trailing_stop_pct=0.08, trailing_stop_activation_pct=0.05)
        assert config.trailing_stop_pct == 0.08
        assert config.trailing_stop_activation_pct == 0.05

    @pytest.mark.parametrize("max_position_size", [0.0, -0.1, 1.5])
    def test_rejects_invalid_max_position_size(self, max_position_size):
        with pytest.raises(ValueError, match="invalid max_position_size"):
            RiskConfig(max_position_size=max_position_size)

    @pytest.mark.parametrize("max_portfolio_risk", [0.0, -0.1, 1.5])
    def test_rejects_invalid_max_portfolio_risk(self, max_portfolio_risk):
        with pytest.raises(ValueError, match="invalid max_portfolio_risk"):
            RiskConfig(max_portfolio_risk=max_portfolio_risk)

    @pytest.mark.parametrize("max_drawdown", [-0.1, 1.5])
    def test_rejects_invalid_max_drawdown(self, max_drawdown):
        with pytest.raises(ValueError, match="invalid max_drawdown"):
            RiskConfig(max_drawdown=max_drawdown)

    @pytest.mark.parametrize("stop_loss_pct", [-0.1, 1.5])
    def test_rejects_invalid_stop_loss_pct(self, stop_loss_pct):
        with pytest.raises(ValueError, match="invalid stop_loss_pct"):
            RiskConfig(stop_loss_pct=stop_loss_pct)

    @pytest.mark.parametrize("take_profit_pct", [-0.1, 1.5])
    def test_rejects_invalid_take_profit_pct(self, take_profit_pct):
        with pytest.raises(ValueError, match="invalid take_profit_pct"):
            RiskConfig(take_profit_pct=take_profit_pct)

    @pytest.mark.parametrize("max_leverage", [0.0, -1.0])
    def test_rejects_invalid_max_leverage(self, max_leverage):
        with pytest.raises(ValueError, match="invalid max_leverage"):
            RiskConfig(max_leverage=max_leverage)

    @pytest.mark.parametrize("trailing_stop_pct", [-0.1, 1.5])
    def test_rejects_invalid_trailing_stop_pct(self, trailing_stop_pct):
        with pytest.raises(ValueError, match="invalid trailing_stop_pct"):
            RiskConfig(trailing_stop_pct=trailing_stop_pct)

    @pytest.mark.parametrize(
        "trailing_stop_activation_pct", [-0.1, 1.5]
    )
    def test_rejects_invalid_trailing_stop_activation_pct(
        self, trailing_stop_activation_pct
    ):
        with pytest.raises(
            ValueError, match="invalid trailing_stop_activation_pct"
        ):
            RiskConfig(trailing_stop_activation_pct=trailing_stop_activation_pct)

    def test_accepts_boundary_valid_values(self):
        config = RiskConfig(
            max_position_size=1.0,
            max_portfolio_risk=1.0,
            max_drawdown=0.0,
            stop_loss_pct=0.0,
            take_profit_pct=1.0,
            max_leverage=1.0,
            trailing_stop_pct=0.0,
            trailing_stop_activation_pct=1.0,
        )
        assert config.max_position_size == 1.0
        assert config.max_portfolio_risk == 1.0
        assert config.max_drawdown == 0.0
        assert config.stop_loss_pct == 0.0
        assert config.take_profit_pct == 1.0
        assert config.max_leverage == 1.0
        assert config.trailing_stop_pct == 0.0
        assert config.trailing_stop_activation_pct == 1.0

    def test_from_dict_rejects_invalid_values(self):
        with pytest.raises(ValueError, match="invalid max_drawdown"):
            RiskConfig.from_dict({"max_drawdown": 1.5})

    def test_from_yaml_rejects_invalid_values(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("risk:\n  max_position_size: 0\n")
        with pytest.raises(ValueError, match="invalid max_position_size"):
            Config.from_yaml(str(path))


class TestPortfolioConfig:
    """Tests for PortfolioConfig."""

    def test_defaults(self):
        config = PortfolioConfig()
        assert config.rebalance_frequency == "monthly"
        assert config.max_positions == 20

    @pytest.mark.parametrize("max_positions", [0, -1])
    def test_rejects_invalid_max_positions(self, max_positions):
        with pytest.raises(ValueError, match="invalid max_positions"):
            PortfolioConfig(max_positions=max_positions)

    @pytest.mark.parametrize("min_position_size", [-0.1, 1.5])
    def test_rejects_invalid_min_position_size(self, min_position_size):
        with pytest.raises(ValueError, match="invalid min_position_size"):
            PortfolioConfig(min_position_size=min_position_size)

    def test_accepts_boundary_valid_values(self):
        config = PortfolioConfig(max_positions=1, min_position_size=0.0)
        assert config.max_positions == 1
        assert config.min_position_size == 0.0
        config = PortfolioConfig(max_positions=5, min_position_size=1.0)
        assert config.max_positions == 5
        assert config.min_position_size == 1.0

    def test_from_dict_rejects_invalid_values(self):
        with pytest.raises(ValueError, match="invalid max_positions"):
            PortfolioConfig.from_dict({"max_positions": 0})

    def test_from_yaml_rejects_invalid_values(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("portfolio:\n  min_position_size: -0.05\n")
        with pytest.raises(ValueError, match="invalid min_position_size"):
            Config.from_yaml(str(path))


class TestDataConfig:
    """Tests for DataConfig."""

    def test_defaults(self):
        config = DataConfig()
        assert config.provider == "yfinance"
        assert config.default_interval == "1d"

    @pytest.mark.parametrize("provider", ["", None])
    def test_rejects_invalid_provider(self, provider):
        with pytest.raises(ValueError, match="invalid provider"):
            DataConfig(provider=provider)

    @pytest.mark.parametrize("default_interval", ["", None])
    def test_rejects_invalid_default_interval(self, default_interval):
        with pytest.raises(ValueError, match="invalid default_interval"):
            DataConfig(default_interval=default_interval)

    @pytest.mark.parametrize("default_period", ["", None])
    def test_rejects_invalid_default_period(self, default_period):
        with pytest.raises(ValueError, match="invalid default_period"):
            DataConfig(default_period=default_period)

    @pytest.mark.parametrize("synthetic_days", [0, -1, -365])
    def test_rejects_invalid_synthetic_days(self, synthetic_days):
        with pytest.raises(ValueError, match="invalid synthetic_days"):
            DataConfig(synthetic_days=synthetic_days)

    def test_accepts_boundary_valid_values(self):
        config = DataConfig(
            provider="yfinance",
            default_interval="1d",
            default_period="1y",
            synthetic_days=1,
        )
        assert config.provider == "yfinance"
        assert config.default_interval == "1d"
        assert config.default_period == "1y"
        assert config.synthetic_days == 1

    def test_from_dict_rejects_invalid_values(self):
        with pytest.raises(ValueError, match="invalid synthetic_days"):
            DataConfig.from_dict({"synthetic_days": 0})

    def test_from_yaml_rejects_invalid_values(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text('data:\n  provider: ""\n')
        with pytest.raises(ValueError, match="invalid provider"):
            Config.from_yaml(str(path))


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

    def test_type_matches_accepts_unrecognized_annotation(self):
        """_type_matches returns True for annotations it does not recognize.

        The fallback at settings.py:136 accepts anything when the annotation is
        not one of the known primitives or a union, so custom class types (such
        as nested dataclass fields) do not raise during type checking.
        """
        from quant_trading.config import settings

        assert settings._type_matches(DataConfig, "anything") is True
        assert settings._type_matches(DataConfig, 123) is True
        assert settings._type_matches(DataConfig, None) is True

    def test_to_yaml_bare_filename(self, tmp_path, monkeypatch):
        """to_yaml with a bare filename skips directory creation (settings.py:96->98)."""
        config = Config()
        monkeypatch.chdir(tmp_path)
        config.to_yaml("bare_config.yaml")
        assert os.path.exists("bare_config.yaml")


class TestConfigFromYamlTypeChecking:
    """Tests that from_yaml rejects wrongly-typed values as ValueError."""

    def _write(self, tmp_path, content):
        path = os.path.join(str(tmp_path), "config.yaml")
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_float_field_rejects_string(self, tmp_path):
        path = self._write(tmp_path, "backtest:\n  initial_capital: abc\n")
        with pytest.raises(ValueError, match="invalid config field"):
            Config.from_yaml(path)

    def test_int_is_valid_for_float_field(self, tmp_path):
        path = self._write(tmp_path, "backtest:\n  initial_capital: 50000\n")
        config = Config.from_yaml(path)
        assert config.backtest.initial_capital == 50000.0

    def test_float_is_not_valid_for_int_field(self, tmp_path):
        path = self._write(tmp_path, "portfolio:\n  max_positions: 20.5\n")
        with pytest.raises(ValueError, match="invalid config field"):
            Config.from_yaml(path)

    def test_bool_is_not_valid_for_int_field(self, tmp_path):
        path = self._write(tmp_path, "backtest:\n  periods_per_year: true\n")
        with pytest.raises(ValueError, match="invalid config field"):
            Config.from_yaml(path)

    def test_int_is_not_valid_for_bool_field(self, tmp_path):
        path = self._write(tmp_path, "data:\n  offline: 1\n")
        with pytest.raises(ValueError, match="invalid config field"):
            Config.from_yaml(path)

    def test_bool_is_valid_for_bool_field(self, tmp_path):
        path = self._write(tmp_path, "data:\n  offline: true\n")
        config = Config.from_yaml(path)
        assert config.data.offline is True

    def test_none_is_valid_for_optional_str_field(self, tmp_path):
        path = self._write(tmp_path, "data:\n  alphavantage_api_key: null\n")
        config = Config.from_yaml(path)
        assert config.data.alphavantage_api_key is None

    def test_string_is_not_valid_for_optional_str_field(self, tmp_path):
        path = self._write(tmp_path, "data:\n  alphavantage_api_key: 123\n")
        with pytest.raises(ValueError, match="invalid config field"):
            Config.from_yaml(path)

    def test_top_level_field_is_checked(self, tmp_path):
        path = self._write(tmp_path, "logging_level: 123\n")
        with pytest.raises(ValueError, match="invalid config field"):
            Config.from_yaml(path)

    def test_unknown_keys_still_ignored_when_types_valid(self, tmp_path):
        path = self._write(
            tmp_path, "backtest:\n  initial_capital: 100000.0\n  bogus_key: ignored\n"
        )
        config = Config.from_yaml(path)
        assert config.backtest.initial_capital == 100000.0


class TestDataConfigSerialization:
    """Tests for DataConfig.to_dict / from_dict round-trips."""

    def test_to_dict_contains_all_fields(self):
        config = DataConfig(provider="synthetic", offline=True, synthetic_days=100)
        assert config.to_dict() == {
            "provider": "synthetic",
            "cache_dir": "./data/cache",
            "default_interval": "1d",
            "default_period": "1y",
            "offline": True,
            "synthetic_days": 100,
            "synthetic_seed": 42,
            "alphavantage_api_key": None,
        }

    def test_round_trip(self):
        config = DataConfig(
            provider="alphavantage",
            cache_dir="./cache",
            synthetic_seed=7,
            alphavantage_api_key="demo",
        )
        assert DataConfig.from_dict(config.to_dict()) == config

    def test_missing_keys_use_defaults(self):
        assert DataConfig.from_dict({}) == DataConfig()

    def test_extra_keys_ignored(self):
        restored = DataConfig.from_dict(
            {"provider": "yfinance", "bogus": 1, "another": "x"}
        )
        assert restored.provider == "yfinance"
        assert not hasattr(restored, "bogus")


class TestBacktestConfigSerialization:
    """Tests for BacktestConfig.to_dict / from_dict round-trips."""

    def test_to_dict_contains_all_fields(self):
        config = BacktestConfig(initial_capital=50000.0, commission=0.002)
        d = config.to_dict()
        assert d["initial_capital"] == 50000.0
        assert d["commission"] == 0.002
        assert d["periods_per_year"] == 252
        assert d["enable_stop_exits"] is False

    def test_round_trip(self):
        config = BacktestConfig(
            initial_capital=50000.0,
            commission=0.002,
            periods_per_year=12,
            enable_stop_exits=True,
        )
        assert BacktestConfig.from_dict(config.to_dict()) == config

    def test_int_values_coerced_to_float(self):
        restored = BacktestConfig.from_dict({"initial_capital": 50000, "slippage": 0})
        assert restored.initial_capital == 50000.0
        assert restored.slippage == 0.0

    def test_missing_keys_use_defaults(self):
        assert BacktestConfig.from_dict({}) == BacktestConfig()

    def test_extra_keys_ignored(self):
        restored = BacktestConfig.from_dict({"initial_capital": 1000, "bogus": 1})
        assert restored.initial_capital == 1000.0
        assert not hasattr(restored, "bogus")


class TestRiskConfigSerialization:
    """Tests for RiskConfig.to_dict / from_dict round-trips."""

    def test_round_trip(self):
        config = RiskConfig(max_position_size=0.15, max_drawdown=0.10, max_leverage=2.0)
        assert RiskConfig.from_dict(config.to_dict()) == config

    def test_missing_keys_use_defaults(self):
        assert RiskConfig.from_dict({}) == RiskConfig()

    def test_extra_keys_ignored(self):
        restored = RiskConfig.from_dict({"max_drawdown": 0.5, "bogus": 1})
        assert restored.max_drawdown == 0.5
        assert not hasattr(restored, "bogus")


class TestPortfolioConfigSerialization:
    """Tests for PortfolioConfig.to_dict / from_dict round-trips."""

    def test_round_trip(self):
        config = PortfolioConfig(rebalance_frequency="weekly", max_positions=10)
        assert PortfolioConfig.from_dict(config.to_dict()) == config

    def test_missing_keys_use_defaults(self):
        assert PortfolioConfig.from_dict({}) == PortfolioConfig()

    def test_extra_keys_ignored(self):
        restored = PortfolioConfig.from_dict({"max_positions": 10, "bogus": 1})
        assert restored.max_positions == 10
        assert restored.rebalance_frequency == "monthly"
        assert not hasattr(restored, "bogus")


class TestConfigSerialization:
    """Tests for Config.to_dict / from_dict round-trips."""

    def test_to_dict_nests_sub_configs(self):
        config = Config(logging_level="DEBUG")
        d = config.to_dict()
        assert set(d) == {
            "data",
            "backtest",
            "risk",
            "portfolio",
            "logging_level",
            "output_dir",
        }
        assert d["logging_level"] == "DEBUG"
        assert d["data"]["provider"] == "yfinance"
        assert d["backtest"]["initial_capital"] == 100000.0

    def test_round_trip(self):
        config = Config(
            data=DataConfig(provider="synthetic", offline=True),
            backtest=BacktestConfig(initial_capital=50000.0),
            risk=RiskConfig(max_position_size=0.15),
            portfolio=PortfolioConfig(max_positions=10),
            logging_level="DEBUG",
            output_dir="./out",
        )
        assert Config.from_dict(config.to_dict()) == config

    def test_missing_keys_use_defaults(self):
        assert Config.from_dict({}) == Config()

    def test_missing_sub_configs_use_defaults(self):
        restored = Config.from_dict({"data": {"provider": "synthetic"}})
        assert restored.data.provider == "synthetic"
        assert restored.backtest == BacktestConfig()
        assert restored.risk == RiskConfig()
        assert restored.portfolio == PortfolioConfig()
        assert restored.logging_level == "INFO"
        assert restored.output_dir == "./output"

    def test_extra_keys_ignored(self):
        restored = Config.from_dict({"logging_level": "DEBUG", "unknown": 1})
        assert restored.logging_level == "DEBUG"
        assert not hasattr(restored, "unknown")


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
