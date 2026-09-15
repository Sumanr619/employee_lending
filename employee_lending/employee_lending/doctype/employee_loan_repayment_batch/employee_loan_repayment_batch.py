from decimal import Decimal

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from employee_lending.employee_lending.accounting import (
    cancel_linked_journal_entry,
    create_batch_repayment_journal,
)
from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings
from employee_lending.employee_lending.doctype.employee_loan_repayment.employee_loan_repayment import rebuild_schedule_status
from employee_lending.employee_lending.utils import money, split_repayment


LOAN_FIELDS = [
    "name",
    "employee",
    "employee_name",
    "company",
    "flat_interest_rate",
    "fortnightly_repayment",
    "principal_outstanding",
    "unearned_interest_outstanding",
    "total_outstanding",
    "principal_recovered",
    "interest_earned",
    "total_repaid",
    "loan_status",
    "docstatus",
]


class EmployeeLoanRepaymentBatch(Document):
    def before_insert(self):
        if not self.posting_date:
            self.posting_date = nowdate()

    def validate(self):
        self.set_defaults()
        self.validate_bank_account()
        self.calculate_rows(lock=False)

    def before_submit(self):
        self.calculate_rows(lock=True)
        settings = get_settings()
        if settings.require_repayment_attachment and not self.proof_of_payment:
            frappe.throw(_("Batch Deposit Proof is required"))

    def on_submit(self):
        journal = create_batch_repayment_journal(self)
        self.db_set("journal_entry", journal.name, update_modified=False)
        self.update_loan_balances(direction=1)

    def on_cancel(self):
        cancel_linked_journal_entry(self.journal_entry)
        self.update_loan_balances(direction=-1)

    def set_defaults(self):
        settings = get_settings()
        self.company = settings.company
        if not self.bank_or_clearing_account:
            self.bank_or_clearing_account = settings.repayment_bank_or_clearing_account

    def validate_bank_account(self):
        settings = get_settings()
        if self.bank_or_clearing_account != settings.repayment_bank_or_clearing_account and not settings.allow_account_override:
            frappe.throw(_("Account override is disabled in Employee Lending Settings"))
        account = frappe.db.get_value(
            "Account", self.bank_or_clearing_account, ["company", "is_group", "disabled"], as_dict=True
        )
        if not account or account.company != self.company or account.is_group or account.disabled:
            frappe.throw(_("Select an active ledger account belonging to {0}").format(self.company))

    def calculate_rows(self, lock=False):
        if not self.repayments:
            frappe.throw(_("Add at least one employee repayment"))
        loan_names = [row.loan_application for row in self.repayments if row.loan_application]
        if len(loan_names) != len(self.repayments):
            frappe.throw(_("Every row must have an Employee Loan"))
        duplicates = sorted({name for name in loan_names if loan_names.count(name) > 1})
        if duplicates:
            frappe.throw(_("A loan can appear only once in a batch. Duplicate: {0}").format(", ".join(duplicates)))

        loans = {}
        for loan_name in sorted(loan_names):
            if lock:
                result = frappe.db.sql(
                    f"select {', '.join(LOAN_FIELDS)} from `tabEmployee Loan Application` where name = %s for update",
                    loan_name,
                    as_dict=True,
                )
                loan = result[0] if result else None
            else:
                loan = frappe.db.get_value("Employee Loan Application", loan_name, LOAN_FIELDS, as_dict=True)
            if not loan or loan.docstatus != 1 or loan.loan_status != "Active":
                frappe.throw(_("Loan {0} is not a submitted active loan").format(loan_name))
            if loan.company != self.company:
                frappe.throw(_("Loan {0} belongs to a different company").format(loan_name))
            loans[loan_name] = loan

        total_repayment = Decimal("0")
        total_principal = Decimal("0")
        total_interest = Decimal("0")
        for row in self.repayments:
            loan = loans[row.loan_application]
            if flt(row.repayment_amount) <= 0:
                frappe.throw(_("Row {0}: Repayment Amount must be greater than zero").format(row.idx))
            try:
                split = split_repayment(
                    row.repayment_amount,
                    loan.flat_interest_rate,
                    loan.principal_outstanding,
                    loan.unearned_interest_outstanding,
                )
            except ValueError as exc:
                frappe.throw(_("Row {0}: {1}").format(row.idx, str(exc)))
            row.employee = loan.employee
            row.employee_name = loan.employee_name
            row.flat_interest_rate = loan.flat_interest_rate
            row.repayment_amount = float(split.amount)
            row.principal_component = float(split.principal)
            row.interest_component = float(split.interest)
            row.principal_outstanding_before = loan.principal_outstanding
            row.unearned_interest_before = loan.unearned_interest_outstanding
            row.total_outstanding_before = loan.total_outstanding
            row.total_outstanding_after = flt(loan.total_outstanding - float(split.amount), 2)
            total_repayment += split.amount
            total_principal += split.principal
            total_interest += split.interest

        self.total_repayment_amount = float(money(total_repayment))
        self.total_principal_component = float(money(total_principal))
        self.total_interest_component = float(money(total_interest))

    def update_loan_balances(self, direction):
        for row in sorted(self.repayments, key=lambda item: item.loan_application):
            result = frappe.db.sql(
                f"select {', '.join(LOAN_FIELDS)} from `tabEmployee Loan Application` where name = %s for update",
                row.loan_application,
                as_dict=True,
            )
            if not result:
                frappe.throw(_("Employee loan {0} no longer exists").format(row.loan_application))
            loan = result[0]
            principal_outstanding = flt(loan.principal_outstanding - direction * row.principal_component, 2)
            interest_outstanding = flt(loan.unearned_interest_outstanding - direction * row.interest_component, 2)
            total_outstanding = flt(loan.total_outstanding - direction * row.repayment_amount, 2)
            principal_recovered = flt(loan.principal_recovered + direction * row.principal_component, 2)
            interest_earned = flt(loan.interest_earned + direction * row.interest_component, 2)
            total_repaid = flt(loan.total_repaid + direction * row.repayment_amount, 2)
            values = {
                "principal_outstanding": max(0, principal_outstanding),
                "unearned_interest_outstanding": max(0, interest_outstanding),
                "total_outstanding": max(0, total_outstanding),
                "principal_recovered": max(0, principal_recovered),
                "interest_earned": max(0, interest_earned),
                "total_repaid": max(0, total_repaid),
                "loan_status": "Closed" if direction == 1 and total_outstanding <= 0.005 else "Active",
            }
            frappe.db.set_value("Employee Loan Application", row.loan_application, values, update_modified=False)
            rebuild_schedule_status(row.loan_application, values["total_repaid"])


