from frappe import _
from frappe.model.document import Document
import frappe


class EmployeeLoanProduct(Document):
    def validate(self):
        if self.tenure_months <= 0 or self.number_of_fortnights <= 0:
            frappe.throw(_("Tenure and number of fortnights must be greater than zero"))
        if self.flat_interest_rate < 0:
            frappe.throw(_("Flat interest rate cannot be negative"))

