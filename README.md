# Kalshi Fills Script

This repository contains a Python script for fetching Kalshi fills and rendering results in JSON, table, or reconciliation-only format.

- Script: `./kalshi.py`

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python3 ./kalshi.py --help
```

Use [`.env.example`](/Users/mcraig/src/Kalshi/.env.example) as a reference for environment variable setup.

## Configuration

`./kalshi.py` supports three override layers (highest to lowest):

1. CLI args
2. Environment variables
3. Top-of-file constants in `./kalshi.py`

Supported options:

- `--api-key-id` / `KALSHI_API_KEY_ID`
- `--private-key-path` / `KALSHI_PRIVATE_KEY_PATH`
- `--timeout-seconds` / `KALSHI_TIMEOUT_SECONDS`
- `--output-format` / `KALSHI_OUTPUT_FORMAT` (`json`, `table`, or `reconciliation`)
  - If omitted and no env/top-of-file override is set, output defaults to `reconciliation`.
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

Default behavior note:

- If `--output-format` is omitted and neither `KALSHI_OUTPUT_FORMAT` nor the top-of-file constant is set, the script prints only the reconciliation section.
- If `KALSHI_OUTPUT_FORMAT` is set (for example `json`, `table`, or `reconciliation`), that format is used.

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

Show the default, curated table view:

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

Enable local cache (starting cash + fetched trade JSON):

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --starting-cash 100 \
  --enable-cache
```

Reuse cached data automatically (no cache flag required if cache file exists):

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history
```

If cache exists (`./.kalshi_cache.json` by default), the script auto-loads cached trade JSON and cached starting cash.

Force full refresh (ignore cached trade JSON):

```bash
source .venv/bin/activate
python3 ./kalshi.py \
  --output-format table \
  --full-history \
  --force-refresh
```

## Reconciliation Output

Reconciliation is shown when:

- `--output-format table` is used (table + reconciliation)
- `--output-format reconciliation` is used (reconciliation only)
- `--output-format` is omitted and no output override is configured (reconciliation only)

Reconciliation output includes:

- Starting Cash
- Ending Cash (Kalshi)
- Portfolio Value (Kalshi)
- Open Market Value
- Open Notional (Cost Basis)
- Estimated Unrealized P/L
- Trades Won
- Trades Loss
- Trades Percent Win/Loss
- Closed Profit/Loss
- Estimated Total Profit/Loss
- Net P/L vs Starting Cash

`Closed Profit/Loss` and trade win/loss metrics include both fill-based closes and expiration settlements.

With `--debug`, details are shown per `market_ticker` (including settlement quantities and unmatched settlement quantity).

## Table Output

Table mode uses a curated default column set:

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

## GitHub Safety Notes

- Do not commit private keys.
- Keep key files local (for example `./kalshi-key.txt`) and out of version control.
- `./kalshi-key.txt`, `./.kalshi_cache.json`, `./.env`, `./.venv/`, and Python cache files are already ignored by `./.gitignore`.
- If you previously exposed API credentials or private keys, rotate them before publishing.

## Key Format Note

Kalshi auth expects an RSA private key PEM file.
An SSH public key like `~/.ssh/id_ed12345.pub` will not work.
