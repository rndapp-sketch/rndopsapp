"""
Patch: Add 'Pending Director Approval' state to the Indent Cum Sanction Sheet workflow.

Mirrors add_igf_director_approval_state.py. Routing into this state is done in
Python (update_send_to_director_icss, when the Dean ticks "Send to Director"
from 'Pending Dean Approval'), not via a Workflow-engine transition.

Run via:
    bench --site <site> execute rndopsapp.patchs.add_icss_director_approval_state.execute
"""

import frappe

DOCTYPE = "Indent Cum Sanction Sheet"
STATE_NAME = "Pending Director Approval"
ALLOW_EDIT_ROLE = "Dean, RnD"


def _ensure_role(role_name):
    if not frappe.db.exists("Role", role_name):
        frappe.get_doc({"doctype": "Role", "role_name": role_name}).insert(
            ignore_permissions=True
        )


def _ensure_workflow_state(state_name):
    if not frappe.db.exists("Workflow State", state_name):
        frappe.get_doc(
            {"doctype": "Workflow State", "workflow_state_name": state_name}
        ).insert(ignore_permissions=True)


def _ensure_workflow_action(action_name):
    if not frappe.db.exists("Workflow Action Master", action_name):
        frappe.get_doc(
            {"doctype": "Workflow Action Master", "workflow_action_name": action_name}
        ).insert(ignore_permissions=True)


def execute():
    wf_name = frappe.db.get_value(
        "Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name"
    )
    if not wf_name:
        print(f"⚠ No active workflow found for '{DOCTYPE}'. Skipping patch.")
        return

    _ensure_role(ALLOW_EDIT_ROLE)
    _ensure_workflow_state(STATE_NAME)
    _ensure_workflow_action("Approve")
    _ensure_workflow_action("Reject")
    _ensure_workflow_action("Put Back")

    wf = frappe.get_doc("Workflow", wf_name)

    existing_states = [s.state for s in wf.states]
    if STATE_NAME in existing_states:
        print(f"ℹ State '{STATE_NAME}' already exists in workflow '{wf_name}'. Skipping.")
        return

    # doc_status "1" — matches every other post-submit ICSS approval state
    # (ICSS submits on entry to the first approval state, unlike IGF).
    wf.append("states", {
        "state": STATE_NAME,
        "doc_status": "1",
        "allow_edit": ALLOW_EDIT_ROLE,
        "update_field": "workflow_state",
        "update_value": STATE_NAME,
    })

    # Same targets as the existing 'Pending Dean Approval' transitions —
    # Director approval is a hardcopy gate layered on top of the Dean step,
    # not a separate approver in the chain.
    wf.append("transitions", {
        "state": STATE_NAME,
        "action": "Approve",
        "next_state": "Pending PO Generation",
        "allowed": ALLOW_EDIT_ROLE,
        "condition": "",
    })
    wf.append("transitions", {
        "state": STATE_NAME,
        "action": "Reject",
        "next_state": "Rejected",
        "allowed": ALLOW_EDIT_ROLE,
        "condition": "",
    })
    wf.append("transitions", {
        "state": STATE_NAME,
        "action": "Put Back",
        "next_state": "Pending HoS Approval",
        "allowed": ALLOW_EDIT_ROLE,
        "condition": "",
    })

    wf.save(ignore_permissions=True)
    frappe.db.commit()

    print(
        f"✅ Added '{STATE_NAME}' state with Approve/Reject/Put Back transitions "
        f"to workflow '{wf_name}' for '{DOCTYPE}'."
    )
