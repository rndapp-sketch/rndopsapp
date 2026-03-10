// Copyright (c) 2025, rndops and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fund Sanction", {
    project_proposal(frm) {
        // When project_proposal changes, fetch project_type from Project Proposal
        if (frm.doc.project_proposal) {
            frappe.db.get_value("Project Proposal", frm.doc.project_proposal, "project_type")
                .then(r => {
                    if (r && r.message && r.message.project_type) {
                        frm.doc.project_type_linked = r.message.project_type;
                        frm.refresh_field("project_type_linked");

                        // Example: show or hide a field based on project_type
                        frm.toggle_display("is_gst_invoice_issued", r.message.project_type === "Consultancy");
                    }
                });
        }
    },

	refresh(frm) {
        // Handle visibility if already selected
        if (frm.doc.project_proposal) {
            frappe.db.get_value("Project Proposal", frm.doc.project_proposal, "project_type")
                .then(r => {
                    if (r && r.message && r.message.project_type) {
                        frm.toggle_display("is_gst_invoice_issued", r.message.project_type === "Consultancy");
                    }
                });
        }
	},
});


