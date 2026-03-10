# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import os
import json
import datetime
import frappe
from frappe import _


class ProjectRegistration(Document):
	pass


# THIS IS THE NEW, CUSTOM API ENDPOINT
# ------------------------------------
@frappe.whitelist()
def get_workflow_states_for_docs(doc_names):
	"""
	A custom API endpoint to reliably fetch the workflow_state for a given
	list of document names.

	Args:
	    doc_names (list): A list of strings, where each string is the name
	                      of a Project Registration document.

	Returns:
	    A list of dictionaries, e.g., [{'name': 'DOC-001', 'workflow_state': 'Approved'}]
	"""
	if not doc_names:
		return []

	# Use frappe.get_all to efficiently query the database for only the fields we need.
	# This is very fast and secure.
	states = frappe.get_all(
		"Project Registration", filters={"name": ("in", doc_names)}, fields=["name", "workflow_state"]
	)

	return states


# import frappe
# from frappe import _

# @frappe.whitelist()
# def handle_action(docname, action):
#     doc = frappe.get_doc("Project Registration", docname)

#     # Check if current user is the designated head approver
#     if frappe.session.user != doc.head_approver:
#         frappe.throw(_("You are not authorized to perform this action. Only {0} can approve/reject.")
#                      .format(doc.head_approver))

#     if action == "Approve":
#         doc.workflow_state = "Approved"
#     elif action == "Reject":
#         doc.workflow_state = "Rejected"
#     elif action == "Cancel":
#         doc.workflow_state = "Cancelled"
#     else:
#         frappe.throw(_("Invalid action"))

#     doc.save()
#     frappe.db.commit()
#     return {"status": "success", "message": f"{action} completed by {frappe.session.user}"}





# def save_doc_as_text_file(doc):
#     """
#     Save a Frappe document as a plain text file inside the private files directory,
#     and log the saved content.

#     Args:
#         doc (Document): Frappe document instance.

#     Returns:
#         dict: Contains file system path and accessible URL.
#     """
#     doc_dict = doc.as_dict()
#     doc_str = ""

#     for key, value in doc_dict.items():
#         doc_str += f"{key}: {value}\n"

#     # Define file name and path
#     file_name = f"{doc.name}.txt"
#     file_path = os.path.join(frappe.get_site_path("private", "files"), file_name)

#     # Write string to file
#     with open(file_path, "w", encoding="utf-8") as f:
#         f.write(doc_str)

#     # Log the saved content (using frappe logger)
#     logger = frappe.logger("project_registration")  # you can name your logger as you want
#     logger.info(f"Saved Project Registration document as text file: {file_name}")
#     logger.info(f"Content:\n{doc_str}")

#     return {
#         "file_path": file_path,
#         "file_url": f"/private/files/{file_name}"
#     }


def save_doc_as_text_file(doc):
	"""
	Save a Frappe document as a plain text file inside the private files directory,
	and log the saved content.

	Args:
	    doc (Document): Frappe document instance.

	Returns:
	    dict: Contains file system path and accessible URL.
	"""
	doc_dict = doc.as_dict()

	def default_serializer(o):
		if isinstance(o, (datetime.datetime, datetime.date)):
			return o.isoformat()
		# Add other type handlers if needed
		return str(o)

	doc_str = json.dumps(doc_dict, indent=4, ensure_ascii=False, default=default_serializer)

	# Define file name and path
	file_name = f"{doc.name}.txt"
	file_path = os.path.join(frappe.get_site_path("private", "files"), file_name)

	# Write string to file
	with open(file_path, "w", encoding="utf-8") as f:
		f.write(doc_str)

	# Log the saved content (using frappe logger)
	logger = frappe.logger("project_registration")
	logger.info(f"Saved Project Registration document as text file: {file_name}")
	logger.info(f"Content:\n{doc_str}")

	return {"file_path": file_path, "file_url": f"/private/files/{file_name}"}


