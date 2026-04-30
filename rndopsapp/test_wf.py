import frappe

def get_wf_states():
    wfs = frappe.get_all("Workflow", filters={"document_type": "Recruitment Adhoc Contractual"}, fields=["name"])
    for wf in wfs:
        doc = frappe.get_doc("Workflow", wf.name)
        print("Workflow Name:", doc.name)
        for state in doc.states:
            print("State:", state.state)
