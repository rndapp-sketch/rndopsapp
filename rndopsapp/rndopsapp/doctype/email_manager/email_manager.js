// Copyright (c) 2026, rndops and contributors
// For license information, please see license.txt

frappe.ui.form.on("Email Manager", {
	onload(frm) {
		// Only offer DocTypes that actually belong to this app (not core/
		// other-app DocTypes) — matches every other DocType this app ships,
		// which are all registered under the "Rndopsapp" module.
		frm.set_query("module", () => ({
			filters: {
				module: "Rndopsapp",
				istable: 0,
			},
		}));
	},

	refresh(frm) {
		set_doc_status_options(frm);
	},

	module(frm) {
		set_doc_status_options(frm);
	},
});

function set_doc_status_options(frm) {
	if (!frm.fields_dict.doc_status) return;

	if (!frm.doc.module) {
		frm.fields_dict.doc_status.grid.update_docfield_property("status", "options", "");
		frm.fields_dict.doc_status.grid.refresh();
		return;
	}

	frappe.call({
		method: "rndopsapp.rndopsapp.email.api.get_doctype_workflow_states",
		args: { doctype: frm.doc.module },
		callback(r) {
			const states = r.message || [];
			frm.fields_dict.doc_status.grid.update_docfield_property(
				"status",
				"options",
				states.join("\n")
			);
			frm.fields_dict.doc_status.grid.refresh();

			if (!states.length) {
				frappe.show_alert({
					message: __("{0} has no Workflow — Doc Status has nothing to offer yet.", [frm.doc.module]),
					indicator: "orange",
				});
			}
		},
	});
}
