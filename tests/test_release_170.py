"""Offline regression tests. Frappe persistence/SQL is stubbed; staging UAT is separate.
Run from the application root: python -m unittest discover -s tests -v
"""
import copy
import importlib
import sys
import types
import unittest
from datetime import date
from unittest.mock import Mock, patch


class AttrDict(dict):
    def __getattr__(self, name):
        return self.get(name)
    __setattr__ = dict.__setitem__


class FakeDocument(AttrDict):
    def __init__(self, **values):
        super().__init__(values)
        self.flags = AttrDict()
    def db_set(self, key, value, **kwargs):
        self[key] = value
    def check_permission(self, *args):
        pass


frappe = types.ModuleType('frappe')
frappe._ = lambda text: text
frappe._dict = AttrDict
frappe.throw = Mock(side_effect=ValueError)
frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
frappe.db = Mock()
utils = types.ModuleType('frappe.utils')
utils.flt = lambda value=0, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)
utils.nowdate = lambda: '2026-11-07'
utils.getdate = lambda value: date.fromisoformat(str(value)[:10])
model = types.ModuleType('frappe.model')
document = types.ModuleType('frappe.model.document')
document.Document = FakeDocument
sys.modules.update({'frappe': frappe, 'frappe.utils': utils, 'frappe.model': model,
                    'frappe.model.document': document})

ROOT = 'employee_lending.employee_lending.'
helpers = importlib.import_module(ROOT + 'balance_reporting')
calc = importlib.import_module(ROOT + 'utils')
repay = importlib.import_module(ROOT + 'doctype.employee_loan_repayment.employee_loan_repayment')
batch = importlib.import_module(ROOT + 'doctype.employee_loan_repayment_batch.employee_loan_repayment_batch')
accounting = importlib.import_module(ROOT + 'accounting')
report = importlib.import_module(ROOT + 'report.employee_loan_outstanding.employee_loan_outstanding')
guard = importlib.import_module(ROOT + 'journal_entry')


def loan(**kwargs):
    values = dict(name='LOAN1', employee='EMP1', employee_name='Employee One', company='Courts',
                  docstatus=1, loan_status='Active', flat_interest_rate=9, fortnightly_repayment=83.85,
                  principal_outstanding=100, unearned_interest_outstanding=9, total_outstanding=109,
                  principal_recovered=0, interest_earned=0, total_repaid=0,
                  disbursement_date='2026-07-31', disbursement_journal_entry='OPEN1')
    values.update(kwargs)
    return AttrDict(values)


class AgeingTests(unittest.TestCase):
    def test_all_bucket_boundaries(self):
        expected = [(-1,'current_amount'),(0,'current_amount'),(1,'age_1_30'),(30,'age_1_30'),
                    (31,'age_31_60'),(60,'age_31_60'),(61,'age_61_90'),(90,'age_61_90'),
                    (91,'age_91_180'),(180,'age_91_180'),(181,'age_181_365'),
                    (365,'age_181_365'),(366,'age_over_365')]
        for days, key in expected:
            with self.subTest(days=days):
                self.assertEqual(helpers.bucket_for(days), key)

    def test_partial_fifo_and_future_instalments(self):
        schedule = [dict(due_date='2026-09-01', repayment_amount=100, paid_amount=100),
                    dict(due_date='2026-10-01', repayment_amount=100, paid_amount=100),
                    dict(due_date='2026-11-01', repayment_amount=100, paid_amount=100)]
        result = helpers.age_balance(150, '2026-10-15', schedule)
        self.assertEqual(result['age_1_30'], 50)
        self.assertEqual(result['current_amount'], 100)
        self.assertEqual(result['days_overdue'], 14)
        self.assertEqual(sum(result[k] for k in helpers.AGE_FIELDS), 150)

    def test_missing_schedule_is_unaged(self):
        self.assertEqual(helpers.age_balance(109,'2026-10-15')['unaged_amount'],109)

    def test_schedule_shortfall_is_visible(self):
        result = helpers.age_balance(150,'2026-10-15',[dict(due_date=None,repayment_amount=100)])
        self.assertEqual(result['unaged_amount'],150)

    def test_credit_ages_negative_without_reducing_loan(self):
        result=helpers.age_balance(-75,'2026-10-15',origin_date='2026-09-01',by_origin=True)
        self.assertEqual(result['age_31_60'],-75)
        self.assertEqual(sum(result[k] for k in helpers.AGE_FIELDS),-75)


