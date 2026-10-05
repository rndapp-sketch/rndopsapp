import frappe

def execute():
    wf_name = "Direct_Purchase_Workflow"
    if not frappe.db.exists("Workflow", wf_name):
        print(f"❌ Workflow {wf_name} not found.")
        return

    doc = frappe.get_doc("Workflow", wf_name)
    
    # 1. Ensure 'Pending Director Approval' State exists
    if not frappe.db.exists("Workflow State", "Pending Director Approval"):
        ws = frappe.new_doc("Workflow State")
        ws.workflow_state_name = "Pending Director Approval"
        ws.insert(ignore_permissions=True)
        
    if not frappe.db.exists("Role", "Director"):
        r = frappe.new_doc("Role")
        r.role_name = "Director"
        r.insert(ignore_permissions=True)

    # Add State
    state_exists = any(s.state == "Pending Director Approval" for s in doc.states)
    if not state_exists:
        doc.append("states", {
            "state": "Pending Director Approval",
            "doc_status": 0,
            "allow_edit": "Director",
            "update_field": "workflow_state",
            "update_value": "Pending Director Approval"
        })
        
    # 2. Filter out old HoS to Associate Dean transition and Dean to Approved without condition
    new_transitions = []
    for t in doc.transitions:
        # Remove anything leaving HoS or Associate Dean or Dean that conflicts
        if t.state == "Pending HoS Approval" and t.next_state == "Pending Associate Dean":
            continue # Remove
        if t.state == "Pending HoS Approval" and t.next_state == "Pending Dean Approval":
            continue # Remove, will recreate
        if t.state == "Pending Associate Dean":
            continue # Removing Associate Dean entirely from this workflow
        if t.state == "Pending Dean Approval":
            continue # Recreating
        
        new_transitions.append(t)
        
    # Clear and replace
    doc.set("transitions", new_transitions)

    # 3. Add New Conditions
    # HoS -> Dean (Always)
    doc.append("transitions", {
        "state": "Pending HoS Approval",
        "action": "Forward",
        "next_state": "Pending Dean Approval",
        "allowed": "Hos, RnD (Head of Section, RnD)",
        "condition": ""
    })
    
    # Dean -> Approved (If <= Dean Limit)
    doc.append("transitions", {
        "state": "Pending Dean Approval",
        "action": "Approve",
        "next_state": "Approved",
        "allowed": "Dean, RnD",
        "condition": "flt(doc.total_estimate) <= flt(frappe.db.get_single_value('ProRnd Workflow Settings', 'dp_dean_limit'))"
    })
    
    # Dean -> Director (If > Dean Limit)
    doc.append("transitions", {
        "state": "Pending Dean Approval",
        "action": "Forward",
        "next_state": "Pending Director Approval",
        "allowed": "Dean, RnD",
        "condition": "flt(doc.total_estimate) > flt(frappe.db.get_single_value('ProRnd Workflow Settings', 'dp_dean_limit'))"
    })
    
    # Director -> Approved (If <= Director Limit)
    doc.append("transitions", {
        "state": "Pending Director Approval",
        "action": "Approve",
        "next_state": "Approved",
        "allowed": "Director",
        "condition": "flt(doc.total_estimate) <= flt(frappe.db.get_single_value('ProRnd Workflow Settings', 'dp_director_limit'))"
    })

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("✅ Successfully patched Direct_Purchase_Workflow with dynamic configuration limits.")
