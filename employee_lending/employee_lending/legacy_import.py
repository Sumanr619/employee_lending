from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY = Decimal("0.01")
HEADER_ALIASES = {
    "employee": ("employee", "employee id"),
    "original_principal": ("principle loan", "principal loan", "original principal"),
    "original_interest": ("interest due", "original interest"),
    "principal_repaid": ("principle paid", "principal paid"),
    "interest_repaid": ("interest paid",),
    "reported_total_outstanding": ("total outstanding",),
    "remarks": ("remarks",),
}
GL_HEADER_ALIASES = {
    "posting_date": ("posting date",),
    "account": ("account",),
    "debit": ("debit (pgk)", "debit"),
    "credit": ("credit (pgk)", "credit"),
    "voucher_type": ("voucher type",),
    "voucher_no": ("voucher no", "voucher number"),
    "against_account": ("against account",),
    "party_type": ("party type",),
    "party": ("party",),
}


def normalize_header(value):
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def map_headers(values, aliases=None):
    aliases = aliases or HEADER_ALIASES
    normalized = {normalize_header(value): index for index, value in enumerate(values)}
    result = {}
    missing = []
    for fieldname, field_aliases in aliases.items():
        index = next((normalized[alias] for alias in field_aliases if alias in normalized), None)
        if index is None and fieldname != "remarks":
            missing.append(" / ".join(field_aliases))
        result[fieldname] = index
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    return result


def map_gl_headers(values):
    return map_headers(values, GL_HEADER_ALIASES)


def decimal_value(value, label):
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value).replace(",", "").strip()).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{label} must be numeric")


