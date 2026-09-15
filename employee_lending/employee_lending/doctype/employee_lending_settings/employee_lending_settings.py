import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeLendingSettings(Document):
    def validate(self):
        account_fields = (
            "staff_loan_receivable_account",
            "unearned_interest_account",
            "interest_income_account",
            "disbursement_bank_account",
            "repayment_bank_or_clearing_account",
            "legacy_temporary_account",
        )
        for fieldname in account_fields:
            account = self.get(fieldname)
            if not account:
                continue
            details = frappe.db.get_value(
                "Account", account, ["company", "is_group", "disabled", "root_type", "account_type"], as_dict=True
            )
            if not details:
                frappe.throw(_("Account {0} does not exist").format(account))
            if details.company != self.company:
                frappe.throw(_("Account {0} does not belong to company {1}").format(account, self.company))
            if details.is_group:
                frappe.throw(_("Account {0} is a group account").format(account))
            if details.disabled:
                frappe.throw(_("Account {0} is disabled").format(account))
            if fieldname == "staff_loan_receivable_account" and details.root_type != "Asset":
                frappe.throw(_("Staff Loan Receivable Account must be an Asset account"))
            if fieldname == "interest_income_account" and details.root_type != "Income":
                frappe.throw(_("Interest Income Account must be an Income account"))
            if fieldname in ("disbursement_bank_account", "repayment_bank_or_clearing_account") and details.root_type != "Asset":
                frappe.throw(_("Bank and clearing accounts must be Asset accounts"))
            if fieldname == "unearned_interest_account" and details.root_type not in ("Asset", "Liability"):
                frappe.throw(_("Unearned Interest Account must be an Asset or Liability account"))
            if fieldname == "legacy_temporary_account" and details.root_type in ("Income", "Expense"):
                frappe.throw(_("Legacy Temporary Account cannot be an Income or Expense account"))
            if fieldname == "legacy_temporary_account" and details.account_type in (
                "Bank",
                "Cash",
                "Receivable",
                "Payable",
            ):
                frappe.throw(_("Legacy Temporary Account must be a plain balance-sheet ledger"))
            if fieldname == "legacy_temporary_account" and account in (
                self.disbursement_bank_account,
                self.repayment_bank_or_clearing_account,
            ):
                frappe.throw(_("Legacy Temporary Account cannot be a bank or repayment account"))

        if self.default_cost_center:
            cost_center_company, is_group = frappe.db.get_value(
                "Cost Center", self.default_cost_center, ["company", "is_group"]
            )
            if cost_center_company != self.company or is_group:
                frappe.throw(_("Default Cost Center must be a ledger cost center belonging to the selected company"))


def get_settings():
    settings = frappe.get_single("Employee Lending Settings")
    required = {
        "company": _("Company"),
        "staff_loan_receivable_account": _("Staff Loan Receivable Account"),
        "unearned_interest_account": _("Unearned Interest Account"),
        "interest_income_account": _("Interest Income Account"),
        "disbursement_bank_account": _("Disbursement Bank Account"),
        "repayment_bank_or_clearing_account": _("Repayment Bank or Clearing Account"),
        "default_cost_center": _("Default Cost Center"),
    }
    missing = [label for field, label in required.items() if not settings.get(field)]
    if missing:
        frappe.throw(_("Configure Employee Lending Settings first. Missing: {0}").format(", ".join(missing)))
    return settings
