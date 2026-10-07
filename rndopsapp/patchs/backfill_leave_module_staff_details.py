import frappe

from rndopsapp.rndopsapp.doctype.leave_module.leave_module import _staff_detail_updates


def execute():
	"""Stamp staff name, employee number, project and day count on leave
	applications made before those fields existed. Without a project number
	they all sat in Pending Task's "Others" tab."""
	for name in frappe.get_all("Leave Module", pluck="name"):
		updates = _staff_detail_updates(frappe.get_doc("Leave Module", name))
		if updates:
			frappe.db.set_value("Leave Module", name, updates, update_modified=False)
