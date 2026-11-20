"""Pure balance allocation helpers shared by reports and regression tests."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


AGE_FIELDS = ("current_amount", "age_1_30", "age_31_60", "age_61_90",
              "age_91_180", "age_181_365", "age_over_365", "unaged_amount")


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def as_date(value):
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def bucket_for(days):
    if days <= 0:
        return "current_amount"
    for limit, key in ((30, "age_1_30"), (60, "age_31_60"),
                       (90, "age_61_90"), (180, "age_91_180"),
                       (365, "age_181_365")):
        if days <= limit:
            return key
    return "age_over_365"


def age_balance(balance, as_of_date, schedule=(), origin_date=None, by_origin=False):
    """Age positive loan balances FIFO, or signed balances by their origin date.

    Schedule paid_amount is deliberately ignored: it reflects today's payments,
    whereas balance is already reconstructed for the selected reporting date.
    Missing schedule coverage/dates stays visible in Unaged.
    """
    result = {key: Decimal("0.00") for key in AGE_FIELDS}
    balance = money(balance)
    cutoff = as_date(as_of_date)
    oldest_due = None
    if by_origin:
        origin = as_date(origin_date)
        key = bucket_for((cutoff - origin).days) if origin else "unaged_amount"
        result[key] = balance
    else:
        schedule = list(schedule)
        scheduled = sum((max(Decimal(0), money(r.get("repayment_amount"))) for r in schedule), Decimal(0))
        paid = max(Decimal(0), scheduled - balance)
        remaining = balance
        for row in schedule:
            amount = max(Decimal(0), money(row.get("repayment_amount")))
            applied = min(paid, amount)
            paid -= applied
            unpaid = min(remaining, amount - applied)
            if unpaid <= 0:
                continue
            due = as_date(row.get("due_date"))
            key = bucket_for((cutoff - due).days) if due else "unaged_amount"
            result[key] += unpaid
            remaining -= unpaid
            if due and due < cutoff and (oldest_due is None or due < oldest_due):
                oldest_due = due
        result["unaged_amount"] += remaining
    result = {key: float(money(value)) for key, value in result.items()}
    result["oldest_unpaid_due_date"] = oldest_due
    result["days_overdue"] = (cutoff - oldest_due).days if oldest_due else 0
    return result


def allocate_receipt(amount, outstanding, rate, principal, interest, splitter):
    """A zero-balance loan accepts any number of independent credit receipts."""
    amount, outstanding = money(amount), money(outstanding)
    if amount <= 0:
        raise ValueError("Repayment Amount must be greater than zero")
    if outstanding < 0 or money(principal) < 0 or money(interest) < 0:
        raise ValueError("Loan balances cannot be negative")
    if outstanding != money(money(principal) + money(interest)):
        raise ValueError("Loan principal and interest do not reconcile to outstanding")
    applied = min(amount, outstanding)
    if applied:
        split = splitter(applied, rate, principal, interest)
        principal_part, interest_part = split.principal, split.interest
    else:
        principal_part = interest_part = Decimal("0.00")
    return {"received": float(amount), "applied": float(applied),
            "credit": float(money(amount - applied)),
            "principal": float(principal_part), "interest": float(interest_part)}
