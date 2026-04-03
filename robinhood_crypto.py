import argparse
import base64
from datetime import datetime, timezone
import json
import os
import time
from urllib.parse import urlencode, urlparse

from reporting_utils import render_table

try:
    import requests
    REQUESTS_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    requests = None
    REQUESTS_IMPORT_ERROR = exc

try:
    from nacl.signing import SigningKey
    NACL_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    SigningKey = None
    NACL_IMPORT_ERROR = exc


ROBINHOOD_API_KEY = None
ROBINHOOD_PRIVATE_KEY_PATH = "~/.ssh/rh_privatekey"
ROBINHOOD_TIMEOUT_SECONDS = 30.0
ROBINHOOD_OUTPUT_FORMAT = "json"
ROBINHOOD_API_VERSION = "v2"
ROBINHOOD_RESOURCE = "accounts"
ROBINHOOD_BASE_URL = "https://trading.robinhood.com"
ROBINHOOD_CREATED_AT_START = None
ROBINHOOD_ACCOUNT_NUMBER = None
ROBINHOOD_LIMIT = None
ROBINHOOD_DEFAULT_ORDER_COLUMNS = (
    "id",
    "account_number",
    "symbol",
    "side",
    "type",
    "state",
    "average_price",
    "filled_asset_quantity",
    "created_at",
)
ORDER_MATCH_EPSILON = 1e-12


class RobinhoodCryptoError(Exception):
    """Base exception for Robinhood crypto client errors."""


class RobinhoodCryptoAPIError(RobinhoodCryptoError):
    """Raised when the Robinhood crypto API returns an error response."""


def _ensure_runtime_dependencies():
    missing = []
    if requests is None:
        missing.append("requests")
    if SigningKey is None:
        missing.append("pynacl")
    if missing:
        requirements_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "requirements.txt"
        )
        packages = ", ".join(sorted(missing))
        raise RobinhoodCryptoError(
            f"Missing required Python package(s): {packages}. "
            "Install them with:\n"
            f"  ./.venv/bin/python -m pip install -r {requirements_path}"
        )


def _parse_csv_list(value: str):
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("$", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Read Robinhood Crypto Trading API account information, holdings, trading pairs, or recent orders."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  ./.venv/bin/python ./robinhood_crypto.py --api-key YOUR_API_KEY --private-key-path ~/.ssh/rh_privatekey --resource accounts\n"
            "  ./.venv/bin/python ./robinhood_crypto.py --api-key YOUR_API_KEY --private-key-path ~/.ssh/rh_privatekey --resource orders --output-format table\n"
            "  ./.venv/bin/python ./robinhood_crypto.py --api-key YOUR_API_KEY --private-key-path ~/.ssh/rh_privatekey --resource orders-report --symbol BTC --limit 25 --output-format table\n"
            "  ./.venv/bin/python ./robinhood_crypto.py --api-key YOUR_API_KEY --private-key-path ~/.ssh/rh_privatekey --resource holdings --account-number YOUR_ACCOUNT\n"
        ),
    )
    parser.add_argument("--api-key", help="Robinhood API key for the x-api-key header.")
    parser.add_argument(
        "--private-key-path",
        help="Path to the base64-encoded Robinhood Ed25519 private key file.",
    )
    parser.add_argument(
        "--resource",
        choices=["accounts", "orders", "orders-report", "holdings", "trading-pairs"],
        help="Resource to fetch. Default: accounts.",
    )
    parser.add_argument(
        "--api-version",
        choices=["v1", "v2"],
        help="Robinhood crypto API version. Default: v2.",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "table"],
        help="Output format. Default: json.",
    )
    parser.add_argument(
        "--account-number",
        help=(
            "Robinhood crypto account number. "
            "If omitted, uses ROBINHOOD_ACCOUNT_NUMBER when set, otherwise auto-selects the first account."
        ),
    )
    parser.add_argument(
        "--symbol",
        help="Comma-separated trading pair symbols, e.g. BTC-USD,ETH-USD.",
    )
    parser.add_argument(
        "--asset-code",
        help="Comma-separated asset codes, e.g. BTC,ETH.",
    )
    parser.add_argument(
        "--created-at-start",
        help="Filter orders created at or after an ISO-8601 timestamp, e.g. 2023-01-01T00:00:00Z.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of rows to return after pagination and filtering.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        help="HTTP request timeout in seconds.",
    )
    return parser.parse_args()


