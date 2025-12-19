# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class Depositslip(Document):
	pass


@frappe.whitelist()
def get_deposit_slip_fields(doc_name=None):
	"""
	API to return Deposit Slip field metadata and prefill data
	based on a Fund Received reference (doc_name).
	"""
	deposit_slip_meta = frappe.get_meta("Deposit slip")

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
			"depends_on": f.depends_on,
			"default": f.default,
		}
		for f in deposit_slip_meta.get("fields")
	]

	prefill_data = {}
	link_options = {}
	related_data = {}

	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch Fund Received document
		fund_received = frappe.db.get_value(
			"Fund Received",
			doc_name,
			["name", "prjreg_title", "sanction_ref_no", "fund_received_amt", "bank_account"],
			as_dict=True,
		)

		if fund_received:
			related_data = fund_received
			prefill_data["fund_received_ref"] = fund_received.name

			# Fetch Project Registration details if available
			if fund_received.prjreg_title:
				project = frappe.db.get_value(
					"Project Registration",
					fund_received.prjreg_title,
					["name", "project_title", "principal_investigator"],
					as_dict=True,
				)
				if project:
					prefill_data["project_title"] = project.name
					prefill_data["principal_investigator"] = project.principal_investigator

	# Link options for dropdowns
	link_options["fund_received_ref"] = frappe.get_all(
		"Fund Received", fields=["name as value", "name as label"], limit=200
	)
	link_options["project_title"] = frappe.get_all(
		"Project Registration", fields=["name as value", "project_title as label"], limit=200
	)
	link_options["principal_investigator"] = frappe.get_all(
		"User", fields=["name as value", "full_name as label"], limit=200
	)
	link_options["principal_consultant_organizer"] = frappe.get_all(
		"User", fields=["name as value", "full_name as label"], limit=200
	)
	link_options["funding_agency"] = frappe.get_all(
		"fundingagency_", fields=["name as value", "name as label"], limit=200
	)
	link_options["amended_from"] = frappe.get_all("Deposit slip", fields=["name as value"])

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
	}


@frappe.whitelist()
def save_deposit_slip(doc_data):
	"""Saves the Deposit Slip data from the React form."""
	try:
		data = json.loads(doc_data)
		print("Received data for Deposit Slip:", data)  # Debug log

		# Create new Deposit Slip document
		new_doc = frappe.new_doc("Deposit slip")

		# Map the form data to doctype fields
		field_mapping = {
			"category": "category",
			"fund_received_ref": "fund_received_ref",
			"project_title": "project_title",
			"principal_investigator": "principal_investigator",
			"consultancy_event_title": "consultancy_event_title",
			"principal_consultant_organizer": "principal_consultant_organizer",
			"client": "client",
			"funding_agency": "funding_agency",
			"gstin_of_funding_agency": "gstin_of_funding_agency",
			"iitg_invoice_no": "iitg_invoice_no",
			"bank": "bank",
			"amount_inclusive_of_gst": "amount_inclusive_of_gst",
			"ecs_acc_no": "ecs_acc_no",
			"igst_18": "igst_18",
			"cgst_9": "cgst_9",
			"sgst_9": "sgst_9",
			"overhead_amount": "overhead_amount",
			"amount_after_gst_tds": "amount_after_gst_tds",
			"total_cost_x": "total_cost_x",
			"consultancy_charge_y": "consultancy_charge_y",
			"operational_charge_z": "operational_charge_z",
			"overhead_from_z_multiplier": "overhead_from_z_multiplier",
			"total_overhead_y_multiplier": "total_overhead_y_multiplier",
			"total_overhead_z_multiplier": "total_overhead_z_multiplier",
			"institute_share_multiplier": "institute_share_multiplier",
			"overhead_from_z_amount": "overhead_from_z_amount",
			"total_overhead_amount": "total_overhead_amount",
			"institute_share_amount": "institute_share_amount",
			"total_overhead_institute_share": "total_overhead_institute_share",
		}

		# Update document with mapped data
		for form_field, doctype_field in field_mapping.items():
			if form_field in data and data[form_field] not in [None, ""]:
				new_doc.set(doctype_field, data[form_field])

		# Handle child table - ECS Dates
		if "ecs_dates" in data:
			for ecs_date in data["ecs_dates"]:
				# Only add rows that have at least date or amount
				if ecs_date.get("ecs_date") or ecs_date.get("amount", 0) > 0:
					new_doc.append(
						"ecs_dates",
						{
							"ecs_date": ecs_date.get("ecs_date"),
							"amount": ecs_date.get("amount", 0),
						},
					)

		# Save the document
		new_doc.insert(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully created Deposit Slip: {new_doc.name}")  # Debug log

		return {"status": "success", "docname": new_doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Deposit Slip Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Deposit Slip: {str(e)}")


@frappe.whitelist()
def submit_deposit_slip(docname):
	"""
	Submit a Deposit Slip document.
	"""
	try:
		doc = frappe.get_doc("Deposit slip", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Deposit Slip '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Deposit Slip '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Deposit Slip '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Deposit Slip Submit Error")
		return {"status": "error", "message": str(e)}
