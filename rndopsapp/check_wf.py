import frappe
frappe.init(site="prornd")
frappe.connect()

doc = frappe.new_doc("Selection Committee Report")
from frappe.model.workflow import get_transitions
print("Transitions:")
for t in get_transitions(doc):
    print(t.action, "->", t.next_state)

