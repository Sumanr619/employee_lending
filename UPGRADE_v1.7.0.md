# Employee Lending v1.7.0 — Combined ageing and repeated credit payments

Prepared: 7 November 2026. Source baseline: recovered v1.6.4 package.
Status: staging release candidate. This package has not been installed on a running ERPNext/Frappe site.

## Requested behavior

1. Employee Loan Outstanding includes available Employee Loan Credit balances alongside loans, with an As of Date and ageing. The existing Credit Ledger remains available.
2. A payment reduces the full remaining loan balance first. Excess is employee credit. A further payment against a closed loan is entirely employee credit, and any number of separate later payments can be recorded. This is not an instalment-cap allocation rule.

No historical imports are executed by this release. No archived IMPORT_READY workbook is a release instruction.

## Combined Outstanding report

Open Employee Loan Outstanding. Select the company, As of Date, and optional employee.

- Include Employee Credits: enabled by default.
- View: Loan and Credit Detail, or Employee Summary.
- Ageing Basis: Instalment Due Date (default), or Loan / Credit Date.
- Loan Status: applies to loan rows only. Available credits, including credit-only employees, remain visible. This scope is stated on the report.

Columns show gross loan outstanding, principal outstanding, unearned interest, available credit, and net outstanding. Credits appear as separate records in detail, once per credit, rather than being copied onto each loan. Employee Summary adds each employee's loans and credits once within each company. Net outstanding = gross loan outstanding - available credit. A negative net balance means a net credit is held for the employee.

Age buckets: Current / Not Due; 1–30; 31–60; 61–90; 91–180; 181–365; Over 365; Unaged.

### Ageing rules

Under Instalment Due Date, the historical loan balance is allocated FIFO over the loan schedule by instalment index, applying paid amounts to the earliest instalments. Instalments due today or later are current. Historical paid amounts are derived from the selected-date outstanding balance, not from today's schedule paid_amount field. Missing schedule amounts/dates are shown as Unaged, so the report does not invent arrears dates.

Under Loan / Credit Date, the entire loan balance ages from its disbursement/conversion date. This is balance age, not instalment delinquency. Days Overdue is only meaningful in Instalment Due Date mode.

Credits always age from their credit/opening cutoff date and appear as negative age-bucket amounts. For each detail or summary row, the sum of the age buckets equals net outstanding. These are net presentation buckets; they do not legally or operationally allocate employee credit against a loan. Submit a Credit Adjustment to perform an actual application or refund.

Credit availability is reconstructed as original credit less currently submitted credit adjustments with posting_date <= As of Date. Future adjustments and draft/cancelled adjustments are excluded. Future credits are excluded. Today's credit status/available balance is not used to filter historical results.

The inherited historical loan reconstruction adds later currently submitted reductions back to the stored loan balances. These reports describe the effective-dated position of current records, not an immutable snapshot of previously issued reports. Changes to underlying records or their cancellation can change a rerun.

Use one company/currency at a time for reconciliation. Totals are not currency-converted.

## Recording repeated overpayments

In Employee Loan Repayment, select the submitted active or closed loan, enter the actual payment date, amount, bank/clearing account, bank reference and proof where required. The loan's Create > Record Repayment button is also available after closure. A closed loan initially previews zero applied amount; enter the receipt amount to see the full credit.

Example:

| Event | Received | Applied to loan | New employee credit | Loan balance |
|---|---:|---:|---:|---:|
| Start | — | — | — | K100 |
| Payment 1 | K150 | K100 | K50 | K0 |
| Payment 2 | K75 | K0 | K75 | K0 |
| Payment 3 | K25 | K0 | K25 | K0 |

Total new credit is K150. Each payment creates its own credit record and linked JE. The second and third receipts leave the loan Closed.

Accounting for a credit-only payment: Dr Bank/Clearing; Cr Staff Loan Receivable with Employee party and no allocation to the closed loan's disbursement JE. No principal recovery or interest income is recognized. No zero-value JE rows are added.

For Repayment Batch, explicitly add a closed loan when a receipt arrives for it. Load All Active Loans remains active-only so it does not prefill every closed account. One loan per batch remains the existing rule; separate receipts may be entered as separate repayment documents or batches. A batch creates one consolidated bank debit and separate applied/unallocated employee lines.

