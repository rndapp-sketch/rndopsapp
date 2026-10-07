// Copyright (c) 2026, rndops and contributors
// For license information, please see license.txt

frappe.ui.form.on("Announcement Pragati", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.dashboard.clear_headline();
		frm.dashboard.set_headline_alert(
			!frm.doc.disabled
				? '<span class="indicator-pill green">Active</span>'
				: '<span class="indicator-pill red">Disabled</span>'
		);

		if (frm.doc.disabled) {
			frm.add_custom_button("Activate", () => set_disabled(frm, 0));
		} else {
			frm.add_custom_button("Disable", () => set_disabled(frm, 1));
		}
	},
});

function set_disabled(frm, disabled) {
	frappe.call({
		method: "rndopsapp.rndopsapp.doctype.announcement_pragati.announcement_pragati.set_disabled",
		args: {
			docname: frm.doc.name,
			disabled: disabled,
		},
		freeze: true,
		callback(r) {
			if (r.message !== undefined) {
				frm.reload_doc();
				frappe.show_alert({
					message: disabled ? "Announcement disabled" : "Announcement activated",
					indicator: disabled ? "red" : "green",
				});
			}
		},
	});
}
