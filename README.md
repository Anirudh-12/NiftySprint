# Nifty One-Minute Options Breakout Strategy

An automated quantitative trading desktop application for NIFTY Index Options, built with Python. It implements a breakout strategy using 1-minute OHLC time-interval candles to capture directional momentum during the morning trading session.

## Features

- **Automated Options Trading**: Monitors and executes trades on NIFTY Call (CE) and Put (PE) options.
- **Advanced Strategy Mechanics**: Includes Reference Candle locking, Two-Layer Directional Filtering (Price Action & Live Open Interest), and Anti-Whipsaw protections.
- **Dynamic Risk Management**: Multi-stage profit taking (T1, T2, T3) and trailing stop-loss features.
- **Desktop UI**: A built-in user interface built natively with PyQt6 for easy configuration and monitoring.
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

1. **Credentials**: The application now stores credentials securely in your operating system's native credential manager. 
   - Launch the application and use the **KEY** tab in the desktop UI to enter and save your credentials securely.
   - *Legacy users*: If you have an old `flattradecred.yaml`, you can run `python export_creds_string.py` to generate a migration string that can be pasted directly into the UI.
2. Strategy defaults and configurations are stored in `ui_defaults.json` and `execonfig.json`. You can modify these directly or via the desktop UI.

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
- **UI Process** (`new_ui.py`): Renders the desktop frontend natively using PyQt6.
- **RPC Communication**: The frontend and backend communicate via ZeroMQ RPC (Dealer-Dealer pattern) over a local TCP socket (auto-selected port) to ensure real-time UI updates without blocking the trading engine.

## Disclaimer

**Algorithmic trading involves significant risk and may not be suitable for all investors.** The strategy and software provided in this repository are for educational and informational purposes only. Use at your own risk. Past performance is not indicative of future results.
