# Robinhood Event Contracts Notes

As of March 29, 2026, Robinhood publicly documents an event contracts product through Robinhood Derivatives, but I have not identified an official public API for event contract account activity comparable to Robinhood's crypto API.

## What Robinhood officially documents

- Event contracts are Yes/No style derivatives that generally settle to `$1` or `$0` per contract.
- Robinhood charges a `$0.01` commission per contract bought or sold.
- The exchange may also charge a fee or embed a spread into pricing.
- Robinhood provides an **Event Contracts Annual Statement** with:
  - Event contract traded
  - Closing date
  - Total costs
  - Total proceeds
  - Total fees and commissions
  - Profits and losses

## Practical implication for this repo

The most reliable first integration path is statement-based reporting rather than undocumented live API scraping.

That is why this repository now includes `./robinhood_event_contracts.py`, which supports:

- annual statement CSV input
- monthly Robinhood Derivatives PDF input
- extracted statement text input for parser testing/debugging

The current monthly statement parser is intentionally narrow. It focuses on:

- statement metadata
- `Trade Confirmation Summary` for fees and trade-cost detail
- `Purchase and Sale Summary` for closed positions
- `Journal Entries` for cash activity

It combines paired YES/NO rows for the same symbol into a single closed position and reports:

- total costs
- total proceeds
- total fees and commissions
- gross profit/loss
- net profit/loss after fees

It also supports importing multiple monthly PDFs into one aggregate report.

## Current limitation

I have not yet confirmed an official Robinhood export endpoint or machine-readable event contracts activity API.

The current PDF flow depends on macOS `swift` + `PDFKit` for text extraction rather than a third-party Python PDF package.

If you later obtain:

- a CSV export
- a PDF annual statement
- or a browser-captured JSON payload from the Prediction Markets hub

then we can build a more native Robinhood adapter from real sample data.

## Sources

- Robinhood event contracts support page:
  - https://robinhood.com/us/en/support/articles/robinhood-event-contracts/
- Robinhood Crypto Trading API announcement:
  - https://robinhood.com/us/en/newsroom/robinhood-crypto-trading-api/
