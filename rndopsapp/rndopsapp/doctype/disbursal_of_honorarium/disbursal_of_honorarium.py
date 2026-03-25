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
	print("dATA==================================================",data)
	if isinstance(data, str):
		data = json.loads(data)
	
	try:
		# Create or Get Doc
		if data.get("name"):
			doc = frappe.get_doc("Disbursal of Honorarium", data.get("name"))
		else:
			doc = frappe.new_doc("Disbursal of Honorarium")
		
		# Auto-resolve Project Name (Link: Project Registration) which expects 'name' (primary key)
		if data.get("project_name") and not frappe.db.exists("Project Registration", data["project_name"]):
			# Frontend might send 'testing full cycle' (project_title), look it up
			pr = frappe.db.get_value("Project Registration", {"project_title": data["project_name"]}, ["name", "project_no"], as_dict=1)
			if pr:
				data["project_name"] = pr.name
				# Update project_no to the correct project_no
				data["project_no"] = pr.project_no
		
		# In case project_name was already the primary key, but project_no is still the title
		elif data.get("project_name") and data.get("project_no") and data["project_name"] == data["project_no"]:
			pr_no = frappe.db.get_value("Project Registration", data["project_name"], "project_no")
			if pr_no:
				data["project_no"] = pr_no
		elif data.get("project_no") and not frappe.db.exists("Project Registration", data["project_no"]):
			pr_num = frappe.db.get_value("Project Registration", {"project_no": data["project_no"]}, "project_no")
			if pr_num:
				data["project_no"] = pr_num

		# Map Fields
		simple_fields = [
			"amended_from",
			"reference_application_number",
			"applying_for_self_or_other",
			"project_name",
			"project_no",
			"webmail_id",
			"name_of_applicant",
			"designation_of_applicant",
			"applicant_department",
			"webmail_id_for",
			"name_of_applicant_for",
			"designation_of_applicant_for",
			"department_for",
			"account_head",
			"approval_comp_authority",
			"total_amount"
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
		doc.workflow_action = action
		
		# Check if next state requires submission (docstatus=1)
		# We check the 'states' table in Workflow to see if doc_status should be 1
		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		
		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		# --- Data Pipeline Integration ---
		# Check if the document was just fully approved ("Approved by Dean(RnD)")
		# And if so, publish the cached commitment to Kafka
		if next_state == "Approved by Dean(RnD)":
			try:
				from rndopsapp.rndopsapp.commitToJsonFrappe import read_json_data, write_json_data
				from rndopsapp.rndopsapp.kafka_sync import publish_message
				import datetime

				commits = read_json_data()
				# Look for the commit matching this docname
				commit_index = next((index for (index, d) in enumerate(commits) if d.get("frapAppId") == docname), None)
				
				if commit_index is not None:
					commit_payload = commits.pop(commit_index)
					
					# Wrap payload as expected by Kafka producer
					wrapped_payload = {
						"schemaVersion": "1.0",
						"eventType": "ACCOUNT_HEAD_COMMIT",
						"timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"),
						"data": commit_payload
					}

					TOPIC_COMMIT = 'account-head-commit-events'
					TOPIC_COMMIT_DLQ = 'account-head-commit-events-dlq'
					
					# Publish to Kafka
					success = publish_message(
						TOPIC_COMMIT, 
						wrapped_payload, 
						doc.name, 
						TOPIC_COMMIT_DLQ, 
						key=commit_payload.get("projectNumber")
					)

					if success:
						frappe.logger().info(f"Successfully published delayed commitment for {docname} to Kafka.")
						# Only write back if publish succeeds, effectively deleting it from the pending cache
						write_json_data(commits)
					else:
						frappe.log_error(f"Failed to publish delayed commitment for {docname} to Kafka.", "Kafka Publish Error")
			except Exception as e:
				frappe.log_error(f"Error processing delayed commitment for {docname}: {str(e)}", "Data Pipeline Error")
		# -------------------------------

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


@frappe.whitelist()
def submit_disbursal_of_honorarium(docname):
	"""
	Submit a Disbursal of Honorarium document.
	Uses the workflow 'Submit' action to properly transition from Draft
	to the next workflow state (e.g. Pending Approval), instead of
	calling doc.submit() which would set docstatus=1 and incorrectly
	match the 'Rejected' workflow state.
	"""
	print("submit_disbursal_of_honorarium: execution started")
	print("Payload received:", docname)
	try:
		doc = frappe.get_doc("Disbursal of Honorarium", docname)

		current_state = doc.workflow_state or "Draft"
		print(f"Current workflow state: {current_state}, docstatus: {doc.docstatus}")

		if current_state != "Draft":
			return {
				"status": "info",
				"message": f"Disbursal of Honorarium '{docname}' is already in state '{current_state}'.",
				"docname": docname,
				"workflow_state": current_state,
			}

		# Use the workflow action to transition properly
		result = perform_disbursal_of_honorarium_action(docname, "Submit")
		if result.get("status") == "success":
			print(f"Disbursal submitted successfully via workflow. New state: {result.get('workflow_state')}")
		else:
			print(f"Disbursal submission failed: {result.get('message')}")

		return result

	except Exception as e:
		import traceback
		tb = traceback.format_exc()
		print(f"[ERROR][submit_disbursal_of_honorarium]: {str(e)}")
		print(f"[ERROR][submit_disbursal_of_honorarium] Traceback:\n{tb}")
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Disbursal of Honorarium Submit Error")
		return {"status": "error", "message": str(e) or tb}


@frappe.whitelist()
def get_disbursal_of_honorarium_by_project(project_code: str = "", limit: int = 200, start: int = 0):
	"""
	Returns Disbursal of Honorarium docs for a given project_code.
	"""
	from frappe.utils import cint

	limit = int(cint(limit) or 200)
	start = int(cint(start) or 0)
	project_code = (project_code or "").strip()

	if not project_code:
		return {"message": []}

	results = []
	try:
		# Use project_no as that's what stores the project_no in Disbursal of Honorarium
		names = frappe.get_all(
			"Disbursal of Honorarium",
			filters={"project_no": project_code},
			fields=["name"],
			limit_start=start,
			limit_page_length=limit,
			order_by="modified desc",
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_disbursal_of_honorarium_by_project: failed to query")
		return {"message": []}

	if not names:
		return {"message": []}

	for row in names:
		name = row.get("name")
		try:
			doc = frappe.get_doc("Disbursal of Honorarium", name)
			doc_dict = doc.as_dict()
			results.append(doc_dict)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"get_disbursal_of_honorarium_by_project: error loading {name}")
			continue

	return {"message": results}
