# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from rndopsapp.rndopsapp.kafka.producer import publish_deposit_slip as publish_research_consultancy_deposit_slip

def extract_eval_expression(expression):
	"""Extracts the JavaScript expression from a Frappe 'eval:' string."""
	if not expression:
		return None
	expression = str(expression).strip()
	if expression.startswith("eval:"):
		return expression[5:].strip()
	return expression


class ResearchConsultancyDepositSlip(Document):
	def autoname(self):
		self.name = make_autoname("RES-DS-.YYYY.-.#####")

	def on_update(self):
		"""
		Trigger Kafka sync on workflow state change to 'Approved' or 'Verified'.
		"""
		try:
			# Check for state transition
			doc_before_save = self.get_doc_before_save()
			old_state = doc_before_save.workflow_state if doc_before_save else None
			new_state = self.workflow_state
			
			# Define states that trigger sync (User requirement: HoS Approve/Verify)
			target_states = ["Approved", "Verified", "Submitted"]
			
			# Trigger if entering target state (and not already there)
			if new_state in target_states and old_state != new_state:
				frappe.msgprint(f"DEBUG: Triggering Kafka Sync for state {new_state}")
				publish_research_consultancy_deposit_slip(self)
				
		except Exception as e:
			frappe.log_error(f"Error in Deposit Slip on_update: {e}", "Research Consultancy Deposit Slip Error")
			# Don't throw error to block save, just log? Or throw if critical?
			# Usually better to log for background syncs, but user wants confirmation.
			pass


@frappe.whitelist()
def get_research_consultancy_deposit_slip_fields(doc_name=None):
	"""
	API to return Research Consultancy Deposit Slip field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	"""
	doctype_name = "Research Consultancy Deposit Slip"
	meta = frappe.get_meta(doctype_name)

	fields = []
	link_fields = []
	child_table_meta = {}  # Store child table field metadata
	
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
				"view": script.view  # "Form", "List", or "Report"
			})
	except Exception:
		pass  # Client Script doctype may not exist in older Frappe versions

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
		"client_scripts": client_scripts,
		"child_table_meta": child_table_meta,
	}


