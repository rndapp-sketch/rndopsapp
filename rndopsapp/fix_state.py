import sys
sys.path.append("/home/prornd/frappe-dev/prornd/apps/frappe")
import frappe

frappe.init(site="prornd.local", sites_path="/home/prornd/frappe-dev/prornd/sites")
frappe.connect()

docname = "tbukqq4af8"
doc = frappe.get_doc("Selection Committee Report", docname)
doc.workflow_state = "Pending Dean Approval"
doc.docstatus = 0
doc.db_update()
frappe.db.set_value("Selection Committee Report", docname, "workflow_state", "Pending Dean Approval")
frappe.db.set_value("Selection Committee Report", docname, "docstatus", 0)
frappe.db.commit()
print(f"Successfully updated document {docname} to Pending Dean Approval")
