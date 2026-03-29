import io
import unittest
from contextlib import redirect_stdout

from reporting_utils import (
    build_closed_contract_summary,
    format_money,
    print_closed_contract_summary,
    render_table,
)


class ReportingUtilsTests(unittest.TestCase):
    def test_build_closed_contract_summary_tracks_totals_and_win_loss_text(self):
        rows = [
            {
                "profit_and_loss": 10.0,
                "total_costs": 25.0,
                "total_proceeds": 40.0,
                "total_fees_and_commissions": 5.0,
            },
            {
                "profit_and_loss": -4.0,
                "total_costs": 12.0,
                "total_proceeds": 8.0,
                "total_fees_and_commissions": 1.0,
            },
        ]

        summary = build_closed_contract_summary(
            rows,
            pnl_key="profit_and_loss",
            costs_key="total_costs",
            proceeds_key="total_proceeds",
            fees_key="total_fees_and_commissions",
        )

        self.assertEqual(summary["contracts_closed"], 2)
        self.assertEqual(summary["winning_contracts"], 1)
        self.assertEqual(summary["losing_contracts"], 1)
        self.assertEqual(summary["win_loss_text"], "50.00% / 50.00%")
        self.assertEqual(summary["total_costs"], 37.0)
        self.assertEqual(summary["total_proceeds"], 48.0)
        self.assertEqual(summary["total_fees_and_commissions"], 6.0)
        self.assertEqual(summary["total_profit_and_loss"], 6.0)

    def test_format_money_formats_positive_and_negative_values(self):
        self.assertEqual(format_money(12.5), "$12.50")
        self.assertEqual(format_money(-3.25), "-$3.25")

    def test_render_table_supports_custom_formatters(self):
        rows = [{"name": "BTC", "profit": 12.5}]
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            render_table(
                rows,
                columns=["name", "profit"],
                formatters={"profit": lambda value: f"{float(value):,.2f}"},
            )

        output = buffer.getvalue()
        self.assertIn("name", output)
        self.assertIn("profit", output)
        self.assertIn("12.50", output)

    def test_print_closed_contract_summary_renders_standard_fields(self):
        summary = {
            "contracts_closed": 2,
            "winning_contracts": 1,
            "losing_contracts": 1,
            "win_loss_text": "50.00% / 50.00%",
            "total_costs": 205.0,
            "total_proceeds": 210.0,
            "total_fees_and_commissions": 6.0,
            "total_profit_and_loss": -1.0,
        }
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            print_closed_contract_summary(summary, title="Shared Summary")

        output = buffer.getvalue()
        self.assertIn("Shared Summary", output)
        self.assertIn("Contracts Closed: 2", output)
        self.assertIn("Win/Loss %: 50.00% / 50.00%", output)
        self.assertIn("Total Profit/Loss: -$1.00", output)


if __name__ == "__main__":
    unittest.main()
