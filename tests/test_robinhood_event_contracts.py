import os
import tempfile
import unittest

from robinhood_event_contracts import (
    RobinhoodEventContractsError,
    _build_monthly_statement_report,
    _combine_monthly_reports,
    _extract_statement_metadata,
    _read_csv_rows,
    _summarize,
)


class RobinhoodEventContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "robinhood_monthly_statement_sample.txt",
        )
        with open(fixture_path, "r", encoding="utf-8") as handle:
            cls.monthly_statement_text = handle.read()

    def test_read_csv_rows_normalizes_statement_columns(self):
        csv_text = (
            "Event contract traded,Closing date,Total costs,Total proceeds,"
            "Total fees and commissions,Profits and losses\n"
            "BTC above 100000,2026-12-31,$125.00,$210.00,$4.00,$81.00\n"
            "Election result,2026-11-04,$80.00,$0.00,$2.00,($82.00)\n"
        )

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write(csv_text)
            path = handle.name

        try:
            rows = _read_csv_rows(path)
        finally:
            os.unlink(path)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event_contract_traded"], "BTC above 100000")
        self.assertEqual(rows[0]["total_costs"], 125.0)
        self.assertEqual(rows[1]["profit_and_loss"], -82.0)

    def test_read_csv_rows_requires_expected_columns(self):
        csv_text = "Event contract traded,Closing date,Total costs\nExample,2026-12-31,$10.00\n"

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write(csv_text)
            path = handle.name

        try:
            with self.assertRaises(RobinhoodEventContractsError):
                _read_csv_rows(path)
        finally:
            os.unlink(path)

    def test_summarize_uses_shared_closed_contract_shape(self):
        rows = [
            {
                "event_contract_traded": "A",
                "closing_date": "2026-01-01",
                "total_costs": 50.0,
                "total_proceeds": 75.0,
                "total_fees_and_commissions": 2.0,
                "profit_and_loss": 23.0,
            },
            {
                "event_contract_traded": "B",
                "closing_date": "2026-01-02",
                "total_costs": 20.0,
                "total_proceeds": 0.0,
                "total_fees_and_commissions": 1.0,
                "profit_and_loss": -21.0,
            },
        ]

        summary = _summarize(rows)

        self.assertEqual(summary["contracts_closed"], 2)
        self.assertEqual(summary["winning_contracts"], 1)
        self.assertEqual(summary["losing_contracts"], 1)
        self.assertEqual(summary["win_loss_text"], "50.00% / 50.00%")
        self.assertEqual(summary["total_profit_and_loss"], 2.0)

    def test_extract_statement_metadata_from_monthly_statement_text(self):
        metadata = _extract_statement_metadata(self.monthly_statement_text)

        self.assertEqual(metadata["statement_date"], "2026-02-28")
        self.assertEqual(metadata["client_name"], "Doe, Jordan")
        self.assertEqual(metadata["account_number"], "RH0000000000")

    def test_build_monthly_statement_report_parses_positions_and_cash_activity(self):
        report = _build_monthly_statement_report(
            self.monthly_statement_text,
            source_name="sample_february_derivatives_events.pdf",
        )

        self.assertEqual(report["statement_metadata"]["account_number"], "RH0000000000")
        self.assertEqual(len(report["trade_confirmation_summary_rows"]), 6)
        self.assertEqual(len(report["raw_summary_rows"]), 6)
        self.assertEqual(len(report["closed_positions"]), 3)
        self.assertEqual(len(report["journal_entries"]), 3)
        self.assertAlmostEqual(report["cash_activity_total"], -3.47)
        self.assertAlmostEqual(report["net_profit_after_fees"], 3.47)

        first_position = report["closed_positions"][0]
        self.assertEqual(first_position["symbol"], "KXNFLPREPACK1HFT-26FEB08SEANE-NE1HSEAFT")
        self.assertEqual(first_position["event_contract_traded"], "NE wins 1H & SEA wins game")
        self.assertAlmostEqual(first_position["profit_and_loss"], -0.84)
        self.assertAlmostEqual(first_position["total_costs"], 0.84)
        self.assertAlmostEqual(first_position["total_proceeds"], 0.0)
        self.assertAlmostEqual(first_position["total_fees_and_commissions"], 0.12)
        self.assertAlmostEqual(first_position["net_profit_after_fees"], -0.96)

        winning_symbols = {
            row["symbol"]: row for row in report["closed_positions"]
        }
        self.assertAlmostEqual(winning_symbols["KXSB-26-SEA"]["profit_and_loss"], 4.34)
        self.assertAlmostEqual(winning_symbols["KXSB-26-SEA"]["total_costs"], 9.66)
        self.assertAlmostEqual(winning_symbols["KXSB-26-SEA"]["total_proceeds"], 14.0)
        self.assertAlmostEqual(
            winning_symbols["KXSB-26-SEA"]["total_fees_and_commissions"], 0.28
        )
        self.assertAlmostEqual(
            winning_symbols["KXSB-26-SEA"]["net_profit_after_fees"], 4.06
        )
        self.assertAlmostEqual(
            winning_symbols["KXWOHOCKEY-MEN26CGOLD-USA"]["profit_and_loss"], 0.39
        )
        self.assertAlmostEqual(
            winning_symbols["KXWOHOCKEY-MEN26CGOLD-USA"]["total_costs"], 0.61
        )
        self.assertAlmostEqual(
            winning_symbols["KXWOHOCKEY-MEN26CGOLD-USA"]["total_proceeds"], 1.0
        )
        self.assertAlmostEqual(
            winning_symbols["KXWOHOCKEY-MEN26CGOLD-USA"]["total_fees_and_commissions"], 0.02
        )
        self.assertAlmostEqual(
            winning_symbols["KXWOHOCKEY-MEN26CGOLD-USA"]["net_profit_after_fees"], 0.37
        )

        summary = report["summary"]
        self.assertEqual(summary["contracts_closed"], 3)
        self.assertEqual(summary["winning_contracts"], 2)
        self.assertEqual(summary["losing_contracts"], 1)
        self.assertEqual(summary["win_loss_text"], "66.67% / 33.33%")
        self.assertAlmostEqual(summary["total_costs"], 11.11)
        self.assertAlmostEqual(summary["total_proceeds"], 15.0)
        self.assertAlmostEqual(summary["total_fees_and_commissions"], 0.42)
        self.assertAlmostEqual(summary["total_profit_and_loss"], 3.89)

    def test_combine_monthly_reports_rolls_up_multiple_statements(self):
        report_a = _build_monthly_statement_report(
            self.monthly_statement_text,
            source_name="statement-a.pdf",
        )
        report_b = _build_monthly_statement_report(
            self.monthly_statement_text,
            source_name="statement-b.pdf",
        )

        combined = _combine_monthly_reports([report_a, report_b])

        self.assertEqual(len(combined["statement_metadata"]), 2)
        self.assertEqual(len(combined["closed_positions"]), 6)
        self.assertEqual(len(combined["journal_entries"]), 6)
        self.assertAlmostEqual(combined["cash_activity_total"], -6.94)
        self.assertAlmostEqual(combined["summary"]["total_costs"], 22.22)
        self.assertAlmostEqual(combined["summary"]["total_proceeds"], 30.0)
        self.assertAlmostEqual(combined["summary"]["total_fees_and_commissions"], 0.84)
        self.assertAlmostEqual(combined["summary"]["total_profit_and_loss"], 7.78)
        self.assertAlmostEqual(combined["net_profit_after_fees"], 6.94)


if __name__ == "__main__":
    unittest.main()
