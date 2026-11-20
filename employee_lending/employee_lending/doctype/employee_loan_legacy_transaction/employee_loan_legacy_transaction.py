import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeLoanLegacyTransaction(Document):
    def validate(self):
        if not self.flags.get("from_legacy_import"):
            frappe.throw(_("Legacy transaction records are created only by the controlled import process"))
        if not frappe.db.exists("Journal Entry", {"name": self.journal_entry, "docstatus": 1}):
            frappe.throw(_("Submitted source Journal Entry {0} was not found").format(self.journal_entry))
        duplicate = frappe.db.get_value(
            "Employee Loan Legacy Transaction",
            {
                "source_key": self.source_key,
                "name": ["!=", self.name],
            },
            "name",
        )
        if duplicate:
            frappe.throw(_("Legacy transaction already exists as {0}").format(duplicate))
