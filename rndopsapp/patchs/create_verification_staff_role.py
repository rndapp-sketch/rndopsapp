import frappe


def execute():
	"""Ensure the 'Verification Staff' role has no Desk access and lands on the
	verification portal after login. DocType sync may have already auto-created
	this role (with desk_access=1) via make_module_and_roles(), so force it here."""
	if frappe.db.exists("Role", "Verification Staff"):
		role = frappe.get_doc("Role", "Verification Staff")
	else:
		role = frappe.new_doc("Role")
		role.role_name = "Verification Staff"

	role.desk_access = 0
	role.home_page = "/project_verification"
	role.flags.ignore_mandatory = True
	role.flags.ignore_permissions = True
	role.save()
