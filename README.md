# Quantitative Trading Framework

A modular Python framework for algorithmic trading strategies, backtesting, and portfolio management.

## Features

- **Strategy Framework**: Abstract base class for creating custom trading strategies
- **Built-in Strategies**: Moving Average Crossover, RSI Mean Reversion, Bollinger Bands
- **Backtesting Engine**: Event-driven backtest with realistic costs (commission, slippage)
- **Data Providers**: Yahoo Finance integration with caching support
- **Portfolio Management**: Position tracking, rebalancing, and allocation
- **Risk Management**: Position limits, portfolio limits, stop-loss/take-profit
- **Performance Metrics**: Sharpe, Sortino, Calmar ratios, max drawdown, VaR, win rate, profit factor
- **Configuration**: YAML-based configuration system

## Installation

```bash
pip install -r requirements.txt
# Or for development:
pip install -e ".[dev]"
```

## Quick Start

```python
from datetime import datetime, timedelta
from quant_trading.backtest.engine import run_backtest
from quant_trading.strategies.examples import MovingAverageCrossover

# Define strategy
strategy = MovingAverageCrossover(fast_period=10, slow_period=30)

# Run backtest
end_date = datetime.now()
start_date = end_date - timedelta(days=365)

result = run_backtest(
    strategy=strategy,
    symbols=["AAPL", "MSFT", "GOOGL"],
    start=start_date,
    end=end_date,
    initial_capital=100000.0,
)

print(f"Total Return: {result.total_return_pct:.2f}%")
print(f"Sharpe Ratio: {result.metrics.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.metrics.max_drawdown_pct:.2f}%")
```

## Project Structure

```
quant_trading/
├── strategies/          # Trading strategies
│   ├── base.py         # Base classes (Strategy, Signal, Position)
│   └── examples.py     # Built-in strategies
├── backtest/           # Backtesting engine
│   ├── engine.py       # Main backtest engine
│   └── metrics.py      # Performance metrics
├── data/               # Data providers
│   ├── providers.py    # Base interfaces
│   └── yfinance_provider.py  # Yahoo Finance implementation
├── portfolio/          # Portfolio management
│   ├── portfolio.py    # Portfolio and holdings
│   └── rebalancer.py   # Rebalancing logic
├── risk/               # Risk management
│   ├── limits.py       # Position/portfolio limits
│   ├── manager.py      # Risk manager
│   └── metrics.py      # Risk metrics
├── config/             # Configuration
│   └── settings.py     # Config classes
└── utils/              # Utilities
    ├── formatting.py   # Number formatting
    └── logging.py      # Logging setup
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Quality

```bash
# Linting
ruff check .

# Type checking
mypy quant_trading/

# Formatting
black quant_trading/
```

## Example Scripts

See `examples/run_backtest.py` for a complete example of running backtests with multiple strategies.

For a deterministic, network-free demonstration, see
`examples/run_backtest_offline.py`. It runs the three built-in
strategies against seeded synthetic data and produces the same
output on every run:

```bash
python examples/run_backtest_offline.py
```

## Data fetching

`DataProvider.fetch_many(requests)` fetches several distinct symbol/date
ranges in one call. Each request is a dict with optional `symbols`, `start`,
`end`, and `interval` keys (matching `fetch` defaults). It returns a dict
mapping a stable request key (`"symbols|start|end|interval"`) to a
`FetchResult`. `DataManager.fetch_many` wraps the same API and applies the
in-memory cache per request:

```python
from quant_trading.data.providers import DataManager

manager = DataManager([provider])
results = manager.fetch_many([
    {"symbols": ["AAPL"], "start": start1, "end": end1, "interval": "1d"},
    {"symbols": ["MSFT"], "start": start2, "end": end2, "interval": "1d"},
])
```

`DataManager.fetch_many` delegates to `DataProvider.fetch_many`, so providers can
batch requests. `YFinanceProvider` overrides `fetch_many` to group requests that
share a date range and fetch them with a single `yfinance.download(...,
group_by="ticker")` call rather than one HTTP request per symbol. Group results
are cached on disk (separate from per-symbol `fetch` cache keys) and each
request's result is keyed by its stable request key.

## Configuration

Create a `config.yaml` file:

```yaml
data:
  provider: "yfinance"
  cache_dir: "./data/cache"
  default_interval: "1d"
  default_period: "1y"

backtest:
  initial_capital: 100000.0
  commission: 0.001
  slippage: 0.0005
  risk_free_rate: 0.02

risk:
  max_position_size: 0.1
  max_portfolio_risk: 0.02
  stop_loss_pct: 0.05
  take_profit_pct: 0.15
  max_drawdown: 0.20

portfolio:
  rebalance_frequency: "monthly"
  max_positions: 20
  min_position_size: 0.01

logging_level: "INFO"
output_dir: "./output"
```

Load in code:

```python
from quant_trading.config.settings import Config

config = Config.from_yaml("config.yaml")
```

## License

MIT License