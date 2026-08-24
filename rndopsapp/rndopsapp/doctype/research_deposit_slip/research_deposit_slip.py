# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from rndopsapp.rndopsapp.kafka.producer import publish_deposit_slip as publish_research_deposit_slip
from rndopsapp.rndopsapp.kafka.utils import record_publish_state
from rndopsapp.rndopsapp.kafka.config import TOPIC_DEPOSIT_SLIP

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

class ResearchDepositSlip(Document):
	def autoname(self):
		self.name = make_autoname("RES-DS-.YYYY.-.#####")

	def on_update(self):
		"""
		Trigger Kafka sync on workflow state change to 'Approved' or 'Verified'.
		Publish must succeed for the transition to be allowed — on failure this
		raises, aborting and rolling back the save/submit that triggered it, so
		the document reverts to its previous state.
		"""
		if self.flags.get('skip_kafka_sync'):
			return
		doc_before_save = self.get_doc_before_save()
		old_state = doc_before_save.workflow_state if doc_before_save else None
		new_state = self.workflow_state
		target_states = ["Approved", "Verified", "Submitted"]

		is_state_transition = new_state in target_states and old_state != new_state
		is_fresh_submit = (
			self.docstatus == 1
			and (not doc_before_save or doc_before_save.docstatus == 0)
			and new_state not in target_states
		)

		if is_state_transition or is_fresh_submit:
			record_publish_state(
				self.doctype, self.name, TOPIC_DEPOSIT_SLIP,
				old_state, new_state,
			)
			try:
				success = publish_research_deposit_slip(self)
			except Exception as e:
				frappe.log_error(frappe.get_traceback(), "Research Deposit Slip Error")
				frappe.throw(_("Cannot proceed: Kafka sync failed ({0}).").format(str(e)))
			if not success:
				frappe.throw(_("Cannot proceed: Kafka sync returned False (check validation errors in the Error Log)."))

@frappe.whitelist()
def get_research_deposit_slip_fields(doc_name=None):
	"""
	API to return Research Deposit Slip field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	"""
	doctype_name = "Research Deposit Slip"
	meta = frappe.get_meta(doctype_name)

	fields = []
	link_fields = []
	child_table_meta = {}

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
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
		}
		fields.append(field_data)

		if f.fieldtype == "Link" and f.options:
			link_fields.append({"fieldname": f.fieldname, "options": f.options})

		# Fetch child table metadata for Table fields
		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				child_fields = []
				for cf in child_meta.get("fields"):
					child_fields.append({
						"fieldname": cf.fieldname,
						"label": cf.label,
						"fieldtype": cf.fieldtype,
						"options": cf.options,
						"mandatory": cf.reqd,
						"hidden": cf.hidden,
						"read_only": cf.read_only,
						"description": cf.description,
						"default": cf.default,
						"fetch_from": cf.fetch_from,
						"in_list_view": cf.in_list_view,
						"columns": cf.columns,
					})
				child_table_meta[f.fieldname] = {
					"doctype": f.options,
					"fields": child_fields
				}
			except Exception:
				pass

	prefill_data = {}
	link_options = {}
	related_data = {}

	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'")
		if frappe.db.exists(doctype_name, doc_name):
			doc = frappe.get_doc(doctype_name, doc_name)
			related_data = doc.as_dict()
			prefill_data = doc.as_dict()
		else:
			# Try to fetch from Fund Received if doc_name is a Fund Received reference
			fund_received = frappe.db.get_value(
				"Fund Received",
				doc_name,
				["name", "prjreg_title", "fund_received_ref_number", "fund_received_amt", "bank_account"],
				as_dict=True,
			)

			if fund_received:
				related_data = fund_received
				prefill_data["fund_received_ref"] = fund_received.name

				if fund_received.prjreg_title:
					project = frappe.db.get_value(
						"Project Registration",
						fund_received.prjreg_title,
						["name", "project_title", "principal_investigator_name"],
						as_dict=True,
					)
					if project:
						prefill_data["project_title"] = project.name
						prefill_data["principal_investigator"] = project.principal_investigator_name

	# Dynamically get link options for all Link fields
	for link_field in link_fields:
		fieldname = link_field["fieldname"]
		linked_doctype = link_field["options"]

		try:
			# Get title field for linked doctype if available
			linked_meta = frappe.get_meta(linked_doctype)
			title_field = linked_meta.title_field or "name"

			# Special handling for User doctype
			if linked_doctype == "User":
				link_options[fieldname] = frappe.get_all(
					linked_doctype,
					fields=["name as value", "full_name as label"],
					limit_page_length=0,
					)
			else:
				link_options[fieldname] = frappe.get_all(
					linked_doctype,
					fields=["name as value", f"{title_field} as label"],
					limit_page_length=0,
				)
		except Exception as e:
			# Fallback to just name if title field doesn't exist
			link_options[fieldname] = frappe.get_all(
				linked_doctype,
				fields=["name as value", "name as label"],
				limit_page_length=0,
			)

	# Fetch Client Scripts from Frappe UI (stored in database)
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
		"related_data": related_data,
		"client_scripts": client_scripts,
		"child_table_meta": child_table_meta,
	}