@frappe.whitelist()
def handle_action(docname, action):
	doc = frappe.get_doc("Project Registration", docname)

	# Check if current user is the designated head approver
	if frappe.session.user != doc.head_approver:
		frappe.throw(
			_("You are not authorized to perform this action. Only {0} can approve/reject.").format(
				doc.head_approver
			)
		)

	if action == "Approve":
		if doc.workflow_state == "Pending HoD Approval":
			doc.workflow_state = "Pending Staff Approval"
		else:
			doc.workflow_state = "Approved"
	elif action == "Reject":
		doc.workflow_state = "Rejected"
	elif action == "Cancel":
		doc.workflow_state = "Cancelled"
	else:
		frappe.throw(_("Invalid action"))

	doc.save()
	frappe.db.commit()
	return {"status": "success", "message": f"{action} completed by {frappe.session.user}"}


# @frappe.whitelist()
# def log_available_workflow_actions(docname):
#     """
#     Logs available workflow actions for the current user using frappe.msgprint
#     """
#     doc = frappe.get_doc("Project Registration", docname)
#     current_state = doc.workflow_state
#     user_roles = frappe.get_roles(frappe.session.user)

#     workflow_name = frappe.get_value("Workflow", {"document_type": doc.doctype}, "name")
#     frappe.msgprint(f"workflow_name: {workflow_name}")
#     if not workflow_name:
#         frappe.msgprint("No workflow is configured.")
#         return

#     workflow = frappe.get_doc("Workflow", workflow_name)
#     frappe.msgprint(f"workflow: {workflow.states}")
#     a =  [ "HoD (Head of Department)", "head_department_center_school", "HoC (Head of Center)", "HoS (Head of School)", "head_approver_1", "Senior Staff", "All_ProRnd_User", "All", "Guest", "Desk User" ]
#     # Get allowed roles for the current state
#     allowed_roles = []
#     for state in workflow.states:
#         if state.state == current_state:
#             if isinstance(state.allow_edit, list):
#                 allowed_roles.extend(state.allow_edit)
#             elif state.allow_edit:
#                 allowed_roles.append(state.allow_edit)
#             break
#     frappe.msgprint(f"You are not allowed to perform any workflow actions. {a}")
#     is_allowed = (
#         "System Manager" in user_roles or
#         any(role in user_roles for role in allowed_roles)
#     )

#     if not is_allowed:
#         frappe.msgprint(f"You are not allowed to perform any workflow actions. {allowed_roles}")
#         return

#     valid_actions = []
#     for t in workflow.transitions:
#         if t.state == current_state:  # ✅ FIXED: use t.state instead of t.current_state
#             valid_actions.append(f"{t.action} → {t.next_state}")

#     if valid_actions:
#         frappe.msgprint("Available Workflow Actions:<br>" + "<br>".join(valid_actions))
#     else:
#         frappe.msgprint("No available workflow actions.")


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
		if t.state == current_state:  # or try t.current_state for older versions
			valid_actions.append(f"{t.action} → {t.next_state}")

	if valid_actions:
		frappe.msgprint("✅ Available Workflow Actions:<br>" + "<br>".join(valid_actions))
		frappe.msgprint("Docname : " + docname)

	else:
		frappe.msgprint("⚠ No available workflow actions from current state.")


import os


# @frappe.whitelist()
# def handle_dynamic_workflow_action(doctype, docname, action, comment=None):
# 	"""
# 	Handle workflow actions dynamically using Frappe's Workflow system.
# 	"""
# 	doc = frappe.get_doc(doctype, docname)
# 	file_info = save_doc_as_text_file(doc)
# 	current_state = doc.workflow_state
# 	user = frappe.session.user
# 	user_roles = frappe.get_roles(user)
# 	d = save_doc_as_text_file(doc)

# 	# Step 1: Get workflow assigned to this DocType
# 	workflow_name = frappe.get_value("Workflow", {"document_type": doctype}, "name")
# 	if not workflow_name:
# 		frappe.throw(f"No workflow configured for DocType {doctype}.")

# 	workflow = frappe.get_doc("Workflow", workflow_name)

# 	# Step 2: Find valid transition
# 	transition = next(
# 		(
# 			t
# 			for t in workflow.get("transitions", [])
# 			if t.get("state") == current_state and t.get("action") == action
# 		),
# 		None,
# 	)

# 	if not transition:
# 		frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

# 	next_state = transition.get("next_state")

