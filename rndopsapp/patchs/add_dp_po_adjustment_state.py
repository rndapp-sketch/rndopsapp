"""
Patch: Add a 'PO Adjustment' step after 'POGenerated' in the Direct Purchase workflow.

    POGenerated --[PO Adjustment, staff, RnD]--> PO Adjustment

Both are submitted states (doc_status 1). Only the workflow document changes.

Run via:
    bench --site <site> execute rndopsapp.patchs.add_dp_po_adjustment_state.execute
"""

import frappe

DOCTYPE = "Direct Purchase"
FROM_STATE = "POGenerated"
STATE_NAME = "PO Adjustment"
ACTION = "PO Adjustment"
ROLE = "staff, RnD"


def execute():
    wf_name = frappe.db.get_value("Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name")
    if not wf_name:
        print(f"No active workflow found for '{DOCTYPE}'. Skipping patch.")
        return

    wf = frappe.get_doc("Workflow", wf_name)
    if FROM_STATE not in [s.state for s in wf.states]:
        print(f"State '{FROM_STATE}' not found in workflow '{wf_name}'. Skipping patch.")
        return

    if not frappe.db.exists("Workflow State", STATE_NAME):
        frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": STATE_NAME}).insert(
            ignore_permissions=True
        )
    if not frappe.db.exists("Workflow Action Master", ACTION):
        frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": ACTION}).insert(
            ignore_permissions=True
        )

    changed = False
    if STATE_NAME not in [s.state for s in wf.states]:
        wf.append("states", {"state": STATE_NAME, "doc_status": "1", "allow_edit": ROLE})
        changed = True

    if not any(t.state == FROM_STATE and t.action == ACTION for t in wf.transitions):
        wf.append("transitions", {
            "state": FROM_STATE,
            "action": ACTION,
            "next_state": STATE_NAME,
            "allowed": ROLE,
            "allow_self_approval": 1,
        })
        changed = True

    if not changed:
        print(f"'{STATE_NAME}' already configured in workflow '{wf_name}'. Skipping.")
        return

    wf.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"Added '{STATE_NAME}' after '{FROM_STATE}' in workflow '{wf_name}'.")
