# Event Contract Reporting

This repository contains small command-line tools for Kalshi reporting, Robinhood crypto reads, and Robinhood event-contract statement reporting.

## Scripts

> **`./kalshi.py`**
>
> Live Kalshi reporting script.
>
> - Pulls fills, settlements, balances, and reconciliation data from the Kalshi API
> - Supports reconciliation-only, JSON, and table output
> - Supports caching, full-history fetches, and starting-cash reconciliation
>
> Detailed guide: [./README-kalshi.md](./README-kalshi.md)

> **`./robinhood_crypto.py`**
>
> Read-only Robinhood Crypto Trading API client.
>
> - Reads accounts, holdings, trading pairs, and order history
> - Supports tabular order reports and summary output
> - Uses Robinhood API-key plus Ed25519 request signing
>
> Detailed guide: [./README-robinhood-crypto.md](./README-robinhood-crypto.md)

> **`./robinhood_event_contracts.py`**
>
> Robinhood event-contract statement reporter.
>
> - Reads annual statement CSV files
> - Reads monthly Robinhood Derivatives PDF statements
> - Combines closed-position data, fee data, and cash activity into a single report
>
> Supporting notes: [./docs/robinhood-event-contracts.md](./docs/robinhood-event-contracts.md)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./.venv/bin/python -m unittest discover -s tests -v
```

## Quick Usage

Run Kalshi reconciliation or table reporting:

```bash
./.venv/bin/python ./kalshi.py \
  --api-key-id "YOUR_KALSHI_API_KEY_ID" \
  --private-key-path "./kalshi-key.txt" \
  --output-format table \
  --full-history
```

Read Robinhood crypto orders with a summary report:

```bash
./.venv/bin/python ./robinhood_crypto.py \
  --api-key "YOUR_ROBINHOOD_API_KEY" \
  --private-key-path ~/.ssh/rh_privatekey \
  --resource orders-report \
  --api-version v2 \
  --output-format table
```

Import Robinhood event-contract monthly statements:

```bash
./.venv/bin/python ./robinhood_event_contracts.py \
  --input-pdf ./_reference_files/*.pdf \
  --output-format table
```

More detailed usage guides:

- [./README-kalshi.md](./README-kalshi.md)
- [./README-robinhood-crypto.md](./README-robinhood-crypto.md)
- [./docs/robinhood-event-contracts.md](./docs/robinhood-event-contracts.md)

Local configuration reference:

- [./.env.example](./.env.example)
- [./docs/robinhood-api-setup.md](./docs/robinhood-api-setup.md)
