import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = [
        {"label": _("Loan"), "fieldname": "name", "fieldtype": "Link", "options": "Employee Loan Application", "width": 170},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": _("Product"), "fieldname": "loan_product", "fieldtype": "Link", "options": "Employee Loan Product", "width": 180},
        {"label": _("Principal"), "fieldname": "approved_principal", "fieldtype": "Currency", "width": 110},
        {"label": _("Principal Outstanding"), "fieldname": "principal_outstanding", "fieldtype": "Currency", "width": 150},
        {"label": _("Unearned Interest"), "fieldname": "unearned_interest_outstanding", "fieldtype": "Currency", "width": 140},
        {"label": _("Total Outstanding"), "fieldname": "total_outstanding", "fieldtype": "Currency", "width": 140},
        {"label": _("Fortnightly"), "fieldname": "fortnightly_repayment", "fieldtype": "Currency", "width": 110},
        {"label": _("Status"), "fieldname": "loan_status", "fieldtype": "Data", "width": 90},
    ]
    conditions = ["docstatus = 1", "loan_status in ('Active', 'Closed')"]
    values = {}
    if filters.get("company"):
        conditions.append("company = %(company)s")
        values["company"] = filters.company
    if filters.get("employee"):
        conditions.append("employee = %(employee)s")
        values["employee"] = filters.employee
    if filters.get("loan_status"):
        conditions.append("loan_status = %(loan_status)s")
        values["loan_status"] = filters.loan_status
    data = frappe.db.sql(
        f"""
        select name, employee, employee_name, loan_product, approved_principal,
               principal_outstanding, unearned_interest_outstanding,
               total_outstanding, fortnightly_repayment, loan_status
          from `tabEmployee Loan Application`
         where {' and '.join(conditions)}
         order by employee_name, disbursement_date
        """,
        values,
        as_dict=True,
    )
    return columns, data
