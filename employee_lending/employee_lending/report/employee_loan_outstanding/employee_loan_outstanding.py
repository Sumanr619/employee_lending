import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from employee_lending.employee_lending.balance_reporting import AGE_FIELDS, age_balance


AGE_LABELS = ("Current / Not Due", "1–30 Days", "31–60 Days", "61–90 Days",
              "91–180 Days", "181–365 Days", "Over 365 Days", "Unaged")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    as_of_date = getdate(filters.get("as_of_date") or nowdate())
    ageing_basis = filters.get("ageing_basis") or "Instalment Due Date"
    if ageing_basis not in ("Instalment Due Date", "Loan / Credit Date"):
        frappe.throw(_("Select a valid ageing basis"))
    include_credits = flt(filters.get("include_credits", 1)) != 0
    summary_view = filters.get("view") == "Employee Summary"
    columns = get_columns(summary_view)
    conditions = [
        "docstatus = 1", "loan_status in ('Active', 'Closed')",
        "disbursement_date is not null", "disbursement_date <= %(as_of_date)s",
    ]
    values = {"as_of_date": as_of_date}
    for field in ("company", "employee"):
        if filters.get(field):
            conditions.append(f"{field} = %({field})s")
            values[field] = filters.get(field)
    if filters.get("date"):
        conditions.append("application_date = %(date)s")
        values["date"] = filters.get("date")
    loans = frappe.db.sql(
        f"""
        select name, company, employee, employee_name, loan_product, approved_principal,
               disbursement_date, principal_outstanding, unearned_interest_outstanding,
               total_outstanding, fortnightly_repayment, loan_status
          from `tabEmployee Loan Application`
         where {' and '.join(conditions)}
         order by employee_name, disbursement_date, name
        """, values, as_dict=True,
    )
    names = [row.name for row in loans]
    future_allocations = get_future_allocations(names, as_of_date)
    schedules = get_schedules(names) if ageing_basis == "Instalment Due Date" else {}
    data = []
    for row in loans:
        future = future_allocations.get(row.name, frappe._dict())
        row.principal_outstanding = flt(max(0, flt(row.principal_outstanding) + flt(future.principal)), 2)
        row.unearned_interest_outstanding = flt(max(0, flt(row.unearned_interest_outstanding) + flt(future.interest)), 2)
        row.total_outstanding = flt(row.principal_outstanding + row.unearned_interest_outstanding, 2)
        row.loan_status = "Closed" if row.total_outstanding <= 0.005 else "Active"
        if filters.get("loan_status") and row.loan_status != filters.loan_status:
            continue
        row.record_type = "Loan"
        row.available_credit = 0
        row.net_outstanding = row.total_outstanding
        row.ageing_date = row.disbursement_date if ageing_basis == "Loan / Credit Date" else None
        row.update(age_balance(
            row.total_outstanding, as_of_date, schedules.get(row.name, ()),
            origin_date=row.disbursement_date, by_origin=ageing_basis == "Loan / Credit Date",
        ))
        if ageing_basis == "Instalment Due Date":
            row.ageing_date = row.oldest_unpaid_due_date
        data.append(row)
    # Credits are deliberately independent of loan-status filtering. This keeps
    # credit-only employees visible, even when the selected loan status is Active.
    if include_credits:
        for credit in get_credits_as_of(filters, as_of_date):
            row = frappe._dict(
                company=credit.company, employee=credit.employee, employee_name=credit.employee_name,
                record_type="Employee Credit", employee_credit=credit.name,
                approved_principal=0, principal_outstanding=0, unearned_interest_outstanding=0,
                total_outstanding=0, fortnightly_repayment=0, available_credit=credit.available,
                net_outstanding=-credit.available, loan_status="Available Credit",
                ageing_date=credit.cutoff_date,
            )
            row.update(age_balance(-credit.available, as_of_date, origin_date=credit.cutoff_date, by_origin=True))
            data.append(row)
    data.sort(key=lambda row: (row.employee_name or "", row.employee or "", row.company or "",
                               row.record_type or "", row.get("name") or row.get("employee_credit") or ""))
    if summary_view:
        data = summarize_employees(data)
    totals = {field: flt(sum(flt(row.get(field)) for row in data), 2)
              for field in ("total_outstanding", "available_credit", "net_outstanding")}
    report_summary = [
        {"label": _("Gross Loan Outstanding"), "value": totals["total_outstanding"], "datatype": "Currency"},
        {"label": _("Available Employee Credit"), "value": totals["available_credit"], "datatype": "Currency"},
        {"label": _("Net Outstanding"), "value": totals["net_outstanding"], "datatype": "Currency"},
    ]
    message = _("As of {0}. Loan balances are positive; employee credits and their age buckets are negative. "
                "Credits age from their credit date and remain unallocated until a Credit Adjustment is submitted. "
                "The loan Status filter applies only to loan rows. Missing schedule coverage or dates appears in Unaged.").format(as_of_date)
    return columns, data, message, None, report_summary


