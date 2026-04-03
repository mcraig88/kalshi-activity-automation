# Agents Guide

This file documents how coding agents (and humans) should work in this repository.

## Repository Purpose

- Main scripts:
  - `./kalshi.py`
  - `./robinhood_event_contracts.py`
  - `./robinhood_crypto.py`
- Goal: report on event-contract activity across providers.
- Current provider support:
  - Kalshi via live API
  - Robinhood event contracts via statement CSV import
  - Robinhood crypto via live read-only API

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python3 ./kalshi.py --help
```

## Runtime Inputs

Required:

- `KALSHI_API_KEY_ID` (or `--api-key-id`)
- `KALSHI_PRIVATE_KEY_PATH` (or `--private-key-path`)

Optional key inputs:

- `--output-format {json,table,reconciliation}`
- `--full-history`
- `--starting-cash`
- `--debug`
- `--force-refresh`
- `--columns`
- `--all-columns`

Robinhood statement reporting:

- `--input-csv`
- `--input-pdf`
- `--input-text`
- `--output-format {table,json}`
- monthly PDF mode parses `Trade Confirmation Summary`, `Purchase and Sale Summary`, and `Journal Entries`
- `--input-pdf` and `--input-text` can accept multiple files for one aggregate report

Robinhood crypto API:

- `--api-key`
- `--private-key-path`
- `--resource {accounts,orders,orders-report,holdings,trading-pairs}`
- `--api-version {v1,v2}`
- `--account-number`
- `orders-report` sorts by `created_at` before FIFO matching and may print warnings when history is limited or current holdings disagree with order-derived open lots

## Cache Behavior

Cache file default: `./.kalshi_cache.json`

- If cache file exists, cached trade JSON is used automatically.
- `--enable-cache` enables persistence to cache.
- `--force-refresh` bypasses cached trade JSON and refreshes from API, then updates cache.
- Starting cash is preserved unless user passes a new `--starting-cash` value.

## Safety and Secrets

- Never commit private key material.
- Keep these local-only:
  - `kalshi-key.txt`
  - `kalshi-key-id.txt`
  - `.kalshi_cache.json`
  - `.venv/`
- If credentials are exposed, rotate them immediately.

## Expected Output

In table mode, script prints:

1. Fill rows table
2. Reconciliation block:
   - Starting Cash
   - Ending Cash (Kalshi)
   - Portfolio Value (Kalshi)
   - Open Market Value
   - Open Notional (Cost Basis)
   - Estimated Unrealized P/L
   - Trades Won/Loss and Win/Loss %
   - Closed Profit/Loss
   - Estimated Total Profit/Loss
   - Net P/L vs Starting Cash

With `--debug`, include per-ticker reconciliation debug lines.

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

Reconciliation-only output is the default if no output format is set via CLI, environment variable, or top-of-file constant.

## Standard Validation Before Commit

```bash
python3 -m py_compile ./kalshi.py ./robinhood_crypto.py ./robinhood_event_contracts.py ./reporting_utils.py
python3 ./kalshi.py --help
./.venv/bin/python ./robinhood_crypto.py --help
./.venv/bin/python -m unittest discover -s tests -v
git status --short
```

## Documentation Sync Rule

If CLI flags, cache behavior, or reconciliation math changes, update:

- `README.md`
- this file (`Agents.md`)
- `docs/robinhood-event-contracts.md` when Robinhood event-contract assumptions change
