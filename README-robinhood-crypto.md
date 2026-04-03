# Robinhood Crypto Guide

This guide is specific to the Robinhood Crypto API workflow in this repository.

Script:

- `./robinhood_crypto.py`

Supporting docs:

- [Robinhood API Setup](./docs/robinhood-api-setup.md)
- [Robinhood Event Contracts Notes](./docs/robinhood-event-contracts.md)

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./.venv/bin/python ./robinhood_crypto.py --help
```

Use [`.env.example`](./.env.example) as a reference for local environment variables.

## What This Script Does

`./robinhood_crypto.py` provides a read-only Robinhood Crypto Trading API client for:

- `accounts`
- `orders`
- `orders-report`
- `holdings`
- `trading-pairs`

## Authentication

Robinhood crypto requests require:

- `x-api-key`
- `x-signature`
- `x-timestamp`

The script expects:

- `ROBINHOOD_API_KEY`
- `ROBINHOOD_PRIVATE_KEY_PATH`
- optionally `ROBINHOOD_ACCOUNT_NUMBER`

See [Robinhood API Setup](./docs/robinhood-api-setup.md) for the credential flow.

## Usage

Read Robinhood crypto accounts:

```bash
./.venv/bin/python ./robinhood_crypto.py \
  --api-key "YOUR_ROBINHOOD_API_KEY" \
  --private-key-path ~/.ssh/rh_privatekey \
  --resource accounts \
  --api-version v2 \
  --output-format json
```

Read recent Robinhood crypto orders:

```bash
./.venv/bin/python ./robinhood_crypto.py \
  --api-key "YOUR_ROBINHOOD_API_KEY" \
  --private-key-path ~/.ssh/rh_privatekey \
  --resource orders \
  --api-version v2 \
  --output-format table
```

Read recent Robinhood crypto orders with a summary report:

```bash
./.venv/bin/python ./robinhood_crypto.py \
  --api-key "YOUR_ROBINHOOD_API_KEY" \
  --private-key-path ~/.ssh/rh_privatekey \
  --resource orders-report \
  --api-version v2 \
  --output-format table
```

Filter recent BTC orders and cap the returned rows:

```bash
./.venv/bin/python ./robinhood_crypto.py \
  --api-key "YOUR_ROBINHOOD_API_KEY" \
  --private-key-path ~/.ssh/rh_privatekey \
  --resource orders-report \
  --symbol BTC \
  --limit 25 \
  --timeout-seconds 60 \
  --output-format table
```

Read holdings:

```bash
./.venv/bin/python ./robinhood_crypto.py \
  --api-key "YOUR_ROBINHOOD_API_KEY" \
  --private-key-path ~/.ssh/rh_privatekey \
  --resource holdings \
  --api-version v2 \
  --output-format table
```

If `--account-number` is omitted for `orders`, `orders-report`, or `holdings`, the script uses `ROBINHOOD_ACCOUNT_NUMBER` when set, otherwise it uses the first account returned by the Robinhood API.

## Notes

- `orders` prints order rows
- `orders-report` prints order rows plus a summary block
- `orders-report` sorts fetched orders by `created_at` before FIFO matching buys and sells
- `orders-report` cross-checks current holdings and hides leftover open cost basis for symbols whose live holdings are zero
- symbol filtering for orders is applied client-side in the current script
- if you use `--limit` or `--created-at-start`, the summary may warn that realized P/L and open cost basis are incomplete because older rows were excluded
- if you have a long history, use a higher timeout and avoid `--limit` when you want the most reliable summary

## Safety Notes

- Do not commit API keys or private keys.
- Keep Robinhood key files local.
- If credentials are exposed, rotate them immediately.
