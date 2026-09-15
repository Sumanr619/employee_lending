frappe.ui.form.on("Employee Loan Application", {
    setup(frm) {
        frm.set_query("loan_product", () => ({ filters: { disabled: 0 } }));
    },

    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.loan_status === "Approved" && !frm.doc.loan_disbursement) {
            frm.add_custom_button(__("Disburse Loan"), () => {
                frappe.new_doc("Employee Loan Disbursement", {
                    loan_application: frm.doc.name,
                });
            }, __("Create"));
        }
        if (frm.doc.docstatus === 1 && frm.doc.loan_status === "Active") {
            frm.add_custom_button(__("Record Repayment"), () => {
                frappe.new_doc("Employee Loan Repayment", {
                    loan_application: frm.doc.name,
                    employee: frm.doc.employee,
                    repayment_amount: Math.min(frm.doc.fortnightly_repayment, frm.doc.total_outstanding),
                });
            }, __("Create"));
        }
        if (frm.doc.loan_disbursement) {
            frm.add_custom_button(__("Loan Disbursement"), () => {
                frappe.set_route("Form", "Employee Loan Disbursement", frm.doc.loan_disbursement);
            }, __("View"));
        }
        if (frm.doc.disbursement_journal_entry) {
            frm.add_custom_button(__("Disbursement Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.disbursement_journal_entry);
            }, __("View"));
        }
    },

    loan_product: calculate,
    approved_principal: calculate,
    net_fortnightly_salary: calculate,
});

function calculate(frm) {
    if (!frm.doc.employee || !frm.doc.loan_product || !frm.doc.approved_principal) return;
    frappe.call({
        method: "employee_lending.employee_lending.doctype.employee_loan_application.employee_loan_application.get_loan_preview",
        args: {
            employee: frm.doc.employee,
            loan_product: frm.doc.loan_product,
            approved_principal: frm.doc.approved_principal,
            net_fortnightly_salary: frm.doc.net_fortnightly_salary || 0,
        },
        callback(r) {
            if (!r.message) return;
            frm.set_value("total_interest", r.message.total_interest);
            frm.set_value("total_amount_due", r.message.total_amount_due);
            frm.set_value("fortnightly_repayment", r.message.fortnightly_repayment);
            frm.set_value("repayment_percent_of_net_pay", r.message.repayment_percent_of_net_pay);
        },
    });
}
