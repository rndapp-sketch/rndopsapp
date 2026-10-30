// Copyright (c) 2026, rndops and contributors
// For license information, please see license.txt

const METHOD_PREFIX =
	"rndopsapp.rndopsapp.doctype.acc_head_to_head_fund_transfer.acc_head_to_head_fund_transfer";

function fill_applicant_details(frm) {
	if (!frm.doc.h2h_app_webmail) return;
	frappe.call({
		method: `${METHOD_PREFIX}.get_applicant_details`,
		args: { user_email: frm.doc.h2h_app_webmail },
		callback(r) {
			if (!r.message) return;
			Object.entries(r.message).forEach(([field, value]) => frm.set_value(field, value));
		},
	});
}

function fill_project_details(frm) {
	if (!frm.doc.h2h_proj_code) return;
	frappe.db
		.get_value("Project Registration", frm.doc.h2h_proj_code, [
			"project_no",
			"project_title",
			"pi_webmail",
		])
		.then(({ message }) => {
			if (!message) return;
			frm.set_value("h2h_proj_num", message.project_no || "");
			frm.set_value("h2h_proj_title", message.project_title || "");
			frm.set_value("h2h_pi_webmail", message.pi_webmail || "");
		});
}

function refresh_amount_in_words(frm) {
	if (!frm.doc.h2h_amount) {
		frm.set_value("h2h_amount_in_words", "");
		return;
	}
	frappe.call({
		method: `${METHOD_PREFIX}.get_amount_in_words`,
		args: { amount: frm.doc.h2h_amount },
		callback(r) {
			frm.set_value("h2h_amount_in_words", r.message || "");
		},
	});
}

frappe.ui.form.on("Acc Head to Head Fund Transfer", {
	setup(frm) {
		// The destination head must differ from the source head.
		frm.set_query("h2h_transfer_to", () => ({
			filters: frm.doc.h2h_transfer_from ? { name: ["!=", frm.doc.h2h_transfer_from] } : {},
		}));
		frm.set_query("h2h_transfer_from", () => ({
			filters: frm.doc.h2h_transfer_to ? { name: ["!=", frm.doc.h2h_transfer_to] } : {},
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.h2h_app_webmail) {
			frm.set_value("h2h_app_webmail", frappe.session.user);
		}
	},

	h2h_app_webmail(frm) {
		fill_applicant_details(frm);
	},

	h2h_proj_code(frm) {
		fill_project_details(frm);
	},

	h2h_amount(frm) {
		refresh_amount_in_words(frm);
	},

	h2h_transfer_to(frm) {
		if (frm.doc.h2h_transfer_from && frm.doc.h2h_transfer_from === frm.doc.h2h_transfer_to) {
			frm.set_value("h2h_transfer_to", "");
			frappe.msgprint(__("The source and destination account heads must be different."));
		}
	},
});
