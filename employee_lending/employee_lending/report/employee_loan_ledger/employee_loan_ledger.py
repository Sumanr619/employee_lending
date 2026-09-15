import frappe
from frappe import _
from frappe.utils import flt

from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings


def execute(filters=None):
    filters = frappe._dict(filters or {})
    settings = get_settings()
    columns = [
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 105},
        {"label": _("Employee Loan"), "fieldname": "employee_loan", "fieldtype": "Link", "options": "Employee Loan Application", "width": 170},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
        {"label": _("Voucher"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
        {"label": _("Entry Source"), "fieldname": "entry_source", "fieldtype": "Data", "width": 120},
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 200},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "width": 110},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "width": 110},
        {"label": _("Loan Balance"), "fieldname": "loan_balance", "fieldtype": "Currency", "width": 125},
        {"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 240},
    ]
    conditions = [
        "gle.is_cancelled = 0",
        "loan.docstatus = 1",
        "gle.account = %(staff_loan_account)s",
        "loan.disbursement_journal_entry is not null",
        "loan.disbursement_journal_entry != ''",
        "((gle.voucher_no = loan.disbursement_journal_entry and not exists ("
        "select 1 from `tabEmployee Loan Legacy Transaction` legacy_txn "
        "where legacy_txn.loan_application = loan.name)) or "
        "(gle.against_voucher_type = 'Journal Entry' and "
        "gle.against_voucher = loan.disbursement_journal_entry))",
    ]
    values = {"staff_loan_account": settings.staff_loan_receivable_account}
    if filters.get("company"):
        conditions.append("gle.company = %(company)s")
        values["company"] = filters.company
    if filters.get("employee_loan"):
        conditions.append("loan.name = %(employee_loan)s")
        values["employee_loan"] = filters.employee_loan
    if filters.get("employee"):
        conditions.append("loan.employee = %(employee)s")
        values["employee"] = filters.employee
    if filters.get("to_date"):
        conditions.append("gle.posting_date <= %(to_date)s")
        values["to_date"] = filters.to_date

    data = frappe.db.sql(
        f"""
        select gle.posting_date, loan.name as employee_loan,
               loan.employee, loan.employee_name, gle.voucher_type,
               gle.voucher_no, 'Module GL' as entry_source, gle.account,
               gle.debit, gle.credit, gle.remarks
          from `tabGL Entry` gle
          inner join `tabEmployee Loan Application` loan
                  on (
                       gle.voucher_no = loan.disbursement_journal_entry
                       or (
                            gle.against_voucher_type = 'Journal Entry'
                            and gle.against_voucher = loan.disbursement_journal_entry
                       )
                  )
         where {' and '.join(conditions)}
         order by loan.name, gle.posting_date, gle.creation, gle.name
        """,
        values,
        as_dict=True,
    )
    legacy_conditions = ["loan.docstatus = 1"]
    if filters.get("company"):
        legacy_conditions.append("loan.company = %(company)s")
    if filters.get("employee_loan"):
        legacy_conditions.append("loan.name = %(employee_loan)s")
    if filters.get("employee"):
        legacy_conditions.append("loan.employee = %(employee)s")
    if filters.get("to_date"):
        legacy_conditions.append("history.posting_date <= %(to_date)s")
    legacy_data = frappe.db.sql(
        f"""
        select history.posting_date, loan.name as employee_loan,
               loan.employee, loan.employee_name, 'Journal Entry' as voucher_type,
               history.journal_entry as voucher_no, 'Historical JE' as entry_source,
               %(staff_loan_account)s as account, history.debit, history.credit,
               concat(history.transaction_type, ': ', ifnull(history.remarks, '')) as remarks
          from `tabEmployee Loan Legacy Transaction` history
          inner join `tabEmployee Loan Application` loan
                  on loan.name = history.loan_application
         where {' and '.join(legacy_conditions)}
        """,
        values,
        as_dict=True,
    )
    data.extend(legacy_data)
    data.sort(
        key=lambda row: (
            row.employee_loan,
            str(row.posting_date),
            0 if row.entry_source == "Historical JE" else 1,
            row.voucher_no,
        )
    )
    balances = {}
    for row in data:
        balances.setdefault(row.employee_loan, 0)
        balances[row.employee_loan] = flt(balances[row.employee_loan] + row.debit - row.credit, 2)
        row.loan_balance = balances[row.employee_loan]
    return columns, data