The existing Employee Loan Credit Receipt route remains available when there is no loan to select. Use only one posting route for each real receipt.

## Cancellation

Cancel the source payment, not its Journal Entry directly. A credit-only repayment cancellation reverses its JE and removes its unused operational credit; it does not reopen the loan or rewrite its repayment schedule. If the credit has been applied/refunded, cancel those adjustments first.

The JE cancellation guard now also covers standalone Employee Loan Credit Receipt documents. Other cancellation checks are retained.

## Staging installation

1. Identify the actual installed site, app version and Git commit. Compare local production changes with this v1.6.4-based package before installing. Do not overwrite unreviewed production patches.
2. Restore a production backup to staging. Preserve the matching app code and site files.
3. Place this complete app source into a controlled app checkout/install in the staging bench. Retain the package root layout containing pyproject.toml and employee_lending/. Do not paste individual snippets.
4. With the app installed in the bench Python environment, run the following against staging (replace the path and site name):

```bash
cd /path/to/staging-bench
bench --site STAGING-SITE backup --with-files
bench --site STAGING-SITE migrate
bench build --app employee_lending
bench --site STAGING-SITE clear-cache
bench restart
bench version
```

Confirm the installed employee_lending version is 1.7.0. This release adds no DocType fields, but normal migration/cache/build steps are still needed for application/report metadata and assets.

## Validation performed locally

- 25 offline Python regression tests passed: ageing boundaries and FIFO allocation; missing schedules; excess versus total balance; repeated closed-loan receipts; submit/cancel control flow; used-credit cancellation protection; mixed batches; balanced unallocated JEs; Credit Receipt cancellation guard; detailed and employee summary reports; credit-only employees; historical credit SQL and future reductions.
- Three Node form/report checks passed: closed-loan single receipt preview; closed-loan batch preview; combined-report filters.
- All Python, JSON and JavaScript source syntax checks passed.
- Historical credit SQL was executed against an in-memory SQLite fixture. Frappe/MariaDB-specific persistence, validation and permissions were not exercised.

Run the offline suite from the extracted application root, outside a live bench test process (the test suite installs Frappe stubs):

```bash
python -m unittest discover -s tests -v
node tests/test_ui_170.js
```

## Required staging acceptance

- Reconcile today's gross loan and credit totals with the existing module reports and GL, using the same date/company/currency.
- Verify 31 July, 31 August and 30 September historical credit availability, including a credit fully used after each cutoff.
- Check a credit-only employee, an employee with two loans and one credit, a partially paid overdue instalment, a missing schedule, and each age boundary.
- Confirm detail totals equal Employee Summary totals, and age buckets sum to net outstanding.
- Submit an ordinary partial payment, a payoff with excess, and at least two further payments after closure. Check each JE, Employee party, bank movement, loan status and credit balance.
- Submit a batch mixing active and closed loans, then a later batch against the closed loan. Confirm one JE per batch and no zero-value rows.
- Cancel an unused credit-only receipt: reverse only that receipt and its credit, keep the loan closed. Apply part of a different credit and confirm cancellation is blocked until its adjustment is cancelled.
- Confirm direct JE cancellation is blocked for standalone Credit Receipts and repayments.
- Test Accounts User / Accounts Manager permissions, report export/print and actual browser behavior on the installed Frappe v16 site.
- Obtain acceptance before using the release on production.

## Scope and outstanding issues

This feature release does not resolve the historical K7,606.21 reconciliation gap, prove the old 75-row import outcomes, or backfill missing historical credit records. A combined report can display only credit records that actually exist in the operational register.

The prior review's cross-route migration duplicate risk and credit-application target-loan concurrency concern remain separate work. Existing source-reference controls are retained, but they do not deduplicate a receipt across an old direct Journal Entry and a newly entered repayment. Do not reimport historical bank receipts or use both archived credit import formats.

Rollback, if required after posting transactions, must preserve/restore consistent database, files and app code. Do not roll back code alone after financial activity without a reviewed reconciliation plan.
