import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from employee_lending.employee_lending.accounting import cancel_linked_journal_entry, create_repayment_journal
from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings
from employee_lending.employee_lending.utils import split_repayment


class EmployeeLoanRepayment(Document):
    def before_insert(self):
        if not self.posting_date:
            self.posting_date = nowdate()

    def validate(self):
        self.set_loan_details(lock=False)
        self.validate_bank_account()
        self.calculate_split()

    def before_submit(self):
        self.set_loan_details(lock=True)
        self.calculate_split()
        self.validate_attachment()

    def on_submit(self):
        loan = frappe.get_doc("Employee Loan Application", self.loan_application)
        journal = create_repayment_journal(self, loan)
        self.db_set("journal_entry", journal.name, update_modified=False)
        self.update_loan_balances(direction=1)

    def on_cancel(self):
        cancel_linked_journal_entry(self.journal_entry)
        self.update_loan_balances(direction=-1)

    def set_loan_details(self, lock=False):
        if not self.loan_application:
            return
        if lock:
            rows = frappe.db.sql(
                """
                select name, employee, employee_name, company, flat_interest_rate,
                       fortnightly_repayment, principal_outstanding,
                       unearned_interest_outstanding, total_outstanding, loan_status, docstatus
                  from `tabEmployee Loan Application`
                 where name = %s
                 for update
                """,
                self.loan_application,
                as_dict=True,
            )
            loan = rows[0] if rows else None
        else:
            loan = frappe.db.get_value(
                "Employee Loan Application",
                self.loan_application,
                [
                    "name", "employee", "employee_name", "company", "flat_interest_rate",
                    "fortnightly_repayment", "principal_outstanding",
                    "unearned_interest_outstanding", "total_outstanding", "loan_status", "docstatus",
                ],
                as_dict=True,
            )
        if not loan or loan.docstatus != 1 or loan.loan_status not in ("Active", "Closed"):
            frappe.throw(_("Select a submitted active employee loan"))
        if loan.loan_status == "Closed" and self.docstatus != 2:
            frappe.throw(_("This employee loan is already closed"))
        self.employee = loan.employee
        self.employee_name = loan.employee_name
        self.company = loan.company
        self.flat_interest_rate = loan.flat_interest_rate
        self.normal_fortnightly_repayment = loan.fortnightly_repayment
        self.principal_outstanding_before = loan.principal_outstanding
        self.unearned_interest_before = loan.unearned_interest_outstanding
        self.total_outstanding_before = loan.total_outstanding

    def calculate_split(self):
        if flt(self.repayment_amount) <= 0:
            frappe.throw(_("Repayment Amount must be greater than zero"))
        if flt(self.total_outstanding_before) <= 0:
            frappe.throw(_("The selected loan has no outstanding balance"))
        try:
            split = split_repayment(
                self.repayment_amount,
                self.flat_interest_rate,
                self.principal_outstanding_before,
                self.unearned_interest_before,
            )
        except ValueError as exc:
            frappe.throw(str(exc))
        self.repayment_amount = float(split.amount)
        self.principal_component = float(split.principal)
        self.interest_component = float(split.interest)
        self.principal_outstanding_after = flt(self.principal_outstanding_before - self.principal_component, 2)
        self.unearned_interest_after = flt(self.unearned_interest_before - self.interest_component, 2)
        self.total_outstanding_after = flt(self.principal_outstanding_after + self.unearned_interest_after, 2)

    def validate_bank_account(self):
        settings = get_settings()
        if not self.bank_or_clearing_account:
            self.bank_or_clearing_account = settings.repayment_bank_or_clearing_account
        account = frappe.db.get_value(
            "Account", self.bank_or_clearing_account, ["company", "is_group", "disabled"], as_dict=True
        )
        if not account or account.company != self.company or account.is_group or account.disabled:
            frappe.throw(_("Select an active ledger account belonging to {0}").format(self.company))

    def validate_attachment(self):
        settings = get_settings()
        if settings.require_repayment_attachment and not self.proof_of_payment:
            frappe.throw(_("Proof of Payment is required"))

    def update_loan_balances(self, direction):
        rows = frappe.db.sql(
            """
            select principal_outstanding, unearned_interest_outstanding,
                   total_outstanding, principal_recovered, interest_earned, total_repaid
              from `tabEmployee Loan Application`
             where name = %s
             for update
            """,
            self.loan_application,
            as_dict=True,
        )
        if not rows:
            frappe.throw(_("Employee loan no longer exists"))
        loan = rows[0]
        principal_outstanding = flt(loan.principal_outstanding - direction * self.principal_component, 2)
        interest_outstanding = flt(loan.unearned_interest_outstanding - direction * self.interest_component, 2)
        total_outstanding = flt(loan.total_outstanding - direction * self.repayment_amount, 2)
        principal_recovered = flt(loan.principal_recovered + direction * self.principal_component, 2)
        interest_earned = flt(loan.interest_earned + direction * self.interest_component, 2)
        total_repaid = flt(loan.total_repaid + direction * self.repayment_amount, 2)

        values = {
            "principal_outstanding": max(0, principal_outstanding),
            "unearned_interest_outstanding": max(0, interest_outstanding),
            "total_outstanding": max(0, total_outstanding),
            "principal_recovered": max(0, principal_recovered),
            "interest_earned": max(0, interest_earned),
            "total_repaid": max(0, total_repaid),
            "loan_status": "Closed" if direction == 1 and total_outstanding <= 0.005 else "Active",
        }
        frappe.db.set_value("Employee Loan Application", self.loan_application, values, update_modified=False)
        rebuild_schedule_status(self.loan_application, values["total_repaid"])


