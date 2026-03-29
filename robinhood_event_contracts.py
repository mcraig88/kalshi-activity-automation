import argparse
import csv
import json
import os
import re
import subprocess

from reporting_utils import (
    build_closed_contract_summary,
    print_closed_contract_summary,
    render_table,
)


ROBINHOOD_SUPPORTED_HEADERS = {
    "event contract traded": "event_contract_traded",
    "closing date": "closing_date",
    "total costs": "total_costs",
    "total proceeds": "total_proceeds",
    "total fees and commissions": "total_fees_and_commissions",
    "profit and loss": "profit_and_loss",
    "profits and loss": "profit_and_loss",
    "profits and losses": "profit_and_loss",
}

ROBINHOOD_REQUIRED_FIELDS = (
    "event_contract_traded",
    "closing_date",
    "total_costs",
    "total_proceeds",
    "total_fees_and_commissions",
    "profit_and_loss",
)

MONTHLY_SUMMARY_ROW_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s+"
    r"(\w+)\s+"
    r"([-0-9.]+)\s+"
    r"([-0-9.]+)\s+"
    r"(YES|NO)\s+"
    r"(\S+)\s+"
    r"(\w+)\s+"
    r"(\d{4}-\d{2}-\d{2})\s+"
    r"([-0-9.Ee]+)\s+"
    r"([A-Z]{3})\s+"
    r"(.*?)(?=(?:\d{4}-\d{2}-\d{2}\s+\w+\s+[-0-9.]+\s+[-0-9.]+\s+(?:YES|NO)\s+\S+\s+\w+\s+\d{4}-\d{2}-\d{2}\s+[-0-9.Ee]+\s+[A-Z]{3}\s)|$)"
)

DATE_TOKEN_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
JOURNAL_ENTRY_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+"
    r"(\w+)\s+"
    r"(.+?)\s+"
    r"([A-Z]{3})\s+"
    r"([-0-9.]+)$"
)


class RobinhoodEventContractsError(Exception):
    """Base exception for Robinhood event contracts reporting."""


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Parse Robinhood Event Contracts data from an annual statement CSV or a monthly derivatives PDF."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Supported inputs:\n"
            "  1. Annual statement CSV with columns like Event contract traded, Closing date,\n"
            "     Total costs, Total proceeds, Total fees and commissions, Profits and losses\n"
            "  2. Monthly Robinhood Derivatives PDF statements containing Purchase and Sale Summary\n"
            "\n"
            "Examples:\n"
            "  python3 ./robinhood_event_contracts.py --input-csv ./samples/robinhood_event_contracts_annual_statement_template.csv --output-format table\n"
            "  python3 ./robinhood_event_contracts.py --input-pdf ./_reference_files/sample_february_derivatives_events.pdf --output-format table\n"
            "  python3 ./robinhood_event_contracts.py --input-text ./tests/fixtures/robinhood_monthly_statement_sample.txt --output-format json\n"
        ),
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-csv",
        help="Path to a Robinhood event contracts CSV export or manually converted annual statement CSV.",
    )
    input_group.add_argument(
        "--input-pdf",
        nargs="+",
        help="Path to a Robinhood monthly derivatives/event contracts PDF statement.",
    )
    input_group.add_argument(
        "--input-text",
        nargs="+",
        help="Path to extracted statement text, useful for testing or debugging parser behavior.",
    )
    parser.add_argument(
        "--output-format",
        choices=["table", "json"],
        default="table",
        help="Render statement rows as a table or JSON. Default: table.",
    )
    return parser.parse_args()


def _normalize_header(value: str) -> str:
    text = " ".join(value.strip().lower().replace("_", " ").split())
    return ROBINHOOD_SUPPORTED_HEADERS.get(text, text.replace(" ", "_"))


def _parse_money(value):
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    normalized = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    try:
        amount = float(normalized)
    except ValueError as exc:
        raise RobinhoodEventContractsError(
            f"Invalid currency value '{value}'. Expected a dollar amount."
        ) from exc
    return -amount if negative else amount


