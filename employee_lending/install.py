import frappe


def after_install():
    products = (
        ("Staff Loan - 6 Months", 6, 13, 9),
        ("Staff Loan - 12 Months", 12, 26, 18),
    )
    for product_name, months, fortnights, rate in products:
        if frappe.db.exists("Employee Loan Product", product_name):
            continue
        frappe.get_doc(
            {
                "doctype": "Employee Loan Product",
                "product_name": product_name,
                "tenure_months": months,
                "number_of_fortnights": fortnights,
                "flat_interest_rate": rate,
            }
        ).insert(ignore_permissions=True)

