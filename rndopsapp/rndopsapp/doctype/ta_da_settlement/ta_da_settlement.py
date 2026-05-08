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


class TADASettlement(Document):
	pass


@frappe.whitelist()
def get_ta_da_settlement_fields(doc_name=None, travel_ref=None):
	"""
	API to return TA DA Settlement field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	Can prefill from a Travel reference.
	"""
	doctype_name = "TA DA Settlement"
	ta_da_meta = frappe.get_meta(doctype_name)

	fields = []
	link_fields = []
	child_table_meta = {}

	for f in ta_da_meta.get("fields"):
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
					"fields": child_fields,
				}
			except Exception:
				pass

	prefill_data = {}
	link_options = {}
	related_data = {}

	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch existing TA DA Settlement document for editing
		if frappe.db.exists(doctype_name, doc_name):
			doc = frappe.get_doc(doctype_name, doc_name)
			related_data = doc.as_dict()
			prefill_data = doc.as_dict()

	# Prefill from Travel reference
	if travel_ref:
		travel_ref = str(travel_ref).strip('"').strip("'")

		if frappe.db.exists("Travel", travel_ref):
			travel_doc = frappe.get_doc("Travel", travel_ref)

			# --- Field mapping: Travel field -> TA DA Settlement field ---
			prefill_data["ta_da_travel_application"] = travel_doc.name
			prefill_data["ta_da_name"] = travel_doc.applicant_name_travel
			prefill_data["ta_da_designation"] = travel_doc.designation_travel
			prefill_data["ta_da_department_section"] = travel_doc.department_travel
			prefill_data["ta_da_project_code"] = travel_doc.travel_project_number
			prefill_data["webmail_id"] = travel_doc.webmail_id_travel

			# Employee ID from User doctype
			if travel_doc.webmail_id_travel:
				emp_id = frappe.db.get_value("User", travel_doc.webmail_id_travel, "employee_id")
				if emp_id:
					prefill_data["ta_da_employee_number"] = emp_id

			# Bank details
			prefill_data["ta_da_bank_account_holder"] = travel_doc.bank_account_holder
			prefill_data["ta_da_bank_account_number"] = travel_doc.bank_account_number
			prefill_data["ta_da_ifsc_code"] = travel_doc.ifsc_code

			# Purpose of journey from Travel's purpose_of_visit
			prefill_data["ta_da_purpose_of_journey"] = travel_doc.purpose_of_visit

			# Advance taken from Travel's total_estimate
			if travel_doc.total_estimate:
				prefill_data["ta_da_advance_taken"] = travel_doc.total_estimate

	# ===== Link options for dropdowns =====
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
					limit_page_length=0,
				)
			else:
				link_options[fieldname] = frappe.get_all(
					linked_doctype,
					fields=["name as value", f"{title_field} as label"],
					limit_page_length=0,
				)
		except Exception:
			link_options[fieldname] = frappe.get_all(
				linked_doctype,
				fields=["name as value", "name as label"],
				limit_page_length=0,
			)

	# Fetch Client Scripts from Frappe (stored in database)
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": doctype_name, "enabled": 1},
			fields=["name", "script", "view"],
		)
		for script in scripts:
			client_scripts.append({
				"name": script.name,
				"script": script.script,
				"view": script.view,
			})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
		"child_table_meta": child_table_meta,
		"client_scripts": client_scripts,
	}


