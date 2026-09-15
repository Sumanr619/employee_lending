frappe.query_reports["Employee Loan Outstanding"] = {
    filters: [
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        { fieldname: "loan_status", label: __("Status"), fieldtype: "Select", options: "\nActive\nClosed" },
    ],
};

