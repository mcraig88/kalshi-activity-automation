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

Local configuration reference:

- [./.env.example](./.env.example)
- [./docs/robinhood-api-setup.md](./docs/robinhood-api-setup.md)
