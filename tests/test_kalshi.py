import io
import unittest
from contextlib import redirect_stdout

from kalshi import _extract_balance_snapshot, _print_reconciliation


class DummyKalshiClient:
    def __init__(self, payload):
        self.payload = payload

    def _get_json(self, endpoint, params=None):
        self.last_endpoint = endpoint
        self.last_params = params
        return self.payload


class KalshiTests(unittest.TestCase):
    def test_extract_balance_snapshot_treats_portfolio_value_as_positions_only(self):
        client = DummyKalshiClient(
            {
                "balance": 1725,
                "portfolio_value": 2609,
                "updated_ts": 1234567890,
            }
        )

        snapshot = _extract_balance_snapshot(client)

        self.assertEqual(client.last_endpoint, "/trade-api/v2/portfolio/balance")
        self.assertEqual(snapshot["ending_cash"], 17.25)
        self.assertEqual(snapshot["positions_value"], 26.09)
        self.assertEqual(snapshot["total_account_value"], 43.34)

    def test_print_reconciliation_uses_total_account_value_for_net_vs_start(self):
        summary = {
            "total_open_notional": 20.00,
            "total_trades_won": 1,
            "total_trades_loss": 0,
            "total_trades_percent_win_loss": "100.00% / 0.00%",
            "total_closed_profit_loss": 2.00,
            "debug_rows": [],
        }
        balance_snapshot = {
            "ending_cash": 17.25,
            "portfolio_value": 26.09,
            "positions_value": 26.09,
            "total_account_value": 43.34,
        }
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            _print_reconciliation(
                summary,
                balance_snapshot=balance_snapshot,
                starting_cash=40.00,
                starting_cash_source="cli",
            )

        output = buffer.getvalue()
        self.assertIn("Ending Cash (Kalshi): $17.25", output)
        self.assertIn("Portfolio Value (Kalshi Positions): $26.09", output)
        self.assertIn("Total Account Value (Cash + Portfolio): $43.34", output)
        self.assertIn("Estimated Unrealized P/L: $6.09", output)
        self.assertIn("Net P/L vs Starting Cash: $3.34", output)

    def test_print_reconciliation_supports_legacy_cached_balance_snapshot_shape(self):
        summary = {
            "total_open_notional": 10.00,
            "total_trades_won": 0,
            "total_trades_loss": 0,
            "total_trades_percent_win_loss": "N/A",
            "total_closed_profit_loss": 0.00,
            "debug_rows": [],
        }
        legacy_balance_snapshot = {
            "ending_cash": 17.25,
            "portfolio_value": 26.09,
        }
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            _print_reconciliation(
                summary,
                balance_snapshot=legacy_balance_snapshot,
                starting_cash=None,
            )

        output = buffer.getvalue()
        self.assertIn("Portfolio Value (Kalshi Positions): $26.09", output)
        self.assertIn("Total Account Value (Cash + Portfolio): $43.34", output)


if __name__ == "__main__":
    unittest.main()