@frappe.whitelist()
def save_ta_da_settlement(doc_data):
	"""Saves or updates the TA DA Settlement data from the React form."""
	print("save_ta_da_settlement: execution started")
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for TA DA Settlement:", data)  # Debug log

		# Check if editing existing document
		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("TA DA Settlement", doc_name)
			if doc.docstatus != 0:
				print("Document is already submitted. Skipping save.")
				return {"status": "info", "message": "Cannot edit a submitted or cancelled document."}
		else:
			doc = frappe.new_doc("TA DA Settlement")

		# Field mapping for TA DA Settlement
		# Maps form_key -> doctype_fieldname
		field_mapping = {
			"ta_da_travel_application": "ta_da_travel_application",
			"ta_da_name": "ta_da_name",
			"ta_da_designation": "ta_da_designation",
			"ta_da_department_section": "ta_da_department_section",
			"ta_da_employee_number": "ta_da_employee_number",
			"ta_da_project_code": "project_no",
			"ta_da_contact": "ta_da_contact",
			"ta_da_ifsc_code": "ta_da_ifsc_code",
			"ta_da_scale_of_pay": "ta_da_scale_of_pay",
			"ta_da_bank_account_number": "ta_da_bank_account_number",
			"ta_da_bank_account_holder": "ta_da_bank_account_holder",
			"ta_da_purpose_of_journey": "ta_da_purpose_of_journey",
			"ta_da_journey_particulars": "ta_da_journey_particulars",
			"ta_da_local_conveyance_used": "ta_da_local_conveyance_used",
			"ta_da_total_claimed": "ta_da_total_claimed",
			"ta_da_advance_taken": "ta_da_advance_taken",
			"ta_da_net_claimed": "ta_da_net_claimed",
			"ta_da_comment": "ta_da_comment",
			"ta_da_additional_comment": "ta_da_additional_comment",
			"ta_da_check": "ta_da_check",
			"ta_da_entitled_class": "ta_da_entitled_class",
			"ta_da_shortest_route": "ta_da_shortest_route",
			"ta_da_not_paid_elsewhere": "ta_da_not_paid_elsewhere",
			"ta_da_boarding_lodging_status": "boarding_and_lodging_status",
			"boarding_and_lodging_status": "boarding_and_lodging_status",
			"ta_da_free_transport": "ta_da_free_transport",
			# Direct doctype fieldname fallbacks
			"webmail_id": "webmail_id",
			"project_no": "project_no",
		}

		# Update document with mapped data
		for form_field, doctype_field in field_mapping.items():
			if form_field in data and data[form_field] not in [None, ""]:
				doc.set(doctype_field, data[form_field])

		# Fetch and set applicant_category for workflow evaluations
		if doc.webmail_id:
			try:
				empclass_id = frappe.db.get_value("User", doc.webmail_id, "empclass")
				if empclass_id:
					empclass_name = frappe.db.get_value("EmployeeClass_prornd", empclass_id, "empclass_name")
					if empclass_name:
						doc.applicant_category = empclass_name
			except Exception as e:
				print(f"Error fetching applicant category for user {doc.webmail_id}: {e}")

		# Handle child table - ta_da_other_expenses_p
		other_expenses = data.get("ta_da_other_expenses_p")
		if isinstance(other_expenses, list):
			doc.set("ta_da_other_expenses_p", [])  # Clear existing
			for expense in other_expenses:
				if expense.get("ta_da_expense_type_other_expense") or expense.get("ta_da_amount_other_expense"):
					doc.append(
						"ta_da_other_expenses_p",
						{
							"ta_da_expense_type_other_expense": expense.get("ta_da_expense_type_other_expense"),
							"ta_da_amount_other_expense": expense.get("ta_da_amount_other_expense", 0),
							"ta_da_proof_other_expense": expense.get("ta_da_proof_other_expense"),
						},
					)

		# Save the document
		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved TA DA Settlement: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		print(f"[ERROR][save_ta_da_settlement]: {str(e)}")
		frappe.log_error(frappe.get_traceback(), "TA DA Settlement Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save TA DA Settlement: {str(e)}")