def _serialize_loan(loan):
    amount = min(flt(loan.fortnightly_repayment, 2), flt(loan.total_outstanding, 2))
    split = split_repayment(
        amount,
        loan.flat_interest_rate,
        loan.principal_outstanding,
        loan.unearned_interest_outstanding,
    )
    return {
        "loan_application": loan.name,
        "employee": loan.employee,
        "employee_name": loan.employee_name,
        "flat_interest_rate": loan.flat_interest_rate,
        "repayment_amount": float(split.amount),
        "principal_component": float(split.principal),
        "interest_component": float(split.interest),
        "principal_outstanding_before": loan.principal_outstanding,
        "unearned_interest_before": loan.unearned_interest_outstanding,
        "total_outstanding_before": loan.total_outstanding,
        "total_outstanding_after": flt(loan.total_outstanding - float(split.amount), 2),
    }


@frappe.whitelist()
def get_batch_defaults():
    frappe.has_permission("Employee Loan Repayment Batch", ptype="create", throw=True)
    settings = get_settings()
    return {
        "company": settings.company,
        "bank_or_clearing_account": settings.repayment_bank_or_clearing_account,
        "allow_account_override": settings.allow_account_override,
    }


@frappe.whitelist()
def get_active_loans():
    frappe.has_permission("Employee Loan Repayment Batch", ptype="create", throw=True)
    settings = get_settings()
    loans = frappe.get_all(
        "Employee Loan Application",
        filters={"docstatus": 1, "loan_status": "Active", "company": settings.company},
        fields=LOAN_FIELDS,
        order_by="employee_name asc, disbursement_date asc",
    )
    return [_serialize_loan(loan) for loan in loans]


@frappe.whitelist()
def get_loan_details(loan_application):
    loan = frappe.get_doc("Employee Loan Application", loan_application)
    loan.check_permission("read")
    if loan.docstatus != 1 or loan.loan_status != "Active":
        frappe.throw(_("Select a submitted active employee loan"))
    return _serialize_loan(loan)
