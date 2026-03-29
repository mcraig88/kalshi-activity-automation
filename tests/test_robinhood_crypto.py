import base64
import os
import unittest
from unittest import mock

from nacl.signing import SigningKey

from robinhood_crypto import (
    RobinhoodCryptoClient,
    _apply_limit,
    _filter_order_rows_by_symbols,
    _prepare_order_rows,
    _resolve_account_number,
    _summarize_orders,
)


class RobinhoodCryptoTests(unittest.TestCase):
    def test_authorization_headers_match_official_signature_example(self):
        private_key_seed = base64.b64decode("xQnTJVeQLmw1/Mg2YimEViSpw/SdJcgNXZ5kQkAXNPU=")
        client = RobinhoodCryptoClient.__new__(RobinhoodCryptoClient)
        client.api_key = "rh-api-6148effc-c0b1-486c-8940-a1d099456be6"
        client.private_key = SigningKey(private_key_seed)

        body = (
            "{'client_order_id': '131de903-5a9c-4260-abc1-28d562a5dcf0', "
            "'side': 'buy', 'symbol': 'BTC-USD', 'type': 'market', "
            "'market_order_config': {'asset_quantity': '0.1'}}"
        )
        headers = client._authorization_headers(
            method="POST",
            path="/api/v1/crypto/trading/orders/",
            body=body,
            timestamp=1698708981,
        )

        self.assertEqual(
            headers["x-signature"],
            "q/nEtxp/P2Or3hph3KejBqnw5o9qeuQ+hYRnB56FaHbjDsNUY9KhB1asMxohDnzdVFSD7StaTqjSd9U9HvaRAw==",
        )
        self.assertEqual(
            headers["x-api-key"], "rh-api-6148effc-c0b1-486c-8940-a1d099456be6"
        )
        self.assertEqual(headers["x-timestamp"], "1698708981")

    def test_build_query_string_supports_lists(self):
        query = RobinhoodCryptoClient._build_query_string(
            {"account_number": "ACC123", "symbol": ["BTC-USD", "ETH-USD"]}
        )
        self.assertEqual(query, "?account_number=ACC123&symbol=BTC-USD&symbol=ETH-USD")

    def test_prepare_order_rows_adds_filled_notional(self):
        rows = [
            {"average_price": "100.5", "filled_asset_quantity": "0.2"},
            {"average_price": None, "filled_asset_quantity": "0.2"},
        ]

        prepared = _prepare_order_rows(rows)

        self.assertEqual(prepared[0]["filled_notional"], 20.1)
        self.assertIsNone(prepared[1]["filled_notional"])

    def test_summarize_orders_tracks_states_and_notional(self):
        rows = [
            {
                "symbol": "BTC-USD",
                "side": "buy",
                "state": "filled",
                "filled_notional": 100.0,
                "filled_asset_quantity": 0.002,
            },
            {
                "symbol": "ETH-USD",
                "side": "sell",
                "state": "partially_filled",
                "filled_notional": 50.0,
                "filled_asset_quantity": 0.1,
            },
            {
                "symbol": "BTC-USD",
                "side": "buy",
                "state": "canceled",
                "filled_notional": None,
                "filled_asset_quantity": 0.0,
            },
        ]

        summary = _summarize_orders(rows)

        self.assertEqual(summary["total_orders"], 3)
        self.assertEqual(summary["buy_orders"], 2)
        self.assertEqual(summary["sell_orders"], 1)
        self.assertEqual(summary["filled_orders"], 1)
        self.assertEqual(summary["partially_filled_orders"], 1)
        self.assertEqual(summary["canceled_orders"], 1)
        self.assertEqual(summary["filled_buy_notional"], 100.0)
        self.assertEqual(summary["filled_sell_notional"], 50.0)
        self.assertEqual(summary["filled_notional"], 150.0)
        self.assertAlmostEqual(summary["filled_asset_quantity"], 0.102)
        self.assertEqual(summary["symbols_traded"], ["BTC-USD", "ETH-USD"])
        self.assertEqual(summary["net_cash_flow"], -50.0)
        self.assertEqual(summary["realized_profit_loss"], 0.0)
        self.assertEqual(summary["open_cost_basis"], 100.0)

    def test_filter_order_rows_by_symbols_matches_symbol_and_asset_code(self):
        rows = [
            {"symbol": "BTC-USD", "side": "buy"},
            {"symbol": "ETH-USD", "side": "buy"},
            {"symbol": "BTC-USD", "side": "sell"},
        ]

        filtered_btc = _filter_order_rows_by_symbols(rows, ["BTC"])
        filtered_eth = _filter_order_rows_by_symbols(rows, ["ETH-USD"])

        self.assertEqual(filtered_btc, [rows[0], rows[2]])
        self.assertEqual(filtered_eth, [rows[1]])

    def test_apply_limit_returns_requested_prefix(self):
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]

        self.assertEqual(_apply_limit(rows, 2), [{"id": 1}, {"id": 2}])
        self.assertEqual(_apply_limit(rows, None), rows)
        self.assertEqual(_apply_limit(rows, 0), rows)

    def test_summarize_orders_calculates_fifo_realized_profit_loss(self):
        rows = [
            {
                "symbol": "BTC-USD",
                "side": "buy",
                "state": "filled",
                "filled_notional": 100.0,
                "filled_asset_quantity": 1.0,
            },
            {
                "symbol": "BTC-USD",
                "side": "buy",
                "state": "filled",
                "filled_notional": 60.0,
                "filled_asset_quantity": 0.5,
            },
            {
                "symbol": "BTC-USD",
                "side": "sell",
                "state": "filled",
                "filled_notional": 180.0,
                "filled_asset_quantity": 1.2,
            },
        ]

        summary = _summarize_orders(rows)

        self.assertAlmostEqual(summary["realized_profit_loss"], 56.0)
        self.assertAlmostEqual(summary["net_cash_flow"], 20.0)
        self.assertAlmostEqual(summary["open_cost_basis"], 36.0)
        self.assertEqual(summary["unmatched_sell_quantity"], 0.0)

    def test_summarize_orders_includes_fees_in_cost_basis_and_proceeds(self):
        rows = [
            {
                "symbol": "BTC-USD",
                "side": "buy",
                "state": "filled",
                "filled_notional": 100.0,
                "filled_asset_quantity": 1.0,
                "fee": 1.0,
            },
            {
                "symbol": "BTC-USD",
                "side": "sell",
                "state": "filled",
                "filled_notional": 110.0,
                "filled_asset_quantity": 1.0,
                "fee": 2.0,
            },
        ]

        summary = _summarize_orders(rows)

        self.assertAlmostEqual(summary["realized_profit_loss"], 7.0)
        self.assertAlmostEqual(summary["net_cash_flow"], 7.0)
        self.assertAlmostEqual(summary["open_cost_basis"], 0.0)

    def test_resolve_account_number_prefers_env_before_fetching_accounts(self):
        client = mock.Mock()
        with mock.patch.dict(os.environ, {"ROBINHOOD_ACCOUNT_NUMBER": "ENV-ACCOUNT"}, clear=False):
            account_number = _resolve_account_number(client, "v2", explicit_account_number=None)
        self.assertEqual(account_number, "ENV-ACCOUNT")
        client.get_accounts.assert_not_called()

    def test_resolve_account_number_fetches_first_account_when_unset(self):
        client = mock.Mock()
        client.get_accounts.return_value = {
            "results": [{"account_number": "311063115497"}]
        }
        with mock.patch.dict(os.environ, {}, clear=False):
            account_number = _resolve_account_number(client, "v2", explicit_account_number=None)
        self.assertEqual(account_number, "311063115497")
        client.get_accounts.assert_called_once_with("v2")


if __name__ == "__main__":
    unittest.main()