@frappe.whitelist()
def submit_ta_da_settlement(docname):
	"""
	Submit a TA DA Settlement document.
	Uses the workflow 'Submit' action to properly transition from Draft
	to the next workflow state (e.g. Pending Staff Approval), instead of
	calling doc.submit() which would set docstatus=1 and incorrectly
	match the 'Rejected' workflow state.
	"""
	print("submit_ta_da_settlement: execution started")
	print("Payload received:", docname)
	try:
		print("Processing TA/DA settlement...")
		doc = frappe.get_doc("TA DA Settlement", docname)

		current_state = doc.workflow_state or "Draft"
		print(f"Current workflow state: {current_state}, docstatus: {doc.docstatus}")

		if current_state != "Draft":
			return {
				"status": "info",
				"message": f"TA DA Settlement '{docname}' is already in state '{current_state}'.",
				"docname": docname,
				"workflow_state": current_state,
			}

		# Use the workflow action to transition properly
		result = perform_ta_da_settlement_action(docname, "Submit")
		if result.get("status") == "success":
			print(f"Settlement submitted successfully via workflow. New state: {result.get('workflow_state')}")
		else:
			print(f"Settlement submission failed: {result.get('message')}")

		return result

	except Exception as e:
		import traceback
		tb = traceback.format_exc()
		print(f"[ERROR][submit_ta_da_settlement]: {str(e)}")
		print(f"[ERROR][submit_ta_da_settlement] Traceback:\n{tb}")
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "TA DA Settlement Submit Error")
		return {"status": "error", "message": str(e) or tb}


@frappe.whitelist()
def get_ta_da_settlement_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("TA DA Settlement", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the active workflow for this doctype
	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": "TA DA Settlement", "is_active": 1},
		"name"
	)

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
def get_ta_da_settlement_commit_details(docname):
	"""
	Returns commit-related fields for the TA DA Settlement pending task page UI.
	Called by the frontend when rendering the Staff's commit form at Pending Staff Approval.
	Frontend should call submit_commit_data + perform_ta_da_settlement_action('Forward') on commit.
	"""
	if not frappe.db.exists("TA DA Settlement", docname):
		frappe.throw(_("TA DA Settlement document not found."))

	doc = frappe.get_doc("TA DA Settlement", docname)

	# Resolve project registration name and number via the linked Travel doc
	project_name = None  # Project Registration docname
	project_number = None  # project_no like "26RBSBESP0391XXLS0010"

	if doc.ta_da_travel_application:
		travel_project_title = frappe.db.get_value(
			"Travel", doc.ta_da_travel_application, "travel_project_title"
		)
		if travel_project_title:
			project_name = travel_project_title
			project_number = frappe.db.get_value(
				"Project Registration", travel_project_title, "project_no"
			)

	# Fall back to project_no stored directly on the doc
	if not project_number and doc.project_no:
		project_number = doc.project_no

	# TA/DA is always funded from Travel Head
	budget_head = "Travel Head"

	# Commit amount is the net claimed (after deducting advance taken)
	commit_amount = doc.ta_da_net_claimed or doc.ta_da_total_claimed or 0

	# Resolve moduleId from Module Registry for "TA DA Settlement"
	module_id = frappe.db.get_value(
		"Module Registry Item",
		{"doctype_name": "TA DA Settlement", "parent": "pending-task"},
		"mod_vis"
	) or None

	return {
		"docname": docname,
		"workflow_state": doc.workflow_state,
		"applicant_name": doc.ta_da_name,
		"webmail_id": doc.webmail_id,
		"travel_application": doc.ta_da_travel_application,
		"project_name": project_name,
		"project_number": project_number,
		"project_no": doc.project_no,
		"total_claimed": doc.ta_da_total_claimed,
		"advance_taken": doc.ta_da_advance_taken,
		"net_claimed": doc.ta_da_net_claimed,
		"commit_amount": commit_amount,
		"budget_head": budget_head,
		"purpose_of_journey": doc.ta_da_purpose_of_journey,
		"module_id": module_id,
		# refDetails = parent Travel's frapAppId (Travel docname)
		# Frontend must pass this as refDetails when calling submit_commit_data
		"ref_details": doc.ta_da_travel_application,
	}


