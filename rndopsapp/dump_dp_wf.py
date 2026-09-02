import frappe
import json

def execute():
    wf_name = "Direct Purchase Workflow"
    if not frappe.db.exists("Workflow", wf_name):
        wf_name = "Direct_Purchase_Workflow"
        
    if not frappe.db.exists("Workflow", wf_name):
        print(f"❌ Workflow {wf_name} does not exist.")
        return
        
    doc = frappe.get_doc("Workflow", wf_name)
    print(f"--- WORKFLOW: {wf_name} ---")
    print(f"Document Type: {doc.document_type}")
    print("\n--- STATES ---")
    for s in doc.states:
        print(f"State: {s.state}, DocStatus: {s.doc_status}, Allow Edit: {s.allow_edit}")
        
    print("\n--- TRANSITIONS ---")
    for t in doc.transitions:
        print(f"{t.state} --({t.action})--> {t.next_state} | Allowed: {t.allowed} | Condition: {t.condition}")
