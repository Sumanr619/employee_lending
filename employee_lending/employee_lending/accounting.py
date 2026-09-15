import frappe
from frappe import _

from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings


def _account_row(
    account,
    debit=0,
    credit=0,
    cost_center=None,
    reference_type=None,
    reference_name=None,
    party_type=None,
    party=None,
):
    row = {
        "account": account,
        "debit_in_account_currency": debit,
        "credit_in_account_currency": credit,
    }
    if cost_center:
        row["cost_center"] = cost_center
    if reference_type and reference_name:
        row["reference_type"] = reference_type
        row["reference_name"] = reference_name
    if party_type and party:
        row["party_type"] = party_type
        row["party"] = party
    return row


def _loan_journal_reference(loan_name, disbursement_journal_entry=None):
    """Return the valid ERPNext receivable/payable reference for a loan.

    Journal Entry Account does not allow custom doctypes in reference_type.
    Each employee loan has one unique disbursement Journal Entry, which is the
    original receivable/payable voucher that repayments must reconcile against.
    """
    journal_entry = disbursement_journal_entry or frappe.db.get_value(
        "Employee Loan Application", loan_name, "disbursement_journal_entry"
    )
    if not journal_entry:
        frappe.throw(
            _("Loan {0} has no submitted disbursement Journal Entry to reconcile against").format(loan_name)
        )
    return "Journal Entry", journal_entry


def create_disbursement_journal(loan, disbursement=None):
    settings = get_settings()
    if loan.company != settings.company:
        frappe.throw(_("The loan company must match Employee Lending Settings"))

    journal = frappe.new_doc("Journal Entry")
    journal.company = loan.company
    journal.posting_date = disbursement.posting_date if disbursement else loan.disbursement_date
    journal.voucher_type = "Bank Entry"
    journal.finance_book = settings.finance_book
    if disbursement and disbursement.bank_reference:
        journal.cheque_no = disbursement.bank_reference
        journal.cheque_date = disbursement.posting_date
    journal.user_remark = _("Employee loan disbursement {0} for {1}").format(loan.name, loan.employee_name)
    journal.append(
        "accounts",
        _account_row(
            settings.staff_loan_receivable_account,
            debit=loan.total_amount_due,
            party_type="Employee",
            party=loan.employee,
        ),
    )
    bank_account = disbursement.bank_account if disbursement else settings.disbursement_bank_account
    journal.append("accounts", _account_row(bank_account, credit=loan.approved_principal))
    if loan.total_interest:
        journal.append(
            "accounts",
            _account_row(
                settings.unearned_interest_account,
                credit=loan.total_interest,
                party_type="Employee",
                party=loan.employee,
            ),
        )
    journal.insert(ignore_permissions=True)
    journal.flags.ignore_permissions = True
    journal.submit()
    return journal


def create_batch_repayment_journal(batch):
    settings = get_settings()
    debit_account = batch.bank_or_clearing_account or settings.repayment_bank_or_clearing_account
    if debit_account != settings.repayment_bank_or_clearing_account and not settings.allow_account_override:
        frappe.throw(_("Account override is disabled in Employee Lending Settings"))

    journal = frappe.new_doc("Journal Entry")
    journal.company = batch.company
    journal.posting_date = batch.posting_date
    journal.voucher_type = "Bank Entry"
    journal.finance_book = settings.finance_book
    journal.cheque_no = batch.batch_reference
    journal.cheque_date = batch.posting_date
    journal.user_remark = _("Consolidated employee loan repayment batch {0} - {1} employee loan(s)").format(
        batch.name, len(batch.repayments)
    )
    journal.append("accounts", _account_row(debit_account, debit=batch.total_repayment_amount))
    for repayment in batch.repayments:
        reference_type, reference_name = _loan_journal_reference(repayment.loan_application)
        journal.append(
            "accounts",
            _account_row(
                settings.staff_loan_receivable_account,
                credit=repayment.repayment_amount,
                reference_type=reference_type,
                reference_name=reference_name,
                party_type="Employee",
                party=repayment.employee,
            ),
        )
    if batch.total_interest_component:
        for repayment in batch.repayments:
            if not repayment.interest_component:
                continue
            reference_type, reference_name = _loan_journal_reference(repayment.loan_application)
            journal.append(
                "accounts",
                _account_row(
                    settings.unearned_interest_account,
                    debit=repayment.interest_component,
                    reference_type=reference_type,
                    reference_name=reference_name,
                    party_type="Employee",
                    party=repayment.employee,
                ),
            )
        journal.append(
            "accounts",
            _account_row(
                settings.interest_income_account,
                credit=batch.total_interest_component,
                cost_center=settings.default_cost_center,
            ),
        )
    journal.insert(ignore_permissions=True)
    journal.flags.ignore_permissions = True
    journal.submit()
    return journal


