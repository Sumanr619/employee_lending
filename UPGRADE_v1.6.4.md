# Employee Lending v1.6.4

## Employee Loan Outstanding as-of date

The Employee Loan Outstanding report now has a required **As of Date** filter,
defaulting to today.

For a historical date, the report:

- excludes loans disbursed after the selected date;
- adds back later submitted individual repayments;
- adds back later submitted batch repayments;
- adds back later employee-credit applications to loans; and
- derives Active or Closed status from the reconstructed balance.

This update changes reporting only. It does not create, cancel, or modify any
loan, repayment, employee credit, or General Ledger entry.

## Deployment

```bash
bench --site <site-name> migrate
bench build --app employee_lending
bench --site <site-name> clear-cache
bench restart
```

After deployment, hard-refresh the browser and open **Employee Loan
Outstanding**. Select the required **As of Date** and refresh the report.