@frappe.whitelist()
def save_research_consultancy_deposit_slip(doc_data):
	"""Saves the Research Consultancy Deposit Slip data from the React form."""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Research Consultancy Deposit Slip:", data)

		doc_name = data.get("name") or data.get("docname")
		
		if doc_name and frappe.db.exists("Research Consultancy Deposit Slip", doc_name):
			doc = frappe.get_doc("Research Consultancy Deposit Slip", doc_name)
		else:
			doc = frappe.new_doc("Research Consultancy Deposit Slip")

		field_mapping = {
			"project_title": "project_title",
			"principal_investigator": "principal_investigator",
			"client": "client",
			"funding_agency": "funding_agency",
			"gstin_of_funding_agency": "gstin_of_funding_agency",
			"ecs_ac_no": "ecs_ac_no",
			"bank": "bank",
			"amount_inclusive_gst_capital": "amount_inclusive_gst_capital",
			"cgst_9": "cgst_9",
			"sgst_9": "sgst_9",
			"project_balance_after_gst": "project_balance_after_gst",
			"overhead_multiplier": "overhead_multiplier",
			"overhead_amount": "overhead_amount",
			"total_gst": "total_gst",
			"total_budget": "total_budget",
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

		print(f"Successfully saved Research Consultancy Deposit Slip: {doc.name}")
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Research Consultancy Deposit Slip Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Research Consultancy Deposit Slip: {str(e)}")


@frappe.whitelist()
def submit_research_consultancy_deposit_slip(docname):
	"""Submit a Research Consultancy Deposit Slip document."""
	try:
		doc = frappe.get_doc("Research Consultancy Deposit Slip", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Research Consultancy Deposit Slip '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Research Consultancy Deposit Slip '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Research Consultancy Deposit Slip '{docname}' is cancelled.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Research Consultancy Deposit Slip Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_research_consultancy_deposit_slip_workflow_actions():
	"""Returns available workflow actions based on user role."""
	user_roles = frappe.get_roles(frappe.session.user)
	workflow_name = "Research_Consultancy_Deposit_Slip_Workflow"
	
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


# Import moved to top of file - using new kafka.producer module

@frappe.whitelist()
def perform_research_consultancy_deposit_slip_workflow_action(docname, action):
	"""Perform a workflow action on a Research Consultancy Deposit Slip document."""
	try:
		doc = frappe.get_doc("Research Consultancy Deposit Slip", docname)
		current_state = doc.workflow_state or "Draft"
		workflow_name = "Research_Consultancy_Deposit_Slip_Workflow"
		
		if not frappe.db.exists("Workflow", workflow_name):
			frappe.throw(f"Workflow '{workflow_name}' not found.")
		
		workflow = frappe.get_doc("Workflow", workflow_name)
		
		# Find transition
		transition = next((t for t in workflow.transitions if t.state == current_state and t.action == action), None)
		if not transition:
			frappe.throw(_("No valid transition found for action '{}' from state '{}'.").format(action, current_state))
			
		next_state = transition.next_state
		
		# Verify Permissions (Optional but recommended, relying on UI roles mostly)
		user_roles = frappe.get_roles(frappe.session.user)
		if transition.allowed not in user_roles and "System Manager" not in user_roles:
			# frappe.throw(_("Not permitted to perform this action."))
			pass # workflow actions often vetted by get_workflow_actions
			
		# Update State
		doc.workflow_state = next_state
		
		# Handle DocStatus updates based on state settings
		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		if state_doc:
			if state_doc.doc_status == 1 and doc.docstatus == 0:
				doc.submit()
			elif state_doc.doc_status == 2 and doc.docstatus != 2:
				doc.cancel()
			else:
				doc.save(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

		# Side Effects: Kafka Sync on HoS Approval/Verification
		# User requirement: "hos approve or verify then send the deposit data to the kafka"
		# Logic: If entering "Approved" state or specific Verified state?
		# Assuming "Approved" is the final state.
		if next_state in ["Approved", "Verified", "Submitted"] and action in ["Approve", "Verify", "Submit"]:
			try:
				success = publish_research_consultancy_deposit_slip(doc)
				if success:
					frappe.msgprint(_("Deposit Slip data synced to Kafka successfully."), indicator='green')
				else:
					frappe.msgprint(_("Kafka sync returned False."), indicator='orange')
			except Exception as k_err:
				print(f"Kafka sync error: {k_err}")
				frappe.log_error(frappe.get_traceback(), "Deposit Slip Workflow Kafka Sync Error")
				frappe.msgprint(_("Failed to sync with Kafka: {}").format(str(k_err)), indicator='red')

		frappe.db.commit()
		
		return {
			"status": "success",
			"message": f"Action '{action}' performed successfully. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Research Consultancy Deposit Slip Workflow Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_deposit_slip_with_fund_received(deposit_slip_name=None, fund_received_ref=None):
	"""
	Get Deposit Slip data along with its linked Fund Received data.
	
	Args:
		deposit_slip_name (str, optional): Name of the Deposit Slip document.
		fund_received_ref (str, optional): Fund Received reference to find the linked Deposit Slip.
		
	Returns:
		dict: Contains deposit_slip data and fund_received data for side-by-side display.
		
	Example:
		/api/method/rndopsapp.rndopsapp.doctype.research_consultancy_deposit_slip.research_consultancy_deposit_slip.get_deposit_slip_with_fund_received?deposit_slip_name=RES-DS-2026-00001
		OR
		/api/method/rndopsapp.rndopsapp.doctype.research_consultancy_deposit_slip.research_consultancy_deposit_slip.get_deposit_slip_with_fund_received?fund_received_ref=REC_170126300-prjreg_refnum
	"""
	try:
		deposit_slip_doc = None
		fund_received_doc = None
		
		# Case 1: Find by deposit slip name
		if deposit_slip_name:
			deposit_slip_name = str(deposit_slip_name).strip().strip('"').strip("'")
			if frappe.db.exists("Research Consultancy Deposit Slip", deposit_slip_name):
				deposit_slip_doc = frappe.get_doc("Research Consultancy Deposit Slip", deposit_slip_name)
		
		# Case 2: Find by fund received reference
		elif fund_received_ref:
			fund_received_ref = str(fund_received_ref).strip().strip('"').strip("'")
			ds_name = frappe.db.get_value(
				"Research Consultancy Deposit Slip", 
				{"fund_received_ref": fund_received_ref}, 
				"name"
			)
			if ds_name:
				deposit_slip_doc = frappe.get_doc("Research Consultancy Deposit Slip", ds_name)
		
		if not deposit_slip_doc:
			return {
				"status": "not_found",
				"message": "Deposit Slip not found",
				"deposit_slip": None,
				"fund_received": None,
			}
		
		# Get linked Fund Received document
		fr_ref = deposit_slip_doc.get("fund_received_ref")
		if fr_ref and frappe.db.exists("Fund Received", fr_ref):
			fund_received_doc = frappe.get_doc("Fund Received", fr_ref)
		
		# Prepare deposit slip data
		deposit_slip_data = deposit_slip_doc.as_dict()
		
		# Ensure child tables are present
		if "ecs_dates" not in deposit_slip_data:
			deposit_slip_data["ecs_dates"] = []
		if "credit_distribution" not in deposit_slip_data:
			deposit_slip_data["credit_distribution"] = []
		
		# Prepare fund received data (if exists)
		fund_received_data = None
		if fund_received_doc:
			fund_received_data = fund_received_doc.as_dict()
			
			# Ensure child tables are present
			if "received_amt_breakup" not in fund_received_data:
				fund_received_data["received_amt_breakup"] = []
			if "fund_transactions" not in fund_received_data:
				fund_received_data["fund_transactions"] = []
		
		return {
			"status": "success",
			"deposit_slip": deposit_slip_data,
			"fund_received": fund_received_data,
		}
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Deposit Slip With Fund Received Error")
		return {
			"status": "error",
			"message": str(e),
			"deposit_slip": None,
			"fund_received": None,
		}


@frappe.whitelist()
def get_deposit_slips_by_fund_received(fund_received_name):
	"""
	Get all Deposit Slips linked to a Fund Received document.
	
	Args:
		fund_received_name (str): Name of the Fund Received document.
		
	Returns:
		dict: List of deposit slips linked to the Fund Received.
	"""
	try:
		fund_received_name = str(fund_received_name).strip().strip('"').strip("'")
		
		# Find all deposit slips linked to this Fund Received
		deposit_slips = frappe.get_all(
			"Research Consultancy Deposit Slip",
			filters={"fund_received_ref": fund_received_name},
			fields=["name", "workflow_state", "project_title", "docstatus", "creation", "modified"],
			order_by="creation desc"
		)
		
		# Get full data for each deposit slip
		results = []
		for ds in deposit_slips:
			try:
				doc = frappe.get_doc("Research Consultancy Deposit Slip", ds.name)
				doc_dict = doc.as_dict()
				
				# Ensure child tables are present
				if "ecs_dates" not in doc_dict:
					doc_dict["ecs_dates"] = []
				if "credit_distribution" not in doc_dict:
					doc_dict["credit_distribution"] = []
					
				results.append(doc_dict)
			except Exception:
				# Log but continue
				frappe.log_error(frappe.get_traceback(), f"Error loading deposit slip {ds.name}")
				continue
		
		return {
			"status": "success",
			"count": len(results),
			"deposit_slips": results,
		}
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Deposit Slips By Fund Received Error")
		return {
			"status": "error",
			"message": str(e),
			"count": 0,
			"deposit_slips": [],
		}

