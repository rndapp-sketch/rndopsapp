"""
Patch: Add 'Pending Director Approval' state to the Indent General Form workflow.

Routing logic (enforced in indent_general_form.py::_resolve_igf_next_state):
  - Equipments  > ₹10,00,000 → Pending Director Approval
  - Consumable  >  ₹3,00,000 → Pending Director Approval
  - All other cases           → Approved (normal Dean flow)

This patch only touches the workflow document; no DocType migration needed.

Run via:
    bench --site <site> execute rndopsapp.patchs.add_igf_director_approval_state.execute
"""

import frappe

DOCTYPE = "Indent General Form"
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

    wf = frappe.get_doc("Workflow", wf_name)

    # Skip if state already exists
    existing_states = [s.state for s in wf.states]
    if STATE_NAME in existing_states:
        print(f"ℹ State '{STATE_NAME}' already exists in workflow '{wf_name}'. Skipping.")
        return

    # Add the new state
    wf.append("states", {
        "state": STATE_NAME,
        "doc_status": "0",
        "allow_edit": ALLOW_EDIT_ROLE,
        "update_field": "workflow_state",
        "update_value": STATE_NAME,
    })

    # Add transitions from Pending Director Approval
    # (routing INTO this state is handled in _resolve_igf_next_state in Python)
    wf.append("transitions", {
        "state": STATE_NAME,
        "action": "Approve",
        "next_state": "Approved",
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

    wf.save(ignore_permissions=True)
    frappe.db.commit()

    print(
        f"✅ Added '{STATE_NAME}' state with Approve/Reject transitions "
        f"to workflow '{wf_name}' for '{DOCTYPE}'."
    )
