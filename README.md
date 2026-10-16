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
- **Market Regime Detection**: Classify equity curves into bull/bear/sideways regimes (low/high volatility)
- **Monte Carlo Simulation**: Bootstrap and parametric simulation of backtest outcomes
- **Parameter Optimization**: Grid search, random search, and walk-forward analysis
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
│   ├── examples.py     # Built-in strategies
│   └── factory.py      # Strategy registry and factory
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

## Strategy Registry

Strategies can be registered in a global registry and created dynamically by
key, with optional aliases. The built-in strategies are pre-registered:

- `ma` (aliases: `moving_average`, `ma_crossover`) → `MovingAverageCrossover`
- `rsi` (alias: `rsi_mean_reversion`) → `RSIStrategy`
- `bb` (aliases: `bollinger_bands`, `bollinger`) → `BollingerBandsStrategy`
- `macd` (alias: `macd_crossover`) → `MACDStrategy`

```python
from quant_trading.strategies import (
    MovingAverageCrossover,
    create_strategy,
    get_strategy,
    list_strategies,
    register_strategy,
    strategy_keys,
)

# Create a built-in strategy by key or alias
strategy = create_strategy("ma", fast_period=5, slow_period=20)
assert get_strategy("ma_crossover") is MovingAverageCrossover

# Register a custom strategy (optionally with aliases)
register_strategy("my_strategy", MyStrategy, aliases=["my_algo"])
custom = create_strategy("my_strategy")

print(strategy_keys())     # primary keys + aliases
print(list_strategies())   # primary keys -> classes
```

`Strategy.from_config(config)` also resolves strategies through the registry:

```python
strategy = Strategy.from_config({
    "type": "rsi",
    "name": "MyRSI",
    "parameters": {"period": 21, "oversold": 25, "overbought": 75},
})
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

### Market Regime Analysis

Annotate a backtest's equity curve with market-regime labels
(bull/bear/sideways x low/high volatility):

```bash
# Run a backtest and print the regimes its equity curve traversed
python examples/cli.py --offline --regime --symbols AAPL --days 120

# Override the auto-derived volatility/return thresholds
python examples/cli.py --offline --regime --regime-window 30 --regime-vol-threshold 0.15 --regime-return-threshold 0.05
```

### Trade Analysis

Detailed trade-level analysis including PnL statistics, holding periods, streaks, and per-symbol breakdowns:

```bash
# Run a backtest with detailed trade analysis
python examples/cli.py --offline --trade-analysis --symbols AAPL --days 120
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
  - **Commodities**: `wti`, `brent`, `natural_gas`, `copper`, `aluminum`, `corn`, `wheat`, `cotton`, `sugar`, `coffee`, `all_commodities` intervals via dedicated commodity endpoints (e.g., WTI, BRENT, COPPER)
  - **Precious Metals**: `gold`, `silver` intervals via GOLD_SILVER_SPOT (spot) and GOLD_SILVER_HISTORY (historical daily/weekly/monthly)
  - **Economic Indicators**: `gdp`, `real_gdp`, `gdp_per_capita`, `cpi`, `inflation`, `retail_sales`, `durables`, `unemployment`, `nonfarm_payroll`, `interest_rate`, `fed_funds_rate`, `treasury_yield`, `consumer_sentiment` intervals via dedicated economic endpoints
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

For a full analysis pass — market regime detection, Monte Carlo
simulation, and trade-level analysis — see
`examples/run_analysis.py`. It runs a single backtest against
synthetic data and prints all three analysis modules:

```bash
python examples/run_analysis.py
```

For a trend-following demonstration using the Parabolic SAR indicator, see
`examples/run_parabolic_sar.py`. It runs the `ParabolicSARStrategy` against
seeded synthetic data, generating buy signals when price crosses above the
SAR (trend turns bullish) and sell signals when price crosses below the SAR
(trend turns bearish):

```bash
python examples/run_parabolic_sar.py
```

For a session-based VWAP demonstration, see `examples/run_vwap.py`. It runs
the `VWAPStrategy` against seeded synthetic data, generating buy signals
when price crosses above the VWAP and sell signals when price crosses below
the VWAP:

