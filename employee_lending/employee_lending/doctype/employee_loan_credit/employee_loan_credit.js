frappe.ui.form.on("Employee Loan Credit", {
    refresh(frm) {
        if (frm.is_new() || flt(frm.doc.available_credit) <= 0) return;

        frm.add_custom_button(__("Refund Credit"), () => {
            frappe.new_doc("Employee Loan Credit Adjustment", {
                employee_credit: frm.doc.name,
                adjustment_type: "Refund",
                amount: frm.doc.available_credit,
            });
        }, __("Create"));

        frm.add_custom_button(__("Apply to Loan"), () => {
            frappe.new_doc("Employee Loan Credit Adjustment", {
                employee_credit: frm.doc.name,
                adjustment_type: "Apply to Loan",
                amount: frm.doc.available_credit,
            });
        }, __("Create"));
    },
});
