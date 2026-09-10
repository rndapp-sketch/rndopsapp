# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname


def extract_eval_expression(expression):
	"""Extracts the JavaScript expression from a Frappe 'eval:' string."""
	if not expression:
		return None
	expression = str(expression).strip()
	if expression.startswith("eval:"):
		return expression[5:].strip()
	return expression


from rndopsapp.rndopsapp.kafka.producer import publish_deposit_slip as publish_consultancy_deposit_slip
from rndopsapp.rndopsapp.doctype.fund_received.deposit_slip_budget_validation import (
	validate_overhead_gst_budget_heads_for_doc,
)
from rndopsapp.rndopsapp.kafka.utils import record_publish_state
from rndopsapp.rndopsapp.kafka.config import TOPIC_DEPOSIT_SLIP

class DConsultancyDepositSlip(Document):
	def autoname(self):
		self.name = make_autoname("D-CONS-.YYYY.-.#####.")

	def on_update(self):
		"""
		Trigger Kafka sync on workflow state change. Publish must succeed for the
		transition to be allowed — on failure this raises, aborting and rolling
		back the save/submit that triggered it, so the document reverts to its
		previous state.
		"""
		if self.flags.get('skip_kafka_sync'):
			return

		doc_before_save = self.get_doc_before_save()
		old_state = doc_before_save.workflow_state if doc_before_save else None
		new_state = self.workflow_state
		target_states = ["Approved", "Verified", "Submitted"]

		is_state_transition = new_state in target_states and old_state != new_state
		is_fresh_submit = self.docstatus == 1 and (not doc_before_save or doc_before_save.docstatus == 0)

		if is_state_transition or is_fresh_submit:
			# Final-gate reconciliation backstop (implementation doc §3.4).
			if self.fund_received_ref and frappe.db.exists("Fund Received", self.fund_received_ref):
				fr_doc = frappe.get_doc("Fund Received", self.fund_received_ref)
				validate_overhead_gst_budget_heads_for_doc(self, fr_doc)

			record_publish_state(
				self.doctype, self.name, TOPIC_DEPOSIT_SLIP,
				old_state, new_state,
			)
			try:
				success = publish_consultancy_deposit_slip(self)
			except Exception as e:
				frappe.log_error(frappe.get_traceback(), "D Cons Deposit Slip Error")
				frappe.throw(_("Cannot proceed: Kafka sync failed ({0}).").format(str(e)))
			if not success:
				frappe.throw(_("Cannot proceed: Kafka sync returned False (check validation errors in the Error Log)."))


