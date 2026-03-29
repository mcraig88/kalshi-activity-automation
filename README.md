# Kalshi Script Setup

This folder contains a Python script for calling Kalshi's API:

- `/Users/mcraig/src/Kalshi/kalshi.py`

## Install Dependencies (PEP 668 safe)

On Homebrew Python, global `pip install` may fail with `externally-managed-environment`.
Use a project virtual environment instead:

```bash
cd /Users/mcraig/src/Kalshi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install requests cryptography
```

## Dependency Status

Dependencies are installed in `/Users/mcraig/src/Kalshi/.venv`:

- `requests==2.33.0`
- `cryptography==46.0.6`

## Configuration

`kalshi.py` defines these defaults at the top of the file:

- `KALSHI_API_KEY_ID = "7a09498c-f8d0-4a50-912a-df455124e905"`
- `KALSHI_PRIVATE_KEY_PATH = "./kalshi-key.txt"`
- `KALSHI_TIMEOUT_SECONDS = 10.0`
- `KALSHI_OUTPUT_FORMAT = "json"`
- `KALSHI_PAGE_LIMIT = 100`
- `KALSHI_FULL_HISTORY = False`
- `KALSHI_DEBUG_APPENDIX = False`

Override precedence:

1. CLI args (`--api-key-id`, `--private-key-path`, `--timeout-seconds`, `--output-format`, `--limit`, `--full-history`, `--debug-appendix`)
2. Environment variables (`KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`, `KALSHI_TIMEOUT_SECONDS`, `KALSHI_OUTPUT_FORMAT`, `KALSHI_PAGE_LIMIT`, `KALSHI_FULL_HISTORY`, `KALSHI_DEBUG_APPENDIX`)
3. Top-of-file defaults

## Usage Examples

### 1) Run with script defaults

```bash
cd /Users/mcraig/src/Kalshi
source .venv/bin/activate
python3 /Users/mcraig/src/Kalshi/kalshi.py
```

### 2) Run with environment variable overrides

```bash
cd /Users/mcraig/src/Kalshi
source .venv/bin/activate
export KALSHI_PRIVATE_KEY_PATH="/absolute/path/to/your/kalshi-private-key.pem"
export KALSHI_TIMEOUT_SECONDS="15"
python3 /Users/mcraig/src/Kalshi/kalshi.py
```

### 3) Run with CLI overrides

```bash
cd /Users/mcraig/src/Kalshi
source .venv/bin/activate
python3 /Users/mcraig/src/Kalshi/kalshi.py \
  --private-key-path "/absolute/path/to/your/kalshi-private-key.pem" \
  --timeout-seconds 15
```

### 4) Output in table format

```bash
cd /Users/mcraig/src/Kalshi
source .venv/bin/activate
python3 /Users/mcraig/src/Kalshi/kalshi.py \
  --private-key-path "/absolute/path/to/your/kalshi-private-key.pem" \
  --output-format table
```

Table output now includes an appendix with:

- Total Dollars Traded
- Total Trades Won
- Total Trades Loss
- Total Trades Percent Win/Loss
- Total Profit/Loss
- Closed Profit/Loss
- Open Notional

### 5) Pull full history (internal pagination)

```bash
cd /Users/mcraig/src/Kalshi
source .venv/bin/activate
python3 /Users/mcraig/src/Kalshi/kalshi.py \
  --private-key-path "/absolute/path/to/your/kalshi-private-key.pem" \
  --full-history \
  --limit 200 \
  --output-format table
```

`--full-history` automatically follows API cursor pagination until no next cursor is returned.

### 6) Show appendix debug math by market ticker

```bash
cd /Users/mcraig/src/Kalshi
source .venv/bin/activate
python3 /Users/mcraig/src/Kalshi/kalshi.py \
  --private-key-path "/absolute/path/to/your/kalshi-private-key.pem" \
  --full-history \
  --output-format table \
  --debug-appendix
```

`--debug-appendix` prints per-`market_ticker + side` buy/sell counts, wagered amount, fees, closed P/L, open notional, and status.

## Important Note

`~/.ssh/id_ed25519.pub` is an SSH public key path, not a Kalshi RSA private key PEM file.
For successful Kalshi authentication, set `KALSHI_PRIVATE_KEY_PATH` (env or CLI) to your Kalshi private key file.
