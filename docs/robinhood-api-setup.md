# Robinhood API Setup

This repository currently supports Robinhood **event contracts reporting** through statement import, not through an official live event-contract API.

As of March 29, 2026, the official Robinhood API key flow I could verify is for the **Robinhood Crypto Trading API**.

## What the Robinhood API key is currently for

Robinhood publicly documents API credentials for its crypto trading API, including actions like:

- reading crypto accounts
- reading crypto holdings
- reading crypto orders
- reading crypto products
- reading crypto quotes
- placing crypto orders

I have **not** verified an official public API key flow for Robinhood event contracts.

## How to generate the Robinhood API key

1. Open Robinhood in a desktop web browser.
2. Sign in to Robinhood **web classic**.
3. Go to your **crypto account settings**.
4. Select **Add key**.
5. Choose the API actions you want to allow.
6. Complete the credential creation flow.
7. Save the generated API key securely.

Robinhood says you can later modify, disable, or delete the API credentials you create.

## Header and signing requirements

Authenticated Robinhood crypto API requests must include:

- `x-api-key`
- `x-signature`
- `x-timestamp`

Robinhood's documented signing message is:

```text
message = f"{api_key}{current_timestamp}{path}{method}{body}"
```

Robinhood notes that for requests without a body, the body can be omitted from the signature message.

The timestamp is a Unix timestamp in seconds and is only valid for `30 seconds` after generation.

## Endpoints currently implemented in this repo

The live Robinhood crypto script in this repo currently targets the documented crypto API at:

- base URL: `https://trading.robinhood.com`
- `GET /api/v2/crypto/trading/accounts/`
- `GET /api/v2/crypto/trading/orders/`
- `GET /api/v2/crypto/trading/holdings/`
- `GET /api/v2/crypto/trading/trading_pairs/`

Script:

- `./robinhood_crypto.py`

## Important limitation for this repo

If your goal is event-contract reporting similar to Kalshi, the Robinhood crypto API key may not help yet because I have not found an official public event-contract API.

That is why the current Robinhood support in this repo is:

- statement-based import via `./robinhood_event_contracts.py`
- documentation and samples for Event Contracts Annual Statement CSV ingestion

## Current recommended workflow

1. Use Robinhood's event-contract statement/document exports to obtain annual statement data.
2. Convert the statement to CSV if Robinhood only provides PDF.
3. Feed that CSV into `./robinhood_event_contracts.py`.

## Sources

- Robinhood Crypto Trading API support article:
  - https://robinhood.com/us/en/support/articles/crypto-api/?hcs=true
- Robinhood Crypto Trading API announcement:
  - https://robinhood.com/us/en/newsroom/robinhood-crypto-trading-api/
- Robinhood event contracts support page:
  - https://robinhood.com/us/en/support/articles/robinhood-event-contracts/
