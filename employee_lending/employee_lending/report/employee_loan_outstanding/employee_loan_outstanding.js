frappe.query_reports["Employee Loan Outstanding"] = {
    filters: [
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
        {
            fieldname: "as_of_date",
            label: __("As of Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        { fieldname: "include_credits", label: __("Include Employee Credits"), fieldtype: "Check", default: 1 },
        { fieldname: "view", label: __("View"), fieldtype: "Select", options: "Loan and Credit Detail\nEmployee Summary", default: "Loan and Credit Detail", reqd: 1 },
        { fieldname: "ageing_basis", label: __("Ageing Basis"), fieldtype: "Select", options: "Instalment Due Date\nLoan / Credit Date", default: "Instalment Due Date", reqd: 1 },
        { fieldname: "loan_status", label: __("Status"), fieldtype: "Select", options: "\nActive\nClosed" },
        { fieldname: "date", label: __("Date"), fieldtype: "Date" },
    ],
};

