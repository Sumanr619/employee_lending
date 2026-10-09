# Employee Lending v1.6.1

This maintenance release fixes repayment processing and employee statements.

## Fixes

1. **Repayment overpayments**
   - A payment may exceed the selected loan's outstanding balance.
   - The outstanding amount is applied to the loan.
   - The excess is posted as an unallocated employee credit and registered in
     **Employee Loan Credit** for later refund or application to another loan.
   - The same treatment is supported for individual and batch repayments.

2. **Statement remarks**
   - Remarks entered on an individual repayment or repayment batch are copied
     to the Journal Entry.
   - Employee Loan Ledger and its statement print format prefer the entered
     repayment remarks over the system-generated GL description.

3. **Zero-value Journal Entry rows**
   - Interest rows are no longer created when the interest component is zero.
   - This resolves `Both Debit and Credit values cannot be zero` for loans such
     as Tiko Tau and Jim Benny where no unearned interest remains.

## Deployment

From the bench directory, after pulling this release:

```bash
bench --site erp.courts.com.pg backup --with-files
bench --site erp.courts.com.pg migrate
bench build --app employee_lending
bench --site erp.courts.com.pg clear-cache
bench restart
```

Migration is required because repayment and batch DocTypes contain new fields
for the amount applied to the loan and the excess employee credit.

## Acceptance checks

- Submit a normal repayment on a loan with zero interest outstanding; the
  Journal Entry must contain no zero-value rows.
- Enter a repayment greater than the loan outstanding; the loan must close and
  an Employee Loan Credit must be created for the difference.
- Print Employee Loan Ledger and confirm the repayment remarks appear in the
  Description column.
- Cancel an unused overpayment repayment and confirm its Employee Loan Credit
  is removed. If the credit has already been used, the system must require the
  credit adjustment to be cancelled first.
