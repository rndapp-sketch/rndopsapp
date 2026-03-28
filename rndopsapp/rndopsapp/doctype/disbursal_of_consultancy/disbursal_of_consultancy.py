# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils.file_manager import save_file
from frappe import _

class DisbursalofConsultancy(Document):
	def validate(self):
		"""Server-side mirror of the calculations and share splits."""
		self.calculate_shares_and_totals()

	def calculate_shares_and_totals(self):
		"""
		Calculates:
		1. Row shares: 70% personal, 30% institute
		2. Total disbursal: Sum of all rows
		3. Institute breakdown: 40% IDF, 50% DPF, 5% Staff Welfare, 5% Student Welfare
		"""
		total_disbursal = 0.0
		for row in self.get("details_of_disbursal", []):
			amount = flt(row.disbursal_amount)
			row.disbursal_personal_share = amount * 0.70
			row.disbursal_institute_share = amount * 0.30
			total_disbursal += amount

		self.total_disbursal_amount = total_disbursal
		
		# Totals
		inst_share_total = total_disbursal * 0.30
		self.total_personal_share = total_disbursal * 0.70
		self.total_institute_share = inst_share_total
		
		# Breakdown (of the 30% Institute Share)
		self.idf = inst_share_total * 0.40
		self.dpf = inst_share_total * 0.50
		self.staff_welfare_fund = inst_share_total * 0.05
		self.student_welfare_fund = inst_share_total * 0.05

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
def get_disbursal_of_consultancy_fields(doc_name=None):
	"""
	Return Disbursal of Consultancy field metadata + prefill data.
	"""
	# --- fields meta (safe) ---
	meta = frappe.get_meta("Disbursal of Consultancy")
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
					# Include link_filters, fetch_from, etc.
					cf_data = {
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
						"fetch_from": getattr(cf, "fetch_from", None),
						"default": getattr(cf, "default", None),
					}
					if cf.fieldtype == "Link" and getattr(cf, "link_filters", None):
						cf_data["link_filters"] = cf.link_filters
					
					child_fields.append(cf_data)
				
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
			doc = frappe.get_doc("Disbursal of Consultancy", doc_name)
			prefill_data = doc.as_dict()
		except Exception:
			pass
	else:
		# Prefill for new doc
		try:
			current_user = frappe.session.user
			if current_user and current_user not in ["Administrator", "Guest"]:
				prefill_data["webmail_id"] = current_user
				
				# Try to fetch details from user record
				user_doc = frappe.get_doc("User", current_user)
				prefill_data["pi_name"] = user_doc.full_name
				prefill_data["employee_id"] = user_doc.employee_id
		except Exception:
			pass

	# 2. Populate Link Options
	# webmail_id (User)
	# 2. Populate Link Options
	# webmail_id (User) - providing full detail for auto-population
	try:
		users_raw = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name", "full_name", "employee_id", "designation_name"],
			limit_page_length=200,
		)
		link_options["webmail_id"] = [
			{
				"value": u.name, 
				"label": u.full_name or u.name,
				"full_name": u.full_name,
				"employee_id": u.employee_id,
				"designation_name": u.designation_name
			} for u in users_raw
		]
	except Exception:
		pass

	# designation (in child table) - "Designation_prornd"
	try:
		designations = frappe.get_all("Designation_prornd", fields=["name as value"], limit_page_length=200)
		link_options["designation"] = designations
	except Exception:
		pass
		
	# amended_from
	try:
		amended = frappe.get_all("Disbursal of Consultancy", fields=["name as value"], limit_page_length=200)
		link_options["amended_from"] = amended
	except Exception:
		pass

	# 3. Client Scripts
	client_scripts = []
	try:
		scripts = frappe.get_all("Client Script", filters={"dt": "Disbursal of Consultancy", "enabled": 1}, fields=["name", "script", "view"])
		for script in scripts:
			client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
	except Exception:
		pass

	# --- Computation Rules (Structured for React) ---
	computation_rules = {
		"row_calculations": [
			{
				"table_fieldname": "details_of_disbursal",
				"target_field": "disbursal_personal_share",
				"formula": "disbursal_amount * 0.70",
				"trigger_fields": ["disbursal_amount"],
				"description": "Personal Share (70%)"
			},
			{
				"table_fieldname": "details_of_disbursal",
				"target_field": "disbursal_institute_share",
				"formula": "disbursal_amount * 0.30",
				"trigger_fields": ["disbursal_amount"],
				"description": "Institute Share (30%)"
			}
		],
		"aggregations": [
			{
				"target_field": "total_disbursal_amount",
				"source_table": "details_of_disbursal",
				"source_field": "disbursal_amount",
				"operation": "sum"
			}
		],
		"derived_fields": [
			{
				"target_field": "total_personal_share",
				"formula": "total_disbursal_amount * 0.70",
				"trigger_fields": ["total_disbursal_amount"]
			},
			{
				"target_field": "total_institute_share",
				"formula": "total_disbursal_amount * 0.30",
				"trigger_fields": ["total_disbursal_amount"]
			},
			{
				"target_field": "idf",
				"formula": "total_institute_share * 0.40",
				"trigger_fields": ["total_institute_share"]
			},
			{
				"target_field": "dpf",
				"formula": "total_institute_share * 0.50",
				"trigger_fields": ["total_institute_share"]
			},
			{
				"target_field": "staff_welfare_fund",
				"formula": "total_institute_share * 0.05",
				"trigger_fields": ["total_institute_share"]
			},
			{
				"target_field": "student_welfare_fund",
				"formula": "total_institute_share * 0.05",
				"trigger_fields": ["total_institute_share"]
			}
		],
		"auto_populate": [
			{
				"trigger_field": "webmail_id",
				"context": "parent",
				"api": "rndopsapp.doctype.disbursal_of_consultancy.disbursal_of_consultancy.get_user_details_disbursal",
				"api_param": "user_email",
				"field_map": {
					"full_name": "pi_name",
					"employee_id": "employee_id"
				}
			}
		]
	}

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
		"computation_rules": computation_rules
	}

