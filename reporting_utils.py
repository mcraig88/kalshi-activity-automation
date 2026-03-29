import json


def value_to_string(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def collect_columns(rows):
    columns = []
    for row in rows:
        if isinstance(row, dict):
            for key in row.keys():
                if key not in columns:
                    columns.append(key)
    return columns


def render_table(rows, columns=None, formatters=None):
    if not rows:
        print("No rows to display.")
        return

    if columns is None:
        columns = collect_columns(rows)
    if formatters is None:
        formatters = {}

    if not columns:
        print("No tabular fields to display.")
        return

    widths = {column: len(column) for column in columns}
    for row in rows:
        for column in columns:
            raw_value = row.get(column, "") if isinstance(row, dict) else ""
            formatter = formatters.get(column)
            if formatter is not None:
                value = formatter(raw_value)
            else:
                value = value_to_string(raw_value)
            widths[column] = max(widths[column], len(value))

    header = " | ".join(column.ljust(widths[column]) for column in columns)
    divider = "-+-".join("-" * widths[column] for column in columns)
    print(header)
    print(divider)
    for row in rows:
        line = " | ".join(
            (
                formatters[column](row.get(column, "") if isinstance(row, dict) else "")
                if column in formatters
                else value_to_string(row.get(column, "") if isinstance(row, dict) else "")
            ).ljust(widths[column])
            for column in columns
        )
        print(line)


def format_money(value: float) -> str:
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def build_closed_contract_summary(rows, *, pnl_key, costs_key, proceeds_key, fees_key):
    total_costs = 0.0
    total_proceeds = 0.0
    total_fees = 0.0
    total_profit_and_loss = 0.0
    wins = 0
    losses = 0

    for row in rows:
        pnl = float(row.get(pnl_key, 0.0) or 0.0)
        costs = float(row.get(costs_key, 0.0) or 0.0)
        proceeds = float(row.get(proceeds_key, 0.0) or 0.0)
        fees = float(row.get(fees_key, 0.0) or 0.0)

        total_costs += costs
        total_proceeds += proceeds
        total_fees += fees
        total_profit_and_loss += pnl
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1

    total_closed = wins + losses
    if total_closed > 0:
        win_pct = (wins / total_closed) * 100.0
        loss_pct = (losses / total_closed) * 100.0
        win_loss_text = f"{win_pct:.2f}% / {loss_pct:.2f}%"
    else:
        win_loss_text = "N/A"

    return {
        "contracts_closed": len(rows),
        "winning_contracts": wins,
        "losing_contracts": losses,
        "win_loss_text": win_loss_text,
        "total_costs": total_costs,
        "total_proceeds": total_proceeds,
        "total_fees_and_commissions": total_fees,
        "total_profit_and_loss": total_profit_and_loss,
    }


def print_closed_contract_summary(summary, *, title="Closed Contract Summary"):
    print("")
    print(title)
    print(f"Contracts Closed: {summary['contracts_closed']}")
    print(f"Winning Contracts: {summary['winning_contracts']}")
    print(f"Losing Contracts: {summary['losing_contracts']}")
    print(f"Win/Loss %: {summary['win_loss_text']}")
    print(f"Total Costs: {format_money(summary['total_costs'])}")
    print(f"Total Proceeds: {format_money(summary['total_proceeds'])}")
    print(f"Total Fees and Commissions: {format_money(summary['total_fees_and_commissions'])}")
    print(f"Total Profit/Loss: {format_money(summary['total_profit_and_loss'])}")
