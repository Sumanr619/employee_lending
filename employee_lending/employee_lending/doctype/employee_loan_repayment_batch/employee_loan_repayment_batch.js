frappe.ui.form.on("Employee Loan Repayment Batch", {
    setup(frm) {
        frm.set_query("loan_application", "repayments", () => ({
            filters: { docstatus: 1, loan_status: "Active", company: frm.doc.company },
        }));
        frm.set_query("bank_or_clearing_account", () => ({
            filters: { company: frm.doc.company, is_group: 0, disabled: 0 },
        }));
    },

    onload(frm) {
        if (!frm.is_new()) return;
        frappe.call({
            method: "employee_lending.employee_lending.doctype.employee_loan_repayment_batch.employee_loan_repayment_batch.get_batch_defaults",
            callback(r) {
                if (!r.message) return;
                frm.set_value("company", r.message.company);
                frm.set_value("bank_or_clearing_account", r.message.bank_or_clearing_account);
                frm.__allow_account_override = r.message.allow_account_override;
                frm.toggle_enable("bank_or_clearing_account", Boolean(r.message.allow_account_override));
            },
        });
    },

    refresh(frm) {
        frm.toggle_enable("bank_or_clearing_account", Boolean(frm.__allow_account_override));
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Load All Active Loans"), () => load_active_loans(frm), __("Get Loans"));
            frm.add_custom_button(__("Clear Rows"), () => {
                frm.clear_table("repayments");
                frm.refresh_field("repayments");
                update_totals(frm);
            }, __("Get Loans"));
        }
        if (frm.doc.journal_entry) {
            frm.add_custom_button(__("Consolidated Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
            }, __("View"));
        }
    },

    repayments_remove(frm) {
        update_totals(frm);
    },
});

frappe.ui.form.on("Employee Loan Repayment Batch Item", {
    loan_application(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.loan_application) return;
        frappe.call({
            method: "employee_lending.employee_lending.doctype.employee_loan_repayment_batch.employee_loan_repayment_batch.get_loan_details",
            args: { loan_application: row.loan_application },
            callback(r) {
                if (!r.message) return;
                set_row_values(cdt, cdn, r.message);
                update_totals(frm);
            },
        });
    },

    repayment_amount(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const amount = flt(row.repayment_amount, 2);
        const rate = flt(row.flat_interest_rate);
        const outstanding = flt(row.total_outstanding_before, 2);
        if (!amount || !outstanding) return;
        if (amount > outstanding) {
            frappe.msgprint(__("Repayment cannot exceed the outstanding amount."));
            return;
        }
        let principal;
        let interest;
        if (amount === outstanding) {
            principal = flt(row.principal_outstanding_before, 2);
            interest = flt(row.unearned_interest_before, 2);
        } else {
            principal = flt(amount * 100 / (100 + rate), 2);
            interest = flt(amount - principal, 2);
        }
        frappe.model.set_value(cdt, cdn, "principal_component", principal);
        frappe.model.set_value(cdt, cdn, "interest_component", interest);
        frappe.model.set_value(cdt, cdn, "total_outstanding_after", flt(outstanding - amount, 2));
        update_totals(frm);
    },
});

function load_active_loans(frm) {
    const proceed = () => {
        frappe.call({
            method: "employee_lending.employee_lending.doctype.employee_loan_repayment_batch.employee_loan_repayment_batch.get_active_loans",
            freeze: true,
            freeze_message: __("Loading active employee loans..."),
            callback(r) {
                frm.clear_table("repayments");
                (r.message || []).forEach((values) => {
                    const row = frm.add_child("repayments");
                    Object.assign(row, values);
                });
                frm.refresh_field("repayments");
                update_totals(frm);
            },
        });
    };
    if ((frm.doc.repayments || []).length) {
        frappe.confirm(__("Replace all current batch rows with active loans?"), proceed);
    } else {
        proceed();
    }
}

function set_row_values(cdt, cdn, values) {
    Object.entries(values).forEach(([fieldname, value]) => {
        if (fieldname !== "loan_application") {
            frappe.model.set_value(cdt, cdn, fieldname, value);
        }
    });
}

function update_totals(frm) {
    const rows = frm.doc.repayments || [];
    frm.set_value("total_repayment_amount", flt(rows.reduce((sum, row) => sum + flt(row.repayment_amount), 0), 2));
    frm.set_value("total_principal_component", flt(rows.reduce((sum, row) => sum + flt(row.principal_component), 0), 2));
    frm.set_value("total_interest_component", flt(rows.reduce((sum, row) => sum + flt(row.interest_component), 0), 2));
}
