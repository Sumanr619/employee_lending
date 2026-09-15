import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class StaffSalaryDeductionAuthority(Document):
    def validate(self):
        loan = frappe.db.get_value(
            "Employee Loan Application",
            self.loan_application,
            ["employee", "employee_name", "company", "department", "fortnightly_repayment", "total_outstanding", "loan_status", "docstatus"],
            as_dict=True,
        )
        if not loan or loan.docstatus != 1 or loan.loan_status not in ("Active", "Closed"):
            frappe.throw(_("Select a submitted employee loan"))
        self.employee = loan.employee
        self.employee_name = loan.employee_name
        self.company = loan.company
        self.department = loan.department
        self.balance_outstanding = loan.total_outstanding
        if self.action == "Commence" and not self.deduction_amount:
            self.deduction_amount = loan.fortnightly_repayment
        if self.action in ("Commence", "Adjust") and flt(self.deduction_amount) <= 0:
            frappe.throw(_("Deduction Amount must be greater than zero"))
        if self.action == "Cease":
            self.deduction_amount = 0