# 	# Step 3: Check permission
# 	allowed_roles = []
# 	for state in workflow.get("states", []):
# 		if state.get("state") == current_state:
# 			roles = state.get("allow_edit")
# 			if isinstance(roles, list):
# 				allowed_roles.extend(roles)
# 			else:
# 				allowed_roles.append(roles)

# 	# if not any(role in user_roles for role in allowed_roles) and "System Manager" not in user_roles:
# 	#     frappe.throw("You are not allowed to perform this action.")

# 	# Step 4: Optional comment
# 	if comment:
# 		doc.add_comment("Comment", f"<strong>Action: {action}</strong><br>{sanitize_html(comment)}")

# 	# Step 5: Apply transition
# 	if action.lower() == "reject":
# 		doc.cancel()

# 	if next_state and doc.docstatus != 2:
# 		doc.workflow_state = next_state
# 		doc.save(ignore_permissions=True)

# 	frappe.msgprint(f"lolsad: {docname}")

# 	return doc.workflow_state


# new


@frappe.whitelist()
def handle_dynamic_workflow_action(doctype, docname, action, comment=None):
	doc = frappe.get_doc(doctype, docname)

	# --- FIX: Initialize workflow_state ---
	current_state = doc.workflow_state or "Draft"
	if not doc.workflow_state:
		doc.workflow_state = "Draft"
		doc.save(ignore_permissions=True)

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
	if action.lower() == "reject":
		doc.cancel()

	if next_state and doc.docstatus != 2:
		doc.workflow_state = next_state
		doc.save(ignore_permissions=True)

	frappe.msgprint(f"Workflow updated for: {docname}")
	return doc.workflow_state


# ori
# @frappe.whitelist()
# def get_available_workflow_actions(docname):
# 	"""
# 	Returns available workflow actions for the current user for a given document.
# 	"""
# 	doc = frappe.get_doc("Project Registration", docname)
# 	current_state = doc.workflow_state or "Draft"
# 	# frappe.msgprint(f"current_state: {docname}")
# 	user_roles = frappe.get_roles(frappe.session.user)

# 	workflow_name = frappe.get_value("Workflow", {"document_type": doc.doctype}, "name")
# 	if not workflow_name:
# 		return []

# 	workflow = frappe.get_doc("Workflow", workflow_name)

# 	allowed_actions = []
# 	for transition in workflow.get("transitions", []):
# 		if transition.get("state") != current_state:
# 			continue

# 		action = transition.get("action")

# 		# Find allowed roles from the state
# 		allowed_roles = []
# 		for state in workflow.get("states", []):
# 			if state.get("state") == current_state:
# 				roles = state.get("allow_edit")
# 				if isinstance(roles, list):
# 					allowed_roles.extend(roles)
# 				else:
# 					allowed_roles.append(roles)

# 		# Check if current user has one of the roles
# 		if any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles:
# 			allowed_actions.append(action)

# 	return allowed_actions


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


# @frappe.whitelist(allow_guest=True)
# def get_doctype_fields(doctype_name):
# 	"""
# 	Return a list of field definitions for a given DocType,
# 	suitable for dynamically building forms or UI components.
# 	"""
# 	try:
# 		# Fetch the metadata for the specified doctype
# 		meta = frappe.get_meta(doctype_name)
# 		field_data = []

# 		for field in meta.fields:
# 			# Skip fields that are typically not displayed on a form
# 			if field.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button"]:
# 				continue

# 			field_details = {
# 				"fieldname": field.fieldname,
# 				"label": _(field.label),  # Use translation for labels
# 				"fieldtype": field.fieldtype,
# 				"default": field.default,
# 				"mandatory": bool(field.reqd),
# 				"read_only": bool(field.read_only),
# 				"hidden": bool(field.hidden),
# 				"description": _(field.description) if field.description else None,
# 				"options": field.options,
# 				"depends_on": field.depends_on,
# 				"fetch_from": field.fetch_from,
# 			}

# 			field_data.append(field_details)

# 		return {"doctype": doctype_name, "fields": field_data}

