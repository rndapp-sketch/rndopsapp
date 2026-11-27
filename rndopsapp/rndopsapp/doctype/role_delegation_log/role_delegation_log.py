import frappe
from frappe.model.document import Document


class RoleDelegationLog(Document):
	pass


def on_doctype_update():
	frappe.db.add_index("Role Delegation Log", ["actual_user", "ref_doctype", "ref_name"])
