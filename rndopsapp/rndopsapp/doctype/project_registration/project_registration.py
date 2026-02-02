# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import os
import json
import datetime
import frappe
from frappe import _
from frappe.utils import sanitize_html
from frappe.utils import flt, nowdate
from frappe.utils import flt
from frappe.utils.file_manager import save_file
import base64
import requests
from rndopsapp.rndopsapp.kafka.producer import publish_project_registration as publish_project




class ProjectRegistration(Document):
	pass


# ==============================================================================
# --- CORE SCRIPT-DRIVEN WORKFLOW ENGINE ---
# The following functions are the active engine for your new workflow.
# ==============================================================================


def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	
	Examples:
		"eval:doc.category=='Research'" -> "doc.category=='Research'"
		"eval:doc.category.includes('Consultancy')" -> "doc.category.includes('Consultancy')"
		None -> None
		"" -> None
	"""
	if not expression:
		return None
	
	expression = str(expression).strip()
	
	if expression.startswith("eval:"):
		return expression[5:].strip()  # Remove 'eval:' prefix
	
	return expression



@frappe.whitelist()
def submit_project_registration(docname):
	# Fetch the Project Registration document
	doc = frappe.get_doc("Project Registration", docname)

	# Convert to dict for reference
	data = doc.as_dict()
	# print(f"Implementation Department: {data.get('implementation_department')}")

	# --- Fetch linked Department_prornd document ---
	dept_doc = frappe.get_doc("Department_prornd", data.get("implementation_department"))
	# print(f"Department Name: {dept_doc.dept_name}")
	# print(f"Department Head: {dept_doc.dept_head}")

	# ✅ Update Project Registration fields from Department_prornd
	doc.department_head = dept_doc.dept_head
	doc.head_approver = dept_doc.dept_head  # You can change this logic if needed

	# Save the updated values before submission
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	# --- Workflow Handling Section ---
	if not doc.workflow_state:
		doc.workflow_state = "Draft"

	# Security: Only owner can submit draft
	# if doc.owner != frappe.session.user:
	# 	frappe.throw("Permission Denied: You are not the owner of this document.")

	if doc.docstatus != 0:
		frappe.throw("This document has already been submitted.")

	# --- Resolve workflow path based on EmployeeClass_prornd ---
	applicant_type_identifier = doc.applicant_type
	if not applicant_type_identifier:
		frappe.throw("Cannot submit: Applicant Type (Employee Class) is missing.")

	emp_class_doc_id = None
	if frappe.db.exists("EmployeeClass_prornd", applicant_type_identifier):
		emp_class_doc_id = applicant_type_identifier
	else:
		found_id = frappe.db.get_value(
			"EmployeeClass_prornd",
			{"empclass_name": applicant_type_identifier},
			"name",
		)
		if found_id:
			emp_class_doc_id = found_id

	if not emp_class_doc_id:
		frappe.throw(
			f"Invalid Applicant Type: Could not find an Employee Class matching '{applicant_type_identifier}'."
		)

	workflow_path = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path")
	if not workflow_path or not frappe.db.exists("Workflow", workflow_path):
		workflow_path = "pending_approval_prjReg"
		frappe.db.set_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path", workflow_path)
		frappe.db.commit()

	workflow_doc = frappe.get_doc("Workflow", workflow_path)
	current_state = doc.workflow_state

	# --- Find the next transition ---
	next_transition = None
	for t in workflow_doc.transitions:
		if t.state == current_state:
			next_transition = t
			break

	if not next_transition:
		frappe.throw(
			f"No transition found from current state '{current_state}' in workflow '{workflow_path}'."
		)

	next_state = next_transition.next_state

	# --- Optional Head Approval Handling ---
	if "Head Approval" in next_state and not doc.head_approver:
		frappe.throw("Cannot submit: The designated Department Head approver has not been determined.")

	# ✅ Update workflow and submit
	doc.workflow_state = next_state
	doc.submit()

	return {
		"workflow_state": doc.workflow_state,
		"department_head": doc.department_head,
		"head_approver": doc.head_approver,
	}



@frappe.whitelist()
def get_workflow_actions(docname):
	"""
	Return available workflow actions for the current user.
	"""
	doc = frappe.get_doc("Project Registration", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.get_value("Workflow", {"document_type": doc.doctype}, "name")

	if not workflow_name:
		return {"message": ["No workflow configured."]}

	workflow = frappe.get_doc("Workflow", workflow_name)

	# Get allowed roles for current state
	allowed_roles = []
	for state in workflow.states:
		if state.state == current_state:
			if isinstance(state.allow_edit, list):
				allowed_roles.extend(state.allow_edit)
			elif state.allow_edit:
				allowed_roles.append(state.allow_edit)
			break

	is_allowed = "System Manager" in user_roles or any(role in user_roles for role in allowed_roles)

	if not is_allowed:
		return {"message": ["🚫 You are not allowed to perform any workflow actions."]}

	valid_actions = []
	for t in workflow.transitions:
		if t.state == current_state:
			valid_actions.append(f"{t.action} → {t.next_state}")

	if not valid_actions:
		return {"message": ["⚠ No available workflow actions from current state."]}

	return {"message": valid_actions}


@frappe.whitelist()
def log_available_workflow_actions(docname):
	"""
	Logs available workflow actions for the current user using frappe.msgprint
	"""
	doc = frappe.get_doc("Project Registration", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.get_value("Workflow", {"document_type": doc.doctype}, "name")
	frappe.msgprint(f"Workflow Name: <b>{workflow_name}</b>")
	frappe.logger().info(f"Jimmy Logging Debug: {user_roles}")
	frappe.logger().warning(f"Jimmy Logging Debug (WARNING): {user_roles}")
	if not workflow_name:
		frappe.msgprint("No workflow is configured.")
		return

	workflow = frappe.get_doc("Workflow", workflow_name)

	# Log current state
	frappe.msgprint(f"Current Workflow State: <b>{current_state}</b>")

	# Get allowed roles for current state
	allowed_roles = []
	for state in workflow.states:
		if state.state == current_state:
			if isinstance(state.allow_edit, list):
				allowed_roles.extend(state.allow_edit)
			elif state.allow_edit:
				allowed_roles.append(state.allow_edit)
			break

	user_roles = frappe.get_roles(frappe.session.user)

	frappe.msgprint(f"Your roles: {user_roles}")
	frappe.msgprint(f"Roles allowed to act at this state: {allowed_roles}")

	is_allowed = "System Manager" in user_roles or any(role in user_roles for role in allowed_roles)

	if not is_allowed:
		frappe.msgprint("🚫 You are not allowed to perform any workflow actions.")
		return

	valid_actions = []
	for t in workflow.transitions:
		# Log all transitions for debugging
		frappe.logger().info(f"Transition: {t.state} --({t.action})--> {t.next_state}")
		frappe.msgprint("Available Transition:" + f"{t.state} --({t.action})--> {t.next_state}" )
		if t.state == current_state:  # or try t.current_state for older versions
			valid_actions.append(f"{t.action} → {t.next_state}")
			

	if valid_actions:
		frappe.msgprint("Available Workflow Actions:<br>" + "<br>".join(valid_actions))
		frappe.msgprint("Docname : " + docname)

	else:
		frappe.msgprint("⚠ No available workflow actions from current state.")


# /home/prornd/project/frappe_dev/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/project_registration/project_registration.py
@frappe.whitelist()
def handle_dynamic_workflow_action(doctype, docname, action, comment=None):
	doc = frappe.get_doc(doctype, docname)

	# --- FIX: Initialize workflow_state ---
	current_state = doc.workflow_state or "Draft"
	if not doc.workflow_state:
		doc.workflow_state = "Draft"
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		# Reload the document to get the latest timestamp and avoid conflicts
		doc = frappe.get_doc(doctype, docname)
		current_state = doc.workflow_state

	user = frappe.session.user
	user_roles = frappe.get_roles(user)

	# Step 1: Get workflow assigned to this DocType
	workflow_name = frappe.get_value("Workflow", {"document_type": doctype}, "name")
	if not workflow_name:
		frappe.throw(f"No workflow configured for DocType {doctype}.")

	workflow = frappe.get_doc("Workflow", workflow_name)

	# Step 2: Find valid transition
	transition = next(
		(
			t
			for t in workflow.get("transitions", [])
			if t.get("state") == current_state and t.get("action") == action
		),
		None,
	)

	if not transition:
		frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

	next_state = transition.get("next_state")

	# Step 3: Optional comment
	if comment:
		doc.add_comment("Comment", f"<strong>Action: {action}</strong><br>{sanitize_html(comment)}")

	# Step 4: Apply transition
	previous_state = doc.workflow_state  # Store current state for rollback
	
	if action.lower() == "reject":
		doc.cancel()

	if next_state and doc.docstatus != 2:
		doc.workflow_state = next_state
		
		# Check if the next state requires document submission
		# Find the state configuration in the workflow
		next_state_config = next(
			(s for s in workflow.get("states", []) if s.get("state") == next_state),
			None
		)
		
		# If the state requires doc_status = 1 (Submitted) and doc is currently draft
		if next_state_config and next_state_config.get("doc_status") == "1" and doc.docstatus == 0:
			doc.submit()
		else:
			# Skip mandatory validation for workflow transitions
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
	
	# --- Integration with External API (Kafka) ---
	if doc.workflow_state == "Approved" and doc.docstatus == 1:
		# print("doc inside: ", doc.as_dict())
		try:
			success = publish_project(doc)
			if success:
				frappe.msgprint(_(f"Workflow updated to: {doc.workflow_state}"), indicator="blue")
				frappe.msgprint(_("Project data synced successfully to external system."), indicator="green")
			else:
				# Reload document before rollback to avoid timestamp conflicts
				doc = frappe.get_doc(doctype, docname)
				doc.workflow_state = previous_state
				doc.flags.ignore_mandatory = True
				doc.save(ignore_permissions=True)
				frappe.msgprint(_("Kafka sync failed. Workflow state reverted to: ") + previous_state, indicator="red")
				frappe.log_error(f"Kafka sync failed for {docname}, rolled back workflow state", "Kafka Rollback")
		except Exception as e:
			# Reload document before rollback to avoid timestamp conflicts
			doc = frappe.get_doc(doctype, docname)
			doc.workflow_state = previous_state
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
			frappe.log_error(frappe.get_traceback(), f"Project Registration Kafka Sync Failed: {docname}")
			frappe.msgprint(_("Kafka sync failed. Workflow state reverted to: ") + previous_state, indicator="red")
	else:
		frappe.msgprint(_(f"Workflow updated to: {doc.workflow_state}"), indicator="blue")

	return doc.workflow_state


def send_project_registration_data_api(doc):
	"""
	Sends Project Registration data to the external API synchronously.
	"""
	try:
		# --- 1. Department Mapping ---
		department_id = None
		implemented_dept_centres = []

		# Helper to resolve dept_id from Department_prornd
		def get_dept_id(dept_link):
			if not dept_link:
				return None
			return frappe.db.get_value("Department_prornd", dept_link, "dept_id")

		# Check if implementation_department is a list (Child Table) or string (Link)
		imp_dept = doc.get("implementation_department")
		# print("implementation_department: ", imp_dept)
		
		if isinstance(imp_dept, list) and imp_dept:
			# Handle as Child Table
			for row in imp_dept:
				# Assuming the column in child table is 'department' or similar. 
				# If it's just a list of strings (unlikely for child table), handle that too.
				d_link = row.get("department") if isinstance(row, dict) or hasattr(row, "get") else row
				d_id = get_dept_id(d_link)
				# print("departmentId: ", d_id)
				if d_id:
					implemented_dept_centres.append({"departmentId": d_id})
			
			# Use the first one as the primary departmentId
			if implemented_dept_centres:
				department_id = implemented_dept_centres[0]["departmentId"]

		elif isinstance(imp_dept, str) and imp_dept:
			# Handle as Link Field (Fallback/Legacy)
			d_id = get_dept_id(imp_dept)
			if d_id:
				department_id = d_id
				implemented_dept_centres.append({"departmentId": d_id})

		# --- 2. Build Payload ---
		payload = {
			"projectNumber": doc.get("project_no") or doc.name,
			"empId": doc.get("pi_employee_id") or doc.get("emp_id"),
			"departmentId": department_id, # Can be None if not found
			"projectType": doc.get("project_type"),
			"projectCategory": doc.get("consultancy_category") or doc.get("category"), # Mapping 'consultancy_category' as likely candidate
			"projectTitle": sanitize_html(doc.get("project_title") or ""),
			"fundingAgencyType": doc.get("funding_agency_type"),
			"fundingAgencyId": 1, # Hardcoded in prompt example? Or need lookup? Prompt said "fundingAgencyId: 1". I'll use 1 or try to find a field.
			"projectScheme": doc.get("funding_agency_schemes") or "NRL-123", # Fallback from prompt
			"totalBudgetAmount": flt(doc.get("total_budget_amount") or doc.get("grand_total_proposal")),
			"overHeadAmountPercentage": flt(doc.get("overhead_percentage_research") or doc.get("overhead_percentage_consultancy")),
			"overHeadAmount": flt(doc.get("overhead_research") or doc.get("overhead_consultancy")),
			"budgetWithOverHeadAmount": flt(doc.get("budget_including_overhead_research") or doc.get("budget_including_overhead_consultancy")),
			"gst": flt(doc.get("service_tax_research") or doc.get("service_tax_consultancy")),
			"grandTotal": flt(doc.get("grand_total_research") or doc.get("grand_total_consultancy")),
			"durationInMonth": int(doc.get("project_duration_months") or 0),
			"durationInDays": int(doc.get("project_duration_days") or 0),
			"gstinNumber": "29ABCDE1234F1Z5", # Hardcoded in prompt example, or find field? Using example for now.
			"projectImplementationLocation": "Guwahati,Assam", # Hardcoded in prompt example
			"startDate": str(doc.get("start_date") or nowdate()), # Fallback to today if missing
			"completionDate": str(doc.get("completion_date") or nowdate()),
			"status": "Approved",
			"applyDate": str(doc.get("creation") or nowdate()).split(" ")[0],
			"verdictDate": str(nowdate()),
			"implementedDeptCentres": implemented_dept_centres
		}
		# print("payload: ", payload)
		# --- 3. Send Request ---
		url = "http://172.16.135.27:18080/api/projects"
		headers = {"Content-Type": "application/json"}
		
		# Log the attempt
		frappe.logger().info(f"Sending Project Registration {doc.name} to {url}")
		
		response = requests.post(url, json=payload, headers=headers, timeout=10)
		
		# --- 4. Handle Response ---
		doc.external_api_status = str(response.status_code)
		doc.external_api_response = response.text
		
		if response.status_code not in [200, 201]:
			frappe.log_error(f"API Error {response.status_code}: {response.text}", f"Project Registration Sync Error: {doc.name}")
		
		doc.save(ignore_permissions=True)
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"Project Registration API Exception: {doc.name}")
		# Update doc with error info
		try:
			doc.external_api_status = "Error"
			doc.external_api_response = str(e)
			doc.save(ignore_permissions=True)
			frappe.db.commit()
		except:
			pass
		# Re-raise to ensure calling function knows, or suppress if we want to avoid breaking the workflow?
		# User said "Retries once... logs errors...". Since it's sync, we probably shouldn't break the user's screen with a 500 if the external API is down, 
		# but we should let them know. The msgprint in the caller handles the warning.
		raise e


@frappe.whitelist()
def get_available_workflow_actions(docname):
	doc = frappe.get_doc("Project Registration", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.get_value("Workflow", {"document_type": doc.doctype}, "name")
	frappe.logger().warning(f"Jimmy Logging Debug workflow_name (WARNING): {workflow_name}")

	# if not workflow_name:
	# 	return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	frappe.logger().warning(f"Jimmy Logging Debug workflow (WARNING): {workflow}")

	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue

		# Check roles on the transition, not the state
		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]

		# User can perform action if they have allowed role
		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			allowed_actions.append(transition.action)

	# Remove duplicates
	allowed_actions = list(dict.fromkeys(allowed_actions))
	frappe.logger().warning(f"Jimmy Logging Debug allowed_actions (WARNING) final: {allowed_actions}")
	return allowed_actions


@frappe.whitelist()
def perform_workflow_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	doc = frappe.get_doc("Project Registration", docname)
	current_state = doc.workflow_state

	workflow_name = frappe.get_value("Workflow", {"document_type": doc.doctype}, "name")
	if not workflow_name:
		frappe.throw("Workflow not found.")

	workflow = frappe.get_doc("Workflow", workflow_name)

	# Find transition
	next_state = None
	for t in workflow.transitions:
		if t.state == current_state and t.action == action:
			next_state = t.next_state
			break

	if not next_state:
		frappe.throw(f"Invalid action '{action}' from state '{current_state}'.")

	# Update state and save
	if doc.docstatus != 2:  # not cancelled
		doc.workflow_state = next_state
		doc.save(ignore_permissions=True)

	return next_state



@frappe.whitelist()
def get_project_form_data(docname=None):
	"""
	Return a comprehensive dictionary containing all data needed to render the Project Registration form.
	This includes field definitions, options for Link/Select fields, and pre-fill data for the current user.
	If docname is provided, it also returns the document data and attached files.
	"""
	doctype_name = "Project Registration"

	try:
		# Fetch metadata of the "Project Registration" doctype
		meta = frappe.get_meta(doctype_name)

		# 1. Get Field Definitions (your existing logic, slightly refined)
		fields = []
		for field in meta.fields:
			# Skip non-input fields like Section Break, Button, etc.
			if field.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
				continue
			fields.append(
				{
					"fieldname": field.fieldname,
					"label": _(field.label),
					"fieldtype": field.fieldtype,
					"default": field.default,
					"mandatory": bool(field.reqd),
					"read_only": bool(field.read_only),
					"hidden": bool(field.hidden),
					"description": _(field.description) if field.description else None,
					"options": field.options,
					# Eval expressions for frontend conditional logic
					"depends_on": field.depends_on,
					"mandatory_depends_on": field.mandatory_depends_on,
					"read_only_depends_on": field.read_only_depends_on,
					# Extract eval expression for easier frontend parsing
					"depends_on_eval": extract_eval_expression(field.depends_on),
					"mandatory_depends_on_eval": extract_eval_expression(field.mandatory_depends_on),
					"read_only_depends_on_eval": extract_eval_expression(field.read_only_depends_on),
				}
			)

		# 2. Get Options for Link and Select Fields
		link_options = {}
		for field in fields:
			if field["fieldtype"] == "Link" and field["options"]:
				try:
					# Fetch 'name' and a common title field like 'title' or 'full_name'
					linked_doctype = field["options"]
					linked_meta = frappe.get_meta(linked_doctype)
					title_field = linked_meta.get_title_field()  # Best way to get the display field

					options_list = frappe.get_list(
						linked_doctype,
						fields=["name", title_field],
						limit_page_length=1000,  # Increase limit if you have many options
					)

					# Format for easy use in frontend: [{ value: '...', label: '...' }]
					link_options[field["fieldname"]] = [
						{"value": item["name"], "label": item.get(title_field, item["name"])}
						for item in options_list
					]
				except Exception as e:
					# If fetching fails, provide an empty list
					link_options[field["fieldname"]] = []

		# 3. Get Pre-fill data for the current user
		prefill_data = {}
		if frappe.session.user != "Guest":
			user_email = frappe.session.user
			user_doc = frappe.get_doc("User", user_email)

			# Pre-fill fields with user data from the "User" doctype
			prefill_data = {
				"pi_userid": user_email,
				"principal_investigator_name": user_doc.full_name,
				"pi_employee_id": user_doc.employee_id,  # Using employee_id field from the User doctype
				"designation": user_doc.designation_name,  # Using designation_name field from User doctype
				"applicant_department": user_doc.department_name,  # Using department_name field from User doctype
			}

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

		result = {
			"fields": fields,
			"link_options": link_options,
			"prefill_data": prefill_data,
			"client_scripts": client_scripts,
		}

		# 4. If docname is provided, fetch document data and files
		if docname:
			doc = frappe.get_doc(doctype_name, docname)
			
			# Check permissions
			if not doc.has_permission("read"):
				frappe.throw(_("You do not have permission to view this document."))

			result["doc_data"] = doc.as_dict()
			
			# Fetch attached files
			files = frappe.get_all(
				"File",
				filters={
					"attached_to_doctype": doctype_name,
					"attached_to_name": docname
				},
				fields=["name", "file_name", "file_url", "is_private", "creation"]
			)
			result["files"] = files

		return result

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching project form data"))
		return {"error": str(e)}


@frappe.whitelist()
def get_user_details_for_pi(user_email):
	"""
	Fetches details for a specific user to populate PI fields.
	"""
	if not user_email:
		frappe.throw(_("User Email is required."))
	try:
		user_doc = frappe.get_doc("User", user_email)
		# IMPORTANT: Replace these with your actual custom field names in the User doctype
		# user_dict = user_doc.as_dict()
		user_dept = user_doc.get("department_name")
		dept_doc = frappe.get_doc("Department_prornd", {"name": user_dept})

		dept_dict = dept_doc.as_dict()

		frappe.logger().warning(f"Jimmy Logging Debug Department_prornd (dept_id=1):{dept_dict['dept_name']}")
		data = {
			"principal_investigator_name": user_doc.full_name,
			"designation": user_doc.get("designation_name"),
			"applicant_department": dept_dict["dept_name"],
		}
		# frappe.logger().warning(f"Jimmy Logging Debug get_user_details_for_pi: {user_dict}")
		return data
	except frappe.DoesNotExistError:
		return None
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching user details"))
		frappe.throw(_("An error occurred while fetching user details."))


@frappe.whitelist()
def get_employee_list():
	"""
	Fetches a list of all active employees, formatted for use in a dropdown menu.

	:return: A list of dictionaries, each with 'value' and 'label' keys.
	"""
	try:
		employees = frappe.get_all(
			"Employee",
			filters={"status": "Active"},
			fields=["name", "employee_name"],  # Use the correct field for the employee's full name
			order_by="employee_name asc",
		)

		# Transform the list into a format that's easy for frontend dropdowns to consume
		# e.g., { value: "EMP/0001", label: "John Doe (EMP/0001)" }
		formatted_list = [
			{"value": emp.name, "label": f"{emp.employee_name} ({emp.name})"} for emp in employees
		]

		return formatted_list

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching employee list"))
		frappe.throw(_("An error occurred while fetching the employee list."))


@frappe.whitelist()
def get_funding_agency_details(agency_name):
	"""
	Fetches and returns the details for a single Funding Agency document.
	Triggered when a user selects an agency from the dropdown on the frontend.

	:param agency_name: The 'name' of the Funding Agency document to fetch.
	:return: A dictionary with the agency's details or None if not found.
	"""
	if not agency_name:
		frappe.throw(_("Funding Agency name is required."))

	# IMPORTANT: Verify 'Funding Agency' is the correct name of your Doctype.
	# In your previous code, it was 'fundingagency_', which might be a typo.
	# Use the real Doctype name here.
	doctype_name = "fundingagency_"

	try:
		# frappe.get_doc is perfect for fetching a single document's data
		agency_doc = frappe.get_doc(doctype_name, agency_name)

		# Return a dictionary with all the required fields
		return {
			"funding_agency_schemes": agency_doc.get("funding_agency_schemes"),
			"funding_agency_type": agency_doc.get("funding_agency_type"),
			"origin_of_funding_agency": agency_doc.get("origin_of_funding_agency"),
			"funding_agency_ministry": agency_doc.get("funding_agency_ministry"),
			"address_country": agency_doc.get("address_country"),
			"address_street_village_locality": agency_doc.get("address_street_village_locality"),
			"address_state": agency_doc.get("address_state"),
			"address_postal_code": agency_doc.get("address_postal_code"),
			"all": agency_doc,
		}

	except frappe.DoesNotExistError:
		# This is a safe failure if the agency doesn't exist for some reason
		return None
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching funding agency details"))
		frappe.throw(_("An error occurred while fetching details for the selected funding agency."))


@frappe.whitelist()
def save_project_data(doc, html_content=None):
	"""
	Receives a JSON object from the frontend, creates a new Project Registration document,
	handles child tables, and processes Base64 encoded file attachments.
	Optionally saves HTML content and converts it to PDF for endorsement.
	"""
	# print("$%$%$%$%$%$%$%$%$%$%$---------------------------$%$%$%$%$%$%$%$%$%$%$%4:")
	# print(doc)
	frappe.logger().warning(f"Jimmy Logging Debug save project data: {doc}")
	try:
		# The 'doc' argument from the frontend is a JSON string, so we parse it.
		# If the frontend sends an object directly, Frappe might auto-parse it.
		# This handles both cases.
		if isinstance(doc, str):
			form_data = json.loads(doc)
			frappe.logger().warning(f"Jimmy Logging Debug save project data form_data: {form_data}")

		else:
			form_data = doc
			frappe.logger().warning(f"Jimmy Logging Debug save project data doca: {form_data}")

		# Get the metadata for the Doctype to validate fields
		meta = frappe.get_meta("Project Registration")

		# Create a new document in memory
		new_project = frappe.new_doc("Project Registration")

		# Loop through the received data and set it on the new document
		for fieldname, value in form_data.items():
			# Security: Only process fields that actually exist in the DocType
			if not meta.has_field(fieldname):
				continue

			df = meta.get_field(fieldname)

			# Handle Child Tables (value is a list of row objects)
			if df.fieldtype == "Table" and isinstance(value, list):
				for child_row in value:
					new_project.append(fieldname, child_row)

			# Handle Attach fields (value is a Base64 data URI string)
			# Frappe's ORM automatically handles Base64 strings for Attach fields
			# during the .insert() call.
			elif df.fieldtype == "Attach" and value:
				# The value should include the filename for Frappe to process it correctly.
				# Format: { "file_name": "my_proposal.pdf", "file_data": "data:application/pdf;base64,..." }
				if isinstance(value, dict) and value.get("file_name") and value.get("file_data"):
					new_project.set(fieldname, value)
				else:
					# Handle cases where only the base64 string is sent (less ideal)
					new_project.set(fieldname, value)

			# Handle regular fields
			else:
				new_project.set(fieldname, value)

		# Set the owner to the currently logged-in user
		new_project.owner = frappe.session.user

		# Insert the document into the database. This is a single transaction.
		# It saves the main doc, child docs, and handles file attachments.
		new_project.insert(ignore_permissions=False, ignore_mandatory=True)

		# Commit the transaction
		frappe.db.commit()

		# --- Handle HTML content - Convert to PDF and save ---
		if html_content:
			try:
				from frappe.utils.pdf import get_pdf
				
				# Get the site path and create Endorsement folder if not exists
				site_path = frappe.get_site_path()
				endorsement_dir = os.path.join(site_path, "private", "files", "Endorsement")
				os.makedirs(endorsement_dir, exist_ok=True)
				
				# Save HTML file directly to filesystem
				html_filename = f"{new_project.name}.html"
				html_filepath = os.path.join(endorsement_dir, html_filename)
				with open(html_filepath, "w", encoding="utf-8") as f:
					f.write(html_content)
				
				# Create File record for HTML
				html_file_url = f"/private/files/Endorsement/{html_filename}"
				html_file_doc = frappe.new_doc("File")
				html_file_doc.file_name = html_filename
				html_file_doc.file_url = html_file_url
				html_file_doc.attached_to_doctype = new_project.doctype
				html_file_doc.attached_to_name = new_project.name
				html_file_doc.is_private = 1
				html_file_doc.save(ignore_permissions=True)
				frappe.db.commit()
				frappe.logger().info(f"HTML file saved: {html_filepath}")
				
				# Convert HTML to PDF and save directly to filesystem
				pdf_filename = f"{new_project.name}.pdf"
				pdf_filepath = os.path.join(endorsement_dir, pdf_filename)
				pdf_content = get_pdf(html_content)
				with open(pdf_filepath, "wb") as f:
					f.write(pdf_content)
				
				# Create File record for PDF
				pdf_file_url = f"/private/files/Endorsement/{pdf_filename}"
				pdf_file_doc = frappe.new_doc("File")
				pdf_file_doc.file_name = pdf_filename
				pdf_file_doc.file_url = pdf_file_url
				pdf_file_doc.attached_to_doctype = new_project.doctype
				pdf_file_doc.attached_to_name = new_project.name
				pdf_file_doc.is_private = 1
				pdf_file_doc.save(ignore_permissions=True)
				frappe.db.commit()
				
				frappe.logger().info(f"PDF file saved: {pdf_filepath}")
			except Exception as pdf_error:
				frappe.log_error(
					frappe.get_traceback(),
					f"save_project_data: PDF conversion/save error for {new_project.name}",
				)
				# Don't throw, just log the error so the main save succeeds

		# Return the name of the newly created document to the frontend
		return {
			"status": "success",
			"message": "Project Registration Successful",
			"docname": new_project.name,
		}

	except Exception as e:
		# If any error occurs, rollback the transaction and inform the user
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Registration Save Error")
		frappe.throw(_("An error occurred while saving the project. Please contact support."))


@frappe.whitelist()
def get_project_activity(docname):
	"""
	Fetches and combines the activity log and comments for a specific
	Project Registration document, sorted chronologically.

	Args:
	    docname (str): The name (ID) of the Project Registration document.

	Returns:
	    list: A list of dictionaries, where each dictionary represents either
	          an activity or a comment, sorted by timestamp in descending order.
	          e.g., [{'type': 'Comment', 'user': 'user@example.com', 'content': '...', 'timestamp': '...'},
	                 {'type': 'Activity', 'user': 'user@example.com', 'content': '...', 'timestamp': '...'}]
	"""
	if not docname:
		frappe.throw(_("Document name (docname) is required."))

	try:
		# This automatically checks for document existence and user permissions
		doc = frappe.get_doc("Project Registration", docname)

		# Fetch activity logs (version history, workflow changes, etc.)
		activities = doc.get_activity()

		# Fetch user-added comments
		comments = doc.get_comments()

		combined_feed = []

		# Format and add activities to the feed
		for item in activities:
			combined_feed.append(
				{
					"type": "Activity",
					"user": item.get("owner"),
					"content": item.get("subject"),  # The 'subject' usually contains the activity description
					"timestamp": item.get("creation"),
				}
			)

		# Format and add comments to the feed
		for comment in comments:
			combined_feed.append(
				{
					"type": "Comment",
					"user": comment.get("comment_by"),
					"content": comment.get("content"),
					"timestamp": comment.get("creation"),
				}
			)

		# Sort the combined feed by timestamp, with the newest items first
		sorted_feed = sorted(combined_feed, key=lambda x: x["timestamp"], reverse=True)

		return sorted_feed

	except frappe.DoesNotExistError:
		frappe.throw(_("Project Registration document not found."), title="Not Found")
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error fetching project activity")
		frappe.throw(_("An error occurred while fetching project activity and comments."))




# -=-=-=-=- validation



def _format_phone_number(phone_string):
	"""
	Helper function to format a phone number string.
	Returns a formatted number or the original string if invalid.
	"""
	raw_phone = str(phone_string or "").strip()

	# Case 1: Already correctly formatted as +91-xxxxxxxxxx OR starts with +
	if raw_phone.startswith("+"):
		return raw_phone

	# Case 2: Raw 10-digit number that needs formatting
	if raw_phone.isdigit() and len(raw_phone) == 10:
		return f"+91-{raw_phone}"

	# Case 3: Invalid or empty. Return None to skip phone validation during draft save.
	return None



@frappe.whitelist()
def save_project_draft(doc_data, html_content=None, files=None):
	"""
	Saves or updates a Project Registration document as a draft (docstatus=0).
	Optionally receives HTML content and saves it as {doc.name}.html file.
	
	Args:
		doc_data: The document data as JSON string or dictionary
		html_content: Optional HTML content to save as a file
		files: Optional list of files to attach (if sent as separate argument)
	"""
	print("$%$%$%$%$%$%$%$%$%$%$---------------------------$%$%$%$%$%$%$%$%$%$%$%4:")
	
	# --- FIX START: Convert JSON string to Python Dictionary ---
	if isinstance(doc_data, str):
		data = frappe.parse_json(doc_data)
	else:
		data = doc_data or {}
	# --- FIX END ---

	# Now 'data' is a dictionary
	frappe.logger().warning(f"Jimmy Logging Debug save project data keys: {list(data.keys())}")
	
	if data.get("implementation_department"):
		# --- Fetch linked Department_prornd document ---
		dept_doc = frappe.get_doc("Department_prornd", data.get("implementation_department"))
		implementation_department = dept_doc.dept_name
		implementation_department_head = dept_doc.dept_head
		implementation_department_id = dept_doc.dept_id
		# print(f"Department Name: {dept_doc.dept_name}")
		# print(f"Department Head: {dept_doc.dept_head}")
		# print(f"Department ID: {dept_doc.dept_id}")
	else:
		print("No Implementation Department found in data")

	try:
		# Extract files payload - check argument first, then doc_data
		files_payload = files
		if not files_payload:
			files_payload = data.pop("files", None)
			
		if isinstance(files_payload, str):
			try:
				files_payload = json.loads(files_payload)
			except Exception:
				pass
		frappe.logger().warning(f"Jimmy Logging Debug files_payload count: {len(files_payload) if files_payload else 0}")
		if files_payload:
			frappe.logger().warning(f"Jimmy Logging Debug first file: {files_payload[0] if len(files_payload) > 0 else 'None'}")

		docname = data.get("name")

		if docname:
			doc = frappe.get_doc("Project Registration", docname)
			if doc.owner != frappe.session.user:
				frappe.throw(_("You do not have permission to edit this draft."))
			if doc.docstatus != 0:
				frappe.throw(_("Cannot save draft. The project has already been submitted."))
		else:
			doc = frappe.new_doc("Project Registration")

		child_tables_map = {
			"additional_pi_table",
			"co_investigator_table",
			"proposed_budget_breakup",
			"proposed_equipment_details",
			"proposed_manpower_details",
			"sanctioned_budget_breakup",
			"sanction_related_files",
			"fund_transactions",
		}
		parent_data = {k: v for k, v in data.items() if k not in child_tables_map}

		# --- Sanitize Parent Data ---
		for key, value in parent_data.items():
			if isinstance(value, dict):
				parent_data[key] = value.get("value") or value.get("name") or None

		if "pi_contact" in parent_data:
			parent_data["pi_contact"] = _format_phone_number(parent_data.get("pi_contact"))
		if "copi_contact" in parent_data:
			parent_data["copi_contact"] = _format_phone_number(parent_data.get("copi_contact"))

		doc.update(parent_data)

		implementation_dept = data.get("applicant_department")
		if not implementation_dept and data.get("pi_webmail"):
			try:
				pi_user = frappe.get_doc("User", data.get("pi_webmail"))
				if pi_user.get("department"):
					doc.implementation_department = pi_user.get("department")
			except frappe.DoesNotExistError:
				frappe.log_error(f"User {data.get('pi_webmail')} not found.", "Project Draft Save")

		# --- Process child tables ---
		for table_fieldname in child_tables_map:
			doc.set(table_fieldname, [])
			child_rows_data = data.get(table_fieldname)

			if not isinstance(child_rows_data, list):
				continue

			for row_data in child_rows_data:
				update_data = row_data.copy() if isinstance(row_data, dict) else {}
				frappe.logger().warning(
					f"Jimmy update_data Logging Debug save project doc_data: {update_data}"
				)

				if table_fieldname == "additional_pi_table" and "pi_contact" in update_data:
					formatted = _format_phone_number(update_data.get("pi_contact"))
					update_data["pi_contact"] = formatted
					update_data["contact_no"] = formatted

				elif table_fieldname == "co_investigator_table" and "copi_contact" in update_data:
					formatted = _format_phone_number(update_data.get("copi_contact"))
					update_data["copi_contact"] = formatted
					update_data["contact_no"] = formatted

				elif table_fieldname == "proposed_budget_breakup":
					# Map head -> budget_head if needed
					if "head" in update_data:
						update_data["account_head"] = update_data.pop("head")
						# Log the update_data for debugging
						# Log the update_data as a warning
					# frappe.logger("budget_update").warning(f"Updated proposed_budget_breakup data: {update_data}")

					# Sanitize budget_head if frontend sends object
					if isinstance(update_data.get("account_head"), dict):
						bh = update_data.get("account_head")
						update_data["account_head"] = bh.get("value") or bh.get("name") or None

					# Handle year budgets
					years_array = update_data.pop("years", []) or []
					year_fields = [
						"first_year_budget",
						"second_year_budget",
						"third_year_budget",
						"fourth_year_budget",
						"fifth_year_budget",
					]
					for i, amount in enumerate(years_array):
						if i < len(year_fields):
							update_data[year_fields[i]] = flt(amount)
				# frappe.logger("budget_update").warning(f"Updated proposed_budget_breakup data: {update_data}")

				child = doc.append(table_fieldname, {})
				child.update(update_data)

				# Sanitize phone fields AFTER update to handle fetch_from values
				if table_fieldname == "additional_pi_table":
					child.pi_contact = _format_phone_number(child.pi_contact)
				elif table_fieldname == "co_investigator_table":
					child.copi_contact = _format_phone_number(child.copi_contact)

		# --- Server-side budget calculations ---
		grand_total = 0
		if doc.proposed_budget_breakup:
			year_fields = [
				"first_year_budget",
				"second_year_budget",
				"third_year_budget",
				"fourth_year_budget",
				"fifth_year_budget",
			]
			for row in doc.proposed_budget_breakup:
				row_total = sum(flt(getattr(row, field, 0)) for field in year_fields)
				row.total_proposal_of_heads = row_total
				grand_total += row_total
		doc.grand_total_proposal = grand_total
		doc.total_budget_amount = grand_total

		if not doc.workflow_state:
			doc.workflow_state = "Draft"

		# --- CRITICAL: Sanitize ALL phone fields across ALL child tables before save ---
		# This catches values from fetch_from, frontend, or any other source
		for child in doc.get("additional_pi_table") or []:
			child.pi_contact = _format_phone_number(child.pi_contact)
		for child in doc.get("co_investigator_table") or []:
			child.copi_contact = _format_phone_number(child.copi_contact)

		# Use flags to ignore mandatory fields and validation during save
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True)

		# --- Handle files payload ---
		if files_payload and isinstance(files_payload, list):
			for f in files_payload:
				try:
					filename = f.get("filename") or f.get("file_name") or f.get("name")
					content_b64 = f.get("content") or f.get("file_data") or f.get("data") or ""
					is_private = int(f.get("is_private") or 1)

					if not (filename and content_b64):
						continue

					# Strip data URI prefix if present
					if content_b64.startswith("data:"):
						content_b64 = content_b64.split(",", 1)[1]

					# Decode base64 content
					file_content = base64.b64decode(content_b64)

					# Use save_file utility to properly save file to disk and create File record
					file_doc = save_file(
						fname=filename,
						content=file_content,
						dt=doc.doctype,
						dn=doc.name,
						is_private=is_private,
						decode=False  # Already decoded above
					)
					
					frappe.logger().info(f"File saved successfully: {filename} -> {file_doc.file_url}")

				except Exception as fe:
						frappe.log_error(
							frappe.get_traceback(),
							f"save_project_draft: file upload error for {f.get('filename')}",
						)
						continue

		frappe.db.commit()

		# --- Handle HTML content - Convert to PDF and save ---
		if html_content:
			# print(f"DEBUG: html_content received, length={len(html_content)}")
			try:
				import os
				from frappe.utils.pdf import get_pdf
				
				# Get the site path and create Endorsement folder if not exists
				site_path = frappe.get_site_path()
				endorsement_dir = os.path.join(site_path, "private", "files", "Endorsement")
				os.makedirs(endorsement_dir, exist_ok=True)
				print(f"DEBUG: endorsement_dir={endorsement_dir}")
				
				# Save HTML file directly to filesystem
				html_filename = f"{doc.name}.html"
				html_filepath = os.path.join(endorsement_dir, html_filename)
				with open(html_filepath, "w", encoding="utf-8") as f:
					f.write(html_content)
				print(f"DEBUG: HTML file written to {html_filepath}")
				
				# Create File record for HTML
				html_file_url = f"/private/files/Endorsement/{html_filename}"
				html_file_doc = frappe.new_doc("File")
				html_file_doc.file_name = html_filename
				html_file_doc.file_url = html_file_url
				html_file_doc.attached_to_doctype = doc.doctype
				html_file_doc.attached_to_name = doc.name
				html_file_doc.is_private = 1
				html_file_doc.save(ignore_permissions=True)
				frappe.db.commit()
				frappe.logger().info(f"HTML file saved: {html_filepath}")
				# print(f"DEBUG: HTML File record created: {html_file_doc.name}")
				
				# Convert HTML to PDF and save directly to filesystem
				pdf_filename = f"{doc.name}.pdf"
				pdf_filepath = os.path.join(endorsement_dir, pdf_filename)
				pdf_content = get_pdf(html_content)
				with open(pdf_filepath, "wb") as f:
					f.write(pdf_content)
				# print(f"DEBUG: PDF file written to {pdf_filepath}")
				
				# Create File record for PDF
				pdf_file_url = f"/private/files/Endorsement/{pdf_filename}"
				pdf_file_doc = frappe.new_doc("File")
				pdf_file_doc.file_name = pdf_filename
				pdf_file_doc.file_url = pdf_file_url
				pdf_file_doc.attached_to_doctype = doc.doctype
				pdf_file_doc.attached_to_name = doc.name
				pdf_file_doc.is_private = 1
				pdf_file_doc.save(ignore_permissions=True)
				frappe.db.commit()
				
				frappe.logger().info(f"PDF file saved: {pdf_filepath}")
				print(f"DEBUG: PDF File record created: {pdf_file_doc.name}")
			except Exception as pdf_error:
				print(f"DEBUG ERROR: PDF conversion/save error: {str(pdf_error)}")
				frappe.log_error(
					frappe.get_traceback(),
					f"save_project_draft: PDF conversion/save error for {doc.name}",
				)
				# Don't throw, just log the error so the main save succeeds
		else:
			print("DEBUG: html_content is empty or None")

		return {"docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Draft Save Error")
		frappe.throw(_("An error occurred while saving the draft: {0}").format(str(e)))


@frappe.whitelist()
def view_endorsement_file(docname):
	"""
	View the endorsement files (PDF and HTML) for a Project Registration document.
	Returns file URLs and HTML content for rendering in the browser.
	
	Args:
		docname: The name of the Project Registration document
		
	Returns:
		dict: Contains file URLs and HTML content if available
	"""
	if not docname:
		frappe.throw(_("Document name is required."))
	
	try:
		# Check if user has permission to view the document
		doc = frappe.get_doc("Project Registration", docname)
		
		result = {
			"pdf_file_url": None,
			"html_file_url": None,
			"html_content": None
		}
		
		# Search for PDF file (first try Endorsement folder, then fallback)
		pdf_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Project Registration",
				"attached_to_name": docname,
				"file_url": ["like", f"%/Endorsement/{docname}.pdf"]
			},
			fields=["name", "file_name", "file_url"],
			order_by="creation desc",
			limit=1
		)
		
		# Fallback for PDF
		if not pdf_files:
			pdf_files = frappe.get_all(
				"File",
				filters={
					"attached_to_doctype": "Project Registration",
					"attached_to_name": docname,
					"file_name": ["like", "%.pdf"]
				},
				fields=["name", "file_name", "file_url"],
				order_by="creation desc",
				limit=1
			)
		
		if pdf_files:
			result["pdf_file_url"] = pdf_files[0].get("file_url")
		
		# Search for HTML file (first try Endorsement folder, then fallback)
		html_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Project Registration",
				"attached_to_name": docname,
				"file_url": ["like", f"%/Endorsement/{docname}.html"]
			},
			fields=["name", "file_url"],
			order_by="creation desc",
			limit=1
		)
		
		# Fallback for HTML
		if not html_files:
			html_files = frappe.get_all(
				"File",
				filters={
					"attached_to_doctype": "Project Registration",
					"attached_to_name": docname,
					"file_name": ["like", "%.html"]
				},
				fields=["name", "file_url"],
				order_by="creation desc",
				limit=1
			)
		
		if html_files:
			result["html_file_url"] = html_files[0].get("file_url")
			# Also read and return HTML content for inline viewing
			try:
				file_doc = frappe.get_doc("File", html_files[0].name)
				file_path = file_doc.get_full_path()
				with open(file_path, "r", encoding="utf-8") as f:
					result["html_content"] = f.read()
			except Exception:
				pass
		
		return result
		
	except frappe.DoesNotExistError:
		frappe.throw(_("Project Registration document not found."), title="Not Found")
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error viewing endorsement file")
		frappe.throw(_("An error occurred while viewing endorsement file: {0}").format(str(e)))


@frappe.whitelist()
def download_endorsement_file(docname, file_type="pdf"):
	"""
	Download the endorsement file (PDF or HTML) for a Project Registration document.
	
	Args:
		docname: The name of the Project Registration document
		file_type: Either 'pdf' or 'html' (default: 'pdf')
		
	Returns:
		File download response
	"""
	if not docname:
		frappe.throw(_("Document name is required."))
	
	if file_type not in ["pdf", "html"]:
		frappe.throw(_("Invalid file type. Use 'pdf' or 'html'."))
	
	try:
		# Check if user has permission to view the document
		doc = frappe.get_doc("Project Registration", docname)
		
		# First try to find file in Endorsement folder (new pattern)
		files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Project Registration",
				"attached_to_name": docname,
				"file_url": ["like", f"%/Endorsement/{docname}.{file_type}"]
			},
			fields=["name", "file_url"],
			order_by="creation desc",
			limit=1
		)
		
		# Fallback: search for any file with matching extension attached to the document
		if not files:
			files = frappe.get_all(
				"File",
				filters={
					"attached_to_doctype": "Project Registration",
					"attached_to_name": docname,
					"file_name": ["like", f"%.{file_type}"]
				},
				fields=["name", "file_url"],
				order_by="creation desc",
				limit=1
			)
		
		if not files:
			frappe.throw(_("No endorsement {0} file found for this document.").format(file_type.upper()))
		
		file_doc = frappe.get_doc("File", files[0].name)
		file_path = file_doc.get_full_path()
		
		with open(file_path, "rb") as f:
			file_content = f.read()
		
		frappe.local.response.filename = f"{docname}.{file_type}"
		frappe.local.response.filecontent = file_content
		frappe.local.response.type = "download"
		
	except frappe.DoesNotExistError:
		frappe.throw(_("Project Registration document or file not found."), title="Not Found")
	except FileNotFoundError:
		frappe.throw(_("The file could not be found on the server."))
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error downloading endorsement file")
		frappe.throw(_("An error occurred while downloading the file: {0}").format(str(e)))

