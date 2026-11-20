import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from employee_lending.employee_lending.accounting import _account_row, cancel_linked_journal_entry
from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings
from employee_lending.employee_lending.doctype.employee_loan_credit.employee_loan_credit import (
    create_repayment_credit,
    delete_unused_repayment_credit,
)


class EmployeeLoanCreditReceipt(Document):
    def before_insert(self):
        if not self.posting_date:
            self.posting_date = nowdate()

    def validate(self):
        self.set_employee_details()
        self.validate_amount()
        self.validate_bank_account()

    def before_submit(self):
        self.set_employee_details()
        self.validate_amount()
        self.validate_bank_account()
        self.validate_attachment()

    def on_submit(self):
        journal = self.create_journal_entry()
        self.db_set("journal_entry", journal.name, update_modified=False)
        credit_name = create_repayment_credit(
            employee=self.employee,
            posting_date=self.posting_date,
            source_reference="credit-receipt:{0}".format(self.name),
            journal_entry=journal.name,
            amount=self.amount,
            remarks=self.remarks or _("Employee loan credit receipt {0}").format(self.name),
        )
        self.db_set("employee_credit", credit_name, update_modified=False)

    def on_cancel(self):
        if self.employee_credit:
            adjustment = frappe.db.get_value(
                "Employee Loan Credit Adjustment",
                {"employee_credit": self.employee_credit, "docstatus": 1},
                "name",
            )
            if adjustment:
                frappe.throw(
                    _("Employee credit {0} has already been used. Cancel adjustment {1} first.").format(
                        self.employee_credit, adjustment
                    )
                )
        cancel_linked_journal_entry(self.journal_entry)
        if self.employee_credit:
            credit_name = self.employee_credit
            self.db_set("employee_credit", None, update_modified=False)
            delete_unused_repayment_credit(credit_name)

    def set_employee_details(self):
        employee = frappe.db.get_value(
            "Employee", self.employee, ["employee_name", "company", "status"], as_dict=True
        )
        if not employee:
            frappe.throw(_("Employee {0} does not exist").format(self.employee))
        self.employee_name = employee.employee_name
        self.company = employee.company

    def validate_amount(self):
        self.amount = flt(self.amount, 2)
        if self.amount <= 0:
            frappe.throw(_("Credit Receipt Amount must be greater than zero"))

    def validate_bank_account(self):
        settings = get_settings()
        if not self.bank_or_clearing_account:
            self.bank_or_clearing_account = settings.repayment_bank_or_clearing_account
        if (
            self.bank_or_clearing_account != settings.repayment_bank_or_clearing_account
            and not settings.allow_account_override
        ):
            frappe.throw(_("Account override is disabled in Employee Lending Settings"))
        account = frappe.db.get_value(
            "Account",
            self.bank_or_clearing_account,
            ["company", "is_group", "disabled"],
            as_dict=True,
        )
        if not account or account.company != self.company or account.is_group or account.disabled:
            frappe.throw(_("Select an active ledger account belonging to {0}").format(self.company))

    def validate_attachment(self):
        settings = get_settings()
        if settings.require_repayment_attachment and not self.proof_of_payment:
            frappe.throw(_("Proof of Payment is required"))

    def create_journal_entry(self):
        settings = get_settings()
        journal = frappe.new_doc("Journal Entry")
        journal.company = self.company
        journal.posting_date = self.posting_date
        journal.voucher_type = "Bank Entry"
        journal.finance_book = settings.finance_book
        journal.cheque_no = self.bank_reference
        journal.cheque_date = self.posting_date
        system_remark = _("Employee loan credit receipt {0} for {1}").format(
            self.name, self.employee_name
        )
        journal.user_remark = (
            "{0} - {1}".format(system_remark, self.remarks) if self.remarks else system_remark
        )
        journal.append(
            "accounts", _account_row(self.bank_or_clearing_account, debit=self.amount)
        )
        journal.append(
            "accounts",
            _account_row(
                settings.staff_loan_receivable_account,
                credit=self.amount,
                party_type="Employee",
                party=self.employee,
            ),
        )
        journal.insert(ignore_permissions=True)
        journal.flags.ignore_permissions = True
        journal.submit()
        return journal
