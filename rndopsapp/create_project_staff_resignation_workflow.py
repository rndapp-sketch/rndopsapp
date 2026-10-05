import frappe

def ensure_role(role_name):
    if not frappe.db.exists("Role", role_name):
        role_doc = frappe.new_doc("Role")
        role_doc.role_name = role_name
        role_doc.insert(ignore_permissions=True)

def ensure_state(state_name):
    if not frappe.db.exists("Workflow State", state_name):
        ws = frappe.new_doc("Workflow State")
        ws.workflow_state_name = state_name
        ws.insert(ignore_permissions=True)

def ensure_action(action_name):
    if not frappe.db.exists("Workflow Action Master", action_name):
        wa = frappe.new_doc("Workflow Action Master")
        wa.workflow_action_name = action_name
        wa.insert(ignore_permissions=True)

def create_workflow():
    wf_name = "project_staff_resignation_workflow"
    doctype = "Project Staff Resignation"

    if frappe.db.exists("Workflow", wf_name):
        frappe.delete_doc("Workflow", wf_name)

    wf = frappe.new_doc("Workflow")
    wf.workflow_name = wf_name
    wf.document_type = doctype
    wf.is_active = 1
    wf.send_email_alert = 0
    wf.workflow_state_field = "workflow_state"

    states = [
        {"state": "Draft", "role": "staff, RnD", "doc_status": 0},
        {"state": "Pending PI Approval", "role": "PI, RnD", "doc_status": 0},
        {"state": "Pending Staff Approval", "role": "staff, RnD", "doc_status": 0},
        {"state": "Pending HoS Approval", "role": "Hos, RnD (Head of Section, RnD)", "doc_status": 0},
        {"state": "Pending Dean Approval", "role": "Dean, RnD", "doc_status": 0},
        {"state": "Approved", "role": "Administrator", "doc_status": 1},
    ]

    # 1. Add States
    for s in states:
        ensure_role(s["role"])
        ensure_state(s["state"])

        wf.append("states", {
            "state": s["state"],
            "doc_status": s["doc_status"],
            "allow_edit": s["role"],
            "update_field": "workflow_state",
            "update_value": s["state"]
        })

    # Helper to add transition
    def add_trans(state, action, next_state, allowed, condition=""):
        ensure_role(allowed)
        ensure_action(action)
        wf.append("transitions", {
            "state": state,
            "action": action,
            "next_state": next_state,
            "allowed": allowed,
            "condition": condition
        })

    # 2. Add Transitions
    add_trans("Draft", "Submit", "Pending PI Approval", "staff, RnD")
    add_trans("Pending PI Approval", "Approve", "Pending Staff Approval", "PI, RnD")
    add_trans("Pending Staff Approval", "Approve", "Pending HoS Approval", "staff, RnD")
    add_trans("Pending HoS Approval", "Approve", "Pending Dean Approval", "Hos, RnD (Head of Section, RnD)")
    add_trans("Pending Dean Approval", "Approve", "Approved", "Dean, RnD")

    wf.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"✅ Workflow '{wf_name}' created successfully for {doctype}!")

def execute():
    create_workflow()
