import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).parents[1] / "employee_lending" / "employee_lending" / "utils.py"
SPEC = importlib.util.spec_from_file_location("employee_lending_utils", MODULE_PATH)
utils = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = utils
SPEC.loader.exec_module(utils)


class LoanCalculationTests(unittest.TestCase):
    def test_six_month_schedule_reconciles(self):
        totals, rows = utils.build_schedule(1000, 9, 13)
        self.assertEqual(str(totals.total_due), "1090.00")
        self.assertEqual(str(totals.normal_repayment), "83.85")
        self.assertEqual(str(rows[0]["principal_component"]), "76.93")
        self.assertEqual(str(rows[0]["interest_component"]), "6.92")
        self.assertEqual(str(rows[-1]["repayment_amount"]), "83.80")
        self.assertEqual(sum(r["principal_component"] for r in rows), totals.principal)
        self.assertEqual(sum(r["interest_component"] for r in rows), totals.interest)
        self.assertEqual(str(rows[-1]["total_outstanding"]), "0.00")

    def test_twelve_month_schedule_reconciles(self):
        totals, rows = utils.build_schedule(1000, 18, 26)
        self.assertEqual(str(totals.total_due), "1180.00")
        self.assertEqual(str(totals.normal_repayment), "45.38")
        self.assertEqual(str(rows[0]["principal_component"]), "38.46")
        self.assertEqual(str(rows[0]["interest_component"]), "6.92")
        self.assertEqual(str(rows[-1]["repayment_amount"]), "45.50")
        self.assertEqual(sum(r["principal_component"] for r in rows), totals.principal)
        self.assertEqual(sum(r["interest_component"] for r in rows), totals.interest)

    def test_overpayment_is_rejected(self):
        with self.assertRaises(ValueError):
            utils.split_repayment(100.01, 9, 90, 10)

    def test_batch_allocations_reconcile(self):
        first = utils.split_repayment(83.85, 9, 1000, 90)
        second = utils.split_repayment(45.38, 18, 1000, 180)
        self.assertEqual(first.amount + second.amount, utils.money("129.23"))
        self.assertEqual(first.principal + second.principal, utils.money("115.39"))
        self.assertEqual(first.interest + second.interest, utils.money("13.84"))

    def test_legacy_conversion_balances_without_bank(self):
        conversion = utils.calculate_legacy_conversion(1000, 90, 76.93, 6.92, 90)
        self.assertEqual(str(conversion.principal_outstanding), "923.07")
        self.assertEqual(str(conversion.interest_outstanding), "83.08")
        self.assertEqual(str(conversion.gross_outstanding), "1006.15")
        self.assertEqual(str(conversion.cleanup_temporary_debit), "1013.07")
        self.assertEqual(str(conversion.cleanup_staff_loan_credit), "923.07")
        self.assertEqual(str(conversion.cleanup_unearned_interest_credit), "90.00")
        self.assertEqual(str(conversion.opening_staff_loan_debit), "1006.15")
        self.assertEqual(str(conversion.opening_temporary_credit), "923.07")
        self.assertEqual(str(conversion.opening_unearned_interest_credit), "83.08")
        self.assertEqual(
            conversion.cleanup_temporary_debit,
            conversion.cleanup_staff_loan_credit + conversion.cleanup_unearned_interest_credit,
        )
        self.assertEqual(
            conversion.opening_staff_loan_debit,
            conversion.opening_temporary_credit + conversion.opening_unearned_interest_credit,
        )

    def test_remaining_legacy_schedule_clears(self):
        rows = utils.build_remaining_schedule(923.07, 83.08, 9, 12, 83.85)
        self.assertEqual(str(rows[-1]["principal_balance"]), "0.00")
        self.assertEqual(str(rows[-1]["unearned_interest_balance"]), "0.00")
        self.assertEqual(str(rows[-1]["total_outstanding"]), "0.00")

    def test_credit_balance_legacy_loan_is_rejected(self):
        with self.assertRaises(ValueError):
            utils.calculate_legacy_conversion(100, 9, 110, 0, 9)


if __name__ == "__main__":
    unittest.main()
