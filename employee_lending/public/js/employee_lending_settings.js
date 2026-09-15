frappe.ui.form.on("Employee Lending Settings", {
    setup(frm) {
        const fields = [
            "staff_loan_receivable_account",
            "unearned_interest_account",
            "interest_income_account",
            "disbursement_bank_account",
            "repayment_bank_or_clearing_account",
            "legacy_temporary_account",
        ];
        fields.forEach((fieldname) => {
            frm.set_query(fieldname, () => ({
                filters: { company: frm.doc.company, is_group: 0, disabled: 0 },
            }));
        });
        frm.set_query("default_cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
    },
});
