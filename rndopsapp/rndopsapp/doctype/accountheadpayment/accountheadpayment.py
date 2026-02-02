# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from rndopsapp.rndopsapp.commitPayment import submit_payment_data


class AccountHeadPayment(Document):
	pass


@frappe.whitelist()
def get_account_head_payment_fields(doc_name=None):
	"""
	API to return AccountHeadPayment field metadata and prefill data.
	
	Args:
		doc_name: Optional document name to fetch existing data for editing
	
	Returns:
		dict: {
			"fields": list of field metadata,
			"prefill_data": dict of prefilled values (if doc_name provided),
			"link_options": dict of dropdown options for Link fields
		}
	"""
	account_head_payment_meta = frappe.get_meta("AccountHeadPayment")
	
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
		}
		for f in account_head_payment_meta.get("fields")
	]
	
	prefill_data = {}
	
	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")
		
		# Fetch existing AccountHeadPayment document
		try:
			doc = frappe.get_doc("AccountHeadPayment", doc_name)
			prefill_data = {
				"name": doc.name,
				"project_ref_number": doc.project_ref_number,
				"commit_id": doc.commit_id,
				"budget_head": doc.budget_head,
				"payment_date": doc.payment_date,
				"payment_particular": doc.payment_particular,
				"payment_reference_details": doc.payment_reference_details,
				"payment_amount": doc.payment_amount,
				"payment_bmr": doc.payment_bmr,
				"payment_status": doc.payment_status,
				"bank_transaction_number": doc.bank_transaction_number,
				"bank_transaction_date": doc.bank_transaction_date,
			}
		except Exception as e:
			frappe.log_error(f"Error fetching AccountHeadPayment {doc_name}: {str(e)}")
	
	# Link options for dropdowns
	link_options = {}
	
	# Project Registration options
	link_options["project_ref_number"] = frappe.get_all(
		"Project Registration",
		fields=["name as value", "project_title as label"],
		limit=200
	)
	
	# Budget Head options
	link_options["budget_head"] = frappe.get_all(
		"Budget Head",
		fields=["name as value", "budget_head as label"],
		limit=200
	)
	
	# Payment Status options (from Select field)
	link_options["payment_status"] = [
		{"value": "PENDING", "label": "PENDING"},
		{"value": "PAID", "label": "PAID"},
		{"value": "REJECTED", "label": "REJECTED"},
		{"value": "RECTIFICATION", "label": "RECTIFICATION"},
	]
	
	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
	}
