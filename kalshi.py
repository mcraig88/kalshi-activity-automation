import base64
import argparse
import datetime
import json
import os
from reporting_utils import collect_columns, render_table

try:
    import requests
    REQUESTS_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    requests = None
    REQUESTS_IMPORT_ERROR = exc

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    CRYPTOGRAPHY_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    hashes = None
    serialization = None
    padding = None
    CRYPTOGRAPHY_IMPORT_ERROR = exc

KALSHI_API_KEY_ID = "YOUR_KALSHI_API_KEY_ID"
KALSHI_PRIVATE_KEY_PATH = "./kalshi-key.txt"
KALSHI_TIMEOUT_SECONDS = 10.0
KALSHI_OUTPUT_FORMAT = None
KALSHI_PAGE_LIMIT = 100
KALSHI_FULL_HISTORY = False
KALSHI_DEBUG_APPENDIX = False
KALSHI_STARTING_CASH = None
KALSHI_USE_CACHED_STARTING_CASH = False
KALSHI_ENABLE_CACHE = False
KALSHI_CACHE_FILE = "./.kalshi_cache.json"
KALSHI_FORCE_REFRESH = False
KALSHI_DEFAULT_TABLE_COLUMNS = (
    "created_time",
    "market_ticker",
    "action",
    "side",
    "count_fp",
    "price_fixed",
    "trade_value_dollars",
    "fee_cost",
    "is_taker",
)


class KalshiClientError(Exception):
    """Base exception for Kalshi client errors."""


class KalshiAPIError(KalshiClientError):
    """Raised when the Kalshi API returns an error response."""


def _ensure_runtime_dependencies():
    missing = []
    if requests is None:
        missing.append("requests")
    if hashes is None or serialization is None or padding is None:
        missing.append("cryptography")
    if missing:
        requirements_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "requirements.txt"
        )
        packages = ", ".join(sorted(missing))
        raise KalshiClientError(
            f"Missing required Python package(s): {packages}. "
            "Install them with:\n"
            f"  python3 -m pip install -r {requirements_path}"
        )


class KalshiClient:

    def __init__(self, key_id: str, key_path: str, timeout_seconds: float = 10.0):
        _ensure_runtime_dependencies()
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

    def _get_json(self, endpoint: str, params: dict = None):
        url = f"{self.base_url}{endpoint}"
        timestamp = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000))
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

    def get_fills(self, limit: int = 100, cursor: str = None):
        """Fetches transaction fills from your portfolio."""
        endpoint = "/trade-api/v2/portfolio/fills"
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._get_json(endpoint, params=params)

    def get_settlements(self, limit: int = 100, cursor: str = None, ticker: str = None):
        """Fetches settlement records from your portfolio."""
        endpoint = "/trade-api/v2/portfolio/settlements"
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if ticker:
            params["ticker"] = ticker
        return self._get_json(endpoint, params=params)


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


def _parse_csv_list(value: str):
    columns = [item.strip() for item in value.split(",")]
    return [item for item in columns if item]


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


