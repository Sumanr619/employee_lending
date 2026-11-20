# Employee Lending v1.6.3

This release adds **Employee Loan Credit Receipt** for money received after an employee loan is already closed or when no target loan exists.

Submitting a credit receipt:

- debits the selected bank or clearing account;
- credits Staff Loan Receivable against the employee without a loan reference;
- creates an available Employee Loan Credit for later refund or application to a future active loan;
- preserves the legacy source reference and source Journal Entry for migration audit;
- prevents duplicate imports through a unique legacy source reference.

After pulling the release, run:

```bash
bench --site <site-name> migrate
bench build --app employee_lending
bench --site <site-name> clear-cache
bench restart
```

Import the credit receipt workbook as Draft. Submit one record first and confirm the generated Journal Entry and Employee Loan Credit before submitting the remaining records.
