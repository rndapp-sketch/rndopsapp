# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	"""
	if not expression:
		return None
	
	expression = str(expression).strip()
	
	if expression.startswith("eval:"):
		return expression[5:].strip()
	
	return expression


class ProjectStaffResignation(Document):
	pass


@frappe.whitelist()
def get_project_staff_resignation_fields(doc_name=None):
	"""
	API to return Project Staff Resignation field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	"""
	resignation_meta = frappe.get_meta("Project Staff Resignation")

	fields = [
		{
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
			"default": f.default,
			# Eval expressions for frontend conditional logic
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			# Extract eval expression for easier frontend parsing
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
		}
		for f in resignation_meta.get("fields")
	]

	prefill_data = {}
	link_options = {}
	related_data = {}

	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch existing Project Staff Resignation document for editing
		doc = frappe.get_doc("Project Staff Resignation", doc_name)
		if doc:
			related_data = doc.as_dict()
			# Copy fields for prefill
			for field in fields:
				if hasattr(doc, field["fieldname"]):
					prefill_data[field["fieldname"]] = getattr(doc, field["fieldname"])

	# Prefill current user data
	current_user = frappe.session.user
	if current_user and current_user != "Guest" and not current_user.endswith("@iitg.ac.in"):
		user_data = frappe.db.get_value(
			"User",
			current_user,
			["name", "full_name", "designation_name", "department_name", "employee_id"],
			as_dict=True,
		)
		if user_data:
			if not prefill_data.get("applicant_email_id"):
				prefill_data["applicant_email_id"] = user_data.name
			if not prefill_data.get("applicant_name"):
				prefill_data["applicant_name"] = user_data.full_name
			if not prefill_data.get("applicant_designation"):
				prefill_data["applicant_designation"] = user_data.designation_name
			if not prefill_data.get("applicant_department"):
				prefill_data["applicant_department"] = user_data.department_name
			if not prefill_data.get("applicant_emp_id"):
				prefill_data["applicant_emp_id"] = user_data.employee_id

	# Link options for dropdowns
	link_options["applicant_email_id"] = frappe.get_all(
		"User",
		filters=[["name", "not like", "%@iitg.ac.in"]],
		fields=["name as value", "full_name as label"],
		limit=200
	)
	link_options["amended_from"] = frappe.get_all(
		"Project Staff Resignation", fields=["name as value", "name as label"], limit=200
	)

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
	}


@frappe.whitelist()
def save_project_staff_resignation(doc_data):
	"""Saves or updates the Project Staff Resignation data from the React form."""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Project Staff Resignation:", data)  # Debug log

		# Check if editing existing document
		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("Project Staff Resignation", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc("Project Staff Resignation")

		# Field mapping for Project Staff Resignation
		field_mapping = {
			"applicant_email_id": "applicant_email_id",
			"applicant_name": "applicant_name",
			"applicant_emp_id": "applicant_emp_id",
			"applicant_prj_num": "applicant_prj_num",
			"applicant_designation": "applicant_designation",
			"applicant_department": "applicant_department",
			"resignation_date": "resignation_date",
			"reason": "reason",
		}

		# Update document with mapped data
		for form_field, doctype_field in field_mapping.items():
			if form_field in data and data[form_field] not in [None, ""]:
				doc.set(doctype_field, data[form_field])

		# Save the document
		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved Project Staff Resignation: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Staff Resignation Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Project Staff Resignation: {str(e)}")


@frappe.whitelist()
def submit_project_staff_resignation(docname):
	"""
	Submit a Project Staff Resignation document.
	"""
	try:
		doc = frappe.get_doc("Project Staff Resignation", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Project Staff Resignation '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Project Staff Resignation '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Project Staff Resignation '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Resignation Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_project_staff_resignation_list():
	"""
	Fetch all Project Staff Resignation documents.
	Returns a list of dictionaries with key details for viewing.
	"""
	try:
		resignations = frappe.get_all(
			"Project Staff Resignation",
			fields=[
				"name",
				"applicant_name",
				"applicant_email_id",
				"applicant_designation",
				"applicant_department",
				"resignation_date",
				"docstatus",
				"modified"
			],
			order_by="modified desc"
		)
		return {"status": "success", "data": resignations}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error fetching Project Staff Resignation list")
		return {"status": "error", "message": str(e)}
