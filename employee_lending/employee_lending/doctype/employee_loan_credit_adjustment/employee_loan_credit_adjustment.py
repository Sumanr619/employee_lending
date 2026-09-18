import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from employee_lending.employee_lending.accounting import (
    _account_row,
    _loan_journal_reference,
    cancel_linked_journal_entry,
)
from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings
from employee_lending.employee_lending.doctype.employee_loan_credit.employee_loan_credit import refresh_credit_totals
from employee_lending.employee_lending.doctype.employee_loan_repayment.employee_loan_repayment import rebuild_schedule_status
from employee_lending.employee_lending.utils import split_repayment


class EmployeeLoanCreditAdjustment(Document):
    def before_insert(self):
        if not self.posting_date:
            self.posting_date = nowdate()

    def validate(self):
        self.set_credit_details(lock=False)
        self.validate_destination()
        self.calculate_components()

    def before_submit(self):
        self.set_credit_details(lock=True)
        self.validate_destination()
        self.calculate_components()

    def on_submit(self):
        journal = self.create_journal_entry()
        self.db_set("journal_entry", journal.name, update_modified=False)
        if self.adjustment_type == "Apply to Loan":
            self.update_loan(direction=1)
        refresh_credit_totals(self.employee_credit)

    def on_cancel(self):
        cancel_linked_journal_entry(self.journal_entry)
        if self.adjustment_type == "Apply to Loan":
            self.update_loan(direction=-1)
        refresh_credit_totals(self.employee_credit)

    def set_credit_details(self, lock=False):
        fields = [
            "name", "employee", "employee_name", "company", "status",
            "principal_credit_available", "interest_credit_available", "available_credit",
        ]
        if lock:
            rows = frappe.db.sql(
                """
                select name, employee, employee_name, company, status,
                       principal_credit_available, interest_credit_available, available_credit
                  from `tabEmployee Loan Credit`
                 where name = %s
                 for update
                """,
                self.employee_credit,
                as_dict=True,
            )
            credit = rows[0] if rows else None
        else:
            credit = frappe.db.get_value("Employee Loan Credit", self.employee_credit, fields, as_dict=True)
        if not credit:
            frappe.throw(_("Select a valid Employee Loan Credit"))
        if flt(credit.available_credit, 2) <= 0:
            frappe.throw(_("The selected employee credit has no available balance"))
        self.employee = credit.employee
        self.employee_name = credit.employee_name
        self.company = credit.company
        self.credit_available_before = flt(credit.available_credit, 2)
        self._principal_available = flt(credit.principal_credit_available, 2)
        self._interest_available = flt(credit.interest_credit_available, 2)

    def validate_destination(self):
        amount = flt(self.amount, 2)
        if amount <= 0:
            frappe.throw(_("Amount must be greater than zero"))
        if amount > flt(self.credit_available_before, 2) + 0.005:
            frappe.throw(_("Amount cannot exceed the available employee credit"))
        if self.adjustment_type == "Refund":
            if not self.bank_account:
                frappe.throw(_("Select the bank account used for the refund"))
            if not self.bank_reference:
                frappe.throw(_("Enter the bank refund reference"))
            account = frappe.db.get_value(
                "Account", self.bank_account, ["company", "is_group", "disabled"], as_dict=True
            )
            if not account or account.company != self.company or account.is_group or account.disabled:
                frappe.throw(_("Select an active ledger account belonging to {0}").format(self.company))
            self.loan_application = None
        elif self.adjustment_type == "Apply to Loan":
            if not self.loan_application:
                frappe.throw(_("Select the employee loan receiving this credit"))
            loan = frappe.db.get_value(
                "Employee Loan Application",
                self.loan_application,
                [
                    "employee", "company", "docstatus", "loan_status", "flat_interest_rate",
                    "principal_outstanding", "unearned_interest_outstanding", "total_outstanding",
                    "disbursement_journal_entry",
                ],
                as_dict=True,
            )
            if not loan or loan.docstatus != 1 or loan.loan_status != "Active":
                frappe.throw(_("Select a submitted active employee loan"))
            if loan.employee != self.employee or loan.company != self.company:
                frappe.throw(_("Employee credit and target loan must belong to the same employee and company"))
            if amount > flt(loan.total_outstanding, 2) + 0.005:
                frappe.throw(_("Amount cannot exceed the target loan outstanding balance"))
            self._loan = loan
            self.bank_account = None
        else:
            frappe.throw(_("Select Refund or Apply to Loan"))

    def calculate_components(self):
        amount = flt(self.amount, 2)
        self.source_principal_component = min(amount, self._principal_available)
        self.source_interest_component = flt(amount - self.source_principal_component, 2)
        if self.source_interest_component > self._interest_available + 0.005:
            frappe.throw(_("The credit source components do not reconcile"))
        self.credit_available_after = flt(self.credit_available_before - amount, 2)
        self.loan_principal_component = 0
        self.loan_interest_component = 0
        if self.adjustment_type == "Apply to Loan":
            split = split_repayment(
                amount,
                self._loan.flat_interest_rate,
                self._loan.principal_outstanding,
                self._loan.unearned_interest_outstanding,
            )
            self.loan_principal_component = float(split.principal)
            self.loan_interest_component = float(split.interest)

    def create_journal_entry(self):
        settings = get_settings()
        journal = frappe.new_doc("Journal Entry")
        journal.company = self.company
        journal.posting_date = self.posting_date
        journal.voucher_type = "Bank Entry" if self.adjustment_type == "Refund" else "Journal Entry"
        journal.finance_book = settings.finance_book
        if self.adjustment_type == "Refund":
            journal.cheque_no = self.bank_reference
            journal.cheque_date = self.posting_date
        journal.user_remark = self.remarks or _("Employee loan credit {0}: {1} for {2}").format(
            self.adjustment_type.lower(), self.name, self.employee_name
        )
        if self.source_principal_component:
            journal.append(
                "accounts",
                _account_row(
                    settings.staff_loan_receivable_account,
                    debit=self.source_principal_component,
                    party_type="Employee",
                    party=self.employee,
                ),
            )
        if self.source_interest_component:
            journal.append(
                "accounts",
                _account_row(
                    settings.unearned_interest_account,
                    debit=self.source_interest_component,
                    party_type="Employee",
                    party=self.employee,
                ),
            )
        if self.adjustment_type == "Refund":
            journal.append("accounts", _account_row(self.bank_account, credit=self.amount))
        else:
            reference_type, reference_name = _loan_journal_reference(
                self.loan_application, self._loan.disbursement_journal_entry
            )
            journal.append(
                "accounts",
                _account_row(
                    settings.staff_loan_receivable_account,
                    credit=self.amount,
                    reference_type=reference_type,
                    reference_name=reference_name,
                    party_type="Employee",
                    party=self.employee,
                ),
            )
            if self.loan_interest_component:
                journal.append(
                    "accounts",
                    _account_row(
                        settings.unearned_interest_account,
                        debit=self.loan_interest_component,
                        reference_type=reference_type,
                        reference_name=reference_name,
                        party_type="Employee",
                        party=self.employee,
                    ),
                )
                journal.append(
                    "accounts",
                    _account_row(
                        settings.interest_income_account,
                        credit=self.loan_interest_component,
                        cost_center=settings.default_cost_center,
                    ),
                )
        journal.insert(ignore_permissions=True)
        journal.flags.ignore_permissions = True
        journal.submit()
        return journal

    def update_loan(self, direction):
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
            frappe.throw(_("Target employee loan no longer exists"))
        loan = rows[0]
        principal = flt(loan.principal_outstanding - direction * self.loan_principal_component, 2)
        interest = flt(loan.unearned_interest_outstanding - direction * self.loan_interest_component, 2)
        total = flt(loan.total_outstanding - direction * self.amount, 2)
        principal_recovered = flt(loan.principal_recovered + direction * self.loan_principal_component, 2)
        interest_earned = flt(loan.interest_earned + direction * self.loan_interest_component, 2)
        total_repaid = flt(loan.total_repaid + direction * self.amount, 2)
        values = {
            "principal_outstanding": max(0, principal),
            "unearned_interest_outstanding": max(0, interest),
            "total_outstanding": max(0, total),
            "principal_recovered": max(0, principal_recovered),
            "interest_earned": max(0, interest_earned),
            "total_repaid": max(0, total_repaid),
            "loan_status": "Closed" if direction == 1 and total <= 0.005 else "Active",
        }
        frappe.db.set_value("Employee Loan Application", self.loan_application, values, update_modified=False)
        rebuild_schedule_status(self.loan_application, values["total_repaid"])
