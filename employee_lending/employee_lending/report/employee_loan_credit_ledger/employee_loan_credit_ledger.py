import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = [
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 105},
        {"label": _("Employee Credit"), "fieldname": "employee_credit", "fieldtype": "Link", "options": "Employee Loan Credit", "width": 165},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": _("Transaction"), "fieldname": "transaction_type", "fieldtype": "Data", "width": 120},
        {"label": _("Voucher"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
        {"label": _("Employee Loan"), "fieldname": "loan_application", "fieldtype": "Link", "options": "Employee Loan Application", "width": 170},
        {"label": _("Credit Added"), "fieldname": "credit", "fieldtype": "Currency", "width": 115},
        {"label": _("Credit Used"), "fieldname": "debit", "fieldtype": "Currency", "width": 115},
        {"label": _("Available Credit"), "fieldname": "balance", "fieldtype": "Currency", "width": 130},
        {"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 260},
    ]
    conditions = ["1 = 1"]
    values = {}
    if filters.get("company"):
        conditions.append("credit.company = %(company)s")
        values["company"] = filters.company
    if filters.get("employee_credit"):
        conditions.append("credit.name = %(employee_credit)s")
        values["employee_credit"] = filters.employee_credit
    if filters.get("employee"):
        conditions.append("credit.employee = %(employee)s")
        values["employee"] = filters.employee
    if filters.get("to_date"):
        conditions.append("credit.cutoff_date <= %(to_date)s")
        values["to_date"] = filters.to_date

    credits = frappe.db.sql(
        f"""
        select credit.name, credit.cutoff_date, credit.employee, credit.employee_name,
               credit.company, credit.original_credit, credit.source_vouchers, credit.remarks
          from `tabEmployee Loan Credit` credit
         where {' and '.join(conditions)}
         order by credit.employee, credit.cutoff_date, credit.name
        """,
        values,
        as_dict=True,
    )
    data = []
    for credit in credits:
        data.append(
            frappe._dict(
                posting_date=credit.cutoff_date,
                employee_credit=credit.name,
                employee=credit.employee,
                employee_name=credit.employee_name,
                transaction_type="Opening Credit",
                voucher_type="",
                voucher_no="",
                loan_application="",
                debit=0,
                credit=credit.original_credit,
                remarks=credit.remarks or ("Existing JEs: " + (credit.source_vouchers or "")),
            )
        )
        adjustment_filters = {"employee_credit": credit.name, "docstatus": 1}
        adjustments = frappe.get_all(
            "Employee Loan Credit Adjustment",
            filters=adjustment_filters,
            fields=[
                "posting_date", "name", "adjustment_type", "amount", "journal_entry",
                "loan_application", "remarks",
            ],
            order_by="posting_date, creation, name",
            limit_page_length=0,
        )
        for adjustment in adjustments:
            if filters.get("to_date") and str(adjustment.posting_date) > str(filters.to_date):
                continue
            data.append(
                frappe._dict(
                    posting_date=adjustment.posting_date,
                    employee_credit=credit.name,
                    employee=credit.employee,
                    employee_name=credit.employee_name,
                    transaction_type=adjustment.adjustment_type,
                    voucher_type="Journal Entry",
                    voucher_no=adjustment.journal_entry,
                    loan_application=adjustment.loan_application,
                    debit=adjustment.amount,
                    credit=0,
                    remarks=adjustment.remarks,
                )
            )

    balances = {}
    for row in data:
        balances.setdefault(row.employee_credit, 0)
        balances[row.employee_credit] = flt(
            balances[row.employee_credit] + flt(row.credit) - flt(row.debit), 2
        )
        row.balance = balances[row.employee_credit]
    return columns, data
