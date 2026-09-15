from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


MONEY = Decimal("0.01")


def decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def money(value) -> Decimal:
    return decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LoanTotals:
    principal: Decimal
    interest: Decimal
    total_due: Decimal
    normal_repayment: Decimal


@dataclass(frozen=True)
class RepaymentSplit:
    amount: Decimal
    principal: Decimal
    interest: Decimal


@dataclass(frozen=True)
class LegacyConversion:
    original_principal: Decimal
    original_interest: Decimal
    principal_repaid: Decimal
    interest_repaid: Decimal
    principal_outstanding: Decimal
    interest_outstanding: Decimal
    gross_outstanding: Decimal
    current_unearned_debit: Decimal
    cleanup_temporary_debit: Decimal
    cleanup_staff_loan_credit: Decimal
    cleanup_unearned_interest_credit: Decimal
    opening_staff_loan_debit: Decimal
    opening_temporary_credit: Decimal
    opening_unearned_interest_credit: Decimal


def calculate_loan(principal, flat_interest_rate, number_of_repayments) -> LoanTotals:
    principal = money(principal)
    rate = decimal(flat_interest_rate)
    count = int(number_of_repayments or 0)

    if principal <= 0:
        raise ValueError("Principal must be greater than zero")
    if rate < 0:
        raise ValueError("Interest rate cannot be negative")
    if count <= 0:
        raise ValueError("Number of repayments must be greater than zero")

    interest = money(principal * rate / Decimal("100"))
    total_due = money(principal + interest)
    normal_repayment = money(total_due / count)
    return LoanTotals(principal, interest, total_due, normal_repayment)


def split_repayment(
    repayment_amount,
    flat_interest_rate,
    outstanding_principal,
    outstanding_interest,
) -> RepaymentSplit:
    amount = money(repayment_amount)
    rate = decimal(flat_interest_rate)
    principal_left = money(outstanding_principal)
    interest_left = money(outstanding_interest)
    total_left = money(principal_left + interest_left)

    if amount <= 0:
        raise ValueError("Repayment amount must be greater than zero")
    if amount > total_left:
        raise ValueError("Repayment cannot exceed the outstanding amount")

    if amount == total_left:
        return RepaymentSplit(amount, principal_left, interest_left)

    denominator = Decimal("100") + rate
    principal = money(amount * Decimal("100") / denominator)
    interest = money(amount - principal)

    if principal > principal_left:
        principal = principal_left
        interest = money(amount - principal)
    if interest > interest_left:
        interest = interest_left
        principal = money(amount - interest)

    return RepaymentSplit(amount, principal, interest)


