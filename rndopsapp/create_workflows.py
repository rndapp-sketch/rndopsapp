import frappe
from frappe import _

# Data mappings for the 3 requested Doctypes
doctypes = {
    "proprietary_purchase": {"amount_field": "pp_grand_total"},
    "standerdized_purchase": {"amount_field": "sp_grand_total"},
    "repair_replacement": {"amount_field": "rr_grand_total"},
    "Direct Purchase": {"amount_field": "total_estimate"}
}

states_list = [
    "Draft",
    "Pending PI Approval",
    "Pending Other PI",
    "Pending Mentor Approval",
    "Pending HoD Approval",
    "Pending Staff Approval",
    "Pending HoS Approval",
    "Pending Associate Dean",
    "Pending Dean Approval",
    "Pending Director Approval",
    "Approved",
    "Rejected"
]

roles_for_states = {
    "Draft": "Project Staff", 
    "Pending PI Approval": "Principal Investigator",
    "Pending Other PI": "Other PI", 
    "Pending Mentor Approval": "Mentor",
    "Pending HoD Approval": "HoD (Head of Department)",
    "Pending Staff Approval": "staff, RnD",
    "Pending HoS Approval": "Hos, RnD (Head of Section, RnD)",
    "Pending Associate Dean": "Associate Dean, RND",
    "Pending Dean Approval": "Dean, RnD",
    "Pending Director Approval": "Director",
    "Approved": "staff, RnD",
    "Rejected": "staff, RnD"
}

docstatus_map = {
    "Draft": 0,
    "Approved": 1,
    "Rejected": 2
}
for s in states_list:
    if s not in docstatus_map:
        docstatus_map[s] = 0

def ensure_role(role_name):
    if not frappe.db.exists("Role", role_name):
        role_doc = frappe.new_doc("Role")
        role_doc.role_name = role_name
        role_doc.insert(ignore_permissions=True)