def money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def classify_outstanding_row(values, headers):
    employee = str(values[headers["employee"]] or "").strip()
    if not employee or normalize_header(employee) in ("total", "grand total"):
        return None

    amounts = {
        fieldname: decimal_value(values[index], fieldname.replace("_", " ").title())
        for fieldname, index in headers.items()
        if fieldname not in ("employee", "remarks")
    }
    remarks_index = headers.get("remarks")
    remarks = str(values[remarks_index] or "").strip() if remarks_index is not None else ""

    original_principal = amounts["original_principal"]
    original_interest = amounts["original_interest"]
    principal_repaid = amounts["principal_repaid"]
    interest_repaid = amounts["interest_repaid"]
    reported = amounts["reported_total_outstanding"]
    principal_outstanding = (original_principal - principal_repaid).quantize(MONEY)
    interest_outstanding = (original_interest - interest_repaid).quantize(MONEY)
    calculated = (principal_outstanding + interest_outstanding).quantize(MONEY)

    status = "Ready"
    message = ""
    if reported <= Decimal("0.00"):
        status = "Excluded"
        message = "Credit or cleared balance"
    elif original_principal <= Decimal("0.00"):
        status = "Invalid"
        message = "Original principal must be greater than zero"
    elif min(original_interest, principal_repaid, interest_repaid) < Decimal("0.00"):
        status = "Invalid"
        message = "Interest and repayment amounts cannot be negative"
    elif principal_repaid > original_principal:
        status = "Invalid"
        message = "Principal repaid exceeds original principal"
    elif interest_repaid > original_interest:
        status = "Invalid"
        message = "Interest repaid exceeds original interest"
    elif abs(calculated - reported) > MONEY:
        status = "Invalid"
        message = "Reported outstanding does not reconcile"

    source_rate = (
        (original_interest / original_principal * Decimal("100")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        if original_principal
        else Decimal("0.0000")
    )
    return {
        "employee": employee,
        "original_principal": original_principal,
        "original_interest": original_interest,
        "principal_repaid": principal_repaid,
        "interest_repaid": interest_repaid,
        "principal_outstanding": principal_outstanding,
        "interest_outstanding": interest_outstanding,
        "reported_total_outstanding": reported,
        "calculated_total_outstanding": calculated,
        "source_interest_rate": source_rate,
        "source_remarks": remarks,
        "validation_status": status,
        "validation_message": message,
    }


def aggregate_gl_rows(rows, staff_account, unearned_account, interest_income_account, legacy_temp_account):
    grouped = defaultdict(lambda: _empty_gl_group())
    employee_totals = defaultdict(lambda: _empty_employee_gl())

    for row in rows:
        if normalize_header(row.get("voucher_type")) != "journal entry":
            continue
        if normalize_header(row.get("party_type")) != "employee":
            continue
        employee = str(row.get("party") or "").strip()
        voucher = str(row.get("voucher_no") or "").strip()
        if not employee or not voucher:
            continue
        account = str(row.get("account") or "").strip()
        if account not in (staff_account, unearned_account, interest_income_account):
            continue

        debit = decimal_value(row.get("debit"), "GL Debit")
        credit = decimal_value(row.get("credit"), "GL Credit")
        account_key = (
            "staff"
            if account == staff_account
            else "unearned"
            if account == unearned_account
            else "income"
        )
        group = grouped[(employee, voucher)]
        group["employee"] = employee
        group["voucher"] = voucher
        group["posting_date"] = row.get("posting_date")
        group["against_accounts"].add(str(row.get("against_account") or "").strip())
        group[f"{account_key}_debit"] += debit
        group[f"{account_key}_credit"] += credit

        totals = employee_totals[employee]
        totals[f"{account_key}_debit"] += debit
        totals[f"{account_key}_credit"] += credit

    transactions = defaultdict(list)
    for group in grouped.values():
        against = ", ".join(sorted(value for value in group.pop("against_accounts") if value))
        group["against_account"] = against
        group["transaction_type"] = classify_gl_group(group, legacy_temp_account)
        group["principal_amount"] = money(
            abs(group["staff_debit"] - group["staff_credit"])
        )
        if group["transaction_type"] == "Repayment":
            group["interest_amount"] = money(
                max(Decimal("0.00"), group["income_credit"] - group["income_debit"])
            )
            group["debit"] = Decimal("0.00")
            group["credit"] = money(group["principal_amount"] + group["interest_amount"])
        elif group["transaction_type"] == "Reversal":
            group["interest_amount"] = money(
                abs(group["unearned_debit"] - group["unearned_credit"])
            )
            group["debit"] = Decimal("0.00")
            group["credit"] = money(group["principal_amount"] + group["interest_amount"])
        else:
            group["interest_amount"] = money(
                abs(group["unearned_debit"] - group["unearned_credit"])
            )
            signed = money(
                group["staff_debit"]
                - group["staff_credit"]
                + group["unearned_debit"]
                - group["unearned_credit"]
            )
            group["debit"] = max(Decimal("0.00"), signed)
            group["credit"] = max(Decimal("0.00"), -signed)
        transactions[group["employee"]].append(group)

    result = {}
    for employee, totals in employee_totals.items():
        totals["staff_balance"] = money(totals["staff_debit"] - totals["staff_credit"])
        totals["unearned_balance"] = money(
            totals["unearned_debit"] - totals["unearned_credit"]
        )
        totals["interest_earned"] = money(totals["income_credit"] - totals["income_debit"])
        totals["total_outstanding"] = money(
            totals["staff_balance"] + totals["unearned_balance"] - totals["interest_earned"]
        )
        employee_transactions = sorted(
            transactions[employee], key=lambda item: (str(item["posting_date"]), item["voucher"])
        )
        totals["transactions"] = employee_transactions
        totals["opening_count"] = sum(
            item["transaction_type"] in ("Opening", "Additional Disbursement")
            for item in employee_transactions
        )
        totals["repayment_count"] = sum(
            item["transaction_type"] == "Repayment" for item in employee_transactions
        )
        totals["source_vouchers"] = [item["voucher"] for item in employee_transactions]
        result[employee] = totals
    return result


def classify_gl_group(group, legacy_temp_account):
    against = group.get("against_account", "")
    has_temp = bool(legacy_temp_account and legacy_temp_account in against)
    staff_net = group["staff_debit"] - group["staff_credit"]
    unearned_net = group["unearned_debit"] - group["unearned_credit"]
    income_net = group["income_credit"] - group["income_debit"]
    if has_temp and (staff_net < 0 or unearned_net < 0):
        return "Reversal"
    if has_temp and (staff_net > 0 or unearned_net > 0):
        return "Opening"
    if group["staff_credit"] > 0 or income_net > 0:
        return "Repayment"
    if staff_net > 0 or unearned_net > 0:
        return "Additional Disbursement"
    return "Adjustment"


def _empty_gl_group():
    return {
        "employee": "",
        "voucher": "",
        "posting_date": None,
        "against_accounts": set(),
        "staff_debit": Decimal("0.00"),
        "staff_credit": Decimal("0.00"),
        "unearned_debit": Decimal("0.00"),
        "unearned_credit": Decimal("0.00"),
        "income_debit": Decimal("0.00"),
        "income_credit": Decimal("0.00"),
    }


def _empty_employee_gl():
    return {
        "staff_debit": Decimal("0.00"),
        "staff_credit": Decimal("0.00"),
        "unearned_debit": Decimal("0.00"),
        "unearned_credit": Decimal("0.00"),
        "income_debit": Decimal("0.00"),
        "income_credit": Decimal("0.00"),
    }
