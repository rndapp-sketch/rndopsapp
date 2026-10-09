"""
Create (or recreate) the Frappe Workflow for 'Acc Head to Head Fund Transfer'.

Run via:
    bench --site <site> execute rndopsapp.rndopsapp.create_h2h_workflow.execute

Mirrors the `h2h_workflow` record that already exists on prornd.local, so the
workflow can be reproduced on a fresh site instead of living only in the DB.

Flow (6 states, 5 transitions):

    Draft ──Submit──▶ Pending Staff Approval ──Forward──▶ Pending HoS Approval
        ──Forward──▶ Pending Dean Approval ──Approve──▶ Approved
                                           └──Reject───▶ Rejected

Notes:
  - Only `Permanent Employee` (the PI) may Submit from Draft. A non-PI applicant
    cannot move the request out of Draft; the PI must do it on their behalf.
  - There are no Put Back transitions — an approver can only Forward, Approve or
    Reject. Add rows here if put-back is needed later.
  - `Rejected` carries doc_status 0 (not 2), matching the live record: a rejected
    request stays a draft rather than becoming a cancelled document.
"""

import frappe

WORKFLOW_NAME = "h2h_workflow"
DOCTYPE = "Acc Head to Head Fund Transfer"

# (state_name, doc_status_str, allow_edit_role)
H2H_STATES = [
    ("Draft",                  "0", "Permanent Employee"),
    ("Pending Staff Approval", "0", "staff, RnD"),
    ("Pending HoS Approval",   "0", "Hos, RnD (Head of Section, RnD)"),
    ("Pending Dean Approval",  "0", "Dean, RnD"),
    ("Approved",               "1", "Administrator"),
    ("Rejected",               "0", "Administrator"),
]

# (from_state, action, next_state, allowed_role)
H2H_TRANSITIONS = [
    ("Draft",                  "Submit",  "Pending Staff Approval", "Permanent Employee"),
    ("Pending Staff Approval", "Forward", "Pending HoS Approval",   "staff, RnD"),
    ("Pending HoS Approval",   "Forward", "Pending Dean Approval",  "Hos, RnD (Head of Section, RnD)"),
    ("Pending Dean Approval",  "Approve", "Approved",               "Dean, RnD"),
    ("Pending Dean Approval",  "Reject",  "Rejected",               "Dean, RnD"),
]


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


def _deactivate_other_workflows():
    existing = frappe.get_all(
        "Workflow",
        filters={"document_type": DOCTYPE, "is_active": 1},
        pluck="name",
    )
    for wf_name in existing:
        if wf_name != WORKFLOW_NAME:
            frappe.db.set_value("Workflow", wf_name, "is_active", 0)


def execute():
    """Create or fully replace the H2H Fund Transfer workflow."""

    all_roles = {row[3] for row in H2H_TRANSITIONS} | {row[2] for row in H2H_STATES}
    all_actions = {row[1] for row in H2H_TRANSITIONS}
    all_state_names = {row[0] for row in H2H_STATES}

    for role in sorted(all_roles):
        _ensure_role(role)
    for state in all_state_names:
        _ensure_workflow_state(state)
    for action in all_actions:
        _ensure_workflow_action(action)

    _deactivate_other_workflows()

    # Delete and recreate so we start from a clean slate
    if frappe.db.exists("Workflow", WORKFLOW_NAME):
        frappe.delete_doc("Workflow", WORKFLOW_NAME, ignore_permissions=True, force=True)

    wf = frappe.new_doc("Workflow")
    wf.workflow_name = WORKFLOW_NAME
    wf.document_type = DOCTYPE
    wf.is_active = 1
    wf.send_email_alert = 0
    wf.workflow_state_field = "workflow_state"

    for state_name, doc_status, allow_edit in H2H_STATES:
        wf.append("states", {
            "state": state_name,
            "doc_status": doc_status,
            "allow_edit": allow_edit,
            "update_field": "workflow_state",
            "update_value": state_name,
        })

    for from_state, action, next_state, allowed in H2H_TRANSITIONS:
        wf.append("transitions", {
            "state": from_state,
            "action": action,
            "next_state": next_state,
            "allowed": allowed,
            "condition": "",
        })

    wf.insert(ignore_permissions=True)
    frappe.db.commit()

    print(
        f"✅ '{WORKFLOW_NAME}' created for '{DOCTYPE}' with "
        f"{len(H2H_STATES)} states and {len(H2H_TRANSITIONS)} transitions."
    )