class RobinhoodCryptoClient:
    def __init__(self, api_key: str, private_key_path: str, timeout_seconds: float = ROBINHOOD_TIMEOUT_SECONDS):
        _ensure_runtime_dependencies()
        self.api_key = api_key
        self.private_key = self._load_private_key(private_key_path)
        self.timeout_seconds = timeout_seconds
        self.base_url = ROBINHOOD_BASE_URL

    def _load_private_key(self, private_key_path: str):
        resolved_path = os.path.expanduser(private_key_path)
        try:
            with open(resolved_path, "r", encoding="utf-8") as handle:
                private_key_base64 = handle.read().strip()
            private_key_seed = base64.b64decode(private_key_base64)
            return SigningKey(private_key_seed)
        except FileNotFoundError as exc:
            raise RobinhoodCryptoError(f"Private key file not found: {resolved_path}") from exc
        except Exception as exc:
            raise RobinhoodCryptoError(
                f"Failed to load Robinhood private key from {resolved_path}: {exc}"
            ) from exc

    @staticmethod
    def _current_timestamp() -> int:
        return int(time.time())

    @staticmethod
    def _build_query_string(params):
        filtered = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, list):
                for item in value:
                    filtered.append((key, item))
            else:
                filtered.append((key, value))
        return f"?{urlencode(filtered)}" if filtered else ""

    def _authorization_headers(self, method: str, path: str, body: str, timestamp: int):
        message = f"{self.api_key}{timestamp}{path}{method}{body}"
        signed = self.private_key.sign(message.encode("utf-8"))
        return {
            "x-api-key": self.api_key,
            "x-signature": base64.b64encode(signed.signature).decode("utf-8"),
            "x-timestamp": str(timestamp),
        }

    def _request(self, method: str, path: str, body: str = ""):
        timestamp = self._current_timestamp()
        headers = self._authorization_headers(method, path, body, timestamp)
        url = f"{self.base_url}{path}"
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            elif method == "POST":
                headers["Content-Type"] = "application/json"
                response = requests.post(
                    url, headers=headers, data=body or "", timeout=self.timeout_seconds
                )
            else:
                raise RobinhoodCryptoError(f"Unsupported method '{method}'.")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout as exc:
            raise RobinhoodCryptoError(
                f"Request timed out after {self.timeout_seconds} seconds"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body_text = exc.response.text if exc.response is not None else str(exc)
            raise RobinhoodCryptoAPIError(f"Robinhood API error {status}: {body_text}") from exc
        except requests.exceptions.RequestException as exc:
            raise RobinhoodCryptoError(f"Network/request error: {exc}") from exc

    def _get_paginated(self, path: str, limit: int = None):
        results = []
        next_path = path
        while next_path:
            payload = self._request("GET", next_path)
            if isinstance(payload, dict) and isinstance(payload.get("results"), list):
                results.extend(payload["results"])
                if limit is not None and limit > 0 and len(results) >= limit:
                    return results[:limit]
                next_url = payload.get("next")
                if next_url:
                    parsed = urlparse(next_url)
                    next_path = parsed.path
                    if parsed.query:
                        next_path += f"?{parsed.query}"
                else:
                    next_path = None
            else:
                return payload
        return results

    def get_accounts(self, api_version: str):
        path = f"/api/{api_version}/crypto/trading/accounts/"
        return self._request("GET", path)

    def get_trading_pairs(self, api_version: str, symbols=None, limit: int = None):
        query_string = self._build_query_string({"symbol": symbols or []})
        path = f"/api/{api_version}/crypto/trading/trading_pairs/{query_string}"
        payload = self._get_paginated(path, limit=limit)
        return payload

    def get_holdings(self, api_version: str, account_number: str, asset_codes=None, limit: int = None):
        params = {"account_number": account_number}
        if asset_codes:
            params["asset_code"] = asset_codes
        query_string = self._build_query_string(params)
        path = f"/api/{api_version}/crypto/trading/holdings/{query_string}"
        return self._get_paginated(path, limit=limit)

    def get_orders(
        self,
        api_version: str,
        account_number: str = None,
        created_at_start: str = None,
        limit: int = None,
    ):
        params = {}
        if api_version == "v2":
            params["account_number"] = account_number
        if created_at_start:
            params["created_at_start"] = created_at_start
        query_string = self._build_query_string(params)
        path = f"/api/{api_version}/crypto/trading/orders/{query_string}"
        return self._get_paginated(path, limit=limit)


def _resolve_api_key(args):
    api_key = args.api_key or os.getenv("ROBINHOOD_API_KEY") or ROBINHOOD_API_KEY
    if not api_key:
        raise RobinhoodCryptoError(
            "Robinhood API key is required. Pass --api-key or set ROBINHOOD_API_KEY."
        )
    return api_key


def _resolve_private_key_path(args):
    private_key_path = (
        args.private_key_path
        or os.getenv("ROBINHOOD_PRIVATE_KEY_PATH")
        or ROBINHOOD_PRIVATE_KEY_PATH
    )
    if not private_key_path:
        raise RobinhoodCryptoError(
            "Robinhood private key path is required. Pass --private-key-path or set ROBINHOOD_PRIVATE_KEY_PATH."
        )
    return private_key_path


def _resolve_account_number(client: RobinhoodCryptoClient, api_version: str, explicit_account_number: str):
    if explicit_account_number:
        return explicit_account_number
    configured_account_number = os.getenv("ROBINHOOD_ACCOUNT_NUMBER") or ROBINHOOD_ACCOUNT_NUMBER
    if configured_account_number:
        return configured_account_number
    accounts_payload = client.get_accounts(api_version)
    if isinstance(accounts_payload, dict) and isinstance(accounts_payload.get("results"), list):
        results = accounts_payload["results"]
    elif isinstance(accounts_payload, list):
        results = accounts_payload
    else:
        results = []
    if not results:
        raise RobinhoodCryptoError("No Robinhood crypto accounts were returned.")
    account_number = results[0].get("account_number")
    if not account_number:
        raise RobinhoodCryptoError("Robinhood account response missing 'account_number'.")
    return account_number


def _prepare_order_rows(rows):
    prepared = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        prepared_row = dict(row)
        average_price = _to_float(row.get("average_price"))
        filled_quantity = _to_float(row.get("filled_asset_quantity"))
        if average_price is not None and filled_quantity is not None:
            prepared_row["filled_notional"] = round(average_price * filled_quantity, 4)
        else:
            prepared_row["filled_notional"] = None
        prepared.append(prepared_row)
    return prepared


def _filter_order_rows_by_symbols(rows, symbols):
    if not symbols:
        return rows

    normalized_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    if not normalized_symbols:
        return rows

    filtered_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = str(row.get("symbol", "")).strip().upper()
        asset_code = row_symbol.split("-", 1)[0] if row_symbol else ""
        if any(symbol == row_symbol or symbol == asset_code for symbol in normalized_symbols):
            filtered_rows.append(row)
    return filtered_rows


def _apply_limit(rows, limit):
    if limit is None or limit <= 0:
        return rows
    return rows[:limit]


def _extract_order_fee(row):
    for key in ("fee", "fees", "fee_amount", "total_fee", "total_fees", "commission"):
        fee_value = _to_float(row.get(key))
        if fee_value is not None:
            return fee_value
    return 0.0


def _parse_created_at_timestamp(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()


def _sort_orders_for_summary(rows):
    sortable_rows = []
    for index, row in enumerate(rows):
        timestamp = None
        if isinstance(row, dict):
            timestamp = _parse_created_at_timestamp(row.get("created_at"))
        sortable_rows.append(
            (
                1 if timestamp is None else 0,
                0.0 if timestamp is None else timestamp,
                index,
                row,
            )
        )
    return [row for _, _, _, row in sorted(sortable_rows)]


def _extract_holdings_rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def _extract_holding_asset_code(row):
    asset_code = str(row.get("asset_code", "")).strip()
    if asset_code:
        return asset_code.upper()
    symbol = str(row.get("symbol", "")).strip().upper()
    if symbol and "-" in symbol:
        return symbol.split("-", 1)[0]
    return symbol


def _extract_holding_quantity(row):
    for key in (
        "total_quantity",
        "quantity",
        "asset_quantity",
        "quantity_available_for_trading",
        "available_quantity",
        "available",
    ):
        quantity = _to_float(row.get(key))
        if quantity is not None:
            return quantity
    return None


def _build_holding_quantity_by_asset(payload):
    quantities = {}
    for row in _extract_holdings_rows(payload):
        if not isinstance(row, dict):
            continue
        asset_code = _extract_holding_asset_code(row)
        quantity = _extract_holding_quantity(row)
        if asset_code and quantity is not None:
            quantities[asset_code] = quantities.get(asset_code, 0.0) + quantity
    return quantities


def _summarize_orders(rows, holdings_payload=None, summary_context=None):
    summary = {
        "total_orders": 0,
        "buy_orders": 0,
        "sell_orders": 0,
        "filled_orders": 0,
        "open_orders": 0,
        "canceled_orders": 0,
        "failed_orders": 0,
        "partially_filled_orders": 0,
        "filled_buy_notional": 0.0,
        "filled_sell_notional": 0.0,
        "filled_notional": 0.0,
        "filled_asset_quantity": 0.0,
        "symbols_traded": set(),
        "realized_profit_loss": 0.0,
        "net_cash_flow": 0.0,
        "open_cost_basis": 0.0,
        "raw_open_cost_basis": 0.0,
        "unmatched_sell_quantity": 0.0,
        "warnings": [],
    }
    if summary_context is None:
        summary_context = {}
    open_lots = {}

    for row in _sort_orders_for_summary(rows):
        if not isinstance(row, dict):
            continue
        summary["total_orders"] += 1

        side = str(row.get("side", "")).strip().lower()
        state = str(row.get("state", "")).strip().lower()
        symbol = str(row.get("symbol", "")).strip()
        if symbol:
            summary["symbols_traded"].add(symbol)

        if side == "buy":
            summary["buy_orders"] += 1
        elif side == "sell":
            summary["sell_orders"] += 1

        state_key = f"{state}_orders"
        if state_key in summary:
            summary[state_key] += 1

        filled_notional = _to_float(row.get("filled_notional")) or 0.0
        filled_quantity = _to_float(row.get("filled_asset_quantity")) or 0.0
        fee_amount = _extract_order_fee(row)
        if state in {"filled", "partially_filled"} and filled_quantity > 0:
            summary["filled_notional"] += filled_notional
            summary["filled_asset_quantity"] += filled_quantity
            if side == "buy":
                summary["filled_buy_notional"] += filled_notional
                summary["net_cash_flow"] -= filled_notional + fee_amount
                lot_unit_cost = (filled_notional + fee_amount) / filled_quantity
                open_lots.setdefault(symbol, []).append(
                    {"quantity": filled_quantity, "unit_cost": lot_unit_cost}
                )
            elif side == "sell":
                summary["filled_sell_notional"] += filled_notional
                net_proceeds = filled_notional - fee_amount
                summary["net_cash_flow"] += net_proceeds
                remaining_to_match = filled_quantity
                matched_quantity = 0.0
                matched_cost = 0.0
                lots = open_lots.setdefault(symbol, [])
                while remaining_to_match > 0 and lots:
                    current_lot = lots[0]
                    lot_quantity = current_lot["quantity"]
                    matched_from_lot = min(remaining_to_match, lot_quantity)
                    matched_quantity += matched_from_lot
                    matched_cost += matched_from_lot * current_lot["unit_cost"]
                    current_lot["quantity"] -= matched_from_lot
                    remaining_to_match -= matched_from_lot
                    if current_lot["quantity"] <= ORDER_MATCH_EPSILON:
                        lots.pop(0)

                if matched_quantity > 0:
                    matched_proceeds = net_proceeds * (matched_quantity / filled_quantity)
                    summary["realized_profit_loss"] += matched_proceeds - matched_cost
                if remaining_to_match > 0:
                    summary["unmatched_sell_quantity"] += remaining_to_match

    open_position_details = []
    for symbol, lots in open_lots.items():
        symbol_quantity = 0.0
        symbol_cost_basis = 0.0
        for lot in lots:
            symbol_quantity += lot["quantity"]
            symbol_cost_basis += lot["quantity"] * lot["unit_cost"]
        if symbol_quantity > ORDER_MATCH_EPSILON:
            open_position_details.append(
                {
                    "symbol": symbol,
                    "asset_code": symbol.split("-", 1)[0].upper() if symbol else "",
                    "quantity": symbol_quantity,
                    "cost_basis": symbol_cost_basis,
                }
            )
            summary["raw_open_cost_basis"] += symbol_cost_basis

    summary["open_cost_basis"] = summary["raw_open_cost_basis"]

    if summary_context.get("limit_applied"):
        summary["warnings"].append(
            "Order history may be incomplete because --limit was used; realized P/L and open cost basis only reflect the fetched rows."
        )
    created_at_start = summary_context.get("created_at_start")
    if created_at_start:
        summary["warnings"].append(
            f"Order history starts at {created_at_start}; older buys or sells are excluded from this summary."
        )
    holdings_warning = summary_context.get("holdings_warning")
    if holdings_warning:
        summary["warnings"].append(holdings_warning)
    if summary["unmatched_sell_quantity"] > ORDER_MATCH_EPSILON:
        summary["warnings"].append(
            "Some sells could not be matched to earlier buys in the fetched order history; the summary should be treated as incomplete."
        )

    if holdings_payload is not None:
        holdings_by_asset = _build_holding_quantity_by_asset(holdings_payload)
        suppressed_symbols = []
        mismatched_symbols = []
        adjusted_open_cost_basis = 0.0
        for position in open_position_details:
            asset_code = position["asset_code"]
            holding_quantity = holdings_by_asset.get(asset_code)
            if holding_quantity is None:
                adjusted_open_cost_basis += position["cost_basis"]
                continue
            if holding_quantity <= ORDER_MATCH_EPSILON:
                suppressed_symbols.append(position["symbol"])
                continue
            adjusted_open_cost_basis += position["cost_basis"]
            if position["quantity"] > holding_quantity + ORDER_MATCH_EPSILON:
                mismatched_symbols.append(position["symbol"])

        summary["open_cost_basis"] = adjusted_open_cost_basis

        if suppressed_symbols:
            suppressed_list = ", ".join(sorted(suppressed_symbols))
            summary["warnings"].append(
                "Current holdings are zero for "
                f"{suppressed_list}, so unmatched FIFO leftovers were excluded from Open Cost Basis."
            )
        if mismatched_symbols:
            mismatch_list = ", ".join(sorted(mismatched_symbols))
            summary["warnings"].append(
                "Current holdings are smaller than the order-derived open quantity for "
                f"{mismatch_list}; Open Cost Basis may still be overstated."
            )

    summary["symbols_traded"] = sorted(summary["symbols_traded"])
    return summary


def _print_order_summary(summary):
    print("")
    print("Robinhood Crypto Orders Summary")
    print(f"Total Orders: {summary['total_orders']}")
    print(f"Buy Orders: {summary['buy_orders']}")
    print(f"Sell Orders: {summary['sell_orders']}")
    print(f"Filled Orders: {summary['filled_orders']}")
    print(f"Partially Filled Orders: {summary['partially_filled_orders']}")
    print(f"Open Orders: {summary['open_orders']}")
    print(f"Canceled Orders: {summary['canceled_orders']}")
    print(f"Failed Orders: {summary['failed_orders']}")
    print(f"Filled Asset Quantity: {summary['filled_asset_quantity']:,.8f}")
    print(f"Filled Buy Notional: ${summary['filled_buy_notional']:,.2f}")
    print(f"Filled Sell Notional: ${summary['filled_sell_notional']:,.2f}")
    print(f"Total Filled Notional: ${summary['filled_notional']:,.2f}")
    print(f"Net Cash Flow: ${summary['net_cash_flow']:,.2f}")
    print(f"Realized Profit/Loss: ${summary['realized_profit_loss']:,.2f}")
    print(f"Open Cost Basis: ${summary['open_cost_basis']:,.2f}")
    if summary["unmatched_sell_quantity"] > ORDER_MATCH_EPSILON:
        print(
            "Unmatched Sell Quantity (History Gap): "
            f"{summary['unmatched_sell_quantity']:,.8f}"
        )
    if summary["symbols_traded"]:
        print(f"Symbols Traded: {', '.join(summary['symbols_traded'])}")
    if summary["warnings"]:
        print("Warnings:")
        for warning in summary["warnings"]:
            print(f"- {warning}")


def _print_payload(
    payload,
    output_format: str,
    resource: str,
    holdings_payload=None,
    summary_context=None,
):
    if output_format == "json":
        print(json.dumps(payload, indent=2))
        return

    if resource in {"orders", "orders-report"}:
        rows = payload if isinstance(payload, list) else payload.get("results", []) if isinstance(payload, dict) else []
        prepared_rows = _prepare_order_rows(rows)
        columns = [column for column in ROBINHOOD_DEFAULT_ORDER_COLUMNS if prepared_rows and column in prepared_rows[0]]
        if prepared_rows and "filled_notional" in prepared_rows[0]:
            columns.append("filled_notional")
        render_table(prepared_rows, columns=columns)
        if resource == "orders-report":
            summary = _summarize_orders(
                prepared_rows,
                holdings_payload=holdings_payload,
                summary_context=summary_context,
            )
            _print_order_summary(summary)
        return

    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        render_table(payload["results"])
        return
    if isinstance(payload, list):
        render_table(payload)
        return

    print(json.dumps(payload, indent=2))


def _symbols_to_asset_codes(symbols):
    asset_codes = []
    for symbol in symbols:
        normalized = symbol.strip().upper()
        if not normalized:
            continue
        asset_codes.append(normalized.split("-", 1)[0])
    return sorted(set(asset_codes))


if __name__ == "__main__":
    try:
        args = _parse_args()
        api_key = _resolve_api_key(args)
        private_key_path = _resolve_private_key_path(args)
        timeout_seconds = args.timeout_seconds or float(
            os.getenv("ROBINHOOD_TIMEOUT_SECONDS", str(ROBINHOOD_TIMEOUT_SECONDS))
        )
        api_version = args.api_version or os.getenv("ROBINHOOD_API_VERSION") or ROBINHOOD_API_VERSION
        output_format = args.output_format or os.getenv("ROBINHOOD_OUTPUT_FORMAT") or ROBINHOOD_OUTPUT_FORMAT
        resource = args.resource or os.getenv("ROBINHOOD_RESOURCE") or ROBINHOOD_RESOURCE
        limit = args.limit
        if limit is None:
            raw_limit = os.getenv("ROBINHOOD_LIMIT")
            if raw_limit:
                limit = int(raw_limit)
            else:
                limit = ROBINHOOD_LIMIT
        created_at_start = (
            args.created_at_start
            or os.getenv("ROBINHOOD_CREATED_AT_START")
            or ROBINHOOD_CREATED_AT_START
        )
        symbols = _parse_csv_list(args.symbol) if args.symbol else []
        asset_codes = _parse_csv_list(args.asset_code) if args.asset_code else []

        client = RobinhoodCryptoClient(
            api_key=api_key,
            private_key_path=private_key_path,
            timeout_seconds=timeout_seconds,
        )

        if resource == "accounts":
            payload = client.get_accounts(api_version)
        elif resource in {"orders", "orders-report"}:
            account_number = _resolve_account_number(client, api_version, args.account_number)
            payload = client.get_orders(
                api_version=api_version,
                account_number=account_number,
                created_at_start=created_at_start,
                limit=limit,
            )
            payload = _filter_order_rows_by_symbols(payload, symbols)
            payload = _apply_limit(payload, limit)
            holdings_payload = None
            holdings_warning = None
            if resource == "orders-report":
                try:
                    holdings_payload = client.get_holdings(
                        api_version=api_version,
                        account_number=account_number,
                        asset_codes=_symbols_to_asset_codes(symbols) if symbols else None,
                        limit=None,
                    )
                except RobinhoodCryptoError as exc:
                    holdings_warning = (
                        "Current holdings could not be fetched for cross-checking: "
                        f"{exc}"
                    )
        elif resource == "holdings":
            account_number = _resolve_account_number(client, api_version, args.account_number)
            payload = client.get_holdings(
                api_version=api_version,
                account_number=account_number,
                asset_codes=asset_codes,
                limit=limit,
            )
        else:
            payload = client.get_trading_pairs(api_version=api_version, symbols=symbols, limit=limit)

        _print_payload(
            payload,
            output_format=output_format,
            resource=resource,
            holdings_payload=holdings_payload if resource == "orders-report" else None,
            summary_context={
                "limit_applied": limit is not None and limit > 0,
                "created_at_start": created_at_start if resource == "orders-report" else None,
                "holdings_warning": holdings_warning if resource == "orders-report" else None,
            },
        )
    except RobinhoodCryptoError as exc:
        print(f"Robinhood crypto error: {exc}")
