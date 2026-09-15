import unittest
from decimal import Decimal

from employee_lending.employee_lending.legacy_import import (
    aggregate_gl_rows,
    classify_outstanding_row,
    map_gl_headers,
    map_headers,
)


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.headers = map_headers(
            [
                "Employee",
                "Principle Loan",
                "Interest Due",
                "Principle Paid",
                "Interest Paid",
                "Total Outstanding",
                "Remarks",
            ]
        )

    def test_positive_row_is_ready(self):
        result = classify_outstanding_row(
            ["EMP-1", 1000, 90, 500, 45, 545, "Outstanding"], self.headers
        )
        self.assertEqual(result["validation_status"], "Ready")
        self.assertEqual(result["principal_outstanding"], Decimal("500.00"))
        self.assertEqual(result["interest_outstanding"], Decimal("45.00"))
        self.assertEqual(result["source_interest_rate"], Decimal("9.0000"))

    def test_credit_balance_is_excluded(self):
        result = classify_outstanding_row(
            ["EMP-2", 0, 0, 100, 10, -110, "Credit Balance"], self.headers
        )
        self.assertEqual(result["validation_status"], "Excluded")

    def test_interest_overpayment_is_invalid(self):
        result = classify_outstanding_row(
            ["EMP-3", 1000, 90, 100, 91, 899, "Outstanding"], self.headers
        )
        self.assertEqual(result["validation_status"], "Invalid")
        self.assertIn("Interest repaid exceeds", result["validation_message"])

    def test_mismatched_outstanding_is_invalid(self):
        result = classify_outstanding_row(
            ["EMP-4", 1000, 90, 500, 45, 600, "Outstanding"], self.headers
        )
        self.assertEqual(result["validation_status"], "Invalid")
        self.assertIn("does not reconcile", result["validation_message"])

    def test_principal_spelling_alias_is_accepted(self):
        mapped = map_headers(
            [
                "Employee ID",
                "Principal Loan",
                "Original Interest",
                "Principal Paid",
                "Interest Paid",
                "Total Outstanding",
            ]
        )
        self.assertEqual(mapped["original_principal"], 1)

    def test_gl_history_is_aggregated_per_employee_and_voucher(self):
        rows = [
            self.gl_row("EMP-1", "JV-OPEN", "Staff", 1000, 0, "Temporary"),
            self.gl_row("EMP-1", "JV-OPEN", "Unearned", 90, 0, "Temporary"),
            self.gl_row("EMP-1", "JV-PAY", "Staff", 0, 100, "Bank"),
            self.gl_row("EMP-1", "JV-PAY", "Income", 0, 9, "Bank"),
        ]
        result = aggregate_gl_rows(rows, "Staff", "Unearned", "Income", "Temporary")["EMP-1"]
        self.assertEqual(result["staff_balance"], Decimal("900.00"))
        self.assertEqual(result["unearned_balance"], Decimal("90.00"))
        self.assertEqual(result["interest_earned"], Decimal("9.00"))
        self.assertEqual(result["total_outstanding"], Decimal("981.00"))
        self.assertEqual(result["opening_count"], 1)
        self.assertEqual(result["repayment_count"], 1)
        self.assertEqual(result["transactions"][0]["debit"], Decimal("1090.00"))
        self.assertEqual(result["transactions"][1]["credit"], Decimal("109.00"))

    def test_multi_employee_repayment_stays_separate(self):
        rows = [
            self.gl_row("EMP-1", "JV-BATCH", "Staff", 0, 50, "Bank"),
            self.gl_row("EMP-1", "JV-BATCH", "Income", 0, 5, "Bank"),
            self.gl_row("EMP-2", "JV-BATCH", "Staff", 0, 80, "Bank"),
            self.gl_row("EMP-2", "JV-BATCH", "Income", 0, 8, "Bank"),
        ]
        result = aggregate_gl_rows(rows, "Staff", "Unearned", "Income", "Temporary")
        self.assertEqual(result["EMP-1"]["transactions"][0]["credit"], Decimal("55.00"))
        self.assertEqual(result["EMP-2"]["transactions"][0]["credit"], Decimal("88.00"))

    def test_gl_header_aliases(self):
        headers = map_gl_headers(
            ["Posting Date", "Account", "Debit (PGK)", "Credit (PGK)", "Voucher Type", "Voucher No", "Against Account", "Party Type", "Party"]
        )
        self.assertEqual(headers["voucher_no"], 5)

    @staticmethod
    def gl_row(employee, voucher, account, debit, credit, against):
        return {
            "posting_date": "2026-07-31" if voucher == "JV-OPEN" else "2026-08-15",
            "account": account,
            "debit": debit,
            "credit": credit,
            "voucher_type": "Journal Entry",
            "voucher_no": voucher,
            "against_account": against,
            "party_type": "Employee",
            "party": employee,
        }


if __name__ == "__main__":
    unittest.main()