def calculate_legacy_conversion(
    original_principal,
    original_interest,
    principal_repaid,
    interest_repaid,
    current_unearned_debit,
) -> LegacyConversion:
    original_principal = money(original_principal)
    original_interest = money(original_interest)
    principal_repaid = money(principal_repaid)
    interest_repaid = money(interest_repaid)
    current_unearned_debit = money(current_unearned_debit)

    if original_principal <= 0:
        raise ValueError("Original principal must be greater than zero")
    if original_interest < 0 or principal_repaid < 0 or interest_repaid < 0:
        raise ValueError("Legacy loan amounts cannot be negative")
    if principal_repaid > original_principal:
        raise ValueError("Principal repaid cannot exceed original principal")
    if interest_repaid > original_interest:
        raise ValueError("Interest repaid cannot exceed original interest")
    if current_unearned_debit < 0:
        raise ValueError("Current unearned-interest balance must be a debit or zero")

    principal_outstanding = money(original_principal - principal_repaid)
    interest_outstanding = money(original_interest - interest_repaid)
    gross_outstanding = money(principal_outstanding + interest_outstanding)
    if gross_outstanding <= 0:
        raise ValueError("Only positive legacy loan balances can be converted")

    # Two separate journals are required. The cleanup journal removes the old
    # principal-only receivable and debit unearned-interest balance. The clean
    # opening journal then establishes one gross receivable voucher that future
    # repayments can reference. Bank and recognized income remain untouched.
    cleanup_temporary_debit = money(principal_outstanding + current_unearned_debit)
    cleanup_staff_loan_credit = principal_outstanding
    cleanup_unearned_interest_credit = current_unearned_debit
    opening_staff_loan_debit = gross_outstanding
    opening_temporary_credit = principal_outstanding
    opening_unearned_interest_credit = interest_outstanding

    if cleanup_temporary_debit != money(cleanup_staff_loan_credit + cleanup_unearned_interest_credit):
        raise ValueError("Legacy cleanup journal does not balance")
    if opening_staff_loan_debit != money(opening_temporary_credit + opening_unearned_interest_credit):
        raise ValueError("Legacy opening journal does not balance")

    return LegacyConversion(
        original_principal=original_principal,
        original_interest=original_interest,
        principal_repaid=principal_repaid,
        interest_repaid=interest_repaid,
        principal_outstanding=principal_outstanding,
        interest_outstanding=interest_outstanding,
        gross_outstanding=gross_outstanding,
        current_unearned_debit=current_unearned_debit,
        cleanup_temporary_debit=cleanup_temporary_debit,
        cleanup_staff_loan_credit=cleanup_staff_loan_credit,
        cleanup_unearned_interest_credit=cleanup_unearned_interest_credit,
        opening_staff_loan_debit=opening_staff_loan_debit,
        opening_temporary_credit=opening_temporary_credit,
        opening_unearned_interest_credit=opening_unearned_interest_credit,
    )


def build_remaining_schedule(
    outstanding_principal,
    outstanding_interest,
    flat_interest_rate,
    number_of_repayments,
    normal_repayment=0,
):
    principal_left = money(outstanding_principal)
    interest_left = money(outstanding_interest)
    count = int(number_of_repayments or 0)
    if principal_left < 0 or interest_left < 0:
        raise ValueError("Outstanding balances cannot be negative")
    if principal_left + interest_left <= 0:
        raise ValueError("Outstanding balance must be greater than zero")
    if count <= 0:
        raise ValueError("Remaining instalments must be greater than zero")

    total_left = money(principal_left + interest_left)
    normal = money(normal_repayment) if money(normal_repayment) > 0 else money(total_left / count)
    rows = []
    for index in range(1, count + 1):
        outstanding = money(principal_left + interest_left)
        amount = outstanding if index == count else min(normal, outstanding)
        split = split_repayment(amount, flat_interest_rate, principal_left, interest_left)
        principal_left = money(principal_left - split.principal)
        interest_left = money(interest_left - split.interest)
        rows.append(
            {
                "repayment_no": index,
                "repayment_amount": split.amount,
                "principal_component": split.principal,
                "interest_component": split.interest,
                "principal_balance": principal_left,
                "unearned_interest_balance": interest_left,
                "total_outstanding": money(principal_left + interest_left),
            }
        )
    return rows


def build_schedule(principal, flat_interest_rate, number_of_repayments):
    totals = calculate_loan(principal, flat_interest_rate, number_of_repayments)
    principal_left = totals.principal
    interest_left = totals.interest
    rows = []

    for index in range(1, int(number_of_repayments) + 1):
        outstanding = money(principal_left + interest_left)
        amount = outstanding if index == int(number_of_repayments) else min(totals.normal_repayment, outstanding)
        split = split_repayment(amount, flat_interest_rate, principal_left, interest_left)
        principal_left = money(principal_left - split.principal)
        interest_left = money(interest_left - split.interest)
        rows.append(
            {
                "repayment_no": index,
                "repayment_amount": split.amount,
                "principal_component": split.principal,
                "interest_component": split.interest,
                "principal_balance": principal_left,
                "unearned_interest_balance": interest_left,
                "total_outstanding": money(principal_left + interest_left),
            }
        )
    return totals, rows