@frappe.whitelist()
def save_research_deposit_slip(doc_data):
	"""Saves the Research Deposit Slip data."""
	try:
		data = json.loads(doc_data)
		print("Received data for Research Deposit Slip:", data)

		new_doc = frappe.new_doc("Research Deposit Slip")

		# Field mapping: form field -> doctype field
		# These must match the fields in research_deposit_slip.json
		field_mapping = {
			"principal_investigator": "principal_investigator",
			"project_title": "project_title",
			"funding_agency": "funding_agency",
			"deposit_date": "deposit_date",
			"total_amount": "total_amount",
			"overhead_amount": "overhead_amount",
			"ecs_scheme_no": "ecs_scheme_no",
			"bank_name": "bank_name",
			"account_number": "account_number",
			"idf_amount": "idf_amount",
			"dpf_amount": "dpf_amount",
			"pdf_amount": "pdf_amount",
			"staff_welfare_amount": "staff_welfare_amount",
			"student_welfare_fund": "student_welfare_fund",
			"project_no": "project_no",
			"project_account_balance": "project_account_balance",
			"grand_total": "grand_total",
		}

		for form_field, doctype_field in field_mapping.items():
			if form_field in data and data[form_field] not in [None, ""]:
				new_doc.set(doctype_field, data[form_field])

		if "ecs_dates" in data:
			for ecs_date in data["ecs_dates"]:
				if ecs_date.get("ecs_date") or ecs_date.get("amount", 0) > 0:
					new_doc.append(
						"ecs_dates",
						{
							"ecs_date": ecs_date.get("ecs_date"),
							"amount": ecs_date.get("amount", 0),
						},
					)

		new_doc.insert(ignore_permissions=True)
		frappe.db.commit()

		return {"status": "success", "docname": new_doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Research Deposit Slip Save Error")
		frappe.db.rollback()
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def submit_research_deposit_slip(docname):
	"""
	Submit a Research Deposit Slip document.
	"""
	try:
		doc = frappe.get_doc("Research Deposit Slip", docname)

		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Research Deposit Slip '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Research Deposit Slip '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Research Deposit Slip '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Research Deposit Slip Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_research_deposit_slip_fields(docname, changes=None, child_table_changes=None):
	"""
	Update only the given fields (and optionally child table rows) on a
	Research Deposit Slip document, including after its workflow_state has
	reached a locked state. Restricted to `staff, RnD` / System Manager. See
	rndopsapp.rndopsapp.deposit_slip_common.update_locked_deposit_slip.

	changes: JSON dict {fieldname: new_value}.
	child_table_changes: JSON list of
	    {"fieldname": "ecs_dates" | "pdf_credit_distribution" | "dpf_credit_distributions",
	     "updated": [{"name": <row name>, "changes": {field: value}}, ...],
	     "inserted": [{field: value, ...}, ...],
	     "deleted": [<row name>, ...]}
	"""
	from rndopsapp.rndopsapp.deposit_slip_common import update_locked_deposit_slip

	return update_locked_deposit_slip("Research Deposit Slip", docname, changes, child_table_changes)
