# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from rndopsapp.rndopsapp.commitPayment import submit_payment_data


class AccountHeadPayment(Document):
	def autoname(self):
		from frappe.utils import today
		import frappe
		
		if not self.project_ref_number:
			return
			
		dt = today().split('-')
		base_name = f"{dt[2]}{dt[1]}{dt[0]}{self.project_ref_number}"
		
		if not frappe.db.exists("AccountHeadPayment", base_name):
			self.name = base_name
		else:
			count = 1
			while frappe.db.exists("AccountHeadPayment", f"{base_name}-{count}"):
				count += 1
			self.name = f"{base_name}-{count}"


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


@frappe.whitelist()
def get_account_head_payment_fields(doc_name=None):
	"""
	API to return AccountHeadPayment field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	Includes client scripts.
	"""
	doctype_name = "AccountHeadPayment"
	meta = frappe.get_meta(doctype_name)
	
	fields = []
	link_fields = []
	
	for f in meta.get("fields"):
		field_data = {
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
			"default": f.default,
			"fetch_from": f.fetch_from,
			"fetch_if_empty": f.fetch_if_empty,
			# Eval expressions for frontend conditional logic
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			# Extract eval expression for easier frontend parsing
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
		}
		fields.append(field_data)

		# Collect Link fields for dynamic options
		if f.fieldtype == "Link" and f.options:
			link_fields.append({"fieldname": f.fieldname, "options": f.options})

	prefill_data = {}
	link_options = {}
	
	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")
		
		# Fetch existing document
		if frappe.db.exists(doctype_name, doc_name):
			doc = frappe.get_doc(doctype_name, doc_name)
			prefill_data = doc.as_dict()

	# ===== Link options for dropdowns =====
	for link_field in link_fields:
		fieldname = link_field["fieldname"]
		linked_doctype = link_field["options"]

		try:
			linked_meta = frappe.get_meta(linked_doctype)
			title_field = linked_meta.title_field or "name"

			if linked_doctype == "User":
				link_options[fieldname] = frappe.get_all(
					linked_doctype,
					filters={"enabled": 1},
					fields=["name as value", "full_name as label"],
					limit_page_length=500
				)
			else:
				link_options[fieldname] = frappe.get_all(
					linked_doctype,
					fields=["name as value", f"{title_field} as label"],
					limit_page_length=500
				)
		except Exception:
			link_options[fieldname] = frappe.get_all(
				linked_doctype,
				fields=["name as value", "name as label"],
				limit_page_length=500
			)

	# Fetch Client Scripts
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": doctype_name, "enabled": 1},
			fields=["name", "script", "view"]
		)
		for script in scripts:
			client_scripts.append({
				"name": script.name,
				"script": script.script,
				"view": script.view
			})
	except Exception:
		pass
	
	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
	}