```bash
python examples/run_vwap.py
```

For an Ichimoku Cloud demonstration, see `examples/run_ichimoku.py`. It runs
the `IchimokuCloudStrategy` against seeded synthetic data, generating buy
signals when Tenkan-sen crosses above Kijun-sen with price above the cloud
and sell signals when Tenkan-sen crosses below Kijun-sen with price below
the cloud:

```bash
python examples/run_ichimoku.py
```

For a momentum trend-following demonstration using the MACD indicator, see
`examples/run_macd.py`. It runs the `MACDStrategy` against seeded synthetic
data, generating buy signals when the MACD line crosses above the signal line
(bullish crossover) and sell signals when the MACD line crosses below the
signal line (bearish crossover):

```bash
python examples/run_macd.py
```

For a Bollinger Bands mean-reversion demonstration, see
`examples/run_bollinger_bands.py`. It runs the `BollingerBandsStrategy` against
seeded synthetic data, generating buy signals when price touches the lower band
and sell signals when price touches the upper band:

```bash
python examples/run_bollinger_bands.py
```

For a momentum oscillator demonstration using the RSI indicator, see
`examples/run_rsi.py`. It runs the `RSIStrategy` against seeded synthetic
data, generating buy signals when RSI is oversold (< 30) and sell signals
when RSI is overbought (> 70):

```bash
python examples/run_rsi.py
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

# Fetch sector performance
result = provider.fetch(["AAPL"], interval="sector")

# Fetch commodities (WTI, BRENT, Natural Gas, Copper, etc.)
result = provider.fetch(["WTI"], interval="wti")
result = provider.fetch(["BRENT"], interval="brent")
result = provider.fetch(["COPPER"], interval="copper")

# Fetch precious metals (gold/silver spot and history)
result = provider.fetch(["GOLD"], interval="gold")  # symbols "GOLD"/"XAU" or "SILVER"/"XAG"
result = provider.fetch(["SILVER"], interval="silver")
df = provider.get_gold_spot("GOLD")  # or "XAU" for gold, "SILVER"/"XAG" for silver
df = provider.get_gold_history("GOLD", interval="daily")  # also "weekly", "monthly"

# Fetch economic indicators (GDP, CPI, Unemployment, etc.)
result = provider.fetch(["GDP"], interval="gdp")
result = provider.fetch(["CPI"], interval="cpi")
df = provider.get_economic_indicator("REAL_GDP", interval="annual")
df = provider.get_economic_indicator("TREASURY_YIELD", interval="monthly", maturity="10year")

# Get a technical indicator directly as a DataFrame
df = provider.get_sma("AAPL")
df = provider.get_rsi("AAPL")
df = provider.get_technical_indicator("AAPL", indicator="SMA")

# Get commodity data directly
df = provider.get_commodity("WTI", interval="monthly")

# Get sector performance directly
df = provider.get_sector_performance()
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
  - Commodities: `wti`, `brent`, `natural_gas`, `copper`, `aluminum`, `corn`, `wheat`, `cotton`, `sugar`, `coffee`, `all_commodities`
  - Precious Metals: `gold`, `silver` (spot via `get_gold_spot()`, history via `get_gold_history()`)
  - Economic Indicators: `gdp`, `real_gdp`, `gdp_per_capita`, `cpi`, `inflation`, `retail_sales`, `durables`, `unemployment`, `nonfarm_payroll`, `interest_rate`, `fed_funds_rate`, `treasury_yield`, `consumer_sentiment`
  - Real-time Batch: any other interval uses `BATCH_STOCK_PRICES`

  Additional methods:
  - `get_market_status()` - Returns DataFrame with global market hours/status
  - `get_currency_exchange_rate(from_currency, to_currency)` - Returns real-time FX rate
  - `get_technical_indicator(symbol, indicator="SMA", ...)` - Returns DataFrame for a TI (e.g. SMA, EMA, RSI, MACD, BBANDS, STOCH)
  - `get_sma(symbol)`, `get_ema(symbol)`, `get_rsi(symbol)`, `get_macd(symbol)`, `get_stoch(symbol)`, `get_bbands(symbol)` - Convenience wrappers for common indicators
  - `get_sector_performance()` - Returns DataFrame of sector performance rankings
  - `get_gold_spot(symbol)` - Returns spot price for gold ("GOLD"/"XAU") or silver ("SILVER"/"XAG")
  - `get_gold_history(symbol, interval)` - Returns historical prices for gold/silver (interval: "daily", "weekly", "monthly")
  - `get_commodity(function, interval)` - Returns commodity data (e.g. "WTI", "BRENT", "COPPER"; interval varies by commodity)
  - `get_economic_indicator(function, interval, **kwargs)` - Returns economic data (e.g. "REAL_GDP", "CPI", "UNEMPLOYMENT"; optional interval, maturity for treasury yields)
  - `search_symbols(query)` - Search for symbols by name or ticker

## Market Regime Analysis

A finished backtest can be inspected for the market regimes its equity curve
traversed. Regimes combine a direction signal (bull/bear/sideways) with a
volatility signal (low/high) derived from rolling-window statistics.

```python
from quant_trading.backtest import analyze_regimes

