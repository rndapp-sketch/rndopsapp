# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


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


class Travel(Document):
	pass


@frappe.whitelist()
def get_travel_fields(doc_name=None):
	"""
	API to return Travel field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	Includes client scripts and child table metadata.
	"""
	doctype_name = "Travel"
	travel_meta = frappe.get_meta(doctype_name)

	fields = []
	link_fields = []
	child_table_meta = {}

	for f in travel_meta.get("fields"):
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
						"depends_on": cf.depends_on,
						"depends_on_eval": extract_eval_expression(cf.depends_on),
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
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch existing Travel document for editing
		if frappe.db.exists(doctype_name, doc_name):
			doc = frappe.get_doc(doctype_name, doc_name)
			related_data = doc.as_dict()
			prefill_data = doc.as_dict()

	# Prefill current user data
	current_user = frappe.session.user
	if current_user and current_user != "Guest":
		user_data = frappe.db.get_value(
			"User",
			current_user,
			["name", "full_name", "designation_name", "department_name"],
			as_dict=True,
		)
		if user_data:
			if not prefill_data.get("webmail_id_travel"):
				prefill_data["webmail_id_travel"] = user_data.name
			if not prefill_data.get("applicant_name_travel"):
				prefill_data["applicant_name_travel"] = user_data.full_name
			if not prefill_data.get("designation_travel"):
				prefill_data["designation_travel"] = user_data.designation_name
			if not prefill_data.get("department_travel"):
				prefill_data["department_travel"] = user_data.department_name

	# ===== Link options for dropdowns =====
	# Dynamically get link options for all Link fields
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

	# Department options (explicit)
	try:
		departments = frappe.get_all(
			"Department_prornd",
			fields=["name as value", "dept_name as label"],
			limit_page_length=500,
		)
		link_options["department_travel"] = departments
	except Exception:
		link_options["department_travel"] = []

	# Designation options (from User doctype - get unique designations)
	try:
		designations_raw = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["designation"],
			limit_page_length=1000,
		)
		unique_designations = list(set(
			d.get("designation") for d in designations_raw 
			if d.get("designation")
		))
		designations = [{"value": d, "label": d} for d in sorted(unique_designations)]
		link_options["designation_travel"] = designations
	except Exception:
		link_options["designation_travel"] = []

	# Fetch Client Scripts from Frappe (stored in database)
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
def get_user_details_travel(user_email):
	"""
	Fetches details for a specific user to populate travel form fields.
	Returns the user document with resolved department name and designation.
	"""
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
				user_dict["department_name"] = dept_doc.dept_name
			except Exception:
				pass  # Keep original value if lookup fails

		# Resolve designation_name if needed
		designation_link = user_dict.get("designation_name")
		if designation_link:
			user_dict["designation_name"] = designation_link

		return user_dict
	except frappe.DoesNotExistError:
		return None
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching user details for Travel"))
		frappe.throw(_("An error occurred while fetching user details."))


