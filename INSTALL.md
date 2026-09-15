# Employee Lending - Installation

## Requirements

- Frappe Framework v16
- ERPNext v16

## Install

Copy this app to the bench `apps` directory, then run:

```bash
cd ~/frappe-bench
bench pip install -e apps/employee_lending
bench --site your-site.example install-app employee_lending
bench --site your-site.example migrate
bench build --app employee_lending
bench restart
```

If installing from a Git repository:

```bash
cd ~/frappe-bench
bench get-app https://your-repository/employee_lending.git
bench --site your-site.example install-app employee_lending
bench --site your-site.example migrate
bench build --app employee_lending
bench restart
```

## Initial configuration

1. Open **Employee Lending Settings**.
2. Select the company and configure:
   - Staff Loan Receivable Account
   - Unearned Interest Account
   - Interest Income Account
   - Disbursement Bank Account
   - Repayment Bank or Clearing Account
   - Legacy Temporary Account, when legacy balances will be converted
   - Default Cost Center
3. Create or confirm these **Employee Loan Product** records (they are seeded during installation):

| Product | Months | Fortnights | Flat interest |
|---|---:|---:|---:|
| Staff Loan - 6 Months | 6 | 13 | 9% |
| Staff Loan - 12 Months | 12 | 26 | 18% |

## Accounting model

For a K1,000 loan at 9% flat interest:

Disbursement:

- Dr Staff Loan Receivable K1,090
- Cr Bank K1,000
- Cr Unearned Interest K90

Repayment of K83.85 with K6.92 interest allocation:

- Dr Bank/Clearing K83.85
- Cr Staff Loan Receivable K83.85
- Dr Unearned Interest K6.92
- Cr Interest Income K6.92

The final instalment is adjusted automatically to clear all balances exactly.

## Approval and disbursement

Submitting **Employee Loan Application** approves the loan but does not post any
bank transaction. The loan status becomes `Approved`. Use **Disburse Loan** only
when the employee is actually paid. The disbursement document records the payment
date, bank account, bank reference, first repayment date and proof of payment.
Submitting it creates the opening Journal Entry and changes the loan status to
`Active`. It cannot be cancelled while submitted repayments exist.

## Bulk repayment batches

Use **Employee Loan Repayment Batch** when one bank deposit contains repayments
for multiple employees. Enter rows manually or click **Get Loans > Load All Active
Loans**. Submission creates one consolidated Journal Entry:

- Dr Bank/Clearing - total batch amount
- Cr Staff Loan Receivable - one separate row per employee loan, linked through
  `reference_type` and `reference_name`
- Dr Unearned Interest - one separate row per employee loan
- Cr Interest Income - total interest allocation

The opening receivable is identified by its own disbursement Journal Entry. Every
repayment credit references that original Journal Entry. This allows each employee
loan to be reconciled independently even though the bank debit and interest-income
credit are consolidated. Employee-level principal, interest, and before/after
balances also remain in the batch rows for audit. Cancelling the batch cancels the
Journal Entry and restores all affected employee loan balances.

Every Staff Loan Receivable and Unearned Interest row carries `Party Type = Employee`
and the specific Employee as Party. Repayment rows additionally reference the
original disbursement Journal Entry, which is a reference type accepted by ERPNext.

## Legacy loan conversion

Use **Employee Loan Legacy Opening** only for positive balances that already exist
in the General Ledger. Do not use Loan Disbursement for these balances because it
would post Bank a second time.

The legacy opening validates the employee's live Staff Loan and Unearned Interest
balances as of the selected reconciliation cut-off date. It refuses to submit if
there is later loan activity, a credit/zero balance, a mismatch against the source
figures, or another active module loan.

Submission creates two Journal Entries and no Bank row:

1. Cleanup entry: Dr Legacy Temporary, Cr old Staff Loan principal balance, and
   Cr the old debit balance in Unearned Interest.
2. Clean opening entry: Dr Staff Loan for the gross amount outstanding, Cr Legacy
   Temporary for principal outstanding, and Cr Unearned Interest for interest
   outstanding.

The clean opening Journal Entry becomes the loan's reconciliation reference for
all future individual and bulk repayments. Historical Bank and Interest Income
postings remain unchanged. Cancel the legacy opening itself to reverse the two
conversion entries; direct cancellation of its Journal Entries is blocked.

For a large population, create **Employee Loan Legacy Import Batch** instead of
entering each opening manually. Attach both the Employee Loan Outstanding XLSX
report and the production General Ledger XLSX through the same cut-off date, then
save and click **Load and Validate Report**. The loader accepts both `Principle`
and `Principal` column spellings. It reconciles every employee's Staff Loan,
Unearned Interest, Interest Income and total outstanding figures between the two
reports before marking the row Ready.

The production GL export is the source for voucher history. For each converted
employee, the importer creates audit-only Legacy Transaction records linked to
the actual submitted opening, reversal, disbursement and repayment Journal
Entries. These records do not repost Bank, cash or historical repayments. If an
employee has multiple historical opening vouchers and the repayments contain no
against-voucher allocation, the importer creates one consolidated legacy loan
for that employee while retaining every contributing Journal Entry link.

Positive balances are mapped to the unique active 9% or 18% product. Cleared and
credit balances are excluded and invalid source rows are listed separately.
Submission queues Ready rows in the long worker. Each employee is committed
independently, so one failed employee does not roll back successful conversions.
Failed rows retain their error and can be retried after the data is corrected.

Do not attach the original Journal Entry import workbook to this batch. It does
not contain subsequent repayments. The Outstanding and GL exports must share the
selected reconciliation cut-off date; the live GL is also revalidated before
each conversion posts its no-bank cleanup and clean opening entries.
This is mandatory when either configured account has Account Type `Receivable` or
`Payable` and also allows General Ledger filtering by employee. In a bulk batch,
these rows remain separate per loan; only the Bank and Interest Income rows are
consolidated.

## Upgrade

Extract version 1.5.1 over the existing app, reinstall the editable Python package,
then migrate and build:

```bash
cd ~/courts-frappe
unzip -o employee_lending_v1.5.1.zip -d apps
./env/bin/pip install -e ./apps/employee_lending
bench --site courts.anantdv.com migrate
bench build --app employee_lending
bench restart
```

## Workflow

The app does not install an opinionated Workflow. Configure an ERPNext Workflow on
**Employee Loan Application** using your actual roles and approval sequence. The
application may be submitted only after `Approval Status` is set to `Approved`.

Recommended states: Draft -> Manager Review -> HR Verification -> Pay Office Review
-> Credit Approval -> Approved.