@frappe.whitelist()
def perform_ta_da_settlement_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("TA DA Settlement", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the active workflow for this doctype
		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": "TA DA Settlement", "is_active": 1},
			"name"
		)

		if not workflow_name:
			frappe.throw(_("No active workflow found for TA DA Settlement."))

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		transition = None

		# Make sure applicant_category is set on the document for condition checking
		if getattr(doc, "webmail_id", None) and not getattr(doc, "applicant_category", None):
			try:
				empclass_id = frappe.db.get_value("User", doc.webmail_id, "empclass")
				if empclass_id:
					empclass_name = frappe.db.get_value("EmployeeClass_prornd", empclass_id, "empclass_name")
					if empclass_name:
						doc.applicant_category = empclass_name
			except Exception as e:
				print(f"Error fetching applicant category for user {doc.webmail_id}: {e}")

		# Get current user roles
		user_roles = frappe.get_roles(frappe.session.user)

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				# Check if user has permission for this specific transition
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]
				
				# System Manager check and role check
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
			doc.flags.ignore_permissions = True
			doc.submit()
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.flags.ignore_permissions = True
			doc.cancel()
		else:
			# Use db_set to bypass Frappe's internal validate_workflow(),
			# which re-checks transition roles against the session user
			# and fails. Our code above already validates roles + conditions.
			doc.db_set("workflow_state", next_state, update_modified=True)
			if getattr(doc, "applicant_category", None):
				doc.db_set("applicant_category", doc.applicant_category, update_modified=False)

		# Kafka publish on Dean / Associate Dean approval
		# db_set is used above (not doc.save()), so check_workflow_and_publish hook
		# does NOT fire automatically — we must publish staged commits explicitly here.
		if next_state == "Approved":
			frappe.logger().info(f"[TA DA Kafka] Approval triggered for {docname}. Searching for staged commits.")
			try:
				from rndopsapp.rndopsapp.kafka.producer.reimbursement import publish_commit as kafka_publish_commit
				staging_docs = frappe.get_all("Kafka Commit Staging", filters={
					"reference_doctype": "TA DA Settlement",
					"reference_name": docname,
					"status": ["in", ["PENDING_APPROVAL", "FAILED"]]
				})
				frappe.logger().info(f"[TA DA Kafka] Found {len(staging_docs)} staged commit(s) for {docname}.")
				if not staging_docs:
					all_staging = frappe.get_all("Kafka Commit Staging", filters={
						"reference_doctype": "TA DA Settlement",
						"reference_name": docname,
					}, fields=["name", "status", "creation"])
					frappe.log_error(
						f"[TA DA Kafka] No PENDING_APPROVAL/FAILED staging records found for {docname}. "
						f"All staging records for this doc: {all_staging}. "
						f"Ensure submit_commit_data was called before the staff Forward action.",
						"TA DA Kafka - No Staging Record"
					)
				for st in staging_docs:
					staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
					try:
						payload = json.loads(staging_doc.payload)
						frappe.logger().info(
							f"[TA DA Kafka] Publishing staging record {staging_doc.name} for {docname}. "
							f"Payload keys: {list(payload.keys())}, commit_amount={payload.get('commit_amount')}, "
							f"budget_head={payload.get('budget_head')}, project_name={payload.get('project_name')}"
						)
						success = kafka_publish_commit(
							doc=doc,
							commit_amount=payload.get("commit_amount"),
							budget_head=payload.get("budget_head"),
							project_name=payload.get("project_name"),
							bmr=payload.get("bmr"),
							bill_amount=payload.get("bill_amount"),
							frap_app_id=payload.get("frap_app_id"),
							ref_details=payload.get("ref_details")
						)
						if success:
							staging_doc.db_set("status", "PUBLISHED")
						else:
							staging_doc.db_set("status", "FAILED")
							staging_doc.db_set("error_message", "kafka_publish_commit returned False")
							frappe.log_error(
								f"[TA DA Kafka] kafka_publish_commit returned False for staging {staging_doc.name}",
								"TA DA Kafka - Publish Failed"
							)
					except Exception as e:
						frappe.log_error(frappe.get_traceback(), f"[TA DA Kafka] Exception processing staging {staging_doc.name} for {docname}")
						staging_doc.db_set("status", "FAILED")
						staging_doc.db_set("error_message", str(e))
			except Exception as e:
				frappe.log_error(frappe.get_traceback(), f"[TA DA Kafka] Outer exception for {docname}")

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_ta_da_settlement_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		import traceback
		tb = traceback.format_exc()
		print(f"[ERROR][perform_ta_da_settlement_action] Traceback:\n{tb}")
		frappe.log_error(frappe.get_traceback(), "TA DA Settlement Action Error")
		return {"status": "error", "message": str(e) or tb}
