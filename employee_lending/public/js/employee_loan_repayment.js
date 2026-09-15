frappe.ui.form.on("Employee Loan Repayment", {
    setup(frm) {
        frm.set_query("loan_application", () => ({ filters: { docstatus: 1, loan_status: "Active" } }));
        frm.set_query("bank_or_clearing_account", () => ({
            filters: { company: frm.doc.company, is_group: 0, disabled: 0 },
        }));
    },

    refresh(frm) {
        frm.toggle_enable("bank_or_clearing_account", Boolean(frm.__allow_account_override));
        if (frm.doc.journal_entry) {
            frm.add_custom_button(__("Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
            }, __("View"));
        }
    },

    loan_application(frm) {
        if (!frm.doc.loan_application) return;
        frappe.call({
            method: "employee_lending.employee_lending.doctype.employee_loan_repayment.employee_loan_repayment.get_active_loan_details",
            args: { loan_application: frm.doc.loan_application },
            callback(r) {
                if (!r.message) return;
                Object.entries(r.message).forEach(([field, value]) => {
                    if (field !== "allow_account_override") frm.set_value(field, value);
                });
                frm.__allow_account_override = r.message.allow_account_override;
                frm.toggle_enable("bank_or_clearing_account", Boolean(frm.__allow_account_override));
            },
        });
    },

    repayment_amount(frm) {
        if (!frm.doc.loan_application || !frm.doc.repayment_amount) return;
        frappe.call({
            method: "employee_lending.employee_lending.doctype.employee_loan_repayment.employee_loan_repayment.get_active_loan_details",
            args: { loan_application: frm.doc.loan_application },
            callback(r) {
                if (!r.message) return;
                const rate = flt(r.message.flat_interest_rate);
                const total = flt(frm.doc.repayment_amount);
                let principal = flt(total * 100 / (100 + rate), 2);
                let interest = flt(total - principal, 2);
                if (total === flt(r.message.total_outstanding_before)) {
                    principal = flt(r.message.principal_outstanding_before, 2);
                    interest = flt(r.message.unearned_interest_before, 2);
                }
                frm.set_value("principal_component", principal);
                frm.set_value("interest_component", interest);
                frm.set_value("principal_outstanding_after", flt(r.message.principal_outstanding_before - principal, 2));
                frm.set_value("unearned_interest_after", flt(r.message.unearned_interest_before - interest, 2));
                frm.set_value("total_outstanding_after", flt(r.message.total_outstanding_before - total, 2));
            },
        });
    },
});