def create_workflow(doctype, amount_field):
    wf_name = f"{doctype} Workflow"
    
    if frappe.db.exists("Workflow", wf_name):
        frappe.delete_doc("Workflow", wf_name)
    
    wf = frappe.new_doc("Workflow")
    wf.workflow_name = wf_name
    wf.document_type = doctype
    wf.is_active = 1
    wf.send_email_alert = 1
    
    # 1. Add States
    for state in states_list:
        role = roles_for_states.get(state, "System Manager")
        ensure_role(role)
        
        wf.append("states", {
            "state": state,
            "doc_status": docstatus_map[state],
            "allow_edit": role,
            "update_field": "workflow_state",
            "update_value": state
        })
        
        # Ensure Workflow State document exists
        if not frappe.db.exists("Workflow State", state):
            ws = frappe.new_doc("Workflow State")
            ws.workflow_state_name = state
            ws.insert(ignore_permissions=True)
            
    # Helper to add transition
    def add_trans(state, action, next_state, allowed, condition=""):
        ensure_role(allowed)
        wf.append("transitions", {
            "state": state,
            "action": action,
            "next_state": next_state,
            "allowed": allowed,
            "condition": condition
        })
        # ensure Action exists
        if not frappe.db.exists("Workflow Action Master", action):
            wa = frappe.new_doc("Workflow Action Master")
            wa.workflow_action_name = action
            wa.insert(ignore_permissions=True)

    # 2. Add Transitions
    # We will build out a simplified dynamic transition mapping based on the user's rules.
    # We use "Project Staff" as an example role base.
    
    # DRAFT -> PENDING PI (For PS)
    add_trans("Draft", "Submit", "Pending PI Approval", "Project Staff")
    
    # DRAFT -> PENDING MENTOR (For IR)
    add_trans("Draft", "Submit", "Pending Mentor Approval", "Independent Researcher")
    
    # DRAFT -> PENDING HOD (For IF)
    add_trans("Draft", "Submit", "Pending HoD Approval", "Inspire Faculty")

    # DRAFT -> PENDING STAFF (For Permanent Employee PDF/Individual)
    add_trans("Draft", "Submit", "Pending Staff Approval", "Permanent Employee", f'frappe.db.get_value("Project Registration", doc.project_no, "project_type") != "Other PI"')
    # DRAFT -> PENDING OTHER PI (For Permanent Employee Other PI)
    add_trans("Draft", "Submit", "Pending Other PI", "Permanent Employee", f'frappe.db.get_value("Project Registration", doc.project_no, "project_type") == "Other PI"')
    

    # ---- PENDING PI APPROVAL ACTIONS ----
    # Applies to PS
    add_trans("Pending PI Approval", "Approve", "Pending Staff Approval", "Principal Investigator", f'frappe.db.get_value("Project Registration", doc.project_no, "project_type") != "Other PI"')
    add_trans("Pending PI Approval", "Approve", "Pending Other PI", "Principal Investigator", f'frappe.db.get_value("Project Registration", doc.project_no, "project_type") == "Other PI"')
    add_trans("Pending PI Approval", "Reject", "Rejected", "Principal Investigator")

    # ---- PENDING MENTOR APPROVAL ACTIONS ----
    # Applies to IR
    # Note: Independent researcher path skips HoD/CET for Standerdized Purchase! 
    # But for Proprietary it doesn't? The rules say "Independent Researcher -> Pending Mentor Approval -> Pending HoD Approval -> Pending Staff Approval" for Proprietary.
    # For Standerdized: "Independent Researcher (IR) (Skips HoD/CET Person for this Item Type)". So:
    if doctype in ["Standerdized Purchase"]:
        add_trans("Pending Mentor Approval", "Approve", "Pending Staff Approval", "Mentor", f'frappe.db.get_value("Project Registration", doc.project_no, "project_type") != "Other PI"')
    else:
        add_trans("Pending Mentor Approval", "Approve", "Pending HoD Approval", "Mentor", f'frappe.db.get_value("Project Registration", doc.project_no, "project_type") != "Other PI"')
        
    add_trans("Pending Mentor Approval", "Approve", "Pending Other PI", "Mentor", f'frappe.db.get_value("Project Registration", doc.project_no, "project_type") == "Other PI"')
    add_trans("Pending Mentor Approval", "Reject", "Rejected", "Mentor")
    
    # ---- PENDING OTHER PI ACTIONS ----
    # If IR: Goes to HoD for Proprietary, or skips HoD for Standardized. We can't know strictly the applicant type from here easily with standard.
    # We will assume a general flow for Other PI going to Staff Approval as converged path.
    add_trans("Pending Other PI", "Approve", "Pending Staff Approval", "Principal Investigator") # (Or whatever role OTHER PI is)
    add_trans("Pending Other PI", "Reject", "Rejected", "Principal Investigator")

    # ---- PENDING HOD APPROVAL ACTIONS ----
    # For IF and P and IR.
    add_trans("Pending HoD Approval", "Approve", "Pending Staff Approval", "HoD (Head of Department)")
    add_trans("Pending HoD Approval", "Reject", "Rejected", "HoD (Head of Department)")

    # ---- PENDING STAFF APPROVAL ACTIONS ----
    add_trans("Pending Staff Approval", "Approve", "Pending HoS Approval", "staff, RnD")
    add_trans("Pending Staff Approval", "Reject", "Rejected", "staff, RnD")
    
    # ---- PENDING HOS APPROVAL ACTIONS ----
    if doctype == "Direct Purchase":
        # Director approval is only needed for Consumable/Contingency > ₹3,00,000.
        # All other budget heads: Dean approves directly regardless of amount.
        cc_heads = '(doc.account_head in ("Consumable", "Contingency"))'
        non_cc_heads = '(doc.account_head not in ("Consumable", "Contingency"))'
        cc_dean_limit = 300000

        cc_dean_approve = f'{cc_heads} and flt(doc.{amount_field}) <= {cc_dean_limit}'
        cc_dean_forward = f'{cc_heads} and flt(doc.{amount_field}) > {cc_dean_limit}'

        # HoS -> Dean (Always, skipping Associate Dean)
        add_trans("Pending HoS Approval", "Approve", "Pending Dean Approval", "Hos, RnD (Head of Section, RnD)")
        add_trans("Pending HoS Approval", "Reject", "Rejected", "Hos, RnD (Head of Section, RnD)")

        # Dean -> Approved (Consumable/Contingency ≤ ₹3,00,000)
        add_trans("Pending Dean Approval", "Approve", "Approved", "Dean, RnD", cc_dean_approve)
        # Dean -> Director (Consumable/Contingency > ₹3,00,000)
        add_trans("Pending Dean Approval", "Forward", "Pending Director Approval", "Dean, RnD", cc_dean_forward)
        # Dean -> Approved (All other budget heads, any amount)
        add_trans("Pending Dean Approval", "Approve", "Approved", "Dean, RnD", non_cc_heads)
        add_trans("Pending Dean Approval", "Reject", "Rejected", "Dean, RnD")

        # Director -> Approved (only reachable for C/C > ₹3,00,000)
        add_trans("Pending Director Approval", "Approve", "Approved", "Director", cc_heads)
        add_trans("Pending Director Approval", "Reject", "Rejected", "Director")
    
    else:
        # DIVERGES BASED ON AMOUNT
        add_trans("Pending HoS Approval", "Approve", "Pending Associate Dean", "Hos, RnD (Head of Section, RnD)", f'flt(doc.{amount_field}) <= 100000')
        add_trans("Pending HoS Approval", "Approve", "Pending Dean Approval", "Hos, RnD (Head of Section, RnD)", f'flt(doc.{amount_field}) > 100000')
        add_trans("Pending HoS Approval", "Reject", "Rejected", "Hos, RnD (Head of Section, RnD)")
        
        # ---- PENDING ASSOCIATE DEAN ACTIONS ----
        add_trans("Pending Associate Dean", "Approve", "Approved", "Associate Dean, RND")
        add_trans("Pending Associate Dean", "Reject", "Rejected", "Associate Dean, RND")
        
        # ---- PENDING DEAN APPROVAL ACTIONS ----
        add_trans("Pending Dean Approval", "Approve", "Approved", "Dean, RnD")
        add_trans("Pending Dean Approval", "Reject", "Rejected", "Dean, RnD")

    wf.insert(ignore_permissions=True)
    print(f"✅ Workflow '{wf_name}' created successfully for {doctype}!")

def execute():
    for dt, info in doctypes.items():
        if frappe.db.exists("DocType", dt):
            create_workflow(dt, info["amount_field"])
        else:
            print(f"❌ DocType '{dt}' does not exist.")
    frappe.db.commit()