@frappe.whitelist()
def get_d_consultancy_deposit_slip_fields(doc_name=None):
	"""
	API to return D Consultancy Deposit Slip field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	"""
	doctype_name = "D Consultancy Deposit Slip"
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
					limit=200
				)
			else:
				link_options[fieldname] = frappe.get_all(
					linked_doctype,
					fields=["name as value", f"{title_field} as label"],
					limit=200
				)
		except Exception as e:
			# Fallback to just name if title field doesn't exist
			link_options[fieldname] = frappe.get_all(
				linked_doctype,
				fields=["name as value", "name as label"],
				limit=200
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
def save_d_consultancy_deposit_slip(doc_data):
	"""Saves the D Consultancy Deposit Slip data from the React form."""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for D Consultancy Deposit Slip:", data)

		doc_name = data.get("name") or data.get("docname")
		
		if doc_name and frappe.db.exists("D Consultancy Deposit Slip", doc_name):
			doc = frappe.get_doc("D Consultancy Deposit Slip", doc_name)
		else:
			doc = frappe.new_doc("D Consultancy Deposit Slip")

		field_mapping = {
			"consultancy_title": "consultancy_title",
			"category_d": "category_d",
			"principal_consultant": "principal_consultant",
			"client": "client",
			"funding_agency": "funding_agency",
			"gstin_of_funding_agency": "gstin_of_funding_agency",
			"iitg_invoice_no": "iitg_invoice_no",
			"bank": "bank",
			"ecs_ac_no": "ecs_ac_no",
			"amount_inclusive_of_gst": "amount_inclusive_of_gst",
			"igst_18_on_consultancy": "igst_18_on_consultancy",
			"amount_after_gst_tds": "amount_after_gst_tds",
			"total_cost_x": "total_cost_x",
			"consultancy_charge_y": "consultancy_charge_y",
			"operational_charge_z": "operational_charge_z",
			"overhead_from_y_multiplier": "overhead_from_y_multiplier",
			"overhead_from_z_multiplier": "overhead_from_z_multiplier",
			"institute_share_multiplier": "institute_share_multiplier",
			"overhead_from_y_amount": "overhead_from_y_amount",
			"overhead_from_z_amount": "overhead_from_z_amount",
			"total_overhead_amount": "total_overhead_amount",
			"institute_share_amount": "institute_share_amount",
			"total_overhead_institute_share": "total_overhead_institute_share",
			"balance_consultancy_fee": "balance_consultancy_fee",
			"balance_operation_charge": "balance_operation_charge",
			"total_gst": "total_gst",
			"total_amount": "total_amount",
			"gst_tds__2": "gst_tds__2",
			"income_tax_tds": "income_tax_tds",
			"idf_amount": "idf_amount",
			"staff_welfare_amount": "staff_welfare_amount",
			"student_welfare_amount": "student_welfare_amount",
			"idf_percentage": "idf_percentage",
		}

		for form_field, doctype_field in field_mapping.items():
			if form_field in data and data[form_field] not in [None, ""]:
				doc.set(doctype_field, data[form_field])

		# Handle child table - ECS Dates
		if "ecs_dates" in data:
			doc.ecs_dates = []
			for ecs_date in data["ecs_dates"]:
				if ecs_date.get("ecs_date") or ecs_date.get("amount", 0) > 0:
					doc.append("ecs_dates", {
						"ecs_date": ecs_date.get("ecs_date"),
						"amount": ecs_date.get("amount", 0),
					})

		# Handle child table - Credit Distribution
		if "credit_distribution" in data:
			doc.credit_distribution = []
			for row in data["credit_distribution"]:
				doc.append("credit_distribution", row)

		doc.save(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved D Consultancy Deposit Slip: {doc.name}")
		return {"status": "success", "name": doc.name, "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "D Consultancy Deposit Slip Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save D Consultancy Deposit Slip: {str(e)}")


@frappe.whitelist()
def submit_d_consultancy_deposit_slip(docname):
	"""Submit a D Consultancy Deposit Slip document."""
	try:
		doc = frappe.get_doc("D Consultancy Deposit Slip", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"D Consultancy Deposit Slip '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"D Consultancy Deposit Slip '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"D Consultancy Deposit Slip '{docname}' is cancelled.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "D Consultancy Deposit Slip Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_d_consultancy_deposit_slip_fields(docname, changes=None, child_table_changes=None):
	"""
	Update only the given fields (and optionally ecs_dates / credit_distribution
	/ dpf_credit_distributions rows) on a D Consultancy Deposit Slip document,
	including after its workflow_state has reached a locked state. Restricted
	to `staff, RnD` / System Manager. See
	rndopsapp.rndopsapp.deposit_slip_common.update_locked_deposit_slip.

	changes: JSON dict {fieldname: new_value}.
	child_table_changes: JSON list of
	    {"fieldname": "ecs_dates" | "dpf_credit_distributions",
	     "updated": [{"name": <row name>, "changes": {field: value}}, ...],
	     "inserted": [{field: value, ...}, ...],
	     "deleted": [<row name>, ...]}
	"""
	from rndopsapp.rndopsapp.deposit_slip_common import update_locked_deposit_slip

	return update_locked_deposit_slip("D Consultancy Deposit Slip", docname, changes, child_table_changes)


@frappe.whitelist()
def get_d_consultancy_deposit_slip_workflow_actions(doc_name):
	"""Returns available workflow actions for the current doc state and user role."""
	doc = frappe.get_doc("D Consultancy Deposit Slip", doc_name)
	user_roles = frappe.get_roles(frappe.session.user)
	workflow_name = frappe.db.get_value("Workflow", {"document_type": "D Consultancy Deposit Slip"}, "name")

	if not workflow_name:
		return []

	transitions = frappe.get_all(
		"Workflow Transition",
		filters={"parent": workflow_name, "state": doc.workflow_state},
		fields=["action", "next_state", "allowed"],
	)
	return [t for t in transitions if t.allowed in user_roles]


@frappe.whitelist()
def perform_d_consultancy_deposit_slip_workflow_action(docname, action):
	"""Perform a workflow action on a D Consultancy Deposit Slip document."""
	try:
		from frappe.model.workflow import apply_workflow
		doc = frappe.get_doc("D Consultancy Deposit Slip", docname)
		apply_workflow(doc, action)
		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' performed successfully.",
			"docname": docname,
			"workflow_state": doc.workflow_state,
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "D Consultancy Deposit Slip Workflow Error")
		return {"status": "error", "message": str(e)}
