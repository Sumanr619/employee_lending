frappe.ui.form.on("Employee Loan Legacy Opening", {
    setup(frm) {
        frm.set_query("loan_product", () => ({ filters: { disabled: 0 } }));
    },

    refresh(frm) {
        if (frm.doc.loan_application) {
            frm.add_custom_button(__("Employee Loan"), () => {
                frappe.set_route("Form", "Employee Loan Application", frm.doc.loan_application);
            }, __("View"));
        }
        if (frm.doc.conversion_journal_entry) {
            frm.add_custom_button(__("Conversion Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.conversion_journal_entry);
            }, __("View"));
        }
        if (frm.doc.cleanup_journal_entry) {
            frm.add_custom_button(__("Cleanup Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.cleanup_journal_entry);
            }, __("View"));
        }
    },
});