class ReceiptTests(unittest.TestCase):
    def test_above_instalment_below_balance_is_loan_reduction(self):
        allocation=helpers.allocate_receipt(100,109,9,100,9,calc.split_repayment)
        self.assertEqual(allocation['applied'],100)
        self.assertEqual(allocation['credit'],0)

    def test_payoff_then_multiple_credit_receipts(self):
        first=helpers.allocate_receipt(150,109,9,100,9,calc.split_repayment)
        second=helpers.allocate_receipt(50,0,9,0,0,calc.split_repayment)
        third=helpers.allocate_receipt(25,0,9,0,0,calc.split_repayment)
        self.assertEqual([first['credit'],second['credit'],third['credit']],[41,50,25])
        self.assertEqual(second['principal']+third['interest'],0)

    def test_invalid_or_inconsistent_balances_rejected(self):
        for args in [(0,0,9,0,0),(-10,0,9,0,0),(10,109,9,99,9)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                helpers.allocate_receipt(*args,calc.split_repayment)

    def test_closed_loan_controller_accepts_and_calculates_credit(self):
        closed=loan(loan_status='Closed',principal_outstanding=0,unearned_interest_outstanding=0,total_outstanding=0)
        doc=repay.EmployeeLoanRepayment(loan_application='LOAN1',repayment_amount=50)
        with patch.object(frappe.db,'get_value',return_value=closed):
            doc.set_loan_details()
        doc.calculate_split()
        self.assertEqual((doc.applied_amount,doc.credit_amount,doc.total_outstanding_after),(0,50,0))

    def test_credit_only_submit_and_cancel_do_not_reopen_loan(self):
        doc=repay.EmployeeLoanRepayment(name='REPAY2',loan_application='LOAN1',applied_amount=0,
                                       credit_amount=50,posting_date='2026-10-15',remarks='Receipt',employee_credit=None)
        with patch.object(frappe,'get_doc',return_value=loan(),create=True), \
             patch.object(repay,'create_repayment_journal',return_value=AttrDict(name='JE2')), \
             patch.object(repay,'create_repayment_credit',return_value='CREDIT2') as create, \
             patch.object(repay.EmployeeLoanRepayment,'update_loan_balances') as update, \
             patch.object(frappe.db,'get_value',return_value=None), \
             patch.object(repay,'cancel_linked_journal_entry'), \
             patch.object(repay,'delete_unused_repayment_credit'):
            doc.on_submit()
            self.assertEqual(doc.employee_credit,'CREDIT2')
            self.assertEqual(create.call_args.kwargs['source_reference'],'repayment:REPAY2')
            doc.on_cancel()
            update.assert_not_called()

    def test_used_credit_blocks_receipt_cancellation(self):
        doc=repay.EmployeeLoanRepayment(employee_credit='CREDIT2')
        with patch.object(frappe.db,'get_value',return_value='ADJUST1'), \
             patch.object(repay,'cancel_linked_journal_entry') as cancel:
            with self.assertRaises(ValueError):
                doc.on_cancel()
            cancel.assert_not_called()

    def test_mixed_batch_closed_and_active(self):
        loans={'CLOSED':loan(name='CLOSED',loan_status='Closed',principal_outstanding=0,
                            unearned_interest_outstanding=0,total_outstanding=0), 'ACTIVE':loan(name='ACTIVE')}
        rows=[AttrDict(loan_application='CLOSED',repayment_amount=50,idx=1),
              AttrDict(loan_application='ACTIVE',repayment_amount=150,idx=2)]
        doc=batch.EmployeeLoanRepaymentBatch(company='Courts',repayments=rows)
        with patch.object(frappe.db,'get_value',side_effect=lambda dt,name,*a,**kw:loans[name]):
            doc.calculate_rows()
        self.assertEqual((doc.total_repayment_amount,doc.total_applied_amount,doc.total_credit_amount),(200,109,91))
        self.assertEqual(rows[0].credit_amount,50)
        self.assertEqual(rows[0].applied_amount,0)

    def test_credit_only_batch_does_not_update_loan(self):
        doc=batch.EmployeeLoanRepaymentBatch(repayments=[AttrDict(loan_application='CLOSED',applied_amount=0)])
        with patch.object(frappe.db,'sql') as sql:
            doc.update_loan_balances(-1)
            sql.assert_not_called()


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.settings=AttrDict(company='Courts',repayment_bank_or_clearing_account='Bank',
                               staff_loan_receivable_account='Loans',unearned_interest_account='Unearned',
                               interest_income_account='Income')
        self.journal=FakeDocument(accounts=[])
        self.journal.append=lambda field,row:self.journal.accounts.append(row)
        self.journal.insert=lambda **kw:None
        self.journal.submit=lambda:None

    def assert_balanced_nonzero(self):
        rows=self.journal.accounts
        self.assertEqual(round(sum(r['debit_in_account_currency']-r['credit_in_account_currency'] for r in rows),2),0)
        self.assertTrue(all(r['debit_in_account_currency'] or r['credit_in_account_currency'] for r in rows))

    def test_single_credit_only_je_has_two_rows_no_loan_reference(self):
        receipt=AttrDict(name='REPAY2',posting_date='2026-10-15',bank_reference='BANK2',
                         repayment_amount=50,applied_amount=0,credit_amount=50,interest_component=0)
        with patch.object(accounting,'get_settings',return_value=self.settings), \
             patch.object(frappe,'new_doc',return_value=self.journal,create=True), \
             patch.object(accounting,'_loan_journal_reference',side_effect=AssertionError('Must not link credit')):
            accounting.create_repayment_journal(receipt,loan())
        self.assert_balanced_nonzero()
        self.assertEqual(len(self.journal.accounts),2)
        self.assertNotIn('reference_name',self.journal.accounts[1])

    def test_active_payoff_and_excess_keep_only_applied_amount_linked(self):
        receipt=AttrDict(name='REPAY1',posting_date='2026-10-15',repayment_amount=150,
                         applied_amount=109,credit_amount=41,interest_component=9)
        with patch.object(accounting,'get_settings',return_value=self.settings), \
             patch.object(frappe,'new_doc',return_value=self.journal,create=True):
            accounting.create_repayment_journal(receipt,loan())
        self.assert_balanced_nonzero()
        loans=[r for r in self.journal.accounts if r['account']=='Loans']
        self.assertEqual([(r['credit_in_account_currency'],r.get('reference_name')) for r in loans],[(109,'OPEN1'),(41,None)])

    def test_credit_only_batch_has_one_bank_debit(self):
        rows=[AttrDict(employee='EMP1',applied_amount=0,credit_amount=50),
              AttrDict(employee='EMP2',applied_amount=0,credit_amount=25)]
        doc=AttrDict(name='BATCH2',company='Courts',posting_date='2026-10-15',repayments=rows,
                     total_repayment_amount=75,total_interest_component=0)
        with patch.object(accounting,'get_settings',return_value=self.settings), \
             patch.object(frappe,'new_doc',return_value=self.journal,create=True), \
             patch.object(accounting,'_loan_journal_reference',side_effect=AssertionError('Must not link credit')):
            accounting.create_batch_repayment_journal(doc)
        self.assert_balanced_nonzero()
        self.assertEqual(len(self.journal.accounts),3)

    def test_standalone_credit_receipt_is_guarded(self):
        def get_value(doctype,*args,**kwargs):
            return 'RECEIPT1' if doctype=='Employee Loan Credit Receipt' else None
        with patch.object(frappe.db,'get_value',side_effect=get_value), self.assertRaises(ValueError):
            guard.prevent_orphaned_lending_entry(FakeDocument(name='JE2'))


class ReportTests(unittest.TestCase):
    def execute(self,filters=None):
        loans=[loan(approved_principal=100)]
        credits=[AttrDict(name='CREDIT1',company='Courts',employee='EMP1',employee_name='Employee One',
                          cutoff_date='2026-09-01',available=30),
                 AttrDict(name='CREDIT2',company='Courts',employee='EMP2',employee_name='Only Credit',
                          cutoff_date='2026-09-02',available=50)]
        schedules={'LOAN1':[AttrDict(due_date='2026-09-01',repayment_amount=109)]}
        with patch.object(frappe.db,'sql',return_value=copy.deepcopy(loans)), \
             patch.object(report,'get_future_allocations',return_value={}), \
             patch.object(report,'get_schedules',return_value=schedules), \
             patch.object(report,'get_credits_as_of',return_value=credits):
            return report.execute(dict(as_of_date='2026-10-15',**(filters or {})))

    def test_detail_credit_only_employee_and_net_reconciliation(self):
        _,rows,_,_,summary=self.execute()
        self.assertEqual(len(rows),3)
        self.assertEqual(sum(r.net_outstanding for r in rows),29)
        self.assertEqual([item['value'] for item in summary],[109,80,29])
        for row in rows:
            self.assertEqual(round(sum(row[k] for k in helpers.AGE_FIELDS),2),row.net_outstanding)
        self.assertEqual([r.employee for r in rows].count('EMP2'),1)

    def test_summary_does_not_repeat_employee_credit_per_loan(self):
        _,rows,*_=self.execute({'view':'Employee Summary'})
        emp1=next(r for r in rows if r.employee=='EMP1')
        self.assertEqual((emp1.total_outstanding,emp1.available_credit,emp1.net_outstanding),(109,30,79))

    def test_two_loans_share_one_credit_total(self):
        rows=[AttrDict(company='Courts',employee='EMP1',employee_name='One',total_outstanding=100,net_outstanding=100),
              AttrDict(company='Courts',employee='EMP1',employee_name='One',total_outstanding=50,net_outstanding=50),
              AttrDict(company='Courts',employee='EMP1',employee_name='One',available_credit=30,net_outstanding=-30)]
        summary=report.summarize_employees(rows)
        self.assertEqual((summary[0].total_outstanding,summary[0].available_credit,summary[0].net_outstanding),(150,30,120))

    def test_historical_credit_query_against_sqlite(self):
        import sqlite3
        import re
        db=sqlite3.connect(':memory:')
        db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE "tabEmployee Loan Credit" (name, company, employee, employee_name, cutoff_date, original_credit)')
        db.execute('CREATE TABLE "tabEmployee Loan Credit Adjustment" (employee_credit, amount, docstatus, posting_date)')
        db.executemany('INSERT INTO "tabEmployee Loan Credit" VALUES (?,?,?,?,?,?)',[
            ('C1','Courts','EMP1','One','2026-08-01',100),
            ('FUTURE','Courts','EMP1','One','2026-12-01',200),
            ('USED','Courts','EMP1','One','2026-08-01',20)])
        db.executemany('INSERT INTO "tabEmployee Loan Credit Adjustment" VALUES (?,?,?,?)',[
            ('C1',30,1,'2026-09-01'),('C1',50,1,'2026-11-01'),
            ('C1',15,2,'2026-09-02'),('C1',5,0,'2026-09-03'),('USED',20,1,'2026-09-01')])
        def sql(query,values,**kwargs):
            query=re.sub(r'%\((\w+)\)s',r':\1',query)
            return [AttrDict(dict(r)) for r in db.execute(query,values)]
        try:
            with patch.object(frappe.db,'sql',side_effect=sql):
                historical=report.get_credits_as_of(AttrDict(company='Courts'),'2026-10-15')
                current=report.get_credits_as_of(AttrDict(company='Courts'),'2026-11-15')
            self.assertEqual([(r.name,r.available) for r in historical],[('C1',70)])
            self.assertEqual([(r.name,r.available) for r in current],[('C1',20)])
        finally:
            db.close()

    def test_include_credit_toggle(self):
        _,rows,*_=self.execute({'include_credits':0})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].net_outstanding,109)

    def test_active_filter_keeps_credit_only_employee(self):
        _,rows,*_=self.execute({'loan_status':'Active'})
        self.assertTrue(any(r.employee=='EMP2' for r in rows))

    def test_future_reduction_reconstructed_in_report(self):
        with patch.object(report,'get_future_allocations',return_value={'LOAN1':AttrDict(principal=10,interest=1)}), \
             patch.object(frappe.db,'sql',return_value=[loan(approved_principal=100)]), \
             patch.object(report,'get_schedules',return_value={}), \
             patch.object(report,'get_credits_as_of',return_value=[]):
            _,rows,*_=report.execute({'as_of_date':'2026-10-15'})
        self.assertEqual(rows[0].total_outstanding,120)

    def test_credit_sql_rebuilds_historical_available_not_current_status(self):
        with patch.object(frappe.db,'sql',return_value=[]) as sql:
            report.get_credits_as_of(AttrDict(employee='EMP1'),'2026-10-15')
        query,values=sql.call_args.args
        self.assertIn('credit.original_credit - coalesce(used.amount, 0)',query)
        self.assertIn('posting_date <= %(as_of_date)s',query)
        self.assertIn('docstatus = 1',query)
        self.assertNotIn('credit.available_credit',query)
        self.assertEqual(values['employee'],'EMP1')


if __name__=='__main__':
    unittest.main()
