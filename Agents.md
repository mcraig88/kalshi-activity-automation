# Agents Guide

This file documents how coding agents (and humans) should work in this repository.

## Repository Purpose

- Main script: `./kalshi.py`
- Goal: fetch Kalshi fills/settlements, compute reconciliation metrics, and render output in `json` or `table` mode.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install requests cryptography
python3 ./kalshi.py --help
```

## Runtime Inputs

Required:

- `KALSHI_API_KEY_ID` (or `--api-key-id`)
- `KALSHI_PRIVATE_KEY_PATH` (or `--private-key-path`)

Optional key inputs:

- `--output-format {json,table}`
- `--full-history`
- `--starting-cash`
- `--debug`
- `--force-refresh`

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

## Standard Validation Before Commit

```bash
python3 -m py_compile ./kalshi.py
python3 ./kalshi.py --help
git status --short
```

## Documentation Sync Rule

If CLI flags, cache behavior, or reconciliation math changes, update:

- `README.md`
- this file (`Agents.md`)
