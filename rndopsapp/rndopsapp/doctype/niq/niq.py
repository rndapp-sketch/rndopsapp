# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

# --- START MKY 2026-04-30 10:08 IST: Added save_niq_data whitelisted endpoint ---
import frappe
from frappe.model.document import Document


class NIQ(Document):
	pass


@frappe.whitelist()
def save_niq_data(project_no=None, direct_purchase_ref=None, niq_data=None):
	"""
	Save or update a NIQ document with the given fields.

	Args:
	    project_no (str):           Project number to link the NIQ record.
	    direct_purchase_ref (str):  Reference to the associated Direct Purchase document.
	    niq_data (str):             HTML content representing the NIQ data.

	Returns:
	    dict: {"status": "success", "docname": <name>} on success,
	          or raises an exception on failure.
	"""
	try:
		# Validate that at least one identifying field is provided
		if not project_no and not direct_purchase_ref:
			frappe.throw("At least one of 'project_no' or 'direct_purchase_ref' must be provided.")

		# Check whether a NIQ document already exists for this project_no / direct_purchase_ref
		existing_name = None
		if project_no:
			existing_name = frappe.db.get_value(
				"NIQ", {"project_no": project_no}, "name"
			)

		if not existing_name and direct_purchase_ref:
			existing_name = frappe.db.get_value(
				"NIQ", {"direct_purchase_ref": direct_purchase_ref}, "name"
			)

		if existing_name:
			# Update existing document
			doc = frappe.get_doc("NIQ", existing_name)
			if project_no is not None:
				doc.project_no = project_no
			if direct_purchase_ref is not None:
				doc.direct_purchase_ref = direct_purchase_ref
			if niq_data is not None:
				doc.niq_data = niq_data
		else:
			# Create a new document
			doc = frappe.new_doc("NIQ")
			doc.project_no = project_no
			doc.direct_purchase_ref = direct_purchase_ref
			doc.niq_data = niq_data

		# Bypass validation/mandatory/link checks to allow partial saves
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True

		doc.save(ignore_permissions=True)
		frappe.db.commit()

		frappe.logger().info(f"NIQ document saved: {doc.name}")
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "save_niq_data Error")
		frappe.throw(f"An error occurred while saving NIQ data: {str(e)}")
# --- END MKY 2026-04-30 10:08 IST ---
