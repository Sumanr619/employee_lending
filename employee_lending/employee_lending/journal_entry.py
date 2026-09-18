import frappe
from frappe import _


def prevent_orphaned_lending_entry(doc, method=None):
    if doc.flags.get("employee_lending_internal_cancel"):
        return
    disbursement = frappe.db.get_value(
        "Employee Loan Disbursement",
        {"journal_entry": doc.name, "docstatus": 1},
        "name",
    )
    if disbursement:
        frappe.throw(
            _("Journal Entry {0} belongs to employee loan disbursement {1}. Cancel the disbursement instead.").format(
                doc.name, disbursement
            )
        )
    loan = frappe.db.get_value(
        "Employee Loan Application",
        {"disbursement_journal_entry": doc.name, "docstatus": 1},
        "name",
    )
    if loan:
        frappe.throw(
            _("Journal Entry {0} belongs to active employee loan {1}. Cancel the loan document instead.").format(
                doc.name, loan
            )
        )
    repayment = frappe.db.get_value(
        "Employee Loan Repayment",
        {"journal_entry": doc.name, "docstatus": 1},
        "name",
    )
    if repayment:
        frappe.throw(
            _("Journal Entry {0} belongs to employee loan repayment {1}. Cancel the repayment instead.").format(
                doc.name, repayment
            )
        )
    batch = frappe.db.get_value(
        "Employee Loan Repayment Batch",
        {"journal_entry": doc.name, "docstatus": 1},
        "name",
    )
    if batch:
        frappe.throw(
            _("Journal Entry {0} belongs to employee loan repayment batch {1}. Cancel the batch instead.").format(
                doc.name, batch
            )
        )

    credit_adjustment = frappe.db.get_value(
        "Employee Loan Credit Adjustment",
        {"journal_entry": doc.name, "docstatus": 1},
        "name",
    )
    if credit_adjustment:
        frappe.throw(
            _("Journal Entry {0} belongs to employee loan credit adjustment {1}. Cancel the adjustment instead.").format(
                doc.name, credit_adjustment
            )
        )

    legacy_rows = frappe.db.sql(
        """
        select name
          from `tabEmployee Loan Legacy Opening`
         where docstatus = 1
           and (conversion_journal_entry = %s or cleanup_journal_entry = %s)
         limit 1
        """,
        (doc.name, doc.name),
    )
    legacy_opening = legacy_rows[0][0] if legacy_rows else None
    if legacy_opening:
        frappe.throw(
            _("Journal Entry {0} belongs to legacy loan opening {1}. Cancel the legacy opening instead.").format(
                doc.name, legacy_opening
            )
        )
