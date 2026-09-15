import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from employee_lending.employee_lending.accounting import (
    cancel_linked_journal_entry,
    create_legacy_conversion_journals,
)
from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings
from employee_lending.employee_lending.utils import calculate_legacy_conversion, money


class EmployeeLoanLegacyOpening(Document):
    def before_insert(self):
        if not self.cutoff_date:
            self.cutoff_date = nowdate()
        self.status = "Draft"

    def validate(self):
        self.set_master_details()
        self.calculate_values()
        self.validate_existing_module_loan()
        self.load_and_validate_gl()

    def before_submit(self):
        if not self.confirm_no_bank_posting:
            frappe.throw(_("Confirm that the legacy conversion must not post any Bank movement"))
        self.validate_existing_module_loan(lock=True)
        self.load_and_validate_gl(lock=True)

    def on_submit(self):
        conversion = self.get_conversion()
        loan = self.create_loan_application(conversion)
        cleanup, journal = create_legacy_conversion_journals(self, loan, conversion)
        frappe.db.set_value(
            "Employee Loan Application",
            loan.name,
            {
                "disbursement_journal_entry": journal.name,
                "disbursement_date": self.cutoff_date,
                "loan_status": "Active",
            },
            update_modified=False,
        )
        self.db_set("loan_application", loan.name, update_modified=False)
        self.db_set("cleanup_journal_entry", cleanup.name, update_modified=False)
        self.db_set("conversion_journal_entry", journal.name, update_modified=False)
        self.db_set("status", "Processed", update_modified=False)

    def before_cancel(self):
        if not self.loan_application:
            return
        if frappe.db.exists("Employee Loan Repayment", {"loan_application": self.loan_application, "docstatus": 1}):
            frappe.throw(_("Cancel all submitted repayments before cancelling this legacy opening"))
        batch = frappe.db.sql(
            """
            select batch.name
              from `tabEmployee Loan Repayment Batch` batch
              inner join `tabEmployee Loan Repayment Batch Item` item on item.parent = batch.name
             where batch.docstatus = 1 and item.loan_application = %s
             limit 1
            """,
            self.loan_application,
        )
        if batch:
            frappe.throw(_("Cancel repayment batch {0} before cancelling this legacy opening").format(batch[0][0]))

    def on_cancel(self):
        cancel_linked_journal_entry(self.conversion_journal_entry)
        cancel_linked_journal_entry(self.cleanup_journal_entry)
        if self.loan_application and frappe.db.exists("Employee Loan Application", self.loan_application):
            loan = frappe.get_doc("Employee Loan Application", self.loan_application)
            if loan.docstatus == 1:
                loan.flags.from_legacy_opening = True
                loan.flags.ignore_permissions = True
                loan.cancel()
        self.db_set("status", "Cancelled", update_modified=False)

    def set_master_details(self):
        if not self.employee or not self.loan_product:
            return
        employee = frappe.db.get_value(
            "Employee", self.employee, ["employee_name", "company"], as_dict=True
        )
        if not employee:
            frappe.throw(_("Employee {0} does not exist").format(self.employee))
        product = frappe.db.get_value(
            "Employee Loan Product",
            self.loan_product,
            ["number_of_fortnights", "flat_interest_rate", "disabled"],
            as_dict=True,
        )
        if not product or product.disabled:
            frappe.throw(_("Select an active Employee Loan Product"))
        settings = get_settings()
        if employee.company != settings.company:
            frappe.throw(_("Employee company must match Employee Lending Settings"))
        self.employee_name = employee.employee_name
        self.company = employee.company
        self.flat_interest_rate = product.flat_interest_rate
        self.original_installments = product.number_of_fortnights

    def calculate_values(self):
        conversion = self.get_conversion()
        self.source_interest_rate = flt(
            float(conversion.original_interest / conversion.original_principal * 100), 4
        )
        if self.flat_interest_rate is not None and abs(flt(self.flat_interest_rate) - self.source_interest_rate) > 0.25:
            frappe.throw(
                _("Selected product rate {0}% does not match the source loan rate {1}%").format(
                    flt(self.flat_interest_rate, 2), flt(self.source_interest_rate, 2)
                )
            )
        self.principal_outstanding = float(conversion.principal_outstanding)
        self.interest_outstanding = float(conversion.interest_outstanding)
        self.calculated_total_outstanding = float(conversion.gross_outstanding)
        if abs(flt(self.reported_total_outstanding) - float(conversion.gross_outstanding)) > 0.01:
            frappe.throw(_("Reported Total Outstanding does not reconcile to principal and interest"))

        original_total = money(conversion.original_principal + conversion.original_interest)
        if not self.fortnightly_repayment and self.original_installments:
            self.fortnightly_repayment = float(money(original_total / int(self.original_installments)))
        if not self.remaining_installments and flt(self.fortnightly_repayment) > 0:
            self.remaining_installments = max(
                1,
                math.ceil(float(conversion.gross_outstanding) / flt(self.fortnightly_repayment)),
            )
        if not self.remaining_installments or self.remaining_installments < 1:
            frappe.throw(_("Remaining Instalments must be greater than zero"))

    def get_conversion(self, current_unearned_debit=None):
        try:
            return calculate_legacy_conversion(
                self.original_principal,
                self.original_interest,
                self.principal_repaid,
                self.interest_repaid,
                self.current_unearned_interest_debit
                if current_unearned_debit is None
                else current_unearned_debit,
            )
        except ValueError as exc:
            frappe.throw(str(exc))

    def validate_existing_module_loan(self, lock=False):
        if not self.employee:
            return
        query = """
            select name
              from `tabEmployee Loan Application`
             where employee = %s
               and docstatus = 1
               and loan_status in ('Approved', 'Active', 'Closed')
               and ifnull(total_outstanding, 0) > 0.005
             limit 1
        """
        if lock:
            query += " for update"
        existing = frappe.db.sql(query, self.employee)
        if existing and existing[0][0] != self.loan_application:
            frappe.throw(_("Employee already has module loan {0}").format(existing[0][0]))
        duplicate = frappe.db.get_value(
            "Employee Loan Legacy Opening",
            {"employee": self.employee, "docstatus": 1, "name": ["!=", self.name]},
            "name",
        )
        if duplicate:
            frappe.throw(_("Employee already has submitted legacy opening {0}").format(duplicate))

    def load_and_validate_gl(self, lock=False):
        if not self.employee or not self.cutoff_date:
            return
        settings = get_settings()
        accounts = (settings.staff_loan_receivable_account, settings.unearned_interest_account)
        if lock:
            frappe.db.sql(
                """
                select name
                  from `tabGL Entry`
                 where party_type = 'Employee'
                   and party = %s
                   and account in %s
                   and is_cancelled = 0
                   and posting_date <= %s
                 for update
                """,
                (self.employee, accounts, self.cutoff_date),
            )
        later_entry = frappe.db.get_value(
            "GL Entry",
            {
                "party_type": "Employee",
                "party": self.employee,
                "account": ["in", accounts],
                "is_cancelled": 0,
                "posting_date": [">", self.cutoff_date],
            },
            "name",
        )
        if later_entry:
            frappe.throw(
                _("Employee has loan ledger activity after the cut-off date. Use an updated reconciliation report")
            )

        balances = frappe.db.sql(
            """
            select account, round(sum(debit - credit), 2) as balance
              from `tabGL Entry`
             where party_type = 'Employee'
               and party = %s
               and account in %s
               and is_cancelled = 0
               and posting_date <= %s
             group by account
            """,
            (self.employee, accounts, self.cutoff_date),
            as_dict=True,
        )
        balance_map = {row.account: flt(row.balance, 2) for row in balances}
        staff_balance = balance_map.get(settings.staff_loan_receivable_account, 0)
        unearned_balance = balance_map.get(settings.unearned_interest_account, 0)
        self.current_staff_loan_balance = staff_balance
        self.current_unearned_interest_debit = unearned_balance

        if abs(staff_balance - flt(self.principal_outstanding)) > 0.01:
            frappe.throw(
                _("Current Staff Loan GL balance {0} does not match principal outstanding {1}").format(
                    frappe.format_value(staff_balance, {"fieldtype": "Currency"}),
                    frappe.format_value(self.principal_outstanding, {"fieldtype": "Currency"}),
                )
            )
        if unearned_balance < -0.005:
            frappe.throw(_("Current Unearned Interest balance is already a credit. Review this employee manually"))

        vouchers = frappe.db.sql_list(
            """
            select voucher_no
              from `tabGL Entry`
             where party_type = 'Employee'
               and party = %s
               and account = %s
               and voucher_type = 'Journal Entry'
               and is_cancelled = 0
               and posting_date <= %s
               and debit > 0
             group by voucher_no
             order by min(posting_date), min(creation), voucher_no
            """,
            (self.employee, settings.staff_loan_receivable_account, self.cutoff_date),
        )
        if not vouchers:
            frappe.throw(_("No historical Staff Loan debit Journal Entry was found for this employee"))
        self.source_journal_entries = "\n".join(vouchers)
        self.get_conversion(current_unearned_debit=unearned_balance)

    def create_loan_application(self, conversion):
        loan = frappe.get_doc(
            {
                "doctype": "Employee Loan Application",
                "application_date": self.cutoff_date,
                "approval_status": "Approved",
                "employee": self.employee,
                "loan_product": self.loan_product,
                "requested_amount": float(conversion.original_principal),
                "approved_principal": float(conversion.original_principal),
                "purpose": "Legacy employee loan opening at {0}".format(self.cutoff_date),
                "first_repayment_date": self.next_repayment_date,
                "total_interest": float(conversion.original_interest),
                "total_amount_due": float(conversion.original_principal + conversion.original_interest),
                "fortnightly_repayment": self.fortnightly_repayment,
                "principal_outstanding": float(conversion.principal_outstanding),
                "unearned_interest_outstanding": float(conversion.interest_outstanding),
                "total_outstanding": float(conversion.gross_outstanding),
                "principal_recovered": float(conversion.principal_repaid),
                "interest_earned": float(conversion.interest_repaid),
                "total_repaid": float(conversion.principal_repaid + conversion.interest_repaid),
                "is_legacy_opening": 1,
                "legacy_opening": self.name,
                "legacy_remaining_installments": self.remaining_installments,
                "legacy_repaid_before_conversion": float(conversion.principal_repaid + conversion.interest_repaid),
                "enforce_policy_limits": 0,
                "is_confirmed_employee": 1,
            }
        )
        loan.flags.ignore_permissions = True
        loan.insert(ignore_permissions=True)
        loan.flags.ignore_permissions = True
        loan.submit()
        return loan


@frappe.whitelist()
def get_legacy_preview(
    employee,
    loan_product,
    cutoff_date,
    original_principal,
    original_interest,
    principal_repaid,
    interest_repaid,
):
    frappe.has_permission("Employee Loan Legacy Opening", ptype="create", throw=True)
    doc = frappe.new_doc("Employee Loan Legacy Opening")
    doc.employee = employee
    doc.loan_product = loan_product
    doc.cutoff_date = cutoff_date
    doc.original_principal = original_principal
    doc.original_interest = original_interest
    doc.principal_repaid = principal_repaid
    doc.interest_repaid = interest_repaid
    doc.set_master_details()
    doc.load_and_validate_gl()
    doc.calculate_values()
    return {
        "employee_name": doc.employee_name,
        "company": doc.company,
        "principal_outstanding": doc.principal_outstanding,
        "interest_outstanding": doc.interest_outstanding,
        "calculated_total_outstanding": doc.calculated_total_outstanding,
        "current_staff_loan_balance": doc.current_staff_loan_balance,
        "current_unearned_interest_debit": doc.current_unearned_interest_debit,
        "source_journal_entries": doc.source_journal_entries,
    }