def create_repayment_journal(repayment, loan):
    settings = get_settings()
    debit_account = repayment.bank_or_clearing_account or settings.repayment_bank_or_clearing_account
    if debit_account != settings.repayment_bank_or_clearing_account and not settings.allow_account_override:
        frappe.throw(_("Account override is disabled in Employee Lending Settings"))

    journal = frappe.new_doc("Journal Entry")
    journal.company = loan.company
    journal.posting_date = repayment.posting_date
    journal.voucher_type = "Bank Entry"
    journal.finance_book = settings.finance_book
    journal.cheque_no = repayment.bank_reference
    journal.cheque_date = repayment.posting_date if repayment.bank_reference else None
    journal.user_remark = _("Employee loan repayment {0} against {1} for {2}").format(
        repayment.name, loan.name, loan.employee_name
    )
    reference_type, reference_name = _loan_journal_reference(
        loan.name, loan.disbursement_journal_entry
    )
    journal.append("accounts", _account_row(debit_account, debit=repayment.repayment_amount))
    journal.append(
        "accounts",
        _account_row(
            settings.staff_loan_receivable_account,
            credit=repayment.repayment_amount,
            reference_type=reference_type,
            reference_name=reference_name,
            party_type="Employee",
            party=loan.employee,
        ),
    )
    journal.append(
        "accounts",
        _account_row(
            settings.unearned_interest_account,
            debit=repayment.interest_component,
            reference_type=reference_type,
            reference_name=reference_name,
            party_type="Employee",
            party=loan.employee,
        ),
    )
    journal.append(
        "accounts",
        _account_row(
            settings.interest_income_account,
            credit=repayment.interest_component,
            cost_center=settings.default_cost_center,
        ),
    )
    journal.insert(ignore_permissions=True)
    journal.flags.ignore_permissions = True
    journal.submit()
    return journal


def create_legacy_conversion_journals(opening, loan, conversion):
    settings = get_settings()
    if not settings.legacy_temporary_account:
        frappe.throw(_("Configure Legacy Temporary Account in Employee Lending Settings"))

    cleanup = frappe.new_doc("Journal Entry")
    cleanup.company = opening.company
    cleanup.posting_date = opening.cutoff_date
    cleanup.voucher_type = "Journal Entry"
    cleanup.finance_book = settings.finance_book
    cleanup.user_remark = _(
        "Legacy employee loan cleanup {0} for {1}. No bank movement. Source vouchers: {2}"
    ).format(opening.name, opening.employee_name, opening.source_journal_entries or "Not recorded")
    cleanup.append(
        "accounts",
        _account_row(
            settings.legacy_temporary_account,
            debit=float(conversion.cleanup_temporary_debit),
        ),
    )
    cleanup.append(
        "accounts",
        _account_row(
            settings.staff_loan_receivable_account,
            credit=float(conversion.cleanup_staff_loan_credit),
            party_type="Employee",
            party=opening.employee,
        ),
    )
    if conversion.cleanup_unearned_interest_credit:
        cleanup.append(
            "accounts",
            _account_row(
                settings.unearned_interest_account,
                credit=float(conversion.cleanup_unearned_interest_credit),
                party_type="Employee",
                party=opening.employee,
            ),
        )
    cleanup.insert(ignore_permissions=True)
    cleanup.flags.ignore_permissions = True
    cleanup.submit()

    journal = frappe.new_doc("Journal Entry")
    journal.company = opening.company
    journal.posting_date = opening.cutoff_date
    journal.voucher_type = "Journal Entry"
    journal.finance_book = settings.finance_book
    journal.user_remark = _(
        "Legacy employee loan clean opening {0} for {1}. No bank movement."
    ).format(opening.name, opening.employee_name)
    journal.append(
        "accounts",
        _account_row(
            settings.staff_loan_receivable_account,
            debit=float(conversion.opening_staff_loan_debit),
            party_type="Employee",
            party=opening.employee,
        ),
    )
    journal.append(
        "accounts",
        _account_row(
            settings.legacy_temporary_account,
            credit=float(conversion.opening_temporary_credit),
        ),
    )
    if conversion.opening_unearned_interest_credit:
        journal.append(
            "accounts",
            _account_row(
                settings.unearned_interest_account,
                credit=float(conversion.opening_unearned_interest_credit),
                party_type="Employee",
                party=opening.employee,
            ),
        )
    journal.insert(ignore_permissions=True)
    journal.flags.ignore_permissions = True
    journal.submit()
    return cleanup, journal


def cancel_linked_journal_entry(journal_entry):
    if not journal_entry or not frappe.db.exists("Journal Entry", journal_entry):
        return
    journal = frappe.get_doc("Journal Entry", journal_entry)
    journal.flags.employee_lending_internal_cancel = True
    if journal.docstatus == 1:
        journal.flags.ignore_permissions = True
        journal.cancel()
    elif journal.docstatus == 0:
        frappe.delete_doc("Journal Entry", journal.name, ignore_permissions=True)
