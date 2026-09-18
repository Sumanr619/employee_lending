import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class EmployeeLoanCredit(Document):
    def before_insert(self):
        self.set_employee_details()
        self.recalculate()

    def validate(self):
        self.set_employee_details()
        self.recalculate()
        if flt(self.original_credit, 2) <= 0:
            frappe.throw(_("Employee credit must be greater than zero"))

    def set_employee_details(self):
        if not self.employee:
            return
        employee = frappe.db.get_value(
            "Employee", self.employee, ["employee_name", "company"], as_dict=True
        )
        if not employee:
            frappe.throw(_("Employee {0} does not exist").format(self.employee))
        self.employee_name = employee.employee_name
        self.company = employee.company

    def recalculate(self):
        self.original_principal_credit = flt(self.original_principal_credit, 2)
        self.original_interest_credit = flt(self.original_interest_credit, 2)
        self.original_credit = flt(
            self.original_principal_credit + self.original_interest_credit, 2
        )
        self.principal_credit_available = flt(self.principal_credit_available, 2)
        self.interest_credit_available = flt(self.interest_credit_available, 2)
        self.available_credit = flt(
            self.principal_credit_available + self.interest_credit_available, 2
        )


def refresh_credit_totals(credit_name):
    rows = frappe.db.sql(
        """
        select adjustment_type, sum(amount) as amount,
               sum(source_principal_component) as principal_component,
               sum(source_interest_component) as interest_component
          from `tabEmployee Loan Credit Adjustment`
         where employee_credit = %s and docstatus = 1
         group by adjustment_type
        """,
        credit_name,
        as_dict=True,
    )
    credit = frappe.db.get_value(
        "Employee Loan Credit",
        credit_name,
        [
            "original_principal_credit",
            "original_interest_credit",
            "original_credit",
        ],
        as_dict=True,
    )
    if not credit:
        frappe.throw(_("Employee Loan Credit {0} does not exist").format(credit_name))

    used_principal = flt(sum(flt(row.principal_component) for row in rows), 2)
    used_interest = flt(sum(flt(row.interest_component) for row in rows), 2)
    applied = flt(
        sum(flt(row.amount) for row in rows if row.adjustment_type == "Apply to Loan"), 2
    )
    refunded = flt(
        sum(flt(row.amount) for row in rows if row.adjustment_type == "Refund"), 2
    )
    principal_available = flt(max(0, flt(credit.original_principal_credit) - used_principal), 2)
    interest_available = flt(max(0, flt(credit.original_interest_credit) - used_interest), 2)
    available = flt(principal_available + interest_available, 2)
    if available <= 0.005:
        status = "Refunded" if refunded and not applied else "Applied" if applied and not refunded else "Closed"
    elif available < flt(credit.original_credit, 2) - 0.005:
        status = "Partly Used"
    else:
        status = "Available"
    frappe.db.set_value(
        "Employee Loan Credit",
        credit_name,
        {
            "principal_credit_available": principal_available,
            "interest_credit_available": interest_available,
            "available_credit": available,
            "applied_amount": applied,
            "refunded_amount": refunded,
            "status": status,
        },
        update_modified=False,
    )
