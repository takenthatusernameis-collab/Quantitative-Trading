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

## Command Line Interface

The framework includes a CLI for running backtests with configurable data providers and strategies.

### Basic Usage

```bash
# Run a backtest with default settings (MA crossover, Yahoo Finance, 1 year daily data)
python examples/cli.py

# Run with specific strategy and symbols
python examples/cli.py --strategy rsi --symbols AAPL MSFT --days 180

# Run with custom parameters
python examples/cli.py --strategy bb --bb-period 20 --bb-std 2.5 --initial-capital 50000
```

### Data Providers

 ```bash
 # Use Yahoo Finance (default, requires network)
 python examples/cli.py --provider yfinance

 # Use Alpha Vantage (supports daily, weekly, monthly, intraday, and real-time)
 python examples/cli.py --provider alphavantage --interval 5m --days 30

 # Use Alpha Vantage with weekly data
 python examples/cli.py --provider alphavantage --interval weekly --days 365

 # Use Alpha Vantage with monthly adjusted data (includes dividends/splits)
 python examples/cli.py --provider alphavantage --interval monthly_adjusted --days 1095

 # Use Alpha Vantage with real-time quote
 python examples/cli.py --provider alphavantage --interval quote

 # Use Alpha Vantage with market status
 python examples/cli.py --provider alphavantage --interval market_status

 # Use Alpha Vantage with FX daily data
 python examples/cli.py --provider alphavantage --interval fx_daily --symbols USD/EUR GBP/USD

 # Use Alpha Vantage with FX intraday data
 python examples/cli.py --provider alphavantage --interval fx_5m --symbols USD/EUR

  # Use Alpha Vantage with crypto data
  python examples/cli.py --provider alphavantage --interval crypto_daily --symbols BTC ETH

  # Use Alpha Vantage with technical indicators (SMA is the default daily series)
  python examples/cli.py --provider alphavantage --interval sma --symbols AAPL MSFT
  python examples/cli.py --provider alphavantage --interval rsi --symbols AAPL
  python examples/cli.py --provider alphavantage --interval macd --symbols AAPL

  # Use Alpha Vantage sector performance
  python examples/cli.py --provider alphavantage --interval sector

  # Use Alpha Vantage with your own API key
  python examples/cli.py --provider alphavantage --alphavantage-key YOUR_API_KEY --interval 1h

 # Run offline with synthetic data (deterministic, no network required)
 python examples/cli.py --offline
 # or
 python examples/cli.py --provider synthetic
 ```

### Utility Commands

```bash
# List available strategies with their default parameters
python examples/cli.py --list-strategies

# List available data providers
python examples/cli.py --list-providers

# Generate a default config.yaml file
python examples/cli.py --init-config config.yaml
```

### Combined Mode

Run all strategies together and compare results:

```bash
python examples/cli.py --combined --symbols AAPL MSFT GOOGL --days 365
```

### Configuration

Load settings from a YAML config file:

```bash
python examples/cli.py --config config.yaml
```

### Output

Save results to JSON:

```bash
python examples/cli.py --output results.json
python examples/cli.py --combined --output comparison.json
```

### Alpha Vantage Specifics

 Alpha Vantage provider supports:
 - **Daily data**: `1d` / `daily` intervals via TIME_SERIES_DAILY_ADJUSTED
 - **Weekly data**: `1w`, `weekly`, `week` intervals via TIME_SERIES_WEEKLY
 - **Weekly adjusted data**: `1wa`, `weekly_adjusted` intervals via TIME_SERIES_WEEKLY_ADJUSTED (includes dividends/splits)
 - **Monthly data**: `1mo`, `monthly`, `month` intervals via TIME_SERIES_MONTHLY
 - **Monthly adjusted data**: `1ma`, `monthly_adjusted` intervals via TIME_SERIES_MONTHLY_ADJUSTED (includes dividends/splits)
 - **Intraday data**: `1m`, `5m`, `15m`, `30m`, `1h` / `60m` intervals via TIME_SERIES_INTRADAY
 - **Global Quote**: `quote`, `realtime`, `rt` intervals via GLOBAL_QUOTE (real-time single symbol quotes)
 - **Market Status**: `market_status`, `marketstatus` intervals via MARKET_STATUS (global market hours/status)
 - **FX Daily**: `fx_daily`, `fx`, `forex_daily` intervals via FX_DAILY (symbols as "FROM/TO", e.g., "USD/EUR")
 - **FX Intraday**: `fx_intraday`, `fx_1m`, `fx_5m`, `fx_15m`, `fx_30m`, `fx_60m` intervals via FX_INTRADAY
 - **Currency Exchange Rate**: real-time forex rates via CURRENCY_EXCHANGE_RATE (use `get_currency_exchange_rate()`)
 - **Crypto Daily**: `crypto_daily`, `digital_daily` intervals via DIGITAL_CURRENCY_DAILY (symbols like "BTC", "ETH")
 - **Crypto Weekly**: `crypto_weekly`, `digital_weekly` intervals via DIGITAL_CURRENCY_WEEKLY
 - **Crypto Monthly**: `crypto_monthly`, `digital_monthly` intervals via DIGITAL_CURRENCY_MONTHLY
  - **Crypto Intraday**: `crypto_intraday`, `digital_intraday` intervals via DIGITAL_CURRENCY_INTRADAY
  - **Technical Indicators**: `sma`, `ema`, `rsi`, `macd`, `bbands`, `stoch`, etc. via TIME_SERIES_<INDICATOR> (default daily series resolution; use the interval as the indicator name)
  - **Sector Performance**: `sector`, `sector_performance`, `sectors` intervals via SECTOR (single global result across requested symbols)
  - **Demo key**: Works out of the box with `"demo"` key (rate limited, warning logged)
 - **API key validation**: Optional warning when using demo key (configurable via `warn_on_demo`)

 For production use, get a free API key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key) and pass it via `--alphavantage-key` or config file.

