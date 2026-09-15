from decimal import Decimal

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from employee_lending.employee_lending.accounting import cancel_linked_journal_entry
from employee_lending.employee_lending.doctype.employee_lending_settings.employee_lending_settings import get_settings
from employee_lending.employee_lending.utils import build_remaining_schedule, build_schedule, calculate_loan


class EmployeeLoanApplication(Document):
    def before_insert(self):
        self.loan_status = "Draft"

    def validate(self):
        self.set_employee_details()
        self.set_product_terms()
        if self.is_legacy_opening:
            self.validate_legacy_values()
            if self.is_new() or self.docstatus == 0:
                self.generate_legacy_schedule()
            return
        self.validate_policy()
        self.calculate_amounts()
        if self.is_new() or self.docstatus == 0:
            self.generate_schedule()

    def before_submit(self):
        if self.approval_status != "Approved":
            frappe.throw(_("Approval Status must be Approved before submission"))

    def on_submit(self):
        self.db_set("loan_status", "Active" if self.is_legacy_opening else "Approved", update_modified=False)

    def before_cancel(self):
        if self.is_legacy_opening and not self.flags.get("from_legacy_opening"):
            frappe.throw(_("Cancel Legacy Loan Opening {0} instead").format(self.legacy_opening))
        if frappe.db.exists("Employee Loan Disbursement", {"loan_application": self.name, "docstatus": 1}):
            frappe.throw(_("Cancel the submitted loan disbursement before cancelling this application"))
        if frappe.db.exists("Employee Loan Repayment", {"loan_application": self.name, "docstatus": 1}):
            frappe.throw(_("Cancel submitted repayments before cancelling this loan"))

    def on_cancel(self):
        # Backward compatibility for loans posted before the separate
        # Employee Loan Disbursement document was introduced.
        if self.disbursement_journal_entry and not self.loan_disbursement and not self.is_legacy_opening:
            cancel_linked_journal_entry(self.disbursement_journal_entry)
        self.db_set("loan_status", "Cancelled", update_modified=False)

    def set_employee_details(self):
        if not self.employee:
            return
        values = frappe.db.get_value(
            "Employee",
            self.employee,
            ["employee_name", "department", "designation", "company", "date_of_joining"],
            as_dict=True,
        )
        if not values:
            frappe.throw(_("Employee {0} does not exist").format(self.employee))
        self.employee_name = values.employee_name
        self.department = values.department
        self.designation = values.designation
        self.company = values.company
        self.date_of_joining = values.date_of_joining

    def set_product_terms(self):
        if not self.loan_product:
            return
        product = frappe.db.get_value(
            "Employee Loan Product",
            self.loan_product,
            ["tenure_months", "number_of_fortnights", "flat_interest_rate", "disabled"],
            as_dict=True,
        )
        if not product or product.disabled:
            frappe.throw(_("Select an active Employee Loan Product"))
        self.tenure_months = product.tenure_months
        self.number_of_fortnights = product.number_of_fortnights
        self.flat_interest_rate = product.flat_interest_rate

    def validate_policy(self):
        settings = get_settings()
        if self.company and self.company != settings.company:
            frappe.throw(_("Employee company must match Employee Lending Settings"))

        if self.date_of_joining:
            service_days = date_diff(getdate(self.application_date or nowdate()), getdate(self.date_of_joining))
            self.service_months = max(0, int(service_days / 30.4375))
        if self.enforce_policy_limits and self.service_months < settings.minimum_service_months:
            frappe.throw(_("Employee has not completed the minimum service period of {0} months").format(settings.minimum_service_months))
        if self.enforce_policy_limits and not self.is_confirmed_employee:
            frappe.throw(_("Employee must be confirmed/permanent"))

    def calculate_amounts(self):
        if not self.approved_principal or not self.number_of_fortnights:
            return
        try:
            totals = calculate_loan(self.approved_principal, self.flat_interest_rate, self.number_of_fortnights)
        except ValueError as exc:
            frappe.throw(str(exc))
        self.total_interest = float(totals.interest)
        self.total_amount_due = float(totals.total_due)
        self.fortnightly_repayment = float(totals.normal_repayment)

        if self.docstatus == 0:
            self.principal_outstanding = self.approved_principal
            self.unearned_interest_outstanding = self.total_interest
            self.total_outstanding = self.total_amount_due
            self.principal_recovered = 0
            self.interest_earned = 0
            self.total_repaid = 0

        settings = get_settings()
        if self.net_fortnightly_salary:
            self.repayment_percent_of_net_pay = flt(self.fortnightly_repayment / self.net_fortnightly_salary * 100, 2)
            if self.enforce_policy_limits and self.repayment_percent_of_net_pay > settings.maximum_repayment_percent_of_net_pay:
                frappe.throw(
                    _("Fortnightly repayment is {0}% of net pay; the configured maximum is {1}%").format(
                        self.repayment_percent_of_net_pay, settings.maximum_repayment_percent_of_net_pay
                    )
                )
        if self.accrued_entitlement:
            self.maximum_eligible_loan = flt(
                self.accrued_entitlement * settings.maximum_loan_percent_of_entitlement / 100, 2
            )
            if self.enforce_policy_limits and self.approved_principal > self.maximum_eligible_loan:
                frappe.throw(_("Approved principal exceeds the configured entitlement-based loan limit"))

    def validate_legacy_values(self):
        numeric_fields = (
            "approved_principal",
            "total_interest",
            "total_amount_due",
            "principal_outstanding",
            "unearned_interest_outstanding",
            "total_outstanding",
            "principal_recovered",
            "interest_earned",
            "total_repaid",
            "fortnightly_repayment",
        )
        if any(flt(self.get(field)) < 0 for field in numeric_fields):
            frappe.throw(_("Legacy loan amounts cannot be negative"))
        if flt(self.total_outstanding) <= 0:
            frappe.throw(_("Legacy loan must have a positive outstanding balance"))
        if abs(flt(self.total_amount_due) - flt(self.approved_principal) - flt(self.total_interest)) > 0.01:
            frappe.throw(_("Legacy original principal and interest do not reconcile to total amount due"))
        if abs(
            flt(self.total_outstanding)
            - flt(self.principal_outstanding)
            - flt(self.unearned_interest_outstanding)
        ) > 0.01:
            frappe.throw(_("Legacy principal and interest outstanding do not reconcile"))
        if flt(self.total_repaid) > flt(self.total_amount_due) + 0.01:
            frappe.throw(_("Legacy repayments cannot exceed total amount due"))
        if not self.legacy_remaining_installments or self.legacy_remaining_installments < 1:
            frappe.throw(_("Remaining instalments must be greater than zero"))

    def generate_legacy_schedule(self):
        try:
            rows = build_remaining_schedule(
                self.principal_outstanding,
                self.unearned_interest_outstanding,
                self.flat_interest_rate,
                self.legacy_remaining_installments,
                self.fortnightly_repayment,
            )
        except ValueError as exc:
            frappe.throw(str(exc))
        start_date = getdate(self.first_repayment_date) if self.first_repayment_date else None
        self.set("repayment_schedule", [])
        for index, row in enumerate(rows):
            self.append(
                "repayment_schedule",
                {
                    **{key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()},
                    "due_date": add_days(start_date, index * 14) if start_date else None,
                    "paid_amount": 0,
                    "status": "Scheduled",
                },
            )

    def generate_schedule(self):
        if not self.approved_principal or not self.number_of_fortnights:
            return
        _, rows = build_schedule(self.approved_principal, self.flat_interest_rate, self.number_of_fortnights)
        start_date = getdate(self.first_repayment_date) if self.first_repayment_date else None
        self.set("repayment_schedule", [])
        for index, row in enumerate(rows):
            self.append(
                "repayment_schedule",
                {
                    **{key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()},
                    "due_date": add_days(start_date, index * 14) if start_date else None,
                    "paid_amount": 0,
                    "status": "Scheduled",
                },
            )


@frappe.whitelist()
def get_loan_preview(employee, loan_product, approved_principal, net_fortnightly_salary=0):
    frappe.has_permission("Employee Loan Application", ptype="create", throw=True)
    product = frappe.get_cached_doc("Employee Loan Product", loan_product)
    totals, rows = build_schedule(approved_principal, product.flat_interest_rate, product.number_of_fortnights)
    return {
        "employee": employee,
        "total_interest": float(totals.interest),
        "total_amount_due": float(totals.total_due),
        "fortnightly_repayment": float(totals.normal_repayment),
        "repayment_percent_of_net_pay": flt(float(totals.normal_repayment) / flt(net_fortnightly_salary) * 100, 2)
        if flt(net_fortnightly_salary)
        else 0,
        "schedule": [{key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()} for row in rows],
    }
