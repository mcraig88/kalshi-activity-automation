# Kalshi Guide

This guide is specific to the Kalshi workflow in this repository.

Script:

- `./kalshi.py`

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python3 ./kalshi.py --help
```

Use [`.env.example`](./.env.example) as a reference for local environment variables.

## Configuration

`./kalshi.py` supports three override layers, highest to lowest:

1. CLI args
2. Environment variables
3. Top-of-file constants in `./kalshi.py`

Supported options:

- `--api-key-id` / `KALSHI_API_KEY_ID`
- `--private-key-path` / `KALSHI_PRIVATE_KEY_PATH`
- `--timeout-seconds` / `KALSHI_TIMEOUT_SECONDS`
- `--output-format` / `KALSHI_OUTPUT_FORMAT` with `json`, `table`, or `reconciliation`
- `--limit` / `KALSHI_PAGE_LIMIT`
- `--full-history` / `KALSHI_FULL_HISTORY`
- `--debug` / `KALSHI_DEBUG_APPENDIX`
- `--starting-cash` / `KALSHI_STARTING_CASH`
- `--enable-cache` / `KALSHI_ENABLE_CACHE`
- `--use-cached-starting-cash` / `KALSHI_USE_CACHED_STARTING_CASH`
- `--cache-file` / `KALSHI_CACHE_FILE`
- `--force-refresh` / `KALSHI_FORCE_REFRESH`
- `--columns` (CLI only)
- `--all-columns` (CLI only)

## Usage

Run with explicit required inputs:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --api-key-id "YOUR_KALSHI_API_KEY_ID" \
  --private-key-path "./kalshi-key.txt"
```

If `--output-format` is omitted and neither `KALSHI_OUTPUT_FORMAT` nor the top-of-file constant is set, the script prints only the reconciliation section.

Run with overrides:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --private-key-path "./kalshi-key.txt" \
  --timeout-seconds 15 \
  --output-format table
```

Run reconciliation mode explicitly:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --api-key-id "YOUR_KALSHI_API_KEY_ID" \
  --private-key-path "./kalshi-key.txt" \
  --output-format reconciliation \
  --full-history \
  --starting-cash 100
```

Pull full history with pagination:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --full-history \
  --limit 200 \
  --output-format table
```

Show per-market reconciliation debug details:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --full-history \
  --output-format table \
  --debug
```

Show the default curated table view:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history
```

Show custom table columns:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --columns created_time,market_ticker,action,side,count_fp,price_fixed,trade_value_dollars
```

Show all available raw table columns:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --all-columns
```

Run with starting cash reconciliation:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --starting-cash 100
```

Enable local cache:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --starting-cash 100 \
  --enable-cache
```

Reuse cached data automatically:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history
```

Force full refresh:

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --force-refresh
```

## Reconciliation Output

Reconciliation is shown when:

- `--output-format table` is used
- `--output-format reconciliation` is used
- `--output-format` is omitted and no output override is configured

Reconciliation output includes:

- Starting Cash
- Ending Cash (Kalshi)
- Portfolio Value (Kalshi Positions)
- Total Account Value (Cash + Portfolio)
- Open Notional (Cost Basis)
- Estimated Unrealized P/L
- Trades Won
- Trades Loss
- Trades Percent Win/Loss
- Closed Profit/Loss
- Estimated Total Profit/Loss
- Net P/L vs Starting Cash

With `--debug`, details are shown per `market_ticker`.

## Table Output

Default table columns:

- `created_time`
- `market_ticker`
- `action`
- `side`
- `count_fp`
- `price_fixed`
- `trade_value_dollars`
- `fee_cost`
- `is_taker`

Use `--columns` to provide a custom comma-separated list, or `--all-columns` to render every raw field returned by the API.

## Safety Notes

- Do not commit private keys.
- Keep key files local and out of version control.
- If credentials are exposed, rotate them before publishing.

Kalshi auth expects an RSA private key PEM file. An SSH public key like `~/.ssh/id_ed12345.pub` will not work.
