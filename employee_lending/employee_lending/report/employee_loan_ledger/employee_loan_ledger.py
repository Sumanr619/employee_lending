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
        {"label": _("Employee Credit"), "fieldname": "employee_credit", "fieldtype": "Link", "options": "Employee Loan Credit", "width": 165},
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
               loan.employee, loan.employee_name, loan.company,
               loan.payroll_number, loan.department, loan.designation,
               loan.loan_product, loan.application_date, loan.disbursement_date,
               loan.first_repayment_date, loan.approved_principal,
               loan.tenure_months, loan.number_of_fortnights,
               loan.flat_interest_rate, loan.total_interest,
               loan.total_amount_due, loan.fortnightly_repayment,
               loan.principal_outstanding, loan.unearned_interest_outstanding,
               loan.total_outstanding, loan.principal_recovered,
               loan.interest_earned, loan.total_repaid, loan.loan_status,
               loan.is_legacy_opening, gle.voucher_type,
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
               loan.employee, loan.employee_name, loan.company,
               loan.payroll_number, loan.department, loan.designation,
               loan.loan_product, loan.application_date, loan.disbursement_date,
               loan.first_repayment_date, loan.approved_principal,
               loan.tenure_months, loan.number_of_fortnights,
               loan.flat_interest_rate, loan.total_interest,
               loan.total_amount_due, loan.fortnightly_repayment,
               loan.principal_outstanding, loan.unearned_interest_outstanding,
               loan.total_outstanding, loan.principal_recovered,
               loan.interest_earned, loan.total_repaid, loan.loan_status,
               loan.is_legacy_opening, 'Journal Entry' as voucher_type,
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
    append_employee_credit_rows(data, filters)
    data.sort(
        key=lambda row: (
            str(row.get("_balance_key") or row.get("employee_loan") or ""),
            str(row.posting_date),
            0 if row.entry_source == "Historical JE" else 1,
            row.voucher_no or "",
        )
    )
    balances = {}
    for row in data:
        balance_key = row.get("_balance_key") or row.get("employee_loan") or "unlinked"
        balances.setdefault(balance_key, 0)
        balances[balance_key] = flt(balances[balance_key] + row.debit - row.credit, 2)
        row.loan_balance = balances[balance_key]
    return columns, data


def append_employee_credit_rows(data, filters):
    """Include imported overpayments and later refund/application activity.

    Existing Journal Entries are referenced only.  This report code does not
    create accounting entries.
    """
    conditions = ["1 = 1"]
    values = {}
    if filters.get("company"):
        conditions.append("credit.company = %(credit_company)s")
        values["credit_company"] = filters.company
    if filters.get("employee"):
        conditions.append("credit.employee = %(credit_employee)s")
        values["credit_employee"] = filters.employee
    if filters.get("to_date"):
        conditions.append("credit.cutoff_date <= %(credit_to_date)s")
        values["credit_to_date"] = filters.to_date

    credits = frappe.db.sql(
        f"""
        select credit.name, credit.cutoff_date, credit.employee, credit.employee_name,
               credit.company, credit.original_credit, credit.source_vouchers, credit.remarks
          from `tabEmployee Loan Credit` credit
         where {' and '.join(conditions)}
        """,
        values,
        as_dict=True,
    )
    for credit in credits:
        credit_key = "credit:" + credit.name
        if not filters.get("employee_loan"):
            data.append(
                frappe._dict(
                    posting_date=credit.cutoff_date,
                    employee_loan="",
                    employee_credit=credit.name,
                    employee=credit.employee,
                    employee_name=credit.employee_name,
                    company=credit.company,
                    voucher_type="",
                    voucher_no="",
                    entry_source="Employee Credit",
                    account="",
                    debit=0,
                    credit=credit.original_credit,
                    remarks=credit.remarks or ("Existing JEs: " + (credit.source_vouchers or "")),
                    _balance_key=credit_key,
                )
            )

        adjustments = frappe.get_all(
            "Employee Loan Credit Adjustment",
            filters={"employee_credit": credit.name, "docstatus": 1},
            fields=[
                "posting_date", "adjustment_type", "amount", "journal_entry",
                "loan_application", "remarks",
            ],
            order_by="posting_date, creation, name",
            limit_page_length=0,
        )
        for adjustment in adjustments:
            if filters.get("to_date") and str(adjustment.posting_date) > str(filters.to_date):
                continue
            if not filters.get("employee_loan"):
                data.append(
                    frappe._dict(
                        posting_date=adjustment.posting_date,
                        employee_loan="",
                        employee_credit=credit.name,
                        employee=credit.employee,
                        employee_name=credit.employee_name,
                        company=credit.company,
                        voucher_type="Journal Entry",
                        voucher_no=adjustment.journal_entry,
                        entry_source="Credit " + adjustment.adjustment_type,
                        account="",
                        debit=adjustment.amount,
                        credit=0,
                        remarks=adjustment.remarks,
                        _balance_key=credit_key,
                    )
                )
            if adjustment.adjustment_type == "Apply to Loan" and (
                not filters.get("employee_loan") or filters.employee_loan == adjustment.loan_application
            ):
                data.append(
                    frappe._dict(
                        posting_date=adjustment.posting_date,
                        employee_loan=adjustment.loan_application,
                        employee_credit=credit.name,
                        employee=credit.employee,
                        employee_name=credit.employee_name,
                        company=credit.company,
                        voucher_type="Journal Entry",
                        voucher_no=adjustment.journal_entry,
                        entry_source="Employee Credit Applied",
                        account="",
                        debit=0,
                        credit=adjustment.amount,
                        remarks=adjustment.remarks,
                        _balance_key=adjustment.loan_application,
                    )
                )