# 	except frappe.DoesNotExistError:
# 		frappe.log_error(f"DocType '{doctype_name}' not found.", _("API Error"))
# 		return {"error": f"DocType '{doctype_name}' not found."}
# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), _("Error fetching doctype fields"))
# 		return {"error": str(e)}


# In your project_registration.py file

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-= working -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
# @frappe.whitelist()  # allow_guest=True is not recommended if you need pre-fill data for a logged-in user
# def get_project_form_data():
# 	"""
# 	Return a comprehensive dictionary containing all data needed to render the Project Registration form.
# 	This includes field definitions, options for Link/Select fields, and pre-fill data for the current user.
# 	"""
# 	doctype_name = "Project Registration"

# 	try:
# 		meta = frappe.get_meta(doctype_name)

# 		# 1. Get Field Definitions (your existing logic, slightly refined)
# 		fields = []
# 		for field in meta.fields:
# 			if field.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
# 				continue
# 			fields.append(
# 				{
# 					"fieldname": field.fieldname,
# 					"label": _(field.label),
# 					"fieldtype": field.fieldtype,
# 					"default": field.default,
# 					"mandatory": bool(field.reqd),
# 					"read_only": bool(field.read_only),
# 					"hidden": bool(field.hidden),
# 					"description": _(field.description) if field.description else None,
# 					"options": field.options,
# 				}
# 			)

# 		# 2. Get Options for Link and Select Fields
# 		link_options = {}
# 		for field in fields:
# 			if field["fieldtype"] == "Link" and field["options"]:
# 				try:
# 					# Fetch 'name' and a common title field like 'title' or 'full_name'
# 					# The 'title' field might not always exist, so we fall back to 'name'
# 					linked_doctype = field["options"]
# 					linked_meta = frappe.get_meta(linked_doctype)
# 					title_field = linked_meta.get_title_field()  # Best way to get the display field

# 					options_list = frappe.get_list(
# 						linked_doctype,
# 						fields=["name", title_field],
# 						limit_page_length=1000,  # Increase limit if you have many options
# 					)

# 					# Format for easy use in frontend: [{ value: '...', label: '...' }]
# 					link_options[field["fieldname"]] = [
# 						{"value": item["name"], "label": item.get(title_field, item["name"])}
# 						for item in options_list
# 					]
# 				except Exception:
# 					# If fetching fails, provide an empty list
# 					link_options[field["fieldname"]] = []

# 		# 3. Get Pre-fill data for the current user
# 		prefill_data = {}
# 		if frappe.session.user != "Guest":
# 			user_email = frappe.session.user
# 			user_doc = frappe.get_doc("User", user_email)

# 			prefill_data = {
# 				"pi_userid": user_email,
# 				"principal_investigator_name": user_doc.full_name,
# 				# Assuming you have an "Employee" doctype linked to the User
# 				# This is a common pattern in Frappe HR
# 			}

# 			# Fetch Employee-specific details
# 			employee = frappe.get_all(
# 				"User", filters={"user_id": user_email}, fields=["name", "designation", "department"]
# 			)
# 			if employee:
# 				prefill_data["pi_employee_id"] = employee[0].name
# 				prefill_data["designation"] = employee[0].designation
# 				prefill_data["applicant_department"] = employee[0].department

# 		return {"fields": fields, "link_options": link_options, "prefill_data": prefill_data}

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), _("Error fetching project form data"))
# 		return {"error": str(e)}


@frappe.whitelist()
def get_project_form_data():
	"""
	Return a comprehensive dictionary containing all data needed to render the Project Registration form.
	This includes field definitions, options for Link/Select fields, and pre-fill data for the current user.
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

		return {"fields": fields, "link_options": link_options, "prefill_data": prefill_data}

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
def save_project_data(doc):
	"""
	Receives a JSON object from the frontend, creates a new Project Registration document,
	handles child tables, and processes Base64 encoded file attachments.
	"""
	try:
		# The 'doc' argument from the frontend is a JSON string, so we parse it.
		# If the frontend sends an object directly, Frappe might auto-parse it.
		# This handles both cases.
		if isinstance(doc, str):
			form_data = json.loads(doc)
		else:
			form_data = doc

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
		new_project.insert(ignore_permissions=False)

		# Commit the transaction
		frappe.db.commit()

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
