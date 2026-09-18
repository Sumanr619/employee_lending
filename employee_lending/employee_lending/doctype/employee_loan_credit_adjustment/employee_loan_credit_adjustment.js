frappe.ui.form.on("Employee Loan Credit Adjustment", {
    setup(frm) {
        frm.set_query("loan_application", () => ({
            filters: {
                employee: frm.doc.employee || "",
                docstatus: 1,
                loan_status: "Active",
            },
        }));
        frm.set_query("bank_account", () => ({
            filters: {
                company: frm.doc.company || "",
                is_group: 0,
                disabled: 0,
                account_type: "Bank",
            },
        }));
    },
    employee_credit(frm) {
        if (!frm.doc.employee_credit) return;
        frappe.db.get_value(
            "Employee Loan Credit",
            frm.doc.employee_credit,
            ["employee", "employee_name", "company", "available_credit"],
        ).then(({ message }) => {
            if (!message) return;
            frm.set_value("employee", message.employee);
            frm.set_value("employee_name", message.employee_name);
            frm.set_value("company", message.company);
            frm.set_value("amount", message.available_credit);
        });
    },
});
