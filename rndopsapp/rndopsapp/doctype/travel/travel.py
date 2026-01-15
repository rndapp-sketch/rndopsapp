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


class Travel(Document):
	pass


@frappe.whitelist()
def get_travel_fields(doc_name=None):
	"""
	API to return Travel field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	"""
	travel_meta = frappe.get_meta("Travel")

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
		for f in travel_meta.get("fields")
	]

	prefill_data = {}
	link_options = {}
	related_data = {}

	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch existing Travel document for editing
		doc = frappe.get_doc("Travel", doc_name)
		if doc:
			related_data = doc.as_dict()
			# Copy fields for prefill
			for field in fields:
				if hasattr(doc, field["fieldname"]):
					prefill_data[field["fieldname"]] = getattr(doc, field["fieldname"])

	# Prefill current user data
	current_user = frappe.session.user
	if current_user and current_user != "Guest":
		user_data = frappe.db.get_value(
			"User",
			current_user,
			["name", "full_name", "designation_name", "department_name"],
			as_dict=True,
		)
		if user_data:
			if not prefill_data.get("webmail_id_travel"):
				prefill_data["webmail_id_travel"] = user_data.name
			if not prefill_data.get("applicant_name_travel"):
				prefill_data["applicant_name_travel"] = user_data.full_name
			if not prefill_data.get("designation_travel"):
				prefill_data["designation_travel"] = user_data.designation_name
			if not prefill_data.get("department_travel"):
				prefill_data["department_travel"] = user_data.department_name

	# Link options for dropdowns
	link_options["webmail_id_travel"] = frappe.get_all(
		"User", fields=["name as value", "name as label"], limit=200
	)
	link_options["travel_project_title"] = frappe.get_all(
		"Project Registration", fields=["name as value", "project_title as label"], limit=200
	)
	link_options["amended_from"] = frappe.get_all(
		"Travel", fields=["name as value", "name as label"], limit=200
	)

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
	}


@frappe.whitelist()
def save_travel(doc_data):
	"""Saves or updates the Travel data from the React form."""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Travel:", data)  # Debug log

		# Check if editing existing document
		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("Travel", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc("Travel")

		# Field mapping for Travel
		field_mapping = {
			"webmail_id_travel": "webmail_id_travel",
			"applicant_name_travel": "applicant_name_travel",
			"designation_travel": "designation_travel",
			"department_travel": "department_travel",
			"if_traveler": "if_traveler",
			"other_traveler": "other_traveler",
			"other_traveler_address": "other_traveler_address",
			"travel_supporting_documents": "travel_supporting_documents",
			"visit_type_travel": "visit_type_travel",
			"specify_type_of_visit": "specify_type_of_visit",
			"nature_of_travel": "nature_of_travel",
			"venue_address": "venue_address",
			"organizing_authority": "organizing_authority",
			"purpose_of_visit": "purpose_of_visit",
			"travel_project_title": "travel_project_title",
			"travel_project_number": "travel_project_number",
			"from_date": "from_date",
			"to_date": "to_date",
			"travel_head": "travel_head",
			"contingency_head": "contingency_head",
			"other_head": "other_head",
			"travel_contribution": "travel_contribution",
			"contingency_contribution": "contingency_contribution",
			"other_account_head": "other_account_head",
			"other_contribution": "other_contribution",
			"travel_financial_assistance": "travel_financial_assistance",
			"travel_mode_of_travel": "travel_mode_of_travel",
			"travel_special_casual_leave": "travel_special_casual_leave",
			"travel_leave_from_date": "travel_leave_from_date",
			"travel_leave_to_date": "travel_leave_to_date",
			"travel_station_leave_from_date": "travel_station_leave_from_date",
			"travel_station_leave_from_session": "travel_station_leave_from_session",
			"travel_station_leave_to_date": "travel_station_leave_to_date",
			"travel_station_leave_to_session": "travel_station_leave_to_session",
			"travel_additional_responsibility": "travel_additional_responsibility",
			"travel_additional_responsibility_details": "travel_additional_responsibility_details",
			"travel_classes_arrangement": "travel_classes_arrangement",
			"travel_comment_if_any": "travel_comment_if_any",
			"travel_declaration_accepted": "travel_declaration_accepted",
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

		print(f"Successfully saved Travel: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Travel Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Travel: {str(e)}")


@frappe.whitelist()
def submit_travel(docname):
	"""
	Submit a Travel document.
	"""
	try:
		doc = frappe.get_doc("Travel", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Travel '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Travel '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Travel '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Travel Submit Error")
		return {"status": "error", "message": str(e)}
