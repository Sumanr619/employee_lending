# Employee Lending v1.6.0 Upgrade

## What this release fixes

- Registers legacy employee overpayments that were previously counted as
  **Excluded Credit / Cleared**.
- References the existing production Journal Entries; importing a credit does
  **not** post another GL entry.
- Adds controlled **Refund** and **Apply to Loan** transactions.
- Displays employee credits in the Employee Loan Ledger.
- Adds a dedicated Employee Loan Credit Ledger.
- Makes the excluded-credit import idempotent so the same batch row cannot be
  imported twice.

## Production deployment

Install the updated app source, then run:

```bash
bench --site courts.anantdv.com migrate
bench build --app employee_lending
bench --site courts.anantdv.com clear-cache
bench restart
```

Do not skip `migrate`. It creates the Employee Loan Credit and Employee Loan
Credit Adjustment DocTypes and adds the new links to the legacy batch rows.

## Import the existing excluded credits

1. Open the already submitted **Employee Loan Legacy Import Batch**.
2. Click **Import Excluded Credits**.
3. Confirm the message stating that no GL entry will be posted.
4. Review the **Imported Employee Credits** count and amount.
5. Open **Employee Loan Credit Ledger** and verify each employee against the
   General Ledger.

Cleared K0 rows remain excluded. Only genuine negative balances are registered
as amounts owed to employees.

## Refund a credit

1. Open **Employee Loan Credit**.
2. Click **Create > Refund Credit**.
3. Enter the amount, bank account, bank reference and posting date.
4. Submit the adjustment.

Submission creates the refund Journal Entry and reduces the available employee
credit. Cancel the adjustment—not its Journal Entry—if reversal is required.

## Apply credit to a later loan

1. Create and disburse the employee's new loan normally.
2. Open **Employee Loan Credit**.
3. Click **Create > Apply to Loan**.
4. Select the employee's active loan and enter the amount.
5. Submit the adjustment.

No new cash receipt is posted. The adjustment transfers the existing employee
credit to the selected loan, updates loan balances and updates the repayment
schedule.
