# Employee Lending v1.6.2

## Fresh-instance legacy migration

This release adds **Source GL Already Exists in This Target Site** to the
legacy import batch and individual legacy opening.

- Keep it selected when the historical Staff Loan and Unearned Interest GL is
  already posted in the target site. The existing cleanup plus clean-opening
  conversion remains unchanged.
- Clear it for a new target instance. The import skips live historical-GL
  validation, does not create a cleanup reversal, and creates only the clean
  employee-loan opening Journal Entry.
- Importing excluded employee credits in fresh-target mode now creates their
  opening Journal Entries against the configured Legacy Temporary Account.
- Neither fresh-target opening path posts to Bank or Cash.

## Deployment

```bash
cd ~/courts-frappe
bench --site <site-name> migrate
bench build --app employee_lending
bench --site <site-name> clear-cache
bench restart
```

Create a new Legacy Import Batch after migration. For a new site, clear
**Source GL Already Exists in This Target Site**, select
**Confirm No Bank Posting**, load/validate both source workbooks, and submit.
