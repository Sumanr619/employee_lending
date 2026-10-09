import frappe


SIDEBAR_ITEMS = (
    ("Loan Management", "Section Break", "DocType", None, 0),
    ("Loan Products", "Link", "DocType", "Employee Loan Product", 1),
    ("Loan Applications", "Link", "DocType", "Employee Loan Application", 1),
    ("Disbursements", "Link", "DocType", "Employee Loan Disbursement", 1),
    ("Repayments", "Link", "DocType", "Employee Loan Repayment", 1),
    ("Bulk Repayment", "Link", "DocType", "Employee Loan Repayment Batch", 1),
    ("Migration", "Section Break", "DocType", None, 0),
    ("Legacy Import Batch", "Link", "DocType", "Employee Loan Legacy Import Batch", 1),
    ("Employee Loan Legacy Opening", "Link", "DocType", "Employee Loan Legacy Opening", 1),
    ("Employee Loan Legacy Transaction", "Link", "DocType", "Employee Loan Legacy Transaction", 1),
    ("Loan Credits", "Section Break", "DocType", None, 0),
    ("Employee Loan Credit", "Link", "DocType", "Employee Loan Credit", 1),
    ("Employee Loan Credit Adjustment", "Link", "DocType", "Employee Loan Credit Adjustment", 1),
    ("Report", "Section Break", "DocType", None, 0),
    ("Loan Ledger", "Link", "Report", "Employee Loan Ledger", 1),
    ("Loan Outstanding", "Link", "Report", "Employee Loan Outstanding", 1),
    ("Employee Loan Credit Ledger", "Link", "Report", "Employee Loan Credit Ledger", 1),
    ("Lending Settings", "Section Break", "DocType", None, 0),
    ("Lending Settings", "Link", "DocType", "Employee Lending Settings", 1),
)


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

    ensure_navigation()


def after_migrate():
    """Keep the v16 desktop icon and curated sidebar owned by this app."""
    ensure_navigation()


def ensure_navigation():
    if not frappe.db.exists("DocType", "Workspace Sidebar"):
        return

    _ensure_workspace_sidebar()
    _ensure_desktop_icon()


def _assign_if_supported(doc, fieldname, value):
    if doc.meta.has_field(fieldname):
        doc.set(fieldname, value)


def _ensure_workspace_sidebar():
    name = "Employee Lending"
    if frappe.db.exists("Workspace Sidebar", name):
        sidebar = frappe.get_doc("Workspace Sidebar", name)
    else:
        sidebar = frappe.new_doc("Workspace Sidebar")
        sidebar.name = name

    _assign_if_supported(sidebar, "title", name)
    _assign_if_supported(sidebar, "header_icon", "landmark")
    _assign_if_supported(sidebar, "standard", 1)
    _assign_if_supported(sidebar, "app", "employee_lending")
    _assign_if_supported(sidebar, "for_user", "")
    _assign_if_supported(sidebar, "module_onboarding", "")

    sidebar.set("items", [])
    for label, item_type, link_type, link_to, is_child in SIDEBAR_ITEMS:
        item = sidebar.append("items", {})
        _assign_if_supported(item, "label", label)
        _assign_if_supported(item, "type", item_type)
        _assign_if_supported(item, "link_type", link_type)
        _assign_if_supported(item, "link_to", link_to or "")
        _assign_if_supported(item, "child", is_child)
        _assign_if_supported(item, "child_item", is_child)

    if sidebar.is_new():
        sidebar.insert(ignore_permissions=True)
    else:
        sidebar.save(ignore_permissions=True)


def _ensure_desktop_icon():
    if not frappe.db.exists("DocType", "Desktop Icon"):
        return

    name = "Employee Lending"
    if frappe.db.exists("Desktop Icon", name):
        icon = frappe.get_doc("Desktop Icon", name)
    else:
        icon = frappe.new_doc("Desktop Icon")
        icon.name = name

    values = {
        "label": name,
        "icon_type": "Link",
        "link_type": "Workspace Sidebar",
        "link_to": name,
        "sidebar": name,
        "standard": 1,
        "app": "employee_lending",
        "icon": "landmark",
        "hidden": 0,
        "bg_color": "gray",
        "idx": 0,
    }
    for fieldname, value in values.items():
        _assign_if_supported(icon, fieldname, value)

    if icon.is_new():
        icon.insert(ignore_permissions=True)
    else:
        icon.save(ignore_permissions=True)
