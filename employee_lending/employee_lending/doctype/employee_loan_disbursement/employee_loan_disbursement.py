import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, nowdate

from employee_lending.employee_lending.accounting import cancel_linked_journal_entry, create_disbursement_journal
from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings


LOAN_FIELDS = [
    "name",
    "employee",
    "employee_name",
    "company",
    "approved_principal",
    "total_interest",
    "total_amount_due",
    "loan_status",
    "approval_status",
    "loan_disbursement",
    "docstatus",
]


class EmployeeLoanDisbursement(Document):
    def before_insert(self):
        if not self.posting_date:
            self.posting_date = nowdate()

    def validate(self):
        self.set_loan_details(lock=False)
        self.set_defaults()
        self.validate_bank_account()

    def before_submit(self):
        self.set_loan_details(lock=True)
        settings = get_settings()
        if settings.require_disbursement_attachment and not self.proof_of_payment:
            frappe.throw(_("Proof of Payment is required"))

    def on_submit(self):
        loan = frappe.get_doc("Employee Loan Application", self.loan_application)
        journal = create_disbursement_journal(loan, self)
        self.db_set("journal_entry", journal.name, update_modified=False)
        frappe.db.set_value(
            "Employee Loan Application",
            self.loan_application,
            {
                "loan_status": "Active",
                "loan_disbursement": self.name,
                "disbursement_journal_entry": journal.name,
                "disbursement_date": self.posting_date,
                "first_repayment_date": self.first_repayment_date,
            },
            update_modified=False,
        )
        self.update_schedule_dates(self.first_repayment_date)

    def before_cancel(self):
        if frappe.db.exists("Employee Loan Repayment", {"loan_application": self.loan_application, "docstatus": 1}):
            frappe.throw(_("Cancel all submitted repayments before cancelling this disbursement"))
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
            frappe.throw(_("Cancel repayment batch {0} before cancelling this disbursement").format(batch[0][0]))

    def on_cancel(self):
        cancel_linked_journal_entry(self.journal_entry)
        frappe.db.set_value(
            "Employee Loan Application",
            self.loan_application,
            {
                "loan_status": "Approved",
                "loan_disbursement": None,
                "disbursement_journal_entry": None,
                "disbursement_date": None,
                "first_repayment_date": None,
            },
            update_modified=False,
        )
        self.update_schedule_dates(None)

    def set_loan_details(self, lock=False):
        if not self.loan_application:
            return
        if lock:
            result = frappe.db.sql(
                f"select {', '.join(LOAN_FIELDS)} from `tabEmployee Loan Application` where name = %s for update",
                self.loan_application,
                as_dict=True,
            )
            loan = result[0] if result else None
        else:
            loan = frappe.db.get_value("Employee Loan Application", self.loan_application, LOAN_FIELDS, as_dict=True)
        if not loan or loan.docstatus != 1 or loan.approval_status != "Approved":
            frappe.throw(_("Select a submitted and approved employee loan"))
        if loan.loan_status != "Approved":
            frappe.throw(_("Loan {0} is not awaiting disbursement").format(loan.name))
        if loan.loan_disbursement and loan.loan_disbursement != self.name:
            frappe.throw(_("Loan {0} has already been disbursed through {1}").format(loan.name, loan.loan_disbursement))
        self.employee = loan.employee
        self.employee_name = loan.employee_name
        self.company = loan.company
        self.disbursement_amount = loan.approved_principal
        self.total_interest = loan.total_interest
        self.gross_loan_receivable = loan.total_amount_due

    def set_defaults(self):
        settings = get_settings()
        if not self.bank_account:
            self.bank_account = settings.disbursement_bank_account
        if not self.first_repayment_date and self.posting_date:
            self.first_repayment_date = add_days(getdate(self.posting_date), 14)

    def validate_bank_account(self):
        settings = get_settings()
        if self.bank_account != settings.disbursement_bank_account and not settings.allow_account_override:
            frappe.throw(_("Account override is disabled in Employee Lending Settings"))
        account = frappe.db.get_value(
            "Account", self.bank_account, ["company", "is_group", "disabled", "root_type"], as_dict=True
        )
        if (
            not account
            or account.company != self.company
            or account.is_group
            or account.disabled
            or account.root_type != "Asset"
        ):
            frappe.throw(_("Select an active Asset ledger account belonging to {0}").format(self.company))

    def update_schedule_dates(self, first_repayment_date):
        rows = frappe.get_all(
            "Employee Loan Schedule",
            filters={"parent": self.loan_application, "parenttype": "Employee Loan Application"},
            fields=["name", "idx"],
            order_by="idx asc",
        )
        for row in rows:
            due_date = add_days(getdate(first_repayment_date), (row.idx - 1) * 14) if first_repayment_date else None
            frappe.db.set_value("Employee Loan Schedule", row.name, "due_date", due_date, update_modified=False)


@frappe.whitelist()
def get_disbursement_details(loan_application):
    loan = frappe.get_doc("Employee Loan Application", loan_application)
    loan.check_permission("read")
    if loan.docstatus != 1 or loan.approval_status != "Approved" or loan.loan_status != "Approved":
        frappe.throw(_("Select a submitted approved loan awaiting disbursement"))
    settings = get_settings()
    return {
        "employee": loan.employee,
        "employee_name": loan.employee_name,
        "company": loan.company,
        "disbursement_amount": loan.approved_principal,
        "total_interest": loan.total_interest,
        "gross_loan_receivable": loan.total_amount_due,
        "bank_account": settings.disbursement_bank_account,
        "first_repayment_date": add_days(nowdate(), 14),
        "allow_account_override": settings.allow_account_override,
    }