def _read_csv_rows(path: str):
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        raise RobinhoodEventContractsError(f"CSV file not found: {resolved}")

    try:
        with open(resolved, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise RobinhoodEventContractsError("CSV file is missing a header row.")

            normalized_fieldnames = [_normalize_header(field) for field in reader.fieldnames]
            missing_fields = [
                field for field in ROBINHOOD_REQUIRED_FIELDS if field not in normalized_fieldnames
            ]
            if missing_fields:
                raise RobinhoodEventContractsError(
                    "CSV file is missing required columns: " + ", ".join(missing_fields)
                )

            rows = []
            for raw_row in reader:
                normalized_row = {}
                for original_key, value in raw_row.items():
                    normalized_key = _normalize_header(original_key)
                    normalized_row[normalized_key] = value.strip() if isinstance(value, str) else value

                row = {
                    "event_contract_traded": normalized_row.get("event_contract_traded", ""),
                    "closing_date": normalized_row.get("closing_date", ""),
                    "total_costs": _parse_money(normalized_row.get("total_costs")),
                    "total_proceeds": _parse_money(normalized_row.get("total_proceeds")),
                    "total_fees_and_commissions": _parse_money(
                        normalized_row.get("total_fees_and_commissions")
                    ),
                    "profit_and_loss": _parse_money(normalized_row.get("profit_and_loss")),
                }
                rows.append(row)
    except RobinhoodEventContractsError:
        raise
    except Exception as exc:
        raise RobinhoodEventContractsError(
            f"Failed to read Robinhood event contracts CSV '{resolved}': {exc}"
        ) from exc

    return rows


def _read_text_file(path: str):
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        raise RobinhoodEventContractsError(f"Statement text file not found: {resolved}")
    try:
        with open(resolved, "r", encoding="utf-8") as handle:
            return handle.read()
    except Exception as exc:
        raise RobinhoodEventContractsError(
            f"Failed to read statement text file '{resolved}': {exc}"
        ) from exc


def _swift_pdf_extractor_source(pdf_path: str) -> str:
    escaped_path = json.dumps(os.path.abspath(pdf_path))
    return (
        "import Foundation\n"
        "import PDFKit\n"
        f"let url = URL(fileURLWithPath: {escaped_path})\n"
        "guard let document = PDFDocument(url: url) else {\n"
        '    fputs("FAILED_TO_OPEN_PDF\\n", stderr)\n'
        "    exit(1)\n"
        "}\n"
        "for pageIndex in 0..<document.pageCount {\n"
        "    guard let page = document.page(at: pageIndex) else { continue }\n"
        '    print("--- PAGE \\(pageIndex + 1) ---")\n'
        "    if let text = page.string {\n"
        "        print(text)\n"
        "    }\n"
        "}\n"
    )


def _extract_pdf_text(path: str):
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        raise RobinhoodEventContractsError(f"PDF statement file not found: {resolved}")

    try:
        result = subprocess.run(
            ["swift", "-"],
            input=_swift_pdf_extractor_source(resolved),
            capture_output=True,
            text=True,
            check=True,
        )
        extracted = result.stdout.strip()
    except FileNotFoundError as exc:
        raise RobinhoodEventContractsError(
            "Swift is required to extract Robinhood PDF text on macOS, but 'swift' was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() or str(exc)
        raise RobinhoodEventContractsError(
            f"Failed to extract text from Robinhood PDF '{resolved}': {stderr}"
        ) from exc

    if not extracted:
        raise RobinhoodEventContractsError(
            f"Extracted empty text from Robinhood PDF '{resolved}'."
        )
    return extracted


def _extract_statement_metadata(text: str):
    metadata = {
        "statement_date": None,
        "client_name": None,
        "account_number": None,
    }
    statement_date_match = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2})", text)
    client_name_match = re.search(r"Client Name:\s*(.+)", text)
    account_match = re.search(r"RHD Account Number:\s*(\S+)", text)

    if statement_date_match:
        metadata["statement_date"] = statement_date_match.group(1).strip()
    if client_name_match:
        metadata["client_name"] = client_name_match.group(1).strip()
    if account_match:
        metadata["account_number"] = account_match.group(1).strip()
    return metadata


def _extract_section(text: str, section_title: str, next_titles):
    start_index = text.find(section_title)
    if start_index == -1:
        raise RobinhoodEventContractsError(f"Section '{section_title}' not found in statement text.")

    section_start = start_index + len(section_title)
    section_end = len(text)
    for next_title in next_titles:
        candidate = text.find(next_title, section_start)
        if candidate != -1:
            section_end = min(section_end, candidate)
    return text[section_start:section_end].strip()


