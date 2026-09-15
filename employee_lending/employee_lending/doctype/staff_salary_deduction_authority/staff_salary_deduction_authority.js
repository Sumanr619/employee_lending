frappe.ui.form.on("Staff Salary Deduction Authority", {
    setup(frm) {
        frm.set_query("loan_application", () => ({ filters: { docstatus: 1 } }));
    },
});

