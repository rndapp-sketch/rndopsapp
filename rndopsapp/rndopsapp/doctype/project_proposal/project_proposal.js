// Copyright (c) 2025, rndops and contributors
// For license information, please see license.txt

frappe.ui.form.on('Project Proposal', {
    refresh(frm) {

        // --- SHOW ENDORSEMENT TAB + GENERATE BUTTON ---
        if (frm.is_new()) return;  // Skip new unsaved docs

        if (
            frm.doc.pi_webmail &&
            frm.doc.project_type &&
            frm.doc.project_title &&
            frm.doc.project_objective &&
            frm.doc.project_deliverables &&
            frm.doc.funding_agen &&
            frm.doc.implementation_department &&
            (frm.doc.project_duration_months || frm.doc.project_duration_days) &&
            frm.doc.is_additional_pi &&
            frm.doc.has_co_pi
        ) {
            // Show Endorsement tab
            frm.toggle_display('endorsement_prj', true);

            // Show "Generate Endorsement" button only in draft (before submit)
            if (frm.doc.docstatus === 0) {
                frm.add_custom_button(__('Generate Endorsement'), function () {
                    frappe.call({
                        method: 'rndopsapp.rndopsapp.doctype.project_proposal.project_proposal.generate_endorsement_pdf_and_notify',
                        args: { docname: frm.doc.name },
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.msgprint(__('Endorsement generated successfully and sent for approval.'));
                                frm.reload_doc();
                            }
                        }
                    });
                }).addClass('btn-primary');
            }
        } else {
            frm.toggle_display('endorsement_prj', false);
        }

        // --- SHOW APPROVAL ACTION BUTTONS FOR DoRnD USER ---
        if (
            frappe.session.user === "dornd@iitg.ac.in" &&
            frm.doc.docstatus === 1 &&
            frm.doc.endorsement_status === "Pending Approval"
        ) {
            frm.add_custom_button(__('Approve'), () => process_endorsement(frm, 'Approved'), 'Actions');
            frm.add_custom_button(__('Reject'), () => process_endorsement(frm, 'Rejected'), 'Actions');
            frm.add_custom_button(__('Put Back'), () => process_endorsement(frm, 'Put Back'), 'Actions');
        }
    }
});

// --- PROCESS ENDORSEMENT ACTION ---
function process_endorsement(frm, action) {
    frappe.confirm(
        `Are you sure you want to <b>${action}</b> this endorsement?`,
        () => {
            frappe.call({
                method: "rndopsapp.rndopsapp.doctype.project_proposal.project_proposal.process_endorsement",
                args: {
                    docname: frm.doc.name,
                    action: action
                },
                callback: function (r) {
                    if (!r.exc) {
                        frappe.show_alert({ message: `Endorsement ${action}`, indicator: 'green' });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}
