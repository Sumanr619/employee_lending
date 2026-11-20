frappe.ui.form.on("Employee Loan Credit Receipt", {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.employee_credit) {
            frm.add_custom_button(__("Open Employee Credit"), () => {
                frappe.set_route("Form", "Employee Loan Credit", frm.doc.employee_credit);
            });
        }
    },
});
