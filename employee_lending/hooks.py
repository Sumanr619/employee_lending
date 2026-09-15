app_name = "employee_lending"
app_title = "Employee Lending"
app_publisher = "Employee Lending"
app_description = "Employee loan and repayment automation for ERPNext"
app_email = ""
app_license = "MIT"

required_apps = ["erpnext"]

after_install = "employee_lending.install.after_install"

doctype_js = {
    "Employee Lending Settings": "public/js/employee_lending_settings.js",
    "Employee Loan Product": "public/js/employee_loan_product.js",
    "Employee Loan Application": "public/js/employee_loan_application.js",
    "Employee Loan Repayment": "public/js/employee_loan_repayment.js",
}

doc_events = {
    "Journal Entry": {
        "before_cancel": "employee_lending.employee_lending.journal_entry.prevent_orphaned_lending_entry"
    }
}
