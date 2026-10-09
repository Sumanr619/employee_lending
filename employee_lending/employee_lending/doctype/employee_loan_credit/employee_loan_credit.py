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


def create_repayment_credit(
    *, employee, posting_date, source_reference, journal_entry, amount, remarks=None
):
    """Register the unapplied part of a repayment as employee credit.

    The Journal Entry already posts this amount as an unallocated party credit,
    so this function creates only the operational credit register record.
    """
    amount = flt(amount, 2)
    if amount <= 0:
        return None
    existing = frappe.db.get_value(
        "Employee Loan Credit", {"source_reference": source_reference}, "name"
    )
    if existing:
        return existing
    credit = frappe.get_doc(
        {
            "doctype": "Employee Loan Credit",
            "employee": employee,
            "cutoff_date": posting_date,
            "source_reference": source_reference,
            "source_vouchers": journal_entry,
            "original_principal_credit": amount,
            "original_interest_credit": 0,
            "principal_credit_available": amount,
            "interest_credit_available": 0,
            "remarks": remarks or _("Repayment overpayment held as employee credit"),
        }
    )
    credit.insert(ignore_permissions=True)
    return credit.name


def delete_unused_repayment_credit(credit_name):
    if not credit_name or not frappe.db.exists("Employee Loan Credit", credit_name):
        return
    adjustment = frappe.db.get_value(
        "Employee Loan Credit Adjustment",
        {"employee_credit": credit_name, "docstatus": 1},
        "name",
    )
    if adjustment:
        frappe.throw(
            _("Employee credit {0} has already been used by adjustment {1}. Cancel that adjustment first.").format(
                credit_name, adjustment
            )
        )
    frappe.delete_doc("Employee Loan Credit", credit_name, ignore_permissions=True)


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
