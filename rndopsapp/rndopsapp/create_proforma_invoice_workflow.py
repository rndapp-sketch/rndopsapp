"""
Create the Frappe Workflow for 'Proforma_Invoice'.

Matches the state machine already hardcoded in proforma_invoice.py:
    Draft --Submit--> Pending HoS Approval --Approve--> Approved
                                            --Reject--> Draft
All three states keep docstatus 0 — the doctype is never actually submitted;
state changes are applied via direct doc.db_set() calls in the API (which
deliberately bypass the workflow transition gate), so these transition rows
exist mainly to register the states/roles and to back the workflow_state
field (creating this Workflow auto-creates that Custom Field).

Run via:
    bench --site <site> execute rndopsapp.rndopsapp.create_proforma_invoice_workflow.execute
"""

import frappe

WORKFLOW_NAME = "porforma_invoice"
DOCTYPE = "Proforma_Invoice"
HOS_ROLE = "Hos, RnD (Head of Section, RnD)"

STATES = [
    ("Draft",                 "0", "All_ProRnd_User"),
    ("Pending HoS Approval",  "0", HOS_ROLE),
    ("Approved",              "0", "Administrator"),
]

TRANSITIONS = [
    ("Draft",                "Submit",  "Pending HoS Approval", "All_ProRnd_User"),
    ("Pending HoS Approval",  "Approve", "Approved",             HOS_ROLE),
    ("Pending HoS Approval",  "Reject",  "Draft",                HOS_ROLE),
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


def execute():
    if frappe.db.exists("Workflow", WORKFLOW_NAME):
        print(f"ℹ Workflow '{WORKFLOW_NAME}' already exists. Skipping.")
        return

    all_roles = {row[3] for row in TRANSITIONS} | {row[2] for row in STATES}
    all_actions = {row[1] for row in TRANSITIONS}
    all_states = {row[0] for row in STATES}

    for role in sorted(all_roles):
        _ensure_role(role)
    for state in all_states:
        _ensure_workflow_state(state)
    for action in all_actions:
        _ensure_workflow_action(action)

    wf = frappe.new_doc("Workflow")
    wf.workflow_name = WORKFLOW_NAME
    wf.document_type = DOCTYPE
    wf.is_active = 1
    wf.send_email_alert = 0
    wf.workflow_state_field = "workflow_state"

    for state_name, doc_status, allow_edit in STATES:
        wf.append("states", {
            "state": state_name,
            "doc_status": doc_status,
            "allow_edit": allow_edit,
            "update_field": "workflow_state",
            "update_value": state_name,
        })

    for from_state, action, next_state, allowed in TRANSITIONS:
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
        f"{len(STATES)} states and {len(TRANSITIONS)} transitions."
    )
