# Nifty One-Minute Options Breakout Strategy

An automated quantitative trading desktop application for NIFTY Index Options, built with Python. It implements a breakout strategy using 1-minute OHLC time-interval candles to capture directional momentum during the morning trading session.

## Features

- **Automated Options Trading**: Monitors and executes trades on NIFTY Call (CE) and Put (PE) options.
- **Advanced Strategy Mechanics**: Includes Reference Candle locking, Two-Layer Directional Filtering (Price Action & Live Open Interest), and Anti-Whipsaw protections.
- **Dynamic Risk Management**: Multi-stage profit taking (T1, T2, T3) and trailing stop-loss features.
- **Desktop UI**: A built-in user interface built with PyQT6
- **Flattrade Integration**: Fully integrates with the Flattrade Broker API for live data and order execution.

## Strategy Deep-Dive

For a detailed technical and functional explanation of the trading strategy logic, please read the [Nifty One-Minute Strategy Explanation](NIFTY_ONE_MIN_STRATEGY_EXPLANATION.md).

## Prerequisites

- Python 3.13 or higher.
- A valid Flattrade trading account and API credentials.
- [uv](https://github.com/astral-sh/uv) (recommended) for dependency management.

## Installation

1. **Clone the repository** (if applicable) or navigate to the project directory.
2. **Install dependencies** using `uv` (recommended):
   ```bash
   uv sync
   ```
   Or using pip:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. You need to configure your Flattrade credentials in the key tab. 
   ```yaml
   user_id: "YOUR_USER_ID"
   password: "YOUR_PASSWORD"
   totp_key: "YOUR_TOTP_KEY"
   api_key: "YOUR_API_KEY"
   api_secret: "YOUR_API_SECRET"
   ```
2. The UI defaults and other configurations are stored in `ui_defaults.json`.

## Usage

Start the application by running the main entry script:

```bash
uv run new_main.py
```
*(Or use `python new_main.py` if your virtual environment is already activated.)*

The desktop application UI will launch, allowing you to:
- Configure strategy parameters (Start/Stop time, target multipliers, etc.).
- Monitor active trades, PNL, and positions.
- Connect to the Flattrade broker.

## Architecture

The application is structured into two main multiprocessing components for stability and performance:
- **Backend Process** (`new_backend.py` / `nifty_one_min_strategy.py`): Handles market data streams, strategy state machine, risk management, and order execution.
- **UI Process** (`new_ui.py`): Renders the desktop frontend using Eel and PyWebview.
- **RPC Communication**: The frontend and backend communicate over a local TCP socket (auto-selected port) to ensure real-time UI updates without blocking the trading engine.

## Disclaimer

**Algorithmic trading involves significant risk and may not be suitable for all investors.** The strategy and software provided in this repository are for educational and informational purposes only. Use at your own risk. Past performance is not indicative of future results.
