frappe.ui.form.on("Employee Loan Legacy Import Batch", {
    refresh(frm) {
        if (frm.doc.docstatus === 0 && !frm.is_new()) {
            frm.add_custom_button(__("Load and Validate Report"), () => {
                frm.call("load_source_file").then(() => frm.reload_doc());
            });
        }

        if (frm.doc.docstatus === 1 && ["Completed", "Completed with Errors"].includes(frm.doc.status) && frm.doc.failed_rows) {
            frm.add_custom_button(__("Retry Failed Rows"), () => {
                frappe.call({
                    method: "employee_lending.employee_lending.doctype.employee_loan_legacy_import_batch.employee_loan_legacy_import_batch.retry_failed_rows",
                    args: { batch_name: frm.doc.name },
                    freeze: true,
                    callback: () => frm.reload_doc(),
                });
            });
        }

        if (frm.doc.docstatus === 1 && ["Completed", "Completed with Errors"].includes(frm.doc.status) && frm.doc.excluded_rows) {
            frm.add_custom_button(__("Import Excluded Credits"), () => {
                frappe.confirm(
                    __("Import employee overpayment balances from the excluded rows? Existing Journal Entries will only be referenced; no GL entry will be posted."),
                    () => {
                        frappe.call({
                            method: "employee_lending.employee_lending.doctype.employee_loan_legacy_import_batch.employee_loan_legacy_import_batch.import_excluded_credits",
                            args: { batch_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Importing employee credits..."),
                            callback: (r) => {
                                const result = r.message || {};
                                frappe.msgprint(__("Imported {0} employee credit record(s), total {1}.", [
                                    result.imported || 0,
                                    format_currency(result.amount || 0),
                                ]));
                                frm.reload_doc();
                            },
                        });
                    },
                );
            });
        }

        if (["Queued", "Running"].includes(frm.doc.status)) {
            setTimeout(() => {
                if (cur_frm && cur_frm.doc.name === frm.doc.name) {
                    frm.reload_doc();
                }
            }, 5000);
        }
    },
});