### Example Scripts

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

### DataManager

`DataManager` manages multiple data providers and provides in-memory caching:

```python
from quant_trading.data.providers import DataManager, YFinanceProvider, AlphaVantageProvider

# Create manager with providers
manager = DataManager([YFinanceProvider(), AlphaVantageProvider()])

# Fetch with specific provider
result = manager.fetch(["AAPL"], provider_name="alphavantage", interval="5m")

# Clear in-memory cache
manager.clear_cache()
```

### Alpha Vantage Provider

 The `AlphaVantageProvider` supports multiple endpoints:

 ```python
 from quant_trading.data.yfinance_provider import AlphaVantageProvider

 # Uses demo key by default (rate limited, logs warning)
 provider = AlphaVantageProvider()  # api_key defaults to "demo"

 # Or provide your own key
 provider = AlphaVantageProvider(api_key="YOUR_API_KEY")

 # Disable demo key warning
 provider = AlphaVantageProvider(api_key="demo", warn_on_demo=False)

 # Fetch daily data
 result = provider.fetch(["AAPL"], interval="1d")

 # Fetch weekly data
 result = provider.fetch(["AAPL"], interval="weekly")

 # Fetch weekly adjusted data (includes dividends/splits)
 result = provider.fetch(["AAPL"], interval="weekly_adjusted")

 # Fetch monthly data
 result = provider.fetch(["AAPL"], interval="monthly")

 # Fetch monthly adjusted data (includes dividends/splits)
 result = provider.fetch(["AAPL"], interval="monthly_adjusted")

 # Fetch intraday data (1m, 5m, 15m, 30m, 1h)
 result = provider.fetch(["AAPL"], interval="5m")

 # Fetch real-time single symbol quote
 result = provider.fetch(["AAPL"], interval="quote")

 # Fetch latest real-time quotes (batch)
 result = provider.fetch_latest(["AAPL", "MSFT"])

 # Get market status
 df = provider.get_market_status()

 # Get real-time currency exchange rate
 df = provider.get_currency_exchange_rate("USD", "EUR")

 # Fetch FX daily data (symbols as "FROM/TO")
 result = provider.fetch(["USD/EUR", "GBP/USD"], interval="fx_daily")

 # Fetch FX intraday data
 result = provider.fetch(["USD/EUR"], interval="fx_5m")

 # Fetch crypto data
 result = provider.fetch(["BTC", "ETH"], interval="crypto_daily")
 result = provider.fetch(["BTC"], interval="crypto_weekly")
 result = provider.fetch(["BTC"], interval="crypto_monthly")
  result = provider.fetch(["BTC"], interval="crypto_intraday")

  # Fetch technical indicators (indicator name as interval, default daily series)
  result = provider.fetch(["AAPL"], interval="sma")
  result = provider.fetch(["AAPL"], interval="rsi")

  # Get a technical indicator directly as a DataFrame
  df = provider.get_sma("AAPL")
  df = provider.get_rsi("AAPL")
  df = provider.get_technical_indicator("AAPL", indicator="SMA")
  ```

 Supported intervals:
 - Daily: `1d`, `daily`
 - Weekly: `1w`, `weekly`, `week`
 - Weekly Adjusted: `1wa`, `weekly_adjusted`
 - Monthly: `1mo`, `monthly`, `month`
 - Monthly Adjusted: `1ma`, `monthly_adjusted`
 - Intraday: `1m`, `5m`, `15m`, `30m`, `1h`, `60m`
 - Global Quote: `quote`, `realtime`, `rt`
 - Market Status: `market_status`, `marketstatus`
 - FX Daily: `fx_daily`, `fx`, `forex_daily` (symbols as "FROM/TO")
 - FX Intraday: `fx_intraday`, `fx_1m`, `fx_5m`, `fx_15m`, `fx_30m`, `fx_60m`
 - Crypto Daily: `crypto_daily`, `digital_daily`
 - Crypto Weekly: `crypto_weekly`, `digital_weekly`
 - Crypto Monthly: `crypto_monthly`, `digital_monthly`
  - Crypto Intraday: `crypto_intraday`, `digital_intraday`
  - Technical Indicators: `sma`, `ema`, `rsi`, `macd`, `bbands`, `stoch`, etc.
  - Sector Performance: `sector`, `sector_performance`, `sectors`
  - Real-time Batch: any other interval uses `BATCH_STOCK_PRICES`

  Additional methods:
  - `get_market_status()` - Returns DataFrame with global market hours/status
  - `get_currency_exchange_rate(from_currency, to_currency)` - Returns real-time FX rate
  - `get_technical_indicator(symbol, indicator="SMA", ...)` - Returns DataFrame for a TI (e.g. SMA, EMA, RSI, MACD, BBANDS, STOCH)
  - `get_sma(symbol)`, `get_ema(symbol)`, `get_rsi(symbol)`, `get_macd(symbol)`, `get_stoch(symbol)`, `get_bbands(symbol)` - Convenience wrappers for common indicators
  - `get_sector_performance()` - Returns DataFrame of sector performance rankings
  - `search_symbols(query)` - Search for symbols by name or ticker

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