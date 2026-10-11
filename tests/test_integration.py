"""Integration tests wiring Config from YAML into the backtest engine."""

import os
import tempfile
from datetime import datetime, timedelta

from quant_trading.backtest.engine import BacktestEngine
from quant_trading.config.settings import Config
from quant_trading.data.providers import DataManager
from quant_trading.strategies.examples import MovingAverageCrossover

from .test_backtest_engine import MockDataProvider, create_mock_data


def test_config_from_yaml_feeds_engine():
    """A Config loaded from YAML must drive BacktestEngine settings."""
    yaml_content = (
        "data:\n"
        "  provider: synthetic\n"
        "  cache_dir: ./data/cache\n"
        "  default_interval: 1d\n"
        "  default_period: 1y\n"
        "backtest:\n"
        "  initial_capital: 25000.0\n"
        "  commission: 0.002\n"
        "  slippage: 0.001\n"
        "  risk_free_rate: 0.03\n"
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
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.yaml")
        with open(path, "w") as f:
            f.write(yaml_content)
        config = Config.from_yaml(path)

    assert config.backtest.initial_capital == 25000.0
    assert config.backtest.commission == 0.002
    assert config.backtest.slippage == 0.001
    assert config.backtest.risk_free_rate == 0.03

    symbols = ["AAPL", "MSFT"]
    mock_data = create_mock_data(symbols, days=60)
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    engine = BacktestEngine(
        config=config.backtest,
        data_manager=data_manager,
    )
    engine.add_strategy(
        MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA")
    )

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()
    result = engine.run(symbols, start_date, end_date, "1d")

    assert result.initial_capital == 25000.0
    assert result.final_value > 0
    assert len(result.equity_curve) > 0
    # Trades must carry the commission/slippage loaded from YAML.
    if len(result.trades) > 0:
        assert (result.trades["commission"] == 0.002).all()
        assert (result.trades["slippage"] == 0.001).all()


def test_default_config_feeds_engine():
    """The default Config must also drive the engine with its defaults."""
    config = Config()

    symbols = ["AAPL"]
    mock_data = create_mock_data(symbols, days=60)
    provider = MockDataProvider(mock_data)
    data_manager = DataManager([provider])

    engine = BacktestEngine(
        config=config.backtest,
        data_manager=data_manager,
    )
    engine.add_strategy(
        MovingAverageCrossover(fast_period=5, slow_period=15, name="Test_MA")
    )

    start_date = datetime.now() - timedelta(days=50)
    end_date = datetime.now()
    result = engine.run(symbols, start_date, end_date, "1d")

    assert result.initial_capital == config.backtest.initial_capital
    assert result.final_value > 0


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