def rebuild_schedule_status(loan_application, total_repaid):
    legacy_values = frappe.db.get_value(
        "Employee Loan Application",
        loan_application,
        ["is_legacy_opening", "legacy_repaid_before_conversion"],
        as_dict=True,
    )
    historical_repaid = (
        flt(legacy_values.legacy_repaid_before_conversion, 2)
        if legacy_values and legacy_values.is_legacy_opening
        else 0
    )
    remaining = flt(max(0, flt(total_repaid, 2) - historical_repaid), 2)
    rows = frappe.get_all(
        "Employee Loan Schedule",
        filters={"parent": loan_application, "parenttype": "Employee Loan Application"},
        fields=["name", "repayment_amount"],
        order_by="idx asc",
    )
    for row in rows:
        scheduled = flt(row.repayment_amount, 2)
        paid = min(remaining, scheduled)
        remaining = flt(max(0, remaining - paid), 2)
        status = "Paid" if paid >= scheduled else ("Partly Paid" if paid > 0 else "Scheduled")
        frappe.db.set_value(
            "Employee Loan Schedule",
            row.name,
            {"paid_amount": paid, "status": status},
            update_modified=False,
        )


@frappe.whitelist()
def get_active_loan_details(loan_application):
    loan = frappe.get_doc("Employee Loan Application", loan_application)
    loan.check_permission("read")
    if loan.docstatus != 1 or loan.loan_status != "Active":
        frappe.throw(_("Select an active submitted employee loan"))
    settings = get_settings()
    amount = min(flt(loan.fortnightly_repayment, 2), flt(loan.total_outstanding, 2))
    split = split_repayment(
        amount, loan.flat_interest_rate, loan.principal_outstanding, loan.unearned_interest_outstanding
    )
    return {
        "employee": loan.employee,
        "employee_name": loan.employee_name,
        "company": loan.company,
        "flat_interest_rate": loan.flat_interest_rate,
        "normal_fortnightly_repayment": loan.fortnightly_repayment,
        "repayment_amount": float(split.amount),
        "principal_component": float(split.principal),
        "interest_component": float(split.interest),
        "principal_outstanding_before": loan.principal_outstanding,
        "unearned_interest_before": loan.unearned_interest_outstanding,
        "total_outstanding_before": loan.total_outstanding,
        "principal_outstanding_after": flt(loan.principal_outstanding - float(split.principal), 2),
        "unearned_interest_after": flt(loan.unearned_interest_outstanding - float(split.interest), 2),
        "total_outstanding_after": flt(loan.total_outstanding - float(split.amount), 2),
        "bank_or_clearing_account": settings.repayment_bank_or_clearing_account,
        "allow_account_override": settings.allow_account_override,
    }