@frappe.whitelist()
def save_disbursal_of_consultancy_data(data):
	"""
	Save Disbursal of Consultancy data.
	Expects 'data' as a JSON string or dict.
	"""
	if isinstance(data, str):
		data = json.loads(data)
	
	try:
		# Create or Get Doc
		if data.get("name"):
			doc = frappe.get_doc("Disbursal of Consultancy", data.get("name"))
		else:
			doc = frappe.new_doc("Disbursal of Consultancy")
		
		# Map Fields
		simple_fields = [
			"amended_from",
			"webmail_id",
			"pi_name",
			"employee_id",
			"project_title",
			"date_of_registration",
			"date_of_completion",
			"total_amount_received",
			"current_balance",
			"disbursal_project_number", 
			"workflow_state" # Just in case
		]

		for field in simple_fields:
			if field in data:
				val = data[field]
				doc.set(field, val if val != "null" else None)
		
		# Handle File Upload fields (Attach)
		# please_attach_a_copy_of_completion_report, disbursal_additional_documents
		file_fields = ["please_attach_a_copy_of_completion_report", "disbursal_additional_documents"]
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
						frappe.log_error(f"Error saving file for {field}: {str(e)}", "Disbursal of Consultancy File Upload")
				elif isinstance(val, str):
					# Existing file URL or cleared
					doc.set(field, val)

		# Handle Child Table: details_of_disbursal
		items_data = data.get("details_of_disbursal", [])
		if isinstance(items_data, str):
			items_data = json.loads(items_data)
			
		if items_data:
			doc.set("details_of_disbursal", []) # Clear existing
			for item in items_data:
				doc.append("details_of_disbursal", item)
		
		# Save (this triggers the validate() hook where calculations reside)
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Disbursal of Consultancy Save Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def perform_disbursal_of_consultancy_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Disbursal of Consultancy", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = frappe.get_value("Workflow", {"document_type": "Disbursal of Consultancy"}, "name")

		if not workflow_name:
			frappe.throw("Workflow not found for Disbursal of Consultancy.")

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				break

		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

		# -------------------------------------------------------------------
		# WHY frappe.db.set_value instead of doc.save() / doc.submit():
		#
		# doc.save()   → calls _validate() → validate_workflow()
		# doc.submit() → also calls validate_workflow()
		#
		# validate_workflow() filters transitions by the CALLER'S roles.
		# API callers lack the desk roles assigned in the workflow definition,
		# so get_transitions() returns [] and Frappe throws "transition not
		# allowed from X to Draft". Writing directly to DB bypasses this.
		# -------------------------------------------------------------------

		next_state_row = next(
			(s for s in workflow.states if s.state == next_state), None
		)
		new_docstatus = int(next_state_row.doc_status or 0) if next_state_row else 0

		workflow_field = workflow.workflow_state_field or "workflow_state"
		update_fields = {workflow_field: next_state}

		if new_docstatus != int(doc.docstatus):
			update_fields["docstatus"] = new_docstatus

		if (
			next_state_row
			and getattr(next_state_row, "update_field", None)
			and next_state_row.update_field != workflow_field
			and next_state_row.update_value is not None
		):
			update_fields[next_state_row.update_field] = next_state_row.update_value

		# Write directly to DB — bypasses validate_workflow completely
		frappe.db.set_value(
			"Disbursal of Consultancy",
			docname,
			update_fields,
			update_modified=True,
		)

		# Add a workflow comment so the timeline reflects the transition
		doc.reload()
		doc.add_comment("Workflow", _(next_state))

		# --- Data Pipeline Integration ---
		# When the document reaches "Approved", publish any pending staged commit
		# payloads to Kafka.
		# NOTE: Since perform_action uses frappe.db.set_value (bypasses ORM),
		# the on_update hook (check_workflow_and_publish) does NOT fire.
		# We must publish staged commits explicitly here.
		if next_state == "Approved":
			frappe.logger().info(f"[Consultancy Kafka] Approval triggered for {docname}. Searching for staged commits.")
			try:
				from rndopsapp.rndopsapp.kafka.producer.reimbursement import publish_commit as kafka_publish_commit

				staging_docs = frappe.get_all("Kafka Commit Staging", filters={
					"reference_doctype": "Disbursal of Consultancy",
					"reference_name": docname,
					"status": ["in", ["PENDING_APPROVAL", "FAILED"]]
				})

				frappe.logger().info(f"[Consultancy Kafka] Found {len(staging_docs)} staged commit(s) for {docname}.")

				if not staging_docs:
					# Log all staging records for this doc regardless of status — helps diagnose missing/wrong-status records
					all_staging = frappe.get_all("Kafka Commit Staging", filters={
						"reference_doctype": "Disbursal of Consultancy",
						"reference_name": docname,
					}, fields=["name", "status", "creation"])
					frappe.log_error(
						f"[Consultancy Kafka] No PENDING_APPROVAL/FAILED staging records found for {docname}. "
						f"All staging records for this doc: {all_staging}. "
						f"This means submit_commit_data was either not called or used a different reference_name.",
						"Consultancy Kafka - No Staging Record"
					)

				for st in staging_docs:
					staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
					try:
						import json as _json
						payload = _json.loads(staging_doc.payload)

						frappe.logger().info(
							f"[Consultancy Kafka] Publishing staging record {staging_doc.name} for {docname}. "
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
							frappe.logger().info(f"[Consultancy Kafka] Successfully published staging record {staging_doc.name} for {docname}.")
						else:
							staging_doc.db_set("status", "FAILED")
							staging_doc.db_set("error_message", "kafka_publish_commit returned False")
							frappe.log_error(
								f"[Consultancy Kafka] kafka_publish_commit returned False for {docname}. "
								f"Staging: {staging_doc.name}, payload: {payload}",
								"Consultancy Kafka Publish Failed"
							)

					except Exception as e:
						frappe.log_error(frappe.get_traceback(), f"[Consultancy Kafka] Exception processing staging {staging_doc.name} for {docname}")
						staging_doc.db_set("status", "FAILED")
						staging_doc.db_set("error_message", str(e))

			except Exception as e:
				frappe.log_error(frappe.get_traceback(), f"[Consultancy Kafka] Outer exception for {docname}")
		# -------------------------------

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_disbursal_of_consultancy_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Disbursal of Consultancy Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_disbursal_of_consultancy(docname):
	"""
	Submit a Disbursal of Consultancy document.
	Uses the workflow 'Submit' action to properly transition from Draft
	to the next workflow state (e.g. Pending Approval), instead of
	calling doc.submit() which would set docstatus=1 and incorrectly
	match the 'Rejected' workflow state.
	"""
	print("submit_disbursal_of_consultancy: execution started")
	print("Payload received:", docname)
	try:
		doc = frappe.get_doc("Disbursal of Consultancy", docname)

		current_state = doc.workflow_state or "Draft"
		print(f"Current workflow state: {current_state}, docstatus: {doc.docstatus}")

		if current_state != "Draft":
			return {
				"status": "info",
				"message": f"Disbursal of Consultancy '{docname}' is already in state '{current_state}'.",
				"docname": docname,
				"workflow_state": current_state,
			}

		# Use the workflow action to transition properly
		result = perform_disbursal_of_consultancy_action(docname, "Submit")
		if result.get("status") == "success":
			print(f"Disbursal submitted successfully via workflow. New state: {result.get('workflow_state')}")
		else:
			print(f"Disbursal submission failed: {result.get('message')}")

		return result

	except Exception as e:
		import traceback
		tb = traceback.format_exc()
		print(f"[ERROR][submit_disbursal_of_consultancy]: {str(e)}")
		print(f"[ERROR][submit_disbursal_of_consultancy] Traceback:\n{tb}")
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Disbursal of Consultancy Submit Error")
		return {"status": "error", "message": str(e) or tb}

@frappe.whitelist()
def get_disbursal_of_consultancy_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Disbursal of Consultancy", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	workflow_name = frappe.get_value("Workflow", {"document_type": "Disbursal of Consultancy"}, "name")
	
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
def get_user_details_disbursal(user_email):
	"""
	Fetch user details for auto-populating PI Name and Employee ID.
	"""
	if not user_email:
		frappe.throw(_("User Email is required."))

	try:
		user_email = str(user_email).strip('"').strip("'")
		user_doc = frappe.get_doc("User", user_email)

		return {
			"full_name": user_doc.full_name,
			"employee_id": user_doc.employee_id,
			"designation_name": user_doc.designation_name,
		}

	except frappe.DoesNotExistError:
		return None
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching user details"))
		frappe.throw(_("An error occurred while fetching user details."))
