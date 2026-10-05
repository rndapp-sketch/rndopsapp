import frappe
from rndopsapp.rndopsapp.commitPayment import manually_publish_staged_commit

def fix_publish():
    frappe.init("prornd.local")
    frappe.connect()
    
    # Publish specifically for the user's document first
    res = manually_publish_staged_commit("202604230A00383", "Recruitment Adhoc Contractual")
    print("Result for 202604230A00383:", res)
    
    # Let's also check if there are other pending docs and publish them
    pending = frappe.get_all("Kafka Commit Staging", filters={"reference_doctype": "Recruitment Adhoc Contractual", "status": "PENDING_APPROVAL"}, fields=["reference_name"])
    for p in pending:
        doc = frappe.get_doc("Recruitment Adhoc Contractual", p.reference_name)
        if doc.workflow_state == "Approved":
            res = manually_publish_staged_commit(p.reference_name, "Recruitment Adhoc Contractual")
            print("Auto-published for", p.reference_name, res)

fix_publish()