def _normalize_section_text(text: str):
    normalized = text.replace("&amp;", "&")
    normalized = re.sub(r"--- PAGE \d+ ---", " ", normalized)
    normalized = re.sub(r"([A-Za-z0-9])-\s*\n\s*([A-Za-z0-9])", r"\1-\2", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _parse_float(value: str):
    text = value.strip()
    if text in {"", "0E-8", "0e-8"}:
        return 0.0
    try:
        return float(text)
    except ValueError as exc:
        raise RobinhoodEventContractsError(
            f"Invalid numeric value '{value}' in Robinhood monthly statement."
        ) from exc


def _parse_monthly_summary_rows(section_text: str):
    normalized = _normalize_section_text(section_text)
    header_text = (
        "Trade Date AT Total Qty Long Total Qty Short Subtype Symbol Month Contract Year "
        "Exchange Exp Date Gross P&L Currency Code Description"
    )
    if normalized.startswith(header_text):
        normalized = normalized[len(header_text) :].strip()

    rows = []
    for match in MONTHLY_SUMMARY_ROW_PATTERN.finditer(normalized):
        rows.append(
            {
                "trade_date": match.group(1),
                "asset_type": match.group(2),
                "total_qty_long": _parse_float(match.group(3)),
                "total_qty_short": _parse_float(match.group(4)),
                "subtype": match.group(5),
                "symbol": match.group(6),
                "exchange": match.group(7),
                "expiration_date": match.group(8),
                "gross_pnl": _parse_float(match.group(9)),
                "currency_code": match.group(10),
                "description": match.group(11).strip(),
            }
        )

    if not rows:
        raise RobinhoodEventContractsError(
            "No rows were parsed from Purchase and Sale Summary."
        )
    return rows


def _split_normalized_rows(text: str):
    starts = [match.start() for match in re.finditer(r"\d{4}-\d{2}-\d{2}\s+\w+\s+", text)]
    rows = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        row_text = text[start:end].strip()
        if row_text:
            rows.append(row_text)
    return rows


def _parse_trade_confirmation_summary_row(row_text: str):
    tokens = row_text.split()
    if len(tokens) < 10:
        raise RobinhoodEventContractsError(
            f"Trade Confirmation Summary row is too short to parse: '{row_text}'"
        )

    trade_date = tokens[0]
    asset_type = tokens[1]
    total_qty_long = _parse_float(tokens[2])
    total_qty_short = _parse_float(tokens[3])
    subtype = tokens[4]
    average_price = _parse_float(tokens[5])
    symbol = tokens[6]

    exp_index = None
    for index in range(len(tokens) - 1, 6, -1):
        if DATE_TOKEN_PATTERN.match(tokens[index]):
            exp_index = index
            break
    if exp_index is None or exp_index <= 7:
        raise RobinhoodEventContractsError(
            f"Trade Confirmation Summary row is missing an expiration date: '{row_text}'"
        )

    currency_code = tokens[-1]
    exchange = tokens[exp_index - 1]
    description_tokens = tokens[7 : exp_index - 1]
    fee_tokens = tokens[exp_index + 1 : -1]

    commission = 0.0
    exchange_fees = 0.0
    nfa_fees = 0.0
    total_fees = 0.0
    if len(fee_tokens) == 1:
        total_fees = abs(_parse_float(fee_tokens[0]))
    elif len(fee_tokens) >= 4:
        commission = abs(_parse_float(fee_tokens[0]))
        exchange_fees = abs(_parse_float(fee_tokens[1]))
        nfa_fees = abs(_parse_float(fee_tokens[2]))
        total_fees = abs(_parse_float(fee_tokens[3]))
    elif len(fee_tokens) > 1:
        total_fees = abs(_parse_float(fee_tokens[-1]))

    description = " ".join(description_tokens).strip()
    return {
        "trade_date": trade_date,
        "asset_type": asset_type,
        "total_qty_long": total_qty_long,
        "total_qty_short": total_qty_short,
        "subtype": subtype,
        "average_price": average_price,
        "symbol": symbol,
        "description": description,
        "exchange": exchange,
        "expiration_date": tokens[exp_index],
        "commission": commission,
        "exchange_fees": exchange_fees,
        "nfa_fees": nfa_fees,
        "total_fees_and_commissions": total_fees,
        "currency_code": currency_code,
    }


def _parse_trade_confirmation_summary_rows(section_text: str):
    normalized = _normalize_section_text(section_text)
    header_text = (
        "Trade Date AT Total Qty Long Total Qty Short Subtype Avg Long Avg Short "
        "Symbol Description Contract Year Month Exchange Exp Date Commission "
        "Exchange Fees NFA Fees Total Commissions and Fees Currency Code"
    )
    header_index = normalized.find(header_text)
    if header_index == -1:
        raise RobinhoodEventContractsError(
            "Trade Confirmation Summary header was not found in monthly statement text."
        )
    normalized = normalized[header_index + len(header_text) :].strip()

    rows = []
    for row_text in _split_normalized_rows(normalized):
        rows.append(_parse_trade_confirmation_summary_row(row_text))
    if not rows:
        raise RobinhoodEventContractsError(
            "No rows were parsed from Trade Confirmation Summary."
        )
    return rows


def _parse_journal_entries(section_text: str):
    entries = []
    for raw_line in section_text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line or line == "Date AT Description Currency Credit/Debit":
            continue
        match = JOURNAL_ENTRY_LINE_PATTERN.match(line)
        if not match:
            continue
        entries.append(
            {
                "date": match.group(1),
                "asset_type": match.group(2),
                "description": match.group(3).strip(),
                "currency_code": match.group(4),
                "amount": _parse_float(match.group(5)),
            }
        )
    return entries


def _combine_monthly_summary_rows(rows):
    grouped = {}
    order = []
    for row in rows:
        key = (
            row["symbol"],
            row["description"],
        )
        if key not in grouped:
            grouped[key] = {
                "trade_date": row["trade_date"],
                "closing_date": row["expiration_date"],
                "symbol": row["symbol"],
                "event_contract_traded": row["description"],
                "description": row["description"],
                "exchange": row["exchange"],
                "yes_contracts": 0.0,
                "no_contracts": 0.0,
                "total_costs": 0.0,
                "total_proceeds": 0.0,
                "total_fees_and_commissions": 0.0,
                "profit_and_loss": 0.0,
                "net_profit_after_fees": 0.0,
                "legs": [],
            }
            order.append(key)

        position = grouped[key]
        if row["subtype"] == "YES":
            position["yes_contracts"] += row["total_qty_long"]
        elif row["subtype"] == "NO":
            position["no_contracts"] += row["total_qty_long"]
        position["profit_and_loss"] += row["gross_pnl"]
        if row["gross_pnl"] < 0:
            position["total_costs"] += abs(row["gross_pnl"])
        elif row["gross_pnl"] > 0:
            position["total_proceeds"] += row["gross_pnl"]
        position["legs"].append(
            {
                "subtype": row["subtype"],
                "gross_pnl": row["gross_pnl"],
                "quantity": row["total_qty_long"],
            }
        )

    combined = [grouped[key] for key in order]
    combined.sort(key=lambda row: (row["closing_date"], row["symbol"], row["trade_date"]))
    return combined


def _attach_trade_confirmation_costs_and_fees(closed_positions, confirmation_rows):
    grouped_fees = {}
    for row in confirmation_rows:
        key = (
            row["symbol"],
            row["description"],
        )
        info = grouped_fees.setdefault(
            key,
            {
                "total_fees_and_commissions": 0.0,
                "trade_confirmation_rows": [],
            },
        )
        info["total_fees_and_commissions"] += row["total_fees_and_commissions"]
        info["trade_confirmation_rows"].append(row)

    for position in closed_positions:
        key = (
            position["symbol"],
            position["description"],
        )
        fee_info = grouped_fees.get(key, {})
        position["total_fees_and_commissions"] = fee_info.get(
            "total_fees_and_commissions", 0.0
        )
        position["net_profit_after_fees"] = (
            position["profit_and_loss"] - position["total_fees_and_commissions"]
        )
        if fee_info:
            position["trade_confirmation_rows"] = fee_info["trade_confirmation_rows"]
    return closed_positions


def _annotate_monthly_report(report):
    metadata = report["statement_metadata"]
    statement_date = metadata.get("statement_date")
    account_number = metadata.get("account_number")
    source_name = report["source_name"]

    for row in report["closed_positions"]:
        row["statement_date"] = statement_date
        row["account_number"] = account_number
        row["source_name"] = source_name
    for entry in report["journal_entries"]:
        entry["statement_date"] = statement_date
        entry["account_number"] = account_number
        entry["source_name"] = source_name
    return report


def _combine_monthly_reports(reports):
    combined_positions = []
    combined_journal_entries = []
    statement_metadata = []
    source_names = []

    for report in reports:
        source_names.append(report["source_name"])
        statement_metadata.append(report["statement_metadata"])
        combined_positions.extend(report["closed_positions"])
        combined_journal_entries.extend(report["journal_entries"])

    combined_positions.sort(
        key=lambda row: (
            row.get("statement_date") or "",
            row.get("closing_date") or "",
            row.get("symbol") or "",
        )
    )
    combined_journal_entries.sort(
        key=lambda row: (
            row.get("statement_date") or "",
            row.get("date") or "",
            row.get("description") or "",
        )
    )

    summary = build_closed_contract_summary(
        combined_positions,
        pnl_key="profit_and_loss",
        costs_key="total_costs",
        proceeds_key="total_proceeds",
        fees_key="total_fees_and_commissions",
    )
    net_profit_after_fees = sum(
        row.get("net_profit_after_fees", row.get("profit_and_loss", 0.0))
        for row in combined_positions
    )
    cash_activity_total = sum(entry["amount"] for entry in combined_journal_entries)
    return {
        "source_names": source_names,
        "statement_reports": reports,
        "statement_metadata": statement_metadata,
        "closed_positions": combined_positions,
        "journal_entries": combined_journal_entries,
        "summary": summary,
        "cash_activity_total": cash_activity_total,
        "net_profit_after_fees": net_profit_after_fees,
    }


def _build_monthly_statement_report(text: str, source_name: str = "<memory>"):
    metadata = _extract_statement_metadata(text)
    trade_confirmation_section = _extract_section(
        text,
        "Trade Confirmation Summary",
        ["Purchase and Sale"],
    )
    summary_section = _extract_section(
        text,
        "Purchase and Sale Summary",
        ["Journal Entries", "Open Positions", "Account Summary"],
    )
    journal_section = _extract_section(
        text,
        "Journal Entries",
        ["Open Positions", "Open Position Summary", "Margin Calls", "Account Summary"],
    )

    trade_confirmation_rows = _parse_trade_confirmation_summary_rows(trade_confirmation_section)
    raw_rows = _parse_monthly_summary_rows(summary_section)
    combined_rows = _combine_monthly_summary_rows(raw_rows)
    combined_rows = _attach_trade_confirmation_costs_and_fees(combined_rows, trade_confirmation_rows)
    journal_entries = _parse_journal_entries(journal_section)
    summary = build_closed_contract_summary(
        combined_rows,
        pnl_key="profit_and_loss",
        costs_key="total_costs",
        proceeds_key="total_proceeds",
        fees_key="total_fees_and_commissions",
    )

    cash_activity_total = sum(entry["amount"] for entry in journal_entries)
    report = {
        "source_name": source_name,
        "statement_metadata": metadata,
        "closed_positions": combined_rows,
        "trade_confirmation_summary_rows": trade_confirmation_rows,
        "raw_summary_rows": raw_rows,
        "journal_entries": journal_entries,
        "summary": summary,
        "cash_activity_total": cash_activity_total,
        "net_profit_after_fees": sum(
            row.get("net_profit_after_fees", row["profit_and_loss"]) for row in combined_rows
        ),
    }
    return _annotate_monthly_report(report)


def _summarize(rows):
    return build_closed_contract_summary(
        rows,
        pnl_key="profit_and_loss",
        costs_key="total_costs",
        proceeds_key="total_proceeds",
        fees_key="total_fees_and_commissions",
    )


def _print_table(rows):
    columns = [
        "closing_date",
        "event_contract_traded",
        "total_costs",
        "total_proceeds",
        "total_fees_and_commissions",
        "profit_and_loss",
    ]
    render_table(
        rows,
        columns=columns,
        formatters={
            "total_costs": lambda value: f"{float(value):,.2f}",
            "total_proceeds": lambda value: f"{float(value):,.2f}",
            "total_fees_and_commissions": lambda value: f"{float(value):,.2f}",
            "profit_and_loss": lambda value: f"{float(value):,.2f}",
        },
    )


def _print_monthly_positions_table(rows):
    columns = [
        "statement_date",
        "trade_date",
        "closing_date",
        "symbol",
        "event_contract_traded",
        "yes_contracts",
        "no_contracts",
        "total_costs",
        "total_proceeds",
        "total_fees_and_commissions",
        "profit_and_loss",
        "net_profit_after_fees",
    ]
    render_table(
        rows,
        columns=columns,
        formatters={
            "yes_contracts": lambda value: f"{float(value):,.2f}",
            "no_contracts": lambda value: f"{float(value):,.2f}",
            "total_costs": lambda value: f"{float(value):,.2f}",
            "total_proceeds": lambda value: f"{float(value):,.2f}",
            "total_fees_and_commissions": lambda value: f"{float(value):,.2f}",
            "profit_and_loss": lambda value: f"{float(value):,.2f}",
            "net_profit_after_fees": lambda value: f"{float(value):,.2f}",
        },
    )


def _print_journal_entries(entries):
    if not entries:
        return
    print("")
    print("Journal Entries")
    render_table(
        entries,
        columns=["date", "description", "currency_code", "amount"],
        formatters={"amount": lambda value: f"{float(value):,.2f}"},
    )


def _print_statement_metadata(metadata):
    print("Statement Metadata")
    print(f"Statement Date: {metadata.get('statement_date') or 'Unknown'}")
    print(f"Client Name: {metadata.get('client_name') or 'Unknown'}")
    print(f"Account Number: {metadata.get('account_number') or 'Unknown'}")


def _print_summary(summary):
    print_closed_contract_summary(summary, title="Robinhood Event Contracts Summary")


def _print_monthly_report(report):
    metadata = report["statement_metadata"]
    if isinstance(metadata, list):
        print("Statement Metadata")
        print(f"Statements Imported: {len(metadata)}")
        account_numbers = sorted(
            {item.get('account_number') for item in metadata if item.get('account_number')}
        )
        statement_dates = sorted(
            {item.get('statement_date') for item in metadata if item.get('statement_date')}
        )
        print(f"Accounts: {', '.join(account_numbers) if account_numbers else 'Unknown'}")
        if statement_dates:
            print(f"Statement Dates: {', '.join(statement_dates)}")
    else:
        _print_statement_metadata(metadata)
    print("")
    print("Closed Positions")
    _print_monthly_positions_table(report["closed_positions"])
    _print_summary(report["summary"])
    print(f"Net Profit/Loss After Fees: {report['net_profit_after_fees']:,.2f}")
    if report["journal_entries"]:
        _print_journal_entries(report["journal_entries"])
        print("")
        print(f"Net Cash Activity: {report['cash_activity_total']:,.2f}")


if __name__ == "__main__":
    try:
        args = _parse_args()
        if args.input_csv:
            rows = _read_csv_rows(args.input_csv)
            summary = _summarize(rows)
            if args.output_format == "json":
                print(json.dumps({"rows": rows, "summary": summary}, indent=2))
            else:
                _print_table(rows)
                _print_summary(summary)
        else:
            if args.input_pdf:
                reports = []
                for pdf_path in args.input_pdf:
                    statement_text = _extract_pdf_text(pdf_path)
                    source_name = os.path.expanduser(pdf_path)
                    reports.append(
                        _build_monthly_statement_report(statement_text, source_name=source_name)
                    )
            else:
                reports = []
                for text_path in args.input_text:
                    statement_text = _read_text_file(text_path)
                    source_name = os.path.expanduser(text_path)
                    reports.append(
                        _build_monthly_statement_report(statement_text, source_name=source_name)
                    )

            report = reports[0] if len(reports) == 1 else _combine_monthly_reports(reports)
            if args.output_format == "json":
                print(json.dumps(report, indent=2))
            else:
                _print_monthly_report(report)
    except RobinhoodEventContractsError as exc:
        print(f"Robinhood event contracts error: {exc}")
