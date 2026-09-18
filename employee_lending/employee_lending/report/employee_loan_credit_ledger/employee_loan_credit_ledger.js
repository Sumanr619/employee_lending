frappe.query_reports["Employee Loan Credit Ledger"] = {
    filters: [
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
        { fieldname: "employee_credit", label: __("Employee Credit"), fieldtype: "Link", options: "Employee Loan Credit" },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
    ],
};
