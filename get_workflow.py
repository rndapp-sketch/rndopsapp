import sys
import os

frappe_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'apps', 'frappe'))
sys.path.insert(0, frappe_path)
import frappe
import json

frappe.init(site="prornd.local", sites_path="../../sites")
frappe.connect()

wf_name = frappe.get_value("Workflow", {"document_type": "Disbursal of Honorarium"}, "name")
print("Workflow Name:", wf_name)

if wf_name:
    transitions = frappe.get_all(
        "Workflow Transition", 
        filters={"parent": wf_name}, 
        fields=["state", "action", "next_state", "allowed"]
    )
    states = frappe.get_all(
        "Workflow Document State", 
        filters={"parent": wf_name}, 
        fields=["state", "doc_status", "allow_edit"]
    )
    print("\nTransitions:")
    print(json.dumps(transitions, indent=2))
    print("\nStates:")
    print(json.dumps(states, indent=2))
else:
    print("Workflow not found")
