# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document


class TemporaryAdvance(Document):
	pass


@frappe.whitelist()
def get_temporary_advance_fields(project_code=None):
	"""
	API to return Temporary Advance field metadata and prefill data
	based on a Project Registration ref number (project_code).
	"""
	temporary_advance_meta = frappe.get_meta("Temporary Advance")

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
		}
		for f in temporary_advance_meta.get("fields")
	]

	prefill_data = {}
	link_options = {}
	related_project_data = {}

	# Pre-fill current user details from User doctype
	user = frappe.session.user
	if user and user != "Guest":
		try:
			user_doc = frappe.get_doc("User", user)
			
			# Applicant details from User doctype
			prefill_data["applicant_webmail"] = user_doc.email
			prefill_data["applicant_department"] = user_doc.department  # Link to Department_prornd
			prefill_data["applicant_designation"] = user_doc.designation
			
			# Also try to get bank details if available (from User Bank doctype)
			try:
				user_bank = frappe.get_all(
					"User Bank",
					filters={"user": user},
					fields=["bank_name", "account_number", "ifsc_code", "account_holder_name"],
					limit_page_length=1,
				)
				if user_bank:
					prefill_data["bank_name"] = user_bank[0].get("bank_name")
					prefill_data["bank_account_number"] = user_bank[0].get("account_number")
					prefill_data["ifsc_code"] = user_bank[0].get("ifsc_code")
					prefill_data["account"] = user_bank[0].get("account_holder_name")
			except Exception:
				pass
		except Exception:
			pass

	# If project_code is provided, fetch project details
	if project_code:
		project_code = str(project_code).strip('"').strip("'")

		project_doc = frappe.db.get_value(
			"Project Registration",
			project_code,
			["name", "project_title", "project_type"],
			as_dict=True
		)

		if project_doc:
			related_project_data = project_doc
			prefill_data["project_code"] = project_doc.name
			prefill_data["project_name"] = project_doc.project_title

	# ===== Link options for dropdowns =====
	
	# Project Registration options (for project_code and project_name)
	try:
		projects = frappe.get_all(
			"Project Registration",
			fields=["name as value", "project_title as label"],
			limit_page_length=500
		)
		link_options["project_code"] = projects
		link_options["project_name"] = projects
	except Exception:
		link_options["project_code"] = []
		link_options["project_name"] = []

	# Users list (for webmail fields - advance_for_id and applicant_webmail)
	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=500,
		)
		link_options["advance_for_id"] = users
		link_options["applicant_webmail"] = users
	except Exception:
		link_options["advance_for_id"] = []
		link_options["applicant_webmail"] = []

	# Department options (for advance_for_department and applicant_department)
	try:
		departments = frappe.get_all(
			"Department_prornd",
			fields=["name as value", "dept_name as label"],
			limit_page_length=500,
		)
		link_options["advance_for_department"] = departments
		link_options["applicant_department"] = departments
	except Exception:
		link_options["advance_for_department"] = []
		link_options["applicant_department"] = []

	# Designation options (from User doctype - get unique designations)
	try:
		# Get unique designations from User records
		designations_raw = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["designation"],
			limit_page_length=1000,
		)
		# Extract unique non-empty designations
		unique_designations = list(set(
			d.get("designation") for d in designations_raw 
			if d.get("designation")
		))
		designations = [{"value": d, "label": d} for d in sorted(unique_designations)]
		link_options["advance_for_designation"] = designations
		link_options["applicant_designation"] = designations
	except Exception:
		link_options["advance_for_designation"] = []
		link_options["applicant_designation"] = []

	# Account Head (Budget Head) options
	try:
		account_heads = frappe.get_all(
			"Budget Head",
			fields=["name as value", "budget_head as label"],
			limit_page_length=500,
		)
		# If budget_head is empty, use name as label
		link_options["account_head"] = [
			{"value": r["value"], "label": r.get("label") or r["value"]} for r in account_heads
		]
	except Exception:
		link_options["account_head"] = []

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_project_data": related_project_data,
	}