@frappe.whitelist()
def save_travel(doc_data):
	"""Saves or updates the Travel data from the React form.
	Handles file uploads for Attach fields.
	"""
	from frappe.utils.file_manager import save_file
	
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Travel:", data)  # Debug log

		doc_name = data.get("name")
		is_new = False
		
		# 1. Initialize Document
		if doc_name and frappe.db.exists("Travel", doc_name):
			doc = frappe.get_doc("Travel", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc("Travel")
			is_new = True

		meta = frappe.get_meta("Travel")
		
		# 2. First Pass: Set standard fields (non-files) to ensure we can insert if new
		file_fields = []
		
		for fieldname, value in data.items():
			if fieldname in ["name", "doctype", "docstatus"]:
				continue

			if not meta.has_field(fieldname):
				continue

			df = meta.get_field(fieldname)
			
			if df.fieldtype in ["Attach", "Attach Image"]:
				file_fields.append((fieldname, value))
			elif df.fieldtype == "Table":
				# We typically process tables after insert too if they contain files
				file_fields.append((fieldname, value))
			else:
				if value not in [None, ""]:
					doc.set(fieldname, value)

		# 3. Create/Save Initial Document to get Name (if new)
		doc.flags.ignore_permissions = True
		if is_new:
			doc.insert(ignore_mandatory=True)
			print(f"Created new Travel doc: {doc.name}")
		else:
			doc.save(ignore_permissions=True)
			print(f"Updated existing Travel doc: {doc.name}")

		# 4. Second Pass: Process Files and Tables (Now we have doc.name)
		for fieldname, value in file_fields:
			df = meta.get_field(fieldname)
			
			if df.fieldtype == "Table" and isinstance(value, list):
				doc.set(fieldname, []) # Clear existing
				child_meta = frappe.get_meta(df.options)
				
				for child_row in value:
					row_dict = child_row.copy()
					
					# Handle files in child row
					for cf in child_meta.fields:
						if cf.fieldtype in ["Attach", "Attach Image"] and row_dict.get(cf.fieldname):
							f_val = row_dict[cf.fieldname]
							
							if isinstance(f_val, dict) and f_val.get("file_data"):
								try:
									saved_file = save_file(
										f_val.get("file_name", "attachment"),
										f_val["file_data"],
										"Travel",
										doc.name, # Attach to parent
										decode=True,
										is_private=1,
										df=cf.fieldname
									)
									row_dict[cf.fieldname] = saved_file.file_url
									print(f"Child table file saved: {saved_file.file_url}")
								except Exception as e:
									frappe.log_error(f"Child File Error: {e}")
									
					doc.append(fieldname, row_dict)
					
			elif df.fieldtype in ["Attach", "Attach Image"]:
				if isinstance(value, dict) and value.get("file_data"):
					try:
						print(f"Uploading file for {fieldname}...")
						saved_file = save_file(
							value.get("file_name", "attachment"),
							value["file_data"],
							"Travel",
							doc.name,
							decode=True,
							is_private=1,
							df=fieldname
						)
						# Explicitly update the field in DB immediately? No, doc.save() will do it.
						doc.set(fieldname, saved_file.file_url)
						print(f"Set {fieldname} to {saved_file.file_url}")
					except Exception as e:
						frappe.log_error(f"File Upload Error for {fieldname}: {str(e)}")
						print(f"Error uploading {fieldname}: {e}")
				
				elif isinstance(value, str):
					# Keep existing URL
					doc.set(fieldname, value)

		# 5. Final Save to persist file URLs and Table data
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully finalized Travel: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Travel Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Travel: {str(e)}")


@frappe.whitelist()
def submit_travel(docname):
	"""
	Submit a Travel document.
	"""
	try:
		doc = frappe.get_doc("Travel", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Travel '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Travel '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Travel '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Travel Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_travel_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Travel", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	# workflow_name = frappe.db.get_value(
	# 	"Workflow",
	# 	{"document_type": "Travel", "is_active": 1},
	# 	"name"
	# )
	workflow_name = "Travel_Workflow"

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
def perform_travel_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Travel", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": "Travel", "is_active": 1},
			"name"
		)

		if not workflow_name:
			frappe.throw(_("No active workflow found for Travel."))

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		transition = None

		# Get current user roles
		user_roles = frappe.get_roles(frappe.session.user)

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				# Check if user has permission for this specific transition
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]
				
				# If "System Manager" is in roles, they can usually do anything, 
				# but strictly following workflow rules is safer for logic differentiation.
				# However, standard practice is to allow if role matches.
				if any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles:
					next_state = t.next_state
					transition = t
					break

		if not next_state:
			frappe.throw(_(f"No valid transition found for action '{action}' from state '{current_state}'."))

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
			"next_actions": get_travel_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Travel Action Error")
		return {"status": "error", "message": str(e)}

