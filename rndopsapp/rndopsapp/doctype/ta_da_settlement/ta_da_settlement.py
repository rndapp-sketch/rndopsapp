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


class TADASettlement(Document):
	pass


@frappe.whitelist()
def get_ta_da_settlement_fields(doc_name=None, travel_ref=None):
	"""
	API to return TA DA Settlement field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	Can prefill from a Travel reference.
	"""
	ta_da_meta = frappe.get_meta("TA DA Settlement")

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
		for f in ta_da_meta.get("fields")
	]

	prefill_data = {}
	link_options = {}
	related_data = {}
	child_table_fields = {}

	# Get child table field metadata for 'ta_da_other_expenses_p'
	other_expense_meta = frappe.get_meta("TA DA Other Expense")
	child_table_fields["ta_da_other_expenses_p"] = [
		{
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"in_list_view": f.in_list_view,
			"read_only": f.read_only,
		}
		for f in other_expense_meta.get("fields")
	]

	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch existing TA DA Settlement document for editing
		doc = frappe.get_doc("TA DA Settlement", doc_name)
		if doc:
			related_data = doc.as_dict()
			# Copy fields for prefill
			for field in fields:
				if hasattr(doc, field["fieldname"]):
					prefill_data[field["fieldname"]] = getattr(doc, field["fieldname"])
			# Include child table data
			prefill_data["ta_da_other_expenses_p"] = [row.as_dict() for row in doc.get("ta_da_other_expenses_p", [])]

	# Prefill from Travel reference
	if travel_ref:
		travel_ref = str(travel_ref).strip('"').strip("'")
		travel_doc = frappe.db.get_value(
			"Travel",
			travel_ref,
			["name", "applicant_name_travel", "designation_travel", "department_travel", "travel_project_number"],
			as_dict=True,
		)
		if travel_doc:
			prefill_data["ta_da_travel_application"] = travel_doc.name
			prefill_data["ta_da_name"] = travel_doc.applicant_name_travel
			prefill_data["ta_da_designation"] = travel_doc.designation_travel
			prefill_data["ta_da_department_section"] = travel_doc.department_travel
			prefill_data["ta_da_project_code"] = travel_doc.travel_project_number

	# Link options for dropdowns
	link_options["ta_da_travel_application"] = frappe.get_all(
		"Travel", fields=["name as value", "name as label"], limit=200
	)
	link_options["amended_from"] = frappe.get_all(
		"TA DA Settlement", fields=["name as value", "name as label"], limit=200
	)

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
		"child_table_fields": child_table_fields,
	}


@frappe.whitelist()
def save_ta_da_settlement(doc_data):
	"""Saves or updates the TA DA Settlement data from the React form."""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for TA DA Settlement:", data)  # Debug log

		# Check if editing existing document
		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("TA DA Settlement", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc("TA DA Settlement")

		# Field mapping for TA DA Settlement
		field_mapping = {
			"ta_da_travel_application": "ta_da_travel_application",
			"ta_da_name": "ta_da_name",
			"ta_da_designation": "ta_da_designation",
			"ta_da_department_section": "ta_da_department_section",
			"ta_da_employee_number": "ta_da_employee_number",
			"ta_da_project_code": "ta_da_project_code",
			"ta_da_contact": "ta_da_contact",
			"ta_da_ifsc_code": "ta_da_ifsc_code",
			"ta_da_scale_of_pay": "ta_da_scale_of_pay",
			"ta_da_bank_account_number": "ta_da_bank_account_number",
			"ta_da_bank_account_holder": "ta_da_bank_account_holder",
			"ta_da_purpose_of_journey": "ta_da_purpose_of_journey",
			"ta_da_journey_particulars": "ta_da_journey_particulars",
			"ta_da_local_conveyance_used": "ta_da_local_conveyance_used",
			"ta_da_total_claimed": "ta_da_total_claimed",
			"ta_da_advance_taken": "ta_da_advance_taken",
			"ta_da_net_claimed": "ta_da_net_claimed",
			"ta_da_comment": "ta_da_comment",
			"ta_da_additional_comment": "ta_da_additional_comment",
			"ta_da_check": "ta_da_check",
			"ta_da_entitled_class": "ta_da_entitled_class",
			"ta_da_shortest_route": "ta_da_shortest_route",
			"ta_da_not_paid_elsewhere": "ta_da_not_paid_elsewhere",
			"ta_da_boarding_lodging_status": "ta_da_boarding_lodging_status",
			"ta_da_free_transport": "ta_da_free_transport",
		}

		# Update document with mapped data
		for form_field, doctype_field in field_mapping.items():
			if form_field in data and data[form_field] not in [None, ""]:
				doc.set(doctype_field, data[form_field])

		# Handle child table - ta_da_other_expenses_p
		if "ta_da_other_expenses_p" in data:
			doc.set("ta_da_other_expenses_p", [])  # Clear existing
			for expense in data["ta_da_other_expenses_p"]:
				if expense.get("ta_da_expense_type_other_expense") or expense.get("ta_da_amount_other_expense"):
					doc.append(
						"ta_da_other_expenses_p",
						{
							"ta_da_expense_type_other_expense": expense.get("ta_da_expense_type_other_expense"),
							"ta_da_amount_other_expense": expense.get("ta_da_amount_other_expense", 0),
							"ta_da_proof_other_expense": expense.get("ta_da_proof_other_expense"),
						},
					)

		# Save the document
		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved TA DA Settlement: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "TA DA Settlement Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save TA DA Settlement: {str(e)}")


@frappe.whitelist()
def submit_ta_da_settlement(docname):
	"""
	Submit a TA DA Settlement document.
	"""
	try:
		doc = frappe.get_doc("TA DA Settlement", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"TA DA Settlement '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"TA DA Settlement '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"TA DA Settlement '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "TA DA Settlement Submit Error")
		return {"status": "error", "message": str(e)}