@frappe.whitelist()
def get_user_details(user_email):
	"""
	Fetches details for a specific user to populate advance form fields.
	Returns the user document with resolved department name and employee class.
	"""
	from frappe import _
	
	if not user_email:
		frappe.throw(_("User Email is required."))
	
	try:
		user_email = str(user_email).strip('"').strip("'")
		user_doc = frappe.get_doc("User", user_email)
		user_dict = user_doc.as_dict()
		
		# Resolve department_name ID to actual department name from Department_prornd
		dept_link = user_dict.get("department_name")
		if dept_link:
			try:
				dept_doc = frappe.get_doc("Department_prornd", dept_link)
				user_dict["department_name"] = dept_doc.dept_name  # Replace ID with actual name
			except Exception:
				pass  # Keep original value if lookup fails
		
		# Resolve empclass ID to actual employee class name from EmployeeClass_prornd
		empclass_link = user_dict.get("empclass")
		if empclass_link:
			try:
				empclass_doc = frappe.get_doc("EmployeeClass_prornd", empclass_link)
				user_dict["empclass"] = empclass_doc.empclass_name  # Replace ID with actual name
			except Exception:
				pass  # Keep original value if lookup fails
		
		return user_dict
	except frappe.DoesNotExistError:
		return None
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching user details"))
		frappe.throw(_("An error occurred while fetching user details."))


@frappe.whitelist()
def save_temporary_advance(doc_data):
	"""
	Saves the Temporary Advance data from the form.
	"""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Temporary Advance:", data)  # Debug log

		# Determine if updating existing or creating new
		doc_name = data.pop("name", None)
		
		if doc_name:
			# Update existing document
			doc = frappe.get_doc("Temporary Advance", doc_name)
			doc.update(data)
		else:
			# Create new document
			doc = frappe.new_doc("Temporary Advance")
			
			# Field mapping
			field_mapping = [
				"appplying_for_select",
				"advance_for_id",
				"advance_for_department",
				"advance_for_designation",
				"applicant_webmail",
				"applicant_department",
				"applicant_designation",
				"bank_name",
				"account",
				"bank_account_number",
				"ifsc_code",
				"project_code",
				"project_name",
				"account_head",
				"amount",
				"justification",
				"documents",
				"comments",
			]

			# Update document with mapped data
			for field in field_mapping:
				if field in data and data[field] not in [None, ""]:
					doc.set(field, data[field])

		# Disable strict validation for flexibility
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True

		# Save the document
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved Temporary Advance: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Temporary Advance Save Error")
		frappe.throw(f"Failed to save Temporary Advance: {str(e)}")


@frappe.whitelist()
def get_temporary_advance_by_project(project_code: str = "", limit: int = 200, start: int = 0):
	"""
	Returns Temporary Advance docs for a given project_code.
	"""
	from frappe.utils import cint

	limit = int(cint(limit) or 200)
	start = int(cint(start) or 0)
	project_code = (project_code or "").strip()

	if not project_code:
		return {"message": []}

	results = []
	try:
		names = frappe.get_all(
			"Temporary Advance",
			filters={"project_code": project_code},
			fields=["name"],
			limit_start=start,
			limit_page_length=limit,
			order_by="modified desc",
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_temporary_advance_by_project: failed to query")
		return {"message": []}

	if not names:
		return {"message": []}

	for row in names:
		name = row.get("name")
		try:
			doc = frappe.get_doc("Temporary Advance", name)
			doc_dict = doc.as_dict()
			results.append(doc_dict)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"get_temporary_advance_by_project: error loading {name}")
			continue

	return {"message": results}


@frappe.whitelist()
def get_temporary_advance_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Temporary Advance", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	workflow_name = "Temp_adv_workflow"
	
	if not frappe.db.exists("Workflow", workflow_name):
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
def perform_temporary_advance_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Temporary Advance", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = "Temp_adv_workflow"
		
		if not frappe.db.exists("Workflow", workflow_name):
			frappe.throw(f"Workflow '{workflow_name}' not found.")

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		transition = None
		 
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				transition = t
				break
		
		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

		# Update workflow state
		doc.workflow_state = next_state
		
		# Check if next state requires submission (docstatus=1)
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
			"next_actions": get_temporary_advance_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Temporary Advance Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_temporary_advance(docname):
	"""
	Submit a Temporary Advance document using Workflow transitions.
	"""
	return perform_temporary_advance_action(docname, "Submit")
