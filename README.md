# Kalshi Fills Script

This repository contains a Python script for fetching Kalshi fills and rendering results in JSON or table format.

- Script: `./kalshi.py`

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install requests cryptography
python3 ./kalshi.py --help
```

## Configuration

`./kalshi.py` supports three override layers (highest to lowest):

1. CLI args
2. Environment variables
3. Top-of-file constants in `./kalshi.py`

Supported options:

- `--api-key-id` / `KALSHI_API_KEY_ID`
- `--private-key-path` / `KALSHI_PRIVATE_KEY_PATH`
- `--timeout-seconds` / `KALSHI_TIMEOUT_SECONDS`
- `--output-format` / `KALSHI_OUTPUT_FORMAT` (`json` or `table`)
- `--limit` / `KALSHI_PAGE_LIMIT`
- `--full-history` / `KALSHI_FULL_HISTORY`
- `--debug-appendix` / `KALSHI_DEBUG_APPENDIX`
- `--starting-cash` / `KALSHI_STARTING_CASH`
- `--enable-cache` / `KALSHI_ENABLE_CACHE`
- `--use-cached-starting-cash` / `KALSHI_USE_CACHED_STARTING_CASH`
- `--cache-file` / `KALSHI_CACHE_FILE`
- `--force-refresh` / `KALSHI_FORCE_REFRESH`

## Usage

Run with defaults:

```bash
source .venv/bin/activate
export KALSHI_API_KEY_ID="YOUR_KALSHI_API_KEY_ID"
python3 ./kalshi.py
```

Run with overrides:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --private-key-path "./kalshi-key.txt" \
  --timeout-seconds 15 \
  --output-format table
```

Pull full history with pagination:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --full-history \
  --limit 200 \
  --output-format table
```

Show per-market debug appendix:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --full-history \
  --output-format table \
  --debug-appendix
```

Run with starting cash reconciliation:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --starting-cash 100
```

Enable local cache (starting cash + fetched trade JSON):

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --starting-cash 100 \
  --enable-cache
```

Reuse cached data and cached starting cash:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --enable-cache \
  --use-cached-starting-cash
```

Force full refresh (ignore cached trade JSON):

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --enable-cache \
  --force-refresh
```

## Appendix Metrics (Table Mode)

Table output includes:

- Total Dollars Traded
- Total Trades Won
- Total Trades Loss
- Total Trades Percent Win/Loss
- Total Profit/Loss
- Closed Profit/Loss
- Open Notional

Reconciliation output includes:

- Starting Cash
- Ending Cash (Kalshi)
- Portfolio Value (Kalshi)
- Open Market Value
- Estimated Unrealized P/L
- Estimated Total Profit/Loss
- Net P/L vs Starting Cash

`Closed Profit/Loss` and Trades Win/Loss metrics include both:

- Fill-based closes (buy/sell round-trips)
- Expiration settlements from `portfolio/settlements`

With `--debug-appendix`, details are shown per `market_ticker` (including settlement quantities and unmatched settlement quantity).

## GitHub Safety Notes

- Do not commit private keys.
- Keep key files local (for example `./kalshi-key.txt`) and out of version control.
- `./kalshi-key.txt`, `./.kalshi_cache.json`, `./.venv/`, and Python cache files are already ignored by `./.gitignore`.
- If you previously exposed API credentials or private keys, rotate them before publishing.

## Key Format Note

Kalshi auth expects an RSA private key PEM file.
An SSH public key like `~/.ssh/id_ed12345.pub` will not work.
