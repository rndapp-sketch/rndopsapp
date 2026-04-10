import frappe

def inspect_workflow():
    workflow_name = "Project Proposal Endorsement Workflow"
    if not frappe.db.exists("Workflow", workflow_name):
        print(f"Workflow '{workflow_name}' not found.")
        return

    workflow = frappe.get_doc("Workflow", workflow_name)
    print(f"Workflow: {workflow.name}")
    print(f"Document Type: {workflow.document_type}")
    print(f"Is Active: {workflow.is_active}")
    
    print("\nTransitions:")
    for t in workflow.transitions:
        print(f"  State: {t.state} -> Action: {t.action} -> Next State: {t.next_state} (Allowed: {t.allowed})")

    print("\nStates:")
    for s in workflow.states:
        print(f"  State: {s.state} (Doc Status: {s.doc_status})")

inspect_workflow()
