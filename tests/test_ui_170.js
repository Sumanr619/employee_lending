/* Offline form-handler regressions. Run: node tests/test_ui_170.js */
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
function context() {
    const handlers = {};
    const rows = {};
    const ctx = {
        __: text => text,
        flt: (value, precision) => precision === undefined ? Number(value || 0) : Number(Number(value || 0).toFixed(precision)),
        locals: rows,
        frappe: {
            ui: { form: { on: (doctype, events) => { handlers[doctype] = events; } } },
            model: { set_value: (doctype, name, field, value) => { rows[doctype][name][field] = value; } },
            query_reports: {},
            datetime: { get_today: () => '2026-11-07' },
        },
    };
    return { ctx, handlers, rows };
}
{
    const {ctx, handlers} = context();
    vm.runInNewContext(fs.readFileSync('employee_lending/public/js/employee_loan_repayment.js','utf8'),ctx);
    const doc = {loan_application:'CLOSED',repayment_amount:75};
    const frm = {doc,set_value:(key,value)=>{doc[key]=value;},set_query:()=>{}};
    ctx.frappe.call = request => request.callback({message:{flat_interest_rate:9,total_outstanding_before:0,
        principal_outstanding_before:0,unearned_interest_before:0}});
    handlers['Employee Loan Repayment'].repayment_amount(frm);
    assert.strictEqual(doc.credit_amount,75);
    assert.strictEqual(doc.applied_amount,0);
    assert.strictEqual(doc.principal_component,0);
    assert.strictEqual(doc.interest_component,0);
    console.log('PASS individual closed-loan payment preview');
}
{
    const {ctx,handlers,rows} = context();
    vm.runInNewContext(fs.readFileSync('employee_lending/employee_lending/doctype/employee_loan_repayment_batch/employee_loan_repayment_batch.js','utf8'),ctx);
    const row = {repayment_amount:75,total_outstanding_before:0,principal_outstanding_before:0,
        unearned_interest_before:0,flat_interest_rate:9};
    rows.Item = {ROW1:row};
    const totals = {};
    const frm = {doc:{repayments:[row]},set_value:(key,value)=>{totals[key]=value;}};
    handlers['Employee Loan Repayment Batch Item'].repayment_amount(frm,'Item','ROW1');
    assert.strictEqual(row.credit_amount,75);
    assert.strictEqual(row.applied_amount,0);
    assert.strictEqual(totals.total_credit_amount,75);
    console.log('PASS batch closed-loan payment preview');
}
{
    const {ctx} = context();
    vm.runInNewContext(fs.readFileSync('employee_lending/employee_lending/report/employee_loan_outstanding/employee_loan_outstanding.js','utf8'),ctx);
    const filters = ctx.frappe.query_reports['Employee Loan Outstanding'].filters;
    assert.strictEqual(filters.find(f=>f.fieldname==='include_credits').default,1);
    assert(filters.find(f=>f.fieldname==='view').options.includes('Employee Summary'));
    assert(filters.find(f=>f.fieldname==='ageing_basis').options.includes('Instalment Due Date'));
    console.log('PASS report filters');
}
