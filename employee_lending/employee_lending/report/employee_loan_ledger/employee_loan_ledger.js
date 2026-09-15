frappe.query_reports["Employee Loan Ledger"] = {
    filters: [
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
        { fieldname: "employee_loan", label: __("Employee Loan"), fieldtype: "Link", options: "Employee Loan Application" },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
    ],
};
