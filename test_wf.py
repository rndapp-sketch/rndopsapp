import frappe
frappe.init(site="prornd.localhost")
frappe.connect()
wf = frappe.get_doc("Workflow", "pending_approval_prjReg")
print("States:")
for s in wf.states:
    print(f"- {s.state}, docstatus: {s.doc_status}")
print("Transitions:")
for t in wf.transitions:
    print(f"- {t.state} -( {t.action} )-> {t.next_state}")