def _get_settlements_full_history(client: KalshiClient, limit: int):
    all_rows = []
    cursor = None
    pages_fetched = 0
    seen_cursors = set()

    while True:
        page = client.get_settlements(limit=limit, cursor=cursor)
        pages_fetched += 1
        settlements = page.get("settlements", []) if isinstance(page, dict) else []
        if settlements:
            all_rows.extend(settlements)

        next_cursor = page.get("cursor") if isinstance(page, dict) else None
        if not next_cursor:
            break
        if next_cursor in seen_cursors:
            raise KalshiClientError(
                f"Settlement pagination cursor repeated ('{next_cursor}'); stopping to avoid infinite loop."
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return {
        "settlements": all_rows,
        "pages_fetched": pages_fetched,
        "total_rows": len(all_rows),
    }


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Kalshi portfolio fills and render output as JSON, table, or reconciliation-only summary."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 ./kalshi.py --api-key-id YOUR_KEY --private-key-path ./kalshi-key.txt --limit 50 --output-format table\n"
            "  python3 ./kalshi.py --output-format reconciliation --starting-cash 100\n"
            "  python3 ./kalshi.py --full-history --limit 200 --output-format table --debug\n"
            "  python3 ./kalshi.py --output-format table --columns created_time,market_ticker,action,side,count_fp,price_fixed\n"
            "  python3 ./kalshi.py --output-format table --all-columns\n"
            "  python3 ./kalshi.py --output-format table --starting-cash 100 --enable-cache\n"
            "  python3 ./kalshi.py --output-format table  # auto-uses cache if ./.kalshi_cache.json exists\n"
            "  python3 ./kalshi.py --output-format table --enable-cache --force-refresh\n"
            "  python3 ./kalshi.py  # no --output-format set anywhere: reconciliation-only output\n"
            "\n"
            "Override precedence:\n"
            "  1) CLI args\n"
            "  2) Environment variables\n"
            "  3) Top-of-file constants\n"
        ),
    )
    parser.add_argument(
        "--api-key-id",
        help=(
            "Kalshi API key ID.\n"
            "Overrides KALSHI_API_KEY_ID and top-of-file KALSHI_API_KEY_ID."
        ),
    )
    parser.add_argument(
        "--private-key-path",
        help=(
            "Path to Kalshi RSA private key PEM file.\n"
            "Overrides KALSHI_PRIVATE_KEY_PATH and top-of-file KALSHI_PRIVATE_KEY_PATH."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        help=(
            "HTTP request timeout (seconds).\n"
            "Overrides KALSHI_TIMEOUT_SECONDS and top-of-file KALSHI_TIMEOUT_SECONDS."
        ),
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "table", "reconciliation"],
        help=(
            "Output format: 'json', 'table', or 'reconciliation'.\n"
            "If omitted and no env/default override is set, script prints reconciliation only.\n"
            "Overrides KALSHI_OUTPUT_FORMAT and top-of-file KALSHI_OUTPUT_FORMAT."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help=(
            "Rows per API page (positive integer).\n"
            "Used per page, including when --full-history is enabled.\n"
            "Overrides KALSHI_PAGE_LIMIT and top-of-file KALSHI_PAGE_LIMIT."
        ),
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help=(
            "Fetch all pages using cursor pagination until no next cursor is returned.\n"
            "If omitted, fetches a single page.\n"
            "Overrides KALSHI_FULL_HISTORY."
        ),
    )
    parser.add_argument(
        "--debug",
        dest="debug_appendix",
        action="store_true",
        help=(
            "Print per-market_ticker reconciliation debug details in table/reconciliation modes.\n"
            "Overrides KALSHI_DEBUG_APPENDIX."
        ),
    )
    parser.add_argument(
        "--starting-cash",
        type=float,
        help=(
            "Starting cash in dollars for P/L reconciliation.\n"
            "Overrides KALSHI_STARTING_CASH."
        ),
    )
    parser.add_argument(
        "--enable-cache",
        action="store_true",
        help=(
            "Enable local cache persistence (starting cash + fetched trade JSON).\n"
            "Cache read is automatic when cache file exists, even without this flag.\n"
            "Overrides KALSHI_ENABLE_CACHE."
        ),
    )
    parser.add_argument(
        "--use-cached-starting-cash",
        action="store_true",
        help=(
            "Explicitly prefer cached starting cash when --starting-cash is not provided.\n"
            "Note: cached starting cash is auto-used when available.\n"
            "Overrides KALSHI_USE_CACHED_STARTING_CASH."
        ),
    )
    parser.add_argument(
        "--cache-file",
        help=(
            "Path to local cache file for starting cash and fetched trade JSON.\n"
            "Overrides KALSHI_CACHE_FILE.\n"
            "Default: ./.kalshi_cache.json"
        ),
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help=(
            "Ignore cached trade JSON and force a full API refresh.\n"
            "Overrides KALSHI_FORCE_REFRESH."
        ),
    )
    table_view_group = parser.add_mutually_exclusive_group()
    table_view_group.add_argument(
        "--columns",
        help=(
            "Comma-separated table columns to display.\n"
            "Example: --columns created_time,market_ticker,action,side,count_fp,price_fixed"
        ),
    )
    table_view_group.add_argument(
        "--all-columns",
        action="store_true",
        help="Show all available raw table columns instead of the curated default set.",
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


def _resolve_output_format(args) -> str:
    output_format = args.output_format
    if output_format is None:
        output_format = os.getenv("KALSHI_OUTPUT_FORMAT")
    if output_format is None:
        output_format = KALSHI_OUTPUT_FORMAT
    if output_format is None:
        output_format = "reconciliation"
    return output_format


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


def _read_json_file(path: str):
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        return None
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise KalshiClientError(f"Failed to read cache file '{resolved}': {exc}") from exc


def _write_json_file(path: str, payload):
    resolved = os.path.expanduser(path)
    parent = os.path.dirname(resolved)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    try:
        with open(resolved, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
    except Exception as exc:
        raise KalshiClientError(f"Failed to write cache file '{resolved}': {exc}") from exc


def _resolve_cache_settings(args):
    cache_file = args.cache_file or os.getenv("KALSHI_CACHE_FILE") or KALSHI_CACHE_FILE
    cache_file = os.path.expanduser(cache_file)

    if args.enable_cache:
        enable_cache = True
    else:
        env_flag = os.getenv("KALSHI_ENABLE_CACHE")
        if env_flag is None:
            # Default behavior: if cache file is present, use cache without requiring flags.
            enable_cache = bool(KALSHI_ENABLE_CACHE) or os.path.exists(cache_file)
        else:
            enable_cache = _parse_bool(env_flag)

    if args.force_refresh:
        force_refresh = True
    else:
        env_flag = os.getenv("KALSHI_FORCE_REFRESH")
        if env_flag is None:
            force_refresh = KALSHI_FORCE_REFRESH
        else:
            force_refresh = _parse_bool(env_flag)

    # Force refresh should always update local cache artifacts.
    if force_refresh:
        enable_cache = True

    return enable_cache, force_refresh, cache_file


def _resolve_starting_cash(args, cache_doc=None):
    starting_cash = args.starting_cash
    starting_cash_source = None
    if starting_cash is not None:
        starting_cash_source = "cli"
    else:
        env_starting_cash = os.getenv("KALSHI_STARTING_CASH")
        if env_starting_cash is not None:
            try:
                starting_cash = float(env_starting_cash)
                starting_cash_source = "env"
            except ValueError as exc:
                raise KalshiClientError(
                    f"Invalid KALSHI_STARTING_CASH value '{env_starting_cash}'. Expected a number."
                ) from exc
        elif KALSHI_STARTING_CASH is not None:
            starting_cash = float(KALSHI_STARTING_CASH)
            starting_cash_source = "default"

    if args.use_cached_starting_cash:
        use_cached = True
    else:
        cached_flag = os.getenv("KALSHI_USE_CACHED_STARTING_CASH")
        if cached_flag is None:
            # Default behavior: if cache has starting cash, use it automatically.
            cache_has_starting_cash = (
                isinstance(cache_doc, dict) and _to_float(cache_doc.get("starting_cash")) is not None
            )
            use_cached = bool(KALSHI_USE_CACHED_STARTING_CASH) or cache_has_starting_cash
        else:
            use_cached = _parse_bool(cached_flag)

    if starting_cash is None and use_cached and isinstance(cache_doc, dict):
        cached_value = _to_float(cache_doc.get("starting_cash"))
        if cached_value is not None:
            starting_cash = cached_value
            starting_cash_source = "cache"

    return starting_cash, starting_cash_source


def _cache_trade_data(cache_doc, fills_data, settlements_rows, balance_snapshot, full_history, limit):
    if not isinstance(cache_doc, dict):
        cache_doc = {}
    cache_doc["trades_cache"] = {
        "fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "full_history": bool(full_history),
        "limit": int(limit),
        "fills_data": fills_data,
        "settlements_rows": settlements_rows,
        "balance_snapshot": balance_snapshot,
    }
    return cache_doc


def _load_cached_trade_data(cache_doc, full_history, limit, allow_any=False):
    if not isinstance(cache_doc, dict):
        return None
    trades_cache = cache_doc.get("trades_cache")
    if not isinstance(trades_cache, dict):
        return None
    if not allow_any:
        if bool(trades_cache.get("full_history")) != bool(full_history):
            return None
        cached_limit = _to_float(trades_cache.get("limit"))
        if cached_limit is None or int(cached_limit) != int(limit):
            return None
    if "fills_data" not in trades_cache:
        return None
    return trades_cache


def _get_display_price_fields(row):
    side = str(row.get("side", "")).strip().lower()
    if side == "yes":
        return row.get("yes_price_fixed"), row.get("yes_price_dollars")
    if side == "no":
        return row.get("no_price_fixed"), row.get("no_price_dollars")
    return None, None


def _prepare_table_rows(rows):
    prepared_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        prepared_row = dict(row)
        price_fixed, price_dollars = _get_display_price_fields(row)
        prepared_row["price_fixed"] = price_fixed
        prepared_row["price_dollars"] = price_dollars

        count = _to_float(row.get("count_fp"))
        price_fixed_float = _to_float(price_fixed)
        if count is not None and price_fixed_float is not None:
            prepared_row["trade_value_dollars"] = round(count * price_fixed_float, 4)
        else:
            prepared_row["trade_value_dollars"] = None
        prepared_rows.append(prepared_row)
    return prepared_rows


def _resolve_table_columns(rows, requested_columns=None, show_all_columns=False):
    available_columns = collect_columns(rows)
    if show_all_columns:
        return available_columns

    if requested_columns:
        unknown_columns = [column for column in requested_columns if column not in available_columns]
        if unknown_columns:
            available_columns_text = ", ".join(available_columns)
            unknown_columns_text = ", ".join(unknown_columns)
            raise KalshiClientError(
                f"Unknown table columns: {unknown_columns_text}. "
                f"Available columns: {available_columns_text}"
            )
        return requested_columns

    default_columns = [
        column for column in KALSHI_DEFAULT_TABLE_COLUMNS if column in available_columns
    ]
    if default_columns:
        return default_columns
    return available_columns


def _compute_table_appendix(rows, settlements=None):
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

        key = ticker
        bucket = grouped.get(key)
        if bucket is None:
            bucket = {
                "ticker": ticker,
                "sides_seen": set(),
                "buy_count": 0,
                "sell_count": 0,
                "wagered": 0.0,
                "fees": 0.0,
                "open_lots": [],
                "closed_pnl": 0.0,
                "matched_qty": 0.0,
                "unmatched_sell_qty": 0.0,
                "settlement_qty": 0.0,
                "settlement_closed_pnl": 0.0,
                "unmatched_settlement_qty": 0.0,
            }
            grouped[key] = bucket

        bucket["sides_seen"].add(side)
        bucket["wagered"] += abs(wager)
        bucket["fees"] += fee

        if action == "buy":
            bucket["buy_count"] += 1
            # FIFO lot: quantity, entry unit cost (including proportional fee), entry price (ex-fee).
            entry_unit_cost = (wager + fee) / count
            bucket["open_lots"].append([count, entry_unit_cost, price])
            continue

        # action == sell: close existing lots in FIFO order for this market_ticker.
        bucket["sell_count"] += 1
        sell_remaining = count
        exit_unit_proceeds = (wager - fee) / count

        while sell_remaining > 0 and bucket["open_lots"]:
            lot_qty, lot_entry_unit_cost, lot_entry_price = bucket["open_lots"][0]
            matched_qty = min(sell_remaining, lot_qty)
            bucket["closed_pnl"] += matched_qty * (exit_unit_proceeds - lot_entry_unit_cost)
            bucket["matched_qty"] += matched_qty

            lot_qty -= matched_qty
            sell_remaining -= matched_qty
            if lot_qty <= 1e-12:
                bucket["open_lots"].pop(0)
            else:
                bucket["open_lots"][0][0] = lot_qty
        if sell_remaining > 1e-12:
            # Keep visibility into sells that could not be matched to prior buys.
            bucket["unmatched_sell_qty"] += sell_remaining

    settlements_by_ticker = {}
    if settlements:
        for settlement in settlements:
            if not isinstance(settlement, dict):
                continue
            ticker = str(settlement.get("ticker", "")).strip()
            if not ticker or ticker not in grouped:
                continue
            settlements_by_ticker.setdefault(ticker, []).append(settlement)

    for ticker, bucket in grouped.items():
        for settlement in settlements_by_ticker.get(ticker, []):
            yes_count = _to_float(settlement.get("yes_count_fp")) or 0.0
            no_count = _to_float(settlement.get("no_count_fp")) or 0.0
            settled_qty = yes_count + no_count
            yes_cost = _to_float(settlement.get("yes_total_cost_dollars")) or 0.0
            no_cost = _to_float(settlement.get("no_total_cost_dollars")) or 0.0
            settlement_fee = _to_float(settlement.get("fee_cost")) or 0.0
            revenue = _to_float(settlement.get("revenue")) or 0.0

            # `revenue` is commonly returned in cents. Detect and normalize to dollars.
            if settled_qty > 0 and revenue / settled_qty > 1.5:
                revenue = revenue / 100.0
            elif revenue > 100 and revenue > (yes_cost + no_cost + settlement_fee) * 10:
                revenue = revenue / 100.0

            settlement_closed_pnl = revenue - (yes_cost + no_cost + settlement_fee)
            bucket["settlement_closed_pnl"] += settlement_closed_pnl
            bucket["settlement_qty"] += settled_qty

            remaining_to_close = settled_qty
            while remaining_to_close > 1e-12 and bucket["open_lots"]:
                lot_qty, lot_entry_unit_cost, lot_entry_price = bucket["open_lots"][0]
                consumed_qty = min(remaining_to_close, lot_qty)
                lot_qty -= consumed_qty
                remaining_to_close -= consumed_qty
                if lot_qty <= 1e-12:
                    bucket["open_lots"].pop(0)
                else:
                    bucket["open_lots"][0][0] = lot_qty
            if remaining_to_close > 1e-12:
                bucket["unmatched_settlement_qty"] += remaining_to_close

    debug_rows = []
    for bucket in grouped.values():
        total_bucket_closed_pnl = bucket["closed_pnl"] + bucket["settlement_closed_pnl"]
        # Count wins/losses only for matched round-trips.
        if bucket["matched_qty"] > 0 or bucket["settlement_qty"] > 0:
            if total_bucket_closed_pnl > 0:
                total_trades_won += 1
            elif total_bucket_closed_pnl < 0:
                total_trades_loss += 1
        total_closed_profit_loss += total_bucket_closed_pnl

        open_notional = 0.0
        for qty, _entry_unit_cost, entry_price in bucket["open_lots"]:
            open_notional += qty * entry_price
        total_open_notional += open_notional

        status = "open"
        if bucket["matched_qty"] > 0 or bucket["settlement_qty"] > 0:
            if total_bucket_closed_pnl > 0:
                status = "won"
            elif total_bucket_closed_pnl < 0:
                status = "loss"
            else:
                status = "breakeven"
        if bucket["unmatched_sell_qty"] > 1e-12:
            status = f"{status}+unmatched_sells"
        if bucket["unmatched_settlement_qty"] > 1e-12:
            status = f"{status}+unmatched_settlement"

        debug_rows.append(
            {
                "market_ticker": bucket["ticker"],
                "sides_seen": ",".join(sorted(bucket["sides_seen"])),
                "buy_count": bucket["buy_count"],
                "sell_count": bucket["sell_count"],
                "wagered": bucket["wagered"],
                "fees": bucket["fees"],
                "closed_pnl": bucket["closed_pnl"],
                "settlement_closed_pnl": bucket["settlement_closed_pnl"],
                "open_notional": open_notional,
                "matched_qty": bucket["matched_qty"],
                "unmatched_sell_qty": bucket["unmatched_sell_qty"],
                "settlement_qty": bucket["settlement_qty"],
                "unmatched_settlement_qty": bucket["unmatched_settlement_qty"],
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
        "debug_rows": sorted(debug_rows, key=lambda x: x["market_ticker"]),
    }


def _extract_balance_snapshot(client: KalshiClient):
    payload = client._get_json("/trade-api/v2/portfolio/balance")
    balance_cents = payload.get("balance")
    portfolio_cents = payload.get("portfolio_value")
    if balance_cents is None or portfolio_cents is None:
        raise KalshiClientError(
            "Balance endpoint response missing expected fields: 'balance' and/or 'portfolio_value'."
        )
    return {
        "ending_cash": float(balance_cents) / 100.0,
        "portfolio_value": float(portfolio_cents) / 100.0,
        "updated_ts": payload.get("updated_ts"),
    }


def _print_reconciliation(
    summary,
    balance_snapshot,
    starting_cash=None,
    starting_cash_source=None,
    debug_appendix: bool = False,
):
    if not balance_snapshot:
        return

    ending_cash = balance_snapshot["ending_cash"]
    portfolio_value = balance_snapshot["portfolio_value"]
    open_market_value = portfolio_value - ending_cash
    open_notional = summary["total_open_notional"]
    estimated_unrealized = open_market_value - open_notional
    estimated_total_profit_loss = summary["total_closed_profit_loss"] + estimated_unrealized

    print("")
    print("Reconciliation")
    if starting_cash is None:
        print("Starting Cash: N/A (set --starting-cash or use --use-cached-starting-cash)")
    else:
        source_text = f" [{starting_cash_source}]" if starting_cash_source else ""
        print(f"Starting Cash{source_text}: ${starting_cash:,.2f}")
    print(f"Ending Cash (Kalshi): ${ending_cash:,.2f}")
    print(f"Portfolio Value (Kalshi): ${portfolio_value:,.2f}")
    print(f"Open Market Value (Portfolio - Cash): ${open_market_value:,.2f}")
    print(f"Open Notional (Cost Basis): ${open_notional:,.2f}")
    print(f"Estimated Unrealized P/L: ${estimated_unrealized:,.2f}")
    print(f"Trades Won: {summary['total_trades_won']}")
    print(f"Trades Loss: {summary['total_trades_loss']}")
    print(f"Trades Percent Win/Loss: {summary['total_trades_percent_win_loss']}")
    print(f"Closed Profit/Loss: ${summary['total_closed_profit_loss']:,.2f}")
    print(f"Estimated Total Profit/Loss: ${estimated_total_profit_loss:,.2f}")
    if starting_cash is not None:
        net_vs_start = portfolio_value - starting_cash
        print(f"Net P/L vs Starting Cash: ${net_vs_start:,.2f}")
    if debug_appendix:
        print("")
        print("Reconciliation Debug (per market_ticker)")
        for row in summary["debug_rows"]:
            print(
                f"- {row['market_ticker']} [sides={row['sides_seen']}]: buys={row['buy_count']}, sells={row['sell_count']}, "
                f"wagered=${row['wagered']:,.2f}, fees=${row['fees']:,.2f}, "
                f"closed_p/l=${row['closed_pnl']:,.2f}, settlement_p/l=${row['settlement_closed_pnl']:,.2f}, "
                f"open_notional=${row['open_notional']:,.2f}, matched_qty={row['matched_qty']:.2f}, "
                f"settlement_qty={row['settlement_qty']:.2f}, unmatched_sell_qty={row['unmatched_sell_qty']:.2f}, "
                f"unmatched_settlement_qty={row['unmatched_settlement_qty']:.2f}, "
                f"status={row['status']}"
            )
def _print_fills_data(
    fills_data,
    output_format: str,
    debug_appendix: bool = False,
    settlements=None,
    balance_snapshot=None,
    starting_cash=None,
    starting_cash_source=None,
    table_columns=None,
    show_all_columns: bool = False,
):
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

    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        if output_format == "reconciliation":
            summary = _compute_table_appendix([], settlements=settlements)
            _print_reconciliation(
                summary,
                balance_snapshot=balance_snapshot,
                starting_cash=starting_cash,
                starting_cash_source=starting_cash_source,
                debug_appendix=debug_appendix,
            )
            return
        # Fallback when response shape is not tabular in table mode.
        print(json.dumps(fills_data, indent=2))
        return

    prepared_rows = _prepare_table_rows(rows)
    if output_format == "table":
        resolved_columns = _resolve_table_columns(
            prepared_rows,
            requested_columns=table_columns,
            show_all_columns=show_all_columns,
        )
        render_table(prepared_rows, columns=resolved_columns)

    summary = _compute_table_appendix(rows, settlements=settlements)
    _print_reconciliation(
        summary,
        balance_snapshot=balance_snapshot,
        starting_cash=starting_cash,
        starting_cash_source=starting_cash_source,
        debug_appendix=debug_appendix,
    )


# --- Example Execution ---
if __name__ == "__main__":
    # Override order:
    #   1) CLI args (--api-key-id, --private-key-path, --timeout-seconds, --output-format, --limit, --full-history, --debug, --starting-cash, --enable-cache, --use-cached-starting-cash, --cache-file, --force-refresh, --columns, --all-columns)
    #   2) Environment variables (KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH, KALSHI_TIMEOUT_SECONDS, KALSHI_OUTPUT_FORMAT, KALSHI_PAGE_LIMIT, KALSHI_FULL_HISTORY, KALSHI_DEBUG_APPENDIX, KALSHI_STARTING_CASH, KALSHI_USE_CACHED_STARTING_CASH, KALSHI_ENABLE_CACHE, KALSHI_CACHE_FILE, KALSHI_FORCE_REFRESH)
    #   3) Module constants at the top of this file
    try:
        args = _parse_args()
        enable_cache, force_refresh, cache_file = _resolve_cache_settings(args)
        cache_doc = _read_json_file(cache_file) if enable_cache else None
        if cache_doc is None:
            cache_doc = {}

        api_key_id = args.api_key_id or os.getenv("KALSHI_API_KEY_ID", KALSHI_API_KEY_ID)
        private_key_path = _resolve_private_key_path(args)
        timeout_seconds = args.timeout_seconds
        if timeout_seconds is None:
            timeout_seconds = float(os.getenv("KALSHI_TIMEOUT_SECONDS", str(KALSHI_TIMEOUT_SECONDS)))
        output_format = _resolve_output_format(args)
        if output_format not in {"json", "table", "reconciliation"}:
            raise KalshiClientError(
                f"Invalid output format '{output_format}'. Use 'json', 'table', or 'reconciliation'."
            )
        table_columns = _parse_csv_list(args.columns) if args.columns else None
        if args.columns and not table_columns:
            raise KalshiClientError("--columns must include at least one column name.")
        if output_format != "table" and (table_columns or args.all_columns):
            raise KalshiClientError(
                "--columns and --all-columns can only be used with --output-format table."
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
        starting_cash, starting_cash_source = _resolve_starting_cash(args, cache_doc=cache_doc)
        if enable_cache and args.starting_cash is not None:
            cache_doc["starting_cash"] = starting_cash
            cache_doc["starting_cash_updated_at_utc"] = (
                datetime.datetime.now(datetime.timezone.utc).isoformat()
            )
            _write_json_file(cache_file, cache_doc)

        client = KalshiClient(api_key_id, private_key_path, timeout_seconds=timeout_seconds)
        settlements_rows = None
        balance_snapshot = None
        cached_trades = None
        if enable_cache and not force_refresh:
            cached_trades = _load_cached_trade_data(cache_doc, full_history=full_history, limit=limit)
            if cached_trades is None:
                cached_trades = _load_cached_trade_data(
                    cache_doc,
                    full_history=full_history,
                    limit=limit,
                    allow_any=True,
                )

        if cached_trades is not None:
            fills_data = cached_trades.get("fills_data")
            settlements_rows = cached_trades.get("settlements_rows")
            balance_snapshot = cached_trades.get("balance_snapshot")
        else:
            if full_history:
                fills_data = _get_fills_full_history(client, limit=limit)
            else:
                fills_data = client.get_fills(limit=limit)
            if output_format in {"table", "reconciliation"}:
                settlements_data = _get_settlements_full_history(client, limit=200)
                all_settlements = settlements_data.get("settlements", [])
                balance_snapshot = _extract_balance_snapshot(client)
                rows_for_filter, _rows_key = _extract_rows(fills_data)
                tickers_in_rows = set()
                if isinstance(rows_for_filter, list):
                    tickers_in_rows = {
                        str(row.get("market_ticker", "")).strip()
                        for row in rows_for_filter
                        if isinstance(row, dict) and row.get("market_ticker")
                    }
                settlements_rows = [
                    settlement
                    for settlement in all_settlements
                    if str(settlement.get("ticker", "")).strip() in tickers_in_rows
                ]
            if enable_cache:
                cache_doc = _cache_trade_data(
                    cache_doc,
                    fills_data=fills_data,
                    settlements_rows=settlements_rows,
                    balance_snapshot=balance_snapshot,
                    full_history=full_history,
                    limit=limit,
                )
                _write_json_file(cache_file, cache_doc)
        # If loaded from cache and reconciliation output is requested,
        # ensure required reconciliation artifacts exist.
        if output_format in {"table", "reconciliation"} and (
            settlements_rows is None or balance_snapshot is None
        ):
            settlements_data = _get_settlements_full_history(client, limit=200)
            all_settlements = settlements_data.get("settlements", [])
            balance_snapshot = _extract_balance_snapshot(client)
            rows_for_filter, _rows_key = _extract_rows(fills_data)
            tickers_in_rows = set()
            if isinstance(rows_for_filter, list):
                tickers_in_rows = {
                    str(row.get("market_ticker", "")).strip()
                    for row in rows_for_filter
                    if isinstance(row, dict) and row.get("market_ticker")
                }
            settlements_rows = [
                settlement
                for settlement in all_settlements
                if str(settlement.get("ticker", "")).strip() in tickers_in_rows
            ]
            if enable_cache:
                cache_doc = _cache_trade_data(
                    cache_doc,
                    fills_data=fills_data,
                    settlements_rows=settlements_rows,
                    balance_snapshot=balance_snapshot,
                    full_history=full_history,
                    limit=limit,
                )
                _write_json_file(cache_file, cache_doc)
        _print_fills_data(
            fills_data,
            output_format,
            debug_appendix=debug_appendix,
            settlements=settlements_rows,
            balance_snapshot=balance_snapshot,
            starting_cash=starting_cash,
            starting_cash_source=starting_cash_source,
            table_columns=table_columns,
            show_all_columns=args.all_columns,
        )
    except KalshiClientError as exc:
        print(f"Kalshi client error: {exc}")
