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
from rndopsapp.rndopsapp.kafka.utils import record_publish_state
from rndopsapp.rndopsapp.kafka.config import TOPIC_DEPOSIT_SLIP

class OtherEventDepositSlip(Document):
	def autoname(self):
		self.name = make_autoname("EVENT-DS-.YYYY.-.#####")

	def on_update(self):
		"""
		Trigger Kafka sync on workflow state change.
		"""
		if self.flags.get('skip_kafka_sync'):
			return
		try:
			doc_before_save = self.get_doc_before_save()
			old_state = doc_before_save.workflow_state if doc_before_save else None
			new_state = self.workflow_state
			target_states = ["Approved", "Verified", "Submitted"]

			if (new_state in target_states and old_state != new_state):
				frappe.msgprint(f"DEBUG: Triggering Kafka Sync (Other) for state {new_state}")
				record_publish_state(
					self.doctype, self.name, TOPIC_DEPOSIT_SLIP,
					old_state, new_state,
				)
				publish_consultancy_deposit_slip(self)
			elif self.docstatus == 1 and (not doc_before_save or doc_before_save.docstatus == 0):
				frappe.msgprint(f"DEBUG: Triggering Kafka Sync (Other) for Submit")
				record_publish_state(
					self.doctype, self.name, TOPIC_DEPOSIT_SLIP,
					old_state, new_state,
				)
				publish_consultancy_deposit_slip(self)
		except Exception as e:
			frappe.log_error(f"Error in Other Event Deposit Slip on_update: {e}", "Other Event Deposit Slip Error")
			pass


@frappe.whitelist()
def get_other_event_deposit_slip_fields(doc_name=None):
	"""
	API to return Other Event Deposit Slip field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	"""
	doctype_name = "Other Event Deposit Slip"
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
			linked_meta = frappe.get_meta(linked_doctype)
			title_field = linked_meta.title_field or "name"
			
			if linked_doctype == "User":
				link_options[fieldname] = frappe.get_all(
					linked_doctype, fields=["name as value", "full_name as label"], limit=200
				)
			else:
				link_options[fieldname] = frappe.get_all(
					linked_doctype, fields=["name as value", f"{title_field} as label"], limit=200
				)
		except Exception:
			link_options[fieldname] = frappe.get_all(
				linked_doctype, fields=["name as value", "name as label"], limit=200
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
def save_other_event_deposit_slip(doc_data):
	"""Saves the Other Event Deposit Slip data from the React form."""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Other Event Deposit Slip:", data)

		doc_name = data.get("name") or data.get("docname")
		
		if doc_name and frappe.db.exists("Other Event Deposit Slip", doc_name):
			doc = frappe.get_doc("Other Event Deposit Slip", doc_name)
		else:
			doc = frappe.new_doc("Other Event Deposit Slip")

		field_mapping = {
			"event_title": "event_title",
			"principal_organizer": "principal_organizer",
			"client": "client",
			"funding_agency": "funding_agency",
			"gstin_no": "gstin_no",
			"ecs_ac_no": "ecs_ac_no",
			"bank": "bank",
			"amount_inclusive_of_gst": "amount_inclusive_of_gst",
			"gst_multiplier": "gst_multiplier",
			"gst_amount": "gst_amount",
			"training_fee": "training_fee",
			"overhead_amount": "overhead_amount",
			"gst_final": "gst_final",
			"total": "total",
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

		# Handle child table - Additional Project Credits
		if "additional_project_credits" in data:
			doc.additional_project_credits = []
			for row in data["additional_project_credits"]:
				doc.append("additional_project_credits", row)

		doc.save(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved Other Event Deposit Slip: {doc.name}")
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Other Event Deposit Slip Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Other Event Deposit Slip: {str(e)}")


@frappe.whitelist()
def submit_other_event_deposit_slip(docname):
	"""Submit an Other Event Deposit Slip document."""
	try:
		doc = frappe.get_doc("Other Event Deposit Slip", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Other Event Deposit Slip '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Other Event Deposit Slip '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Other Event Deposit Slip '{docname}' is cancelled.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Other Event Deposit Slip Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_other_event_deposit_slip_fields(docname, changes=None, child_table_changes=None):
	"""
	Update only the given fields (and optionally ecs_dates / credit_distribution
	/ additional_project_credits rows) on an Other Event Deposit Slip document,
	including after its workflow_state has reached a locked state. Restricted
	to `staff, RnD` / System Manager. See
	rndopsapp.rndopsapp.deposit_slip_common.update_locked_deposit_slip.

	changes: JSON dict {fieldname: new_value}.
	child_table_changes: JSON list of
	    {"fieldname": "ecs_dates" | "credit_distribution" | "additional_project_credits",
	     "updated": [{"name": <row name>, "changes": {field: value}}, ...],
	     "inserted": [{field: value, ...}, ...],
	     "deleted": [<row name>, ...]}
	"""
	from rndopsapp.rndopsapp.deposit_slip_common import update_locked_deposit_slip

	return update_locked_deposit_slip("Other Event Deposit Slip", docname, changes, child_table_changes)


@frappe.whitelist()
def get_other_event_deposit_slip_workflow_actions():
	"""Returns available workflow actions based on user role."""
	user_roles = frappe.get_roles(frappe.session.user)
	workflow_name = "Other_Event_Deposit_Slip_Workflow"
	
	if not frappe.db.exists("Workflow", workflow_name):
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	actions = []

	for transition in workflow.transitions:
		if transition.allowed in user_roles:
			actions.append({
				"action": transition.action,
				"state": transition.state,
				"next_state": transition.next_state,
				"allowed": transition.allowed,
			})

	return actions


@frappe.whitelist()
def perform_other_event_deposit_slip_workflow_action(docname, action):
	"""Perform a workflow action on an Other Event Deposit Slip document."""
	try:
		doc = frappe.get_doc("Other Event Deposit Slip", docname)
		doc.run_method("apply_workflow", action)
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		
		return {
			"status": "success",
			"message": f"Action '{action}' performed successfully.",
			"docname": docname,
			"workflow_state": doc.workflow_state,
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Other Event Deposit Slip Workflow Error")
		return {"status": "error", "message": str(e)}
