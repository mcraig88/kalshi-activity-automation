import base64
import argparse
import datetime
import json
import os
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

KALSHI_API_KEY_ID = "7a09498c-f8d0-4a50-912a-df455124e905"
KALSHI_PRIVATE_KEY_PATH = "./kalshi-key.txt"
KALSHI_TIMEOUT_SECONDS = 10.0
KALSHI_OUTPUT_FORMAT = "json"
KALSHI_PAGE_LIMIT = 100
KALSHI_FULL_HISTORY = False
KALSHI_DEBUG_APPENDIX = False


class KalshiClientError(Exception):
    """Base exception for Kalshi client errors."""


class KalshiAPIError(KalshiClientError):
    """Raised when the Kalshi API returns an error response."""


class KalshiClient:

    def __init__(self, key_id: str, key_path: str, timeout_seconds: float = 10.0):
        self.key_id = key_id
        self.private_key = self._load_private_key(key_path)
        self.timeout_seconds = timeout_seconds
        # Note: 'api.elections.kalshi.com' is Kalshi's default host for ALL v2 market operations,
        # not just election markets.
        self.base_url = "https://api.elections.kalshi.com"

    def _load_private_key(self, file_path: str):
        """Loads the RSA private key downloaded from the Kalshi UI."""
        resolved_path = os.path.expanduser(file_path)
        try:
            with open(resolved_path, "rb") as key_file:
                key_data = key_file.read()

            # Common misconfiguration: passing an SSH public key (*.pub) instead of a Kalshi private key.
            if key_data.startswith(b"ssh-ed25519") or resolved_path.endswith(".pub"):
                raise KalshiClientError(
                    f"Configured key path is an SSH public key, not a Kalshi private key: {resolved_path}. "
                    "Use the RSA private key file downloaded from Kalshi (PEM format)."
                )

            return serialization.load_pem_private_key(key_data, password=None)
        except FileNotFoundError as exc:
            raise KalshiClientError(f"Private key file not found: {resolved_path}") from exc
        except KalshiClientError:
            raise
        except Exception as exc:
            raise KalshiClientError(
                f"Failed to load private key from {resolved_path}: {exc}. "
                "Expected a Kalshi RSA private key PEM file (for example, with header "
                "'-----BEGIN RSA PRIVATE KEY-----')."
            ) from exc

    def _sign_request(self, timestamp: str, method: str, path: str) -> str:
        """Signs the request according to Kalshi's V2 spec (RSA-PSS + SHA256)."""
        # Strip query parameters from the path before signing
        path_without_query = path.split("?")[0]
        msg_string = f"{timestamp}{method}{path_without_query}"

        pss_salt_length = getattr(padding.PSS, "DIGEST_LENGTH", padding.PSS.MAX_LENGTH)

        signature = self.private_key.sign(
            msg_string.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=pss_salt_length,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def get_fills(self, limit: int = 100, cursor: str = None):
        """Fetches transaction fills from your portfolio."""
        endpoint = "/trade-api/v2/portfolio/fills"

        # Build query parameters
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        # Format URL
        url = f"{self.base_url}{endpoint}"

        # Current UTC time in milliseconds
        timestamp = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000))

        # Generate signature
        sig = self._sign_request(timestamp, "GET", endpoint)

        headers = {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=self.timeout_seconds
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout as exc:
            raise KalshiClientError(
                f"Request timed out after {self.timeout_seconds} seconds"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = exc.response.text if exc.response is not None else str(exc)
            raise KalshiAPIError(f"Kalshi API error {status}: {body}") from exc
        except requests.exceptions.RequestException as exc:
            raise KalshiClientError(f"Network/request error: {exc}") from exc


def _extract_rows(payload):
    if isinstance(payload, dict):
        if isinstance(payload.get("fills"), list):
            return payload["fills"], "fills"
        if isinstance(payload.get("data"), list):
            return payload["data"], "data"
    if isinstance(payload, list):
        return payload, "fills"
    return None, None


def _extract_next_cursor(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("cursor", "next_cursor", "nextCursor"):
        value = payload.get(key)
        if value:
            return value
    return None


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise KalshiClientError(f"Invalid boolean value '{value}'.")


def _get_fills_full_history(client: KalshiClient, limit: int):
    all_rows = []
    cursor = None
    pages_fetched = 0
    seen_cursors = set()
    container_key = "fills"

    while True:
        page = client.get_fills(limit=limit, cursor=cursor)
        pages_fetched += 1

        rows, page_container_key = _extract_rows(page)
        if rows:
            all_rows.extend(rows)
            if page_container_key:
                container_key = page_container_key

        next_cursor = _extract_next_cursor(page)
        if not next_cursor:
            break
        if next_cursor in seen_cursors:
            raise KalshiClientError(
                f"Pagination cursor repeated ('{next_cursor}'); stopping to avoid infinite loop."
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return {
        container_key: all_rows,
        "pages_fetched": pages_fetched,
        "full_history": True,
        "limit_per_page": limit,
        "total_rows": len(all_rows),
    }


def _parse_args():
    parser = argparse.ArgumentParser(description="Fetch Kalshi portfolio fills.")
    parser.add_argument("--api-key-id", help="Kalshi API key ID override.")
    parser.add_argument("--private-key-path", help="Private key file path override.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        help="Request timeout in seconds override.",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "table"],
        help="Output format override.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Rows per API page (default from config).",
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Fetch all pages using API cursor pagination.",
    )
    parser.add_argument(
        "--debug-appendix",
        action="store_true",
        help="Print per-market appendix calculation details (table mode).",
    )
    return parser.parse_args()


def _resolve_private_key_path(args) -> str:
    cli_value = args.private_key_path
    env_value = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    default_value = KALSHI_PRIVATE_KEY_PATH

    # Keep precedence (CLI > env > top constant), but gracefully fall back to the top constant
    # when an override points to a missing file.
    for candidate in (cli_value, env_value, default_value):
        if not candidate:
            continue
        resolved = os.path.expanduser(candidate)
        if os.path.exists(resolved):
            return candidate

    raise KalshiClientError(
        "No valid private key path found. Checked CLI arg, "
        "KALSHI_PRIVATE_KEY_PATH env var, and top-of-file KALSHI_PRIVATE_KEY_PATH."
    )


def _value_to_string(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


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


def _compute_table_appendix(rows):
    total_dollars_traded = 0.0
    total_closed_profit_loss = 0.0
    total_open_notional = 0.0
    total_trades_won = 0
    total_trades_loss = 0
    grouped = {}

    # Process in time order so lot matching is deterministic.
    sorted_rows = sorted(
        [row for row in rows if isinstance(row, dict)],
        key=lambda row: (row.get("ts", 0), row.get("created_time", "")),
    )
    for row in sorted_rows:
        action = str(row.get("action", "")).strip().lower()
        side = str(row.get("side", "")).strip().lower()
        ticker = str(row.get("market_ticker", "")).strip()
        if action not in {"buy", "sell"} or side not in {"yes", "no"} or not ticker:
            continue

        count = _to_float(row.get("count_fp"))
        if count is None or count <= 0:
            continue
        price = _to_float(row.get("yes_price_fixed")) if side == "yes" else _to_float(row.get("no_price_fixed"))
        if price is None:
            continue
        fee = _to_float(row.get("fee_cost")) or 0.0
        wager = count * price

        total_dollars_traded += abs(wager)

        key = (ticker, side)
        bucket = grouped.get(key)
        if bucket is None:
            bucket = {
                "ticker": ticker,
                "side": side,
                "buy_count": 0,
                "sell_count": 0,
                "wagered": 0.0,
                "fees": 0.0,
                "open_lots": [],
                "closed_pnl": 0.0,
                "matched_qty": 0.0,
            }
            grouped[key] = bucket

        bucket["wagered"] += abs(wager)
        bucket["fees"] += fee

        if action == "buy":
            bucket["buy_count"] += 1
            fee_per_share = fee / count if count else 0.0
            bucket["open_lots"].append([count, price, fee_per_share])
            continue

        # action == sell: close existing lots in FIFO order for this ticker+side.
        bucket["sell_count"] += 1
        sell_remaining = count
        sell_fee_per_share = fee / count if count else 0.0
        sell_price = price

        while sell_remaining > 0 and bucket["open_lots"]:
            lot_qty, lot_price, lot_fee_per_share = bucket["open_lots"][0]
            matched_qty = min(sell_remaining, lot_qty)
            buy_cost = matched_qty * (lot_price + lot_fee_per_share)
            sell_proceeds = matched_qty * (sell_price - sell_fee_per_share)
            bucket["closed_pnl"] += (sell_proceeds - buy_cost)
            bucket["matched_qty"] += matched_qty

            lot_qty -= matched_qty
            sell_remaining -= matched_qty
            if lot_qty <= 1e-12:
                bucket["open_lots"].pop(0)
            else:
                bucket["open_lots"][0][0] = lot_qty

    debug_rows = []
    for bucket in grouped.values():
        # Count wins/losses only for matched round-trips.
        if bucket["matched_qty"] > 0:
            if bucket["closed_pnl"] > 0:
                total_trades_won += 1
            elif bucket["closed_pnl"] < 0:
                total_trades_loss += 1
        total_closed_profit_loss += bucket["closed_pnl"]

        open_notional = 0.0
        for qty, entry_price, _entry_fee_per_share in bucket["open_lots"]:
            open_notional += qty * entry_price
        total_open_notional += open_notional

        status = "open"
        if bucket["matched_qty"] > 0:
            if bucket["closed_pnl"] > 0:
                status = "won"
            elif bucket["closed_pnl"] < 0:
                status = "loss"
            else:
                status = "breakeven"

        debug_rows.append(
            {
                "market_ticker": bucket["ticker"],
                "side": bucket["side"],
                "buy_count": bucket["buy_count"],
                "sell_count": bucket["sell_count"],
                "wagered": bucket["wagered"],
                "fees": bucket["fees"],
                "closed_pnl": bucket["closed_pnl"],
                "open_notional": open_notional,
                "status": status,
            }
        )

    considered_trades = total_trades_won + total_trades_loss
    if considered_trades > 0:
        win_pct = (total_trades_won / considered_trades) * 100.0
        loss_pct = (total_trades_loss / considered_trades) * 100.0
        win_loss_text = f"{win_pct:.2f}% / {loss_pct:.2f}%"
    else:
        win_loss_text = "N/A"

    closed_profit_loss_text = f"${total_closed_profit_loss:,.2f}"
    return {
        "total_dollars_traded": total_dollars_traded,
        "total_trades_won": total_trades_won,
        "total_trades_loss": total_trades_loss,
        "total_trades_percent_win_loss": win_loss_text,
        "total_profit_loss_text": closed_profit_loss_text,
        "total_closed_profit_loss": total_closed_profit_loss,
        "total_open_notional": total_open_notional,
        "debug_rows": sorted(debug_rows, key=lambda x: (x["market_ticker"], x["side"])),
    }


def _print_table_appendix(rows, debug_appendix: bool = False):
    summary = _compute_table_appendix(rows)
    print("")
    print("Appendix")
    print(f"Total Dollars Traded: ${summary['total_dollars_traded']:,.2f}")
    print(f"Total Trades Won: {summary['total_trades_won']}")
    print(f"Total Trades Loss: {summary['total_trades_loss']}")
    print(f"Total Trades Percent Win/Loss: {summary['total_trades_percent_win_loss']}")
    print(f"Total Profit/Loss: {summary['total_profit_loss_text']}")
    print(f"Closed Profit/Loss: ${summary['total_closed_profit_loss']:,.2f}")
    print(f"Open Notional: ${summary['total_open_notional']:,.2f}")
    if debug_appendix:
        print("")
        print("Appendix Debug (per market_ticker + side)")
        for row in summary["debug_rows"]:
            print(
                f"- {row['market_ticker']} [{row['side']}]: buys={row['buy_count']}, sells={row['sell_count']}, "
                f"wagered=${row['wagered']:,.2f}, fees=${row['fees']:,.2f}, "
                f"closed_p/l=${row['closed_pnl']:,.2f}, open_notional=${row['open_notional']:,.2f}, "
                f"status={row['status']}"
            )


def _print_table(rows):
    if not rows:
        print("No rows to display.")
        return

    columns = []
    for row in rows:
        if isinstance(row, dict):
            for key in row.keys():
                if key not in columns:
                    columns.append(key)

    if not columns:
        print("No tabular fields to display.")
        return

    widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            value = _value_to_string(row.get(col, "") if isinstance(row, dict) else "")
            widths[col] = max(widths[col], len(value))

    header = " | ".join(col.ljust(widths[col]) for col in columns)
    divider = "-+-".join("-" * widths[col] for col in columns)
    print(header)
    print(divider)
    for row in rows:
        line = " | ".join(
            _value_to_string(row.get(col, "") if isinstance(row, dict) else "").ljust(widths[col])
            for col in columns
        )
        print(line)


def _print_fills_data(fills_data, output_format: str, debug_appendix: bool = False):
    if output_format == "json":
        print(json.dumps(fills_data, indent=2))
        return

    rows = None
    if isinstance(fills_data, dict):
        if isinstance(fills_data.get("fills"), list):
            rows = fills_data["fills"]
        elif isinstance(fills_data.get("data"), list):
            rows = fills_data["data"]
    elif isinstance(fills_data, list):
        rows = fills_data

    if isinstance(rows, list) and rows and all(isinstance(item, dict) for item in rows):
        _print_table(rows)
        _print_table_appendix(rows, debug_appendix=debug_appendix)
    else:
        # Fallback when response shape is not tabular.
        print(json.dumps(fills_data, indent=2))


# --- Example Execution ---
if __name__ == "__main__":
    # Override order:
    #   1) CLI args (--api-key-id, --private-key-path, --timeout-seconds, --output-format, --limit, --full-history, --debug-appendix)
    #   2) Environment variables (KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH, KALSHI_TIMEOUT_SECONDS, KALSHI_OUTPUT_FORMAT, KALSHI_PAGE_LIMIT, KALSHI_FULL_HISTORY, KALSHI_DEBUG_APPENDIX)
    #   3) Module constants at the top of this file
    try:
        args = _parse_args()

        api_key_id = args.api_key_id or os.getenv("KALSHI_API_KEY_ID", KALSHI_API_KEY_ID)
        private_key_path = _resolve_private_key_path(args)
        timeout_seconds = args.timeout_seconds
        if timeout_seconds is None:
            timeout_seconds = float(os.getenv("KALSHI_TIMEOUT_SECONDS", str(KALSHI_TIMEOUT_SECONDS)))
        output_format = args.output_format or os.getenv(
            "KALSHI_OUTPUT_FORMAT", KALSHI_OUTPUT_FORMAT
        )
        if output_format not in {"json", "table"}:
            raise KalshiClientError(
                f"Invalid output format '{output_format}'. Use 'json' or 'table'."
            )
        limit = args.limit
        if limit is None:
            limit = int(os.getenv("KALSHI_PAGE_LIMIT", str(KALSHI_PAGE_LIMIT)))
        if limit <= 0:
            raise KalshiClientError("limit must be a positive integer.")

        if args.full_history:
            full_history = True
        else:
            full_history_env = os.getenv("KALSHI_FULL_HISTORY")
            if full_history_env is None:
                full_history = KALSHI_FULL_HISTORY
            else:
                full_history = _parse_bool(full_history_env)
        if args.debug_appendix:
            debug_appendix = True
        else:
            debug_appendix_env = os.getenv("KALSHI_DEBUG_APPENDIX")
            if debug_appendix_env is None:
                debug_appendix = KALSHI_DEBUG_APPENDIX
            else:
                debug_appendix = _parse_bool(debug_appendix_env)

        client = KalshiClient(api_key_id, private_key_path, timeout_seconds=timeout_seconds)
        if full_history:
            fills_data = _get_fills_full_history(client, limit=limit)
        else:
            fills_data = client.get_fills(limit=limit)
        _print_fills_data(fills_data, output_format, debug_appendix=debug_appendix)
    except KalshiClientError as exc:
        print(f"Kalshi client error: {exc}")
