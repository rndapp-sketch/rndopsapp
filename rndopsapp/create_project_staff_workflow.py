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
    wf_name = "project_staff_joining_workflow"
    doctype = "Project Staff Details"
    
    if frappe.db.exists("Workflow", wf_name):
        frappe.delete_doc("Workflow", wf_name)
    
    wf = frappe.new_doc("Workflow")
    wf.workflow_name = wf_name
    wf.document_type = doctype
    wf.is_active = 1
    wf.send_email_alert = 0
    wf.workflow_state_field = "workflow_state"
    
    states = [
        {"state": "Draft", "role": "staff, RnD"},
        {"state": "Pending HoS Approval", "role": "Hos, RnD (Head of Section, RnD)"},
        {"state": "Pending Associate Dean Approval", "role": "Ado_RnD"},
        {"state": "Pending Dean Approval", "role": "Dean, RnD"},
        {"state": "Approved", "role": "Administrator"},
        {"state": "Rejected", "role": "Dean, RnD"},
        {"state": "Put Back", "role": "All_ProRnd_User"}
    ]
    
    # 1. Add States
    for s in states:
        ensure_role(s["role"])
        ensure_state(s["state"])
        
        wf.append("states", {
            "state": s["state"],
            "doc_status": 0,
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
    add_trans("Draft", "Submit", "Pending HoS Approval", "staff, RnD")
    add_trans("Pending HoS Approval", "Forward", "Pending Associate Dean Approval", "Hos, RnD (Head of Section, RnD)")
    add_trans("Pending Associate Dean Approval", "Approve", "Approved", "Ado_RnD")

    wf.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"✅ Workflow '{wf_name}' created successfully for {doctype}!")

def execute():
    create_workflow()