analysis = analyze_regimes(result, window=20)
print(analysis.current_regime)   # e.g. Regime.BULL_LOW_VOL
for seg in analysis.segments:
    print(seg.regime.value, seg.start, seg.end, seg.volatility, seg.return_pct)
```

The analysis is also available from the CLI:

```bash
python examples/cli.py --offline --regime --symbols AAPL --days 120
```

Optional explicit thresholds can be supplied to override the auto-derived
defaults:

```python
analysis = analyze_regimes(
    result,
    window=20,
    vol_threshold=0.15,
    return_threshold=0.05,
)
```

## Monte Carlo Simulation

Run many simulated backtests by resampling the equity curve's daily
returns (bootstrap) or drawing from a fitted normal distribution
(parametric). This produces a distribution of outcomes — Sharpe, drawdown,
total return — and estimates the probability of profit and the confidence
interval around the original result.

```python
from quant_trading.monte_carlo import run_monte_carlo

mc = run_monte_carlo(result, n_simulations=1000, method="bootstrap", random_state=42)
print(f"Probability of profit: {mc.probability_of_profit():.2%}")
lower, upper = mc.get_confidence_interval("total_return_pct")
print(f"95% CI for total return: [{lower:.2f}%, {upper:.2f}%]")
```

The analysis is also available from the CLI:

```bash
python examples/cli.py --offline --monte-carlo --symbols AAPL --days 120
```

Override the simulation parameters:

```bash
python examples/cli.py --offline --monte-carlo --mc-simulations 500 --mc-method parametric --mc-confidence 0.99 --mc-seed 7
```

## Trade Analysis

Detailed trade-level analysis including PnL statistics, holding periods, consecutive win/loss streaks, monthly/weekly returns, and per-symbol breakdowns.

```python
from quant_trading.backtest import analyze_trades, print_trade_analysis

analysis = analyze_trades(result)
print_trade_analysis(analysis)
```

The analysis is also available from the CLI:

```bash
python examples/cli.py --offline --trade-analysis --symbols AAPL --days 120
```

This provides:
- **Overview**: Total trades, win rate, winning/losing trade counts
- **PnL Statistics**: Total/avg/median PnL, avg win/loss, largest win/loss, profit factor, expectancy
- **Holding Periods**: Average, median, min, max holding periods in days
- **Streaks**: Maximum consecutive wins/losses, current streak
- **Trade-Level Risk**: Trade-level Sharpe and Sortino ratios
- **Monthly/Weekly Returns**: Periodic return breakdowns
- **Per-Symbol Statistics**: Detailed breakdown by symbol

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

For a stochastic oscillator demonstration using the Stochastic indicator, see
`examples/run_stochastic.py`. It runs the `StochasticOscillatorStrategy`
against seeded synthetic data, generating buy signals when %K crosses above %D
in oversold territory (< 20) and sell signals when %K crosses below %D in
overbought territory (> 80):

```bash
python examples/run_stochastic.py
```