def get_columns(summary_view=False):
    columns = [
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 110},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
    ]
    if not summary_view:
        columns.extend([
            {"label": _("Type"), "fieldname": "record_type", "fieldtype": "Data", "width": 125},
            {"label": _("Loan"), "fieldname": "name", "fieldtype": "Link", "options": "Employee Loan Application", "width": 170},
            {"label": _("Employee Credit"), "fieldname": "employee_credit", "fieldtype": "Link", "options": "Employee Loan Credit", "width": 170},
            {"label": _("Product"), "fieldname": "loan_product", "fieldtype": "Link", "options": "Employee Loan Product", "width": 180},
        ])
    for label, field in (("Original Principal", "approved_principal"), ("Principal Outstanding", "principal_outstanding"),
                         ("Unearned Interest", "unearned_interest_outstanding"), ("Gross Loan Outstanding", "total_outstanding"),
                         ("Available Credit", "available_credit"), ("Net Outstanding", "net_outstanding")):
        columns.append({"label": _(label), "fieldname": field, "fieldtype": "Currency", "width": 145})
    for field, label in zip(AGE_FIELDS, AGE_LABELS):
        columns.append({"label": _(label), "fieldname": field, "fieldtype": "Currency", "width": 125})
    if not summary_view:
        columns.extend([
            {"label": _("Ageing Date"), "fieldname": "ageing_date", "fieldtype": "Date", "width": 110},
            {"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Data", "width": 110},
            {"label": _("Fortnightly"), "fieldname": "fortnightly_repayment", "fieldtype": "Currency", "width": 110},
            {"label": _("Status"), "fieldname": "loan_status", "fieldtype": "Data", "width": 120},
        ])
    return columns


def get_schedules(loan_names):
    schedules = {}
    if loan_names:
        for row in frappe.db.sql(
            """select parent, due_date, repayment_amount
                 from `tabEmployee Loan Schedule`
                where parenttype = 'Employee Loan Application' and parent in %(loans)s
                order by parent, idx""", {"loans": tuple(loan_names)}, as_dict=True,
        ):
            schedules.setdefault(row.parent, []).append(row)
    return schedules


def get_credits_as_of(filters, as_of_date):
    conditions = ["credit.cutoff_date <= %(as_of_date)s"]
    values = {"as_of_date": as_of_date}
    for field in ("company", "employee"):
        if filters.get(field):
            conditions.append(f"credit.{field} = %({field})s")
            values[field] = filters.get(field)
    # Reconstruct from original credit and dated, currently submitted uses.
    # Today's available_credit/status must not filter historical credit balances.
    return frappe.db.sql(
        f"""select credit.name, credit.company, credit.employee, credit.employee_name,
                   credit.cutoff_date,
                   round(credit.original_credit - coalesce(used.amount, 0), 2) as available
              from `tabEmployee Loan Credit` credit
              left join (
                  select employee_credit, sum(amount) as amount
                    from `tabEmployee Loan Credit Adjustment`
                   where docstatus = 1 and posting_date <= %(as_of_date)s
                   group by employee_credit
              ) used on used.employee_credit = credit.name
             where {' and '.join(conditions)}
               and round(credit.original_credit - coalesce(used.amount, 0), 2) > 0
             order by credit.employee_name, credit.cutoff_date, credit.name""",
        values, as_dict=True,
    )


def summarize_employees(rows):
    fields = ("approved_principal", "principal_outstanding", "unearned_interest_outstanding",
              "total_outstanding", "available_credit", "net_outstanding") + AGE_FIELDS
    grouped = {}
    for row in rows:
        key = (row.company, row.employee)
        if key not in grouped:
            grouped[key] = frappe._dict(company=row.company, employee=row.employee, employee_name=row.employee_name,
                                       **{field: 0 for field in fields})
        for field in fields:
            grouped[key][field] = flt(grouped[key][field] + flt(row.get(field)), 2)
    return list(grouped.values())


def get_future_allocations(loan_names, as_of_date):
    """Return submitted loan reductions posted after the report date.

    The loan master stores today's balance. Adding later reductions back gives
    the balance at the selected date without duplicating opening logic for
    normal and legacy loans.
    """
    allocations = {}
    if not loan_names:
        return allocations

    values = {"loan_names": tuple(loan_names), "as_of_date": as_of_date}
    queries = [
        """
        select repayment.loan_application,
               coalesce(sum(repayment.principal_component), 0) as principal,
               coalesce(sum(repayment.interest_component), 0) as interest
          from `tabEmployee Loan Repayment` repayment
         where repayment.docstatus = 1
           and repayment.posting_date > %(as_of_date)s
           and repayment.loan_application in %(loan_names)s
         group by repayment.loan_application
        """,
        """
        select item.loan_application,
               coalesce(sum(item.principal_component), 0) as principal,
               coalesce(sum(item.interest_component), 0) as interest
          from `tabEmployee Loan Repayment Batch Item` item
          inner join `tabEmployee Loan Repayment Batch` batch
                  on batch.name = item.parent
                 and item.parenttype = 'Employee Loan Repayment Batch'
         where batch.docstatus = 1
           and batch.posting_date > %(as_of_date)s
           and item.loan_application in %(loan_names)s
         group by item.loan_application
        """,
        """
        select adjustment.loan_application,
               coalesce(sum(adjustment.loan_principal_component), 0) as principal,
               coalesce(sum(adjustment.loan_interest_component), 0) as interest
          from `tabEmployee Loan Credit Adjustment` adjustment
         where adjustment.docstatus = 1
           and adjustment.adjustment_type = 'Apply to Loan'
           and adjustment.posting_date > %(as_of_date)s
           and adjustment.loan_application in %(loan_names)s
         group by adjustment.loan_application
        """,
    ]
    for query in queries:
        for row in frappe.db.sql(query, values, as_dict=True):
            allocation = allocations.setdefault(
                row.loan_application, frappe._dict(principal=0, interest=0)
            )
            allocation.principal = flt(
                allocation.principal + flt(row.principal), 2
            )
            allocation.interest = flt(
                allocation.interest + flt(row.interest), 2
            )
    return allocations
