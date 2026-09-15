frappe.ui.form.on("Employee Loan Disbursement", {
    setup(frm) {
        frm.set_query("loan_application", () => ({
            filters: { docstatus: 1, approval_status: "Approved", loan_status: "Approved" },
        }));
        frm.set_query("bank_account", () => ({
            filters: { company: frm.doc.company, is_group: 0, disabled: 0, root_type: "Asset" },
        }));
    },

    onload(frm) {
        if (frm.is_new() && frm.doc.loan_application) {
            load_loan(frm);
        }
    },

    refresh(frm) {
        frm.toggle_enable("bank_account", Boolean(frm.__allow_account_override));
        if (frm.doc.journal_entry) {
            frm.add_custom_button(__("Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
            }, __("View"));
        }
    },

    loan_application(frm) {
        if (frm.doc.loan_application) load_loan(frm);
    },

    posting_date(frm) {
        if (frm.doc.posting_date && frm.is_new()) {
            frm.set_value("first_repayment_date", frappe.datetime.add_days(frm.doc.posting_date, 14));
        }
    },
});

function load_loan(frm) {
    frappe.call({
        method: "employee_lending.employee_lending.doctype.employee_loan_disbursement.employee_loan_disbursement.get_disbursement_details",
        args: { loan_application: frm.doc.loan_application },
        callback(r) {
            if (!r.message) return;
            Object.entries(r.message).forEach(([fieldname, value]) => {
                if (fieldname !== "allow_account_override") frm.set_value(fieldname, value);
            });
            frm.__allow_account_override = r.message.allow_account_override;
            frm.toggle_enable("bank_account", Boolean(r.message.allow_account_override));
        },
    });
}

