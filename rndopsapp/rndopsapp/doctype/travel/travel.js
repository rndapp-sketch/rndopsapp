// Copyright (c) 2025, rndops and contributors
// For license information, please see license.txt

frappe.ui.form.on("Travel", {
	travel_project_title(frm) {
		if (frm.doc.travel_project_title) {
			frappe.db.get_value(
				"Project Registration",
				frm.doc.travel_project_title,
				"project_no",
				(r) => {
					frm.set_value("travel_project_number", r && r.project_no ? r.project_no : "");
				}
			);
		} else {
			frm.set_value("travel_project_number", "");
		}
	},
});
