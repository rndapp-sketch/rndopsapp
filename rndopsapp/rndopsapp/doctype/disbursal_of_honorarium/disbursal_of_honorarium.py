# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document
from frappe.utils.file_manager import save_file
from frappe import _

class DisbursalofHonorarium(Document):
	pass

def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	"""
	if not expression:
		return None
	
	expression = str(expression).strip()
	
	if expression.startswith("eval:"):
		return expression[5:].strip()  # Remove 'eval:' prefix
	
	return expression

@frappe.whitelist()
def get_disbursal_of_honorarium_fields(doc_name=None):
	"""
	Return Disbursal of Honorarium field metadata + prefill data.
	"""
	# --- fields meta (safe) ---
	meta = frappe.get_meta("Disbursal of Honorarium")
	fields = []
	for f in meta.get("fields"):
		fields.append(
			{
				"fieldname": f.fieldname,
				"label": f.label,
				"fieldtype": f.fieldtype,
				"options": getattr(f, "options", None),
				"mandatory": getattr(f, "reqd", False),
				"hidden": getattr(f, "hidden", False),
				"read_only": getattr(f, "read_only", False),
				"description": getattr(f, "description", "") or "",
				"default": getattr(f, "default", None),
				# Eval expressions for frontend conditional logic
				"depends_on": getattr(f, "depends_on", None),
				"mandatory_depends_on": getattr(f, "mandatory_depends_on", None),
				"read_only_depends_on": getattr(f, "read_only_depends_on", None),
				# Extract eval expression for easier frontend parsing
				"depends_on_eval": extract_eval_expression(getattr(f, "depends_on", None)),
				"mandatory_depends_on_eval": extract_eval_expression(getattr(f, "mandatory_depends_on", None)),
				"read_only_depends_on_eval": extract_eval_expression(getattr(f, "read_only_depends_on", None)),
			}
		)

		# If field is a Table, fetch its fields too
		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				child_fields = []
				for cf in child_meta.fields:
					child_fields.append({
						"fieldname": cf.fieldname,
						"label": cf.label,
						"fieldtype": cf.fieldtype,
						"options": getattr(cf, "options", None),
						"mandatory": getattr(cf, "reqd", False),
						"hidden": getattr(cf, "hidden", False),
						"read_only": getattr(cf, "read_only", False),
						"in_list_view": getattr(cf, "in_list_view", False),
						"depends_on": getattr(cf, "depends_on", None),
						"depends_on_eval": extract_eval_expression(getattr(cf, "depends_on", None)),
					})
				# Append child fields to the parent field definition
				fields[-1]["child_fields"] = child_fields
			except Exception:
				pass

	# --- containers to return ---
	prefill_data = {}
	link_options = {}

	# 1. Fetch Data (if doc_name provided)
	if doc_name:
		try:
			doc = frappe.get_doc("Disbursal of Honorarium", doc_name)
			prefill_data = doc.as_dict()
		except Exception:
			pass
	else:
		# Default prefill for new doc
		try:
			current_user = frappe.session.user
			if current_user and current_user not in ["Administrator", "Guest"]:
				prefill_data["webmail_id"] = current_user
				
				# Try to fetch details from user record
				user_doc = frappe.get_doc("User", current_user)
				prefill_data["name_of_applicant"] = user_doc.full_name
				prefill_data["designation_of_applicant"] = getattr(user_doc, "designation_name", None) or getattr(user_doc, "designation", None)
				prefill_data["department"] = getattr(user_doc, "department_name", None) or getattr(user_doc, "department", None)
		except Exception:
			pass

	# 2. Populate Link Options
	# webmail_id (User)
	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=200,
		)
		link_options["webmail_id"] = users
	except Exception:
		pass
		
	# account_head is a Select, options already in metadata
	# amended_from
	try:
		amended = frappe.get_all("Disbursal of Honorarium", fields=["name as value"], limit_page_length=200)
		link_options["amended_from"] = amended
	except Exception:
		pass

	# 3. Client Scripts
	client_scripts = []
	try:
		scripts = frappe.get_all("Client Script", filters={"dt": "Disbursal of Honorarium", "enabled": 1}, fields=["name", "script", "view"])
		for script in scripts:
			client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts
	}

@frappe.whitelist()
def save_disbursal_of_honorarium_data(data):
	"""
	Save Disbursal of Honorarium data.
	Expects 'data' as a JSON string or dict.
	"""
	if isinstance(data, str):
		data = json.loads(data)
	
	try:
		# Create or Get Doc
		if data.get("name"):
			doc = frappe.get_doc("Disbursal of Honorarium", data.get("name"))
		else:
			doc = frappe.new_doc("Disbursal of Honorarium")
		
		# Map Fields
		simple_fields = [
			"amended_from",
			"reference_application_number",
			"applying_for_self_or_other",
			"webmail_id",
			"name_of_applicant",
			"designation_of_applicant",
			"department",
			"account_head",
			"approval_comp_authority",
			"total_amount",
			"workflow_state" # Just in case it's passed, though usually handled by perform_action
		]

		for field in simple_fields:
			if field in data:
				val = data[field]
				doc.set(field, val if val != "null" else None)
		
		# Handle File Upload fields (Attach)
		# attached_approvals, additional_documents
		file_fields = ["attached_approvals", "additional_documents"]
		for field in file_fields:
			if field in data:
				val = data[field]
				# If val is a dict, it's a new file upload
				if isinstance(val, dict) and val.get("file_name") and val.get("file_data"):
					try:
						saved_file = save_file(
							val["file_name"],
							val["file_data"],
							doc.doctype,
							doc.name,
							decode=True,
							is_private=0,
							df=field
						)
						doc.set(field, saved_file.file_url)
					except Exception as e:
						frappe.log_error(f"Error saving file for {field}: {str(e)}", "Disbursal of Honorarium File Upload")
						# If upload fails, maybe don't set the field or set to None
						# Ensure we don't break the whole save
				elif isinstance(val, str):
					# Existing file URL or cleared
					doc.set(field, val)
		
		# Handle Child Table: table_weoy (Honorarium Table)
		items_data = data.get("table_weoy", [])
		if isinstance(items_data, str):
			items_data = json.loads(items_data)
			
		if items_data:
			doc.set("table_weoy", []) # Clear existing
			for item in items_data:
				# Check for file uploads in child table (if any - none in honorarium_table currently, but good practice)
				doc.append("table_weoy", item)
		
		# Save
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Disbursal of Honorarium Save Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def perform_disbursal_of_honorarium_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Disbursal of Honorarium", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = frappe.get_value("Workflow", {"document_type": "Disbursal of Honorarium"}, "name")
		
		if not workflow_name:
			frappe.throw("Workflow not found for Disbursal of Honorarium.")

		workflow = frappe.get_doc("Workflow", workflow_name)
		
		next_state = None
		
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				break
		
		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

		# Update workflow state
		doc.workflow_state = next_state
		
		# Check if next state requires submission (docstatus=1)
		# We check the 'states' table in Workflow to see if doc_status should be 1
		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		
		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_disbursal_of_honorarium_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Disbursal of Honorarium Action Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def get_disbursal_of_honorarium_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Disbursal of Honorarium", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	workflow_name = frappe.get_value("Workflow", {"document_type": "Disbursal of Honorarium"}, "name")
	
	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue

		# Check roles on the transition
		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]

		# User can perform action if they have allowed role
		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))
