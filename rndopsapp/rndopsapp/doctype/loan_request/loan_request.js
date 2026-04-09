// Copyright (c) 2026, rndops and contributors
// For license information, please see license.txt

function update_loan_total(frm) {
	const rows = frm.doc.account_head_fund_breakup || [];
	const total = rows.reduce((sum, row) => sum + (parseFloat(row.account_head_amount) || 0), 0);
	frm.set_value("loan_amount", total);
}

frappe.ui.form.on("Loan Request", {
	refresh(frm) {
		update_loan_total(frm);
	},
});

frappe.ui.form.on("loan_amount_accounthead_breakup", {
	account_head_amount(frm) {
		update_loan_total(frm);
	},
	account_head_fund_breakup_remove(frm) {
		update_loan_total(frm);
	},
});
