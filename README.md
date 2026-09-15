# Employee Lending

Employee loan origination, flat-interest scheduling, disbursement, bank repayment,
salary deduction authority, and Journal Entry automation for ERPNext/Frappe v16.

## Included

- Configurable accounting and policy settings
- Configurable 6-month/13-fortnight and 12-month/26-fortnight products
- Employee loan application and eligibility assessment
- Separate loan disbursement document with bank reference and proof of payment
- Liabilities, assets, bank details, supporting documents and approvals
- Exact flat-interest schedule with final-instalment rounding adjustment
- Automatic submitted Journal Entry for loan disbursement
- Bank repayment interface with proof of payment
- Automatic submitted four-line repayment Journal Entry
- Bulk repayment batch with manual rows or automatic loading of active loans
- One consolidated Journal Entry per repayment batch, with a separate referenced
  receivable row against every employee loan
- Employee Party Type and Party on every receivable row for ERPNext receivable-account validation
- Employee party and original disbursement Journal Entry reference on every
  receivable and unearned-interest repayment row, including bulk batches
- Transaction-safe outstanding balance updates and cancellation reversal
- Staff Salary Deduction Authority document
- Employee Loan Outstanding report and workspace
- Controlled Legacy Loan Opening for balances already posted through historical Journal Entries
- Live GL validation at the reconciliation cut-off date
- Two no-bank conversion entries: cleanup of the old principal/interest structure and a clean gross-receivable opening
- Automatic blocking of credit balances, cleared balances, duplicate module loans, mismatched GL balances, and post-cut-off activity
- Bulk legacy import jointly validated from the Employee Loan Outstanding and production General Ledger XLSX reports
- Audit-only legacy transaction records linking every employee allocation to its existing submitted Journal Entry without reposting Bank or repayments
- Background row-by-row conversion with progress tracking, resumable failures, and an exception list
- Seed data for the standard 9% and 18% products

See `INSTALL.md` for installation and configuration.
