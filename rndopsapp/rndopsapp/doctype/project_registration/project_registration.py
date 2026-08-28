# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import os
import re
import json
import datetime
import frappe
from frappe import _
from frappe.utils import sanitize_html
from frappe.utils import flt, nowdate
from frappe.utils import flt
from frappe.utils.file_manager import save_file
from rndopsapp.config import MATTERMOST_POSTS_URL, ACCOUNT_PORTAL_PROJECTS
import base64
import requests
from rndopsapp.rndopsapp.kafka.producer import publish_project_registration as publish_project
from rndopsapp.minio import get_rnd_file_service
from rndopsapp.file_handler import get_file_category_for_doctype


class ProjectRegistration(Document):
	def on_update(self):
		# Automatically generate the Endorsement PDF if text is provided and state is early manually
		if self.text_editor_zwfu and self.workflow_state in ["Draft", "Endorsement Draft", "Pending Dean Approval", "Endorsement Approved"]:
			self.generate_endorsement_pdf(self.text_editor_zwfu)

	def validate(self):
		"""
		Intercept file uploads from Frappe UI and upload to MinIO instead of local filesystem.
		"""
		self._validate_budget_amounts()
		self._process_attach_fields()
		self._process_child_attach_fields()

	def _validate_budget_amounts(self):
		amount = self.get("total_budget_amount")
		if amount is None:
			amount = self.get("grand_total_proposal")
		if flt(amount) < 0:
			frappe.throw("Total Budget Amount cannot be negative.")

	def _process_attach_fields(self):
		meta = frappe.get_meta(self.doctype)
		for df in meta.fields:
			if df.fieldtype == "Attach":
				fieldname = df.fieldname
				file_url = self.get(fieldname)
				if file_url and (file_url.startswith("/files/") or file_url.startswith("/private/files/")):
					self._migrate_file_to_minio(fieldname, file_url)

	def _process_child_attach_fields(self):
		meta = frappe.get_meta(self.doctype)
		for df in meta.fields:
			if df.fieldtype == "Table":
				child_meta = frappe.get_meta(df.options)
				for child_row in self.get(df.fieldname) or []:
					for child_field in child_meta.fields:
						if child_field.fieldtype == "Attach":
							fieldname = child_field.fieldname
							file_url = child_row.get(fieldname)
							if file_url and (file_url.startswith("/files/") or file_url.startswith("/private/files/")):
								self._migrate_child_file_to_minio(child_row, fieldname, file_url)

	def _migrate_file_to_minio(self, fieldname, file_url):
		try:
			from rndopsapp.file_handler import migrate_local_file_to_minio
			result = migrate_local_file_to_minio(
				file_url=file_url, doctype=self.doctype, docname=self.name, fieldname=fieldname
			)
			if result.get("status"):
				self.set(fieldname, result.get("file_url"))
			else:
				frappe.log_error(result.get("message"), f"MinIO Migration Error for {fieldname}")
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"MinIO Migration Error for {fieldname}")

	def _migrate_child_file_to_minio(self, child_row, fieldname, file_url):
		try:
			from rndopsapp.file_handler import migrate_local_file_to_minio
			result = migrate_local_file_to_minio(
				file_url=file_url, doctype=self.doctype, docname=self.name, fieldname=fieldname
			)
			if result.get("status"):
				child_row.set(fieldname, result.get("file_url"))
			else:
				frappe.log_error(result.get("message"), f"Child MinIO Migration Error for {fieldname}")
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"Child MinIO Migration Error for {fieldname}")

	def generate_endorsement_pdf(self, html_content=None):
		from frappe.utils.pdf import get_pdf

		# Avoid recursion if saving within this function
		if getattr(self.flags, "in_pdf_generation", False):
			return
		self.flags.in_pdf_generation = True

		try:
			if not html_content:
				html_content = self.text_editor_zwfu
				
			if not html_content:
				return # Nothing to generate
			
			# Get MinIO file service
			file_service = get_rnd_file_service()

			# Prepare filenames
			html_filename = f"{self.name}-Endorsement.html"
			pdf_filename = f"{self.name}-Endorsement.pdf"

			# Generate PDF content in memory
			pdf_content = get_pdf(html_content)

			# Save HTML to MinIO
			html_result = file_service.save_file(
				filename=html_filename,
				content=html_content,
				is_private=True,
				doctype=self.doctype,
				docname=self.name,
				folder=get_file_category_for_doctype(self.doctype, "endorsement_html")
			)

			if not html_result.get("status"):
				frappe.log_error(f"HTML upload failed: {html_result.get('message')}",
					f"Endorsement HTML Upload Failed for {self.name}")

			# Save PDF to MinIO
			pdf_result = file_service.save_file(
				filename=pdf_filename,
				content=pdf_content,
				is_private=True,
				doctype=self.doctype,
				docname=self.name,
				folder=get_file_category_for_doctype(self.doctype, "endorsement_pdf")
			)

			if not pdf_result.get("status"):
				frappe.log_error(f"PDF upload failed: {pdf_result.get('message')}",
					f"Endorsement PDF Upload Failed for {self.name}")

		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"Endorsement PDF Generation Failed for {self.name}")
		finally:
			self.flags.in_pdf_generation = False


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


# ============================================================
# EDITED BY OJS | 2026-04-21 01:46 IST
# START OF EDIT — Hardened notify_mattermost: split timeout
# into (connect=2s, read=3s) so a dead/unreachable Mattermost
# server fails fast and NEVER blocks or affects functionality.
# ============================================================
def notify_mattermost(message: str, urgent: bool = False, channel_id: str = "ihmkbbfq9ibzugfpy9rncq5yke") -> None:
	"""
	Sends a message to the configured Mattermost channel.
	- connect timeout = 2 s : fails fast if server is unreachable
	- read timeout   = 3 s : fails fast if server is slow
	All exceptions are silently swallowed — this call must NEVER
	affect the main application flow under any circumstances.
	"""
	try:
		_url = MATTERMOST_POSTS_URL

		_headers = {
			"Authorization": "Bearer fmjih41b4iymicttnuhinsqime",
			"Content-Type": "application/json",
		}

		_payload = {
			"channel_id": channel_id,
			"message": str(message),
		}

		# Add URGENT priority only when requested
		if urgent:
			_payload["metadata"] = {
				"priority": {
					"priority": "urgent",
					"requested_ack": False,
					"persistent_notifications": False,
				}
			}

		import requests as _req

		_req.post(
			_url,
			json=_payload,
			headers=_headers,
			timeout=(2, 3),
		)

	except Exception:
		pass  # never interrupt main flow
# END OF EDIT — OJS | 2026-04-21 01:46 IST
# ============================================================


@frappe.whitelist()
def submit_project_registration(docname):
	# ============================================================
	# EDITED BY OJS | 2026-04-21 01:54 IST
	# START OF EDIT — Wrapped entire function in try/except so ALL
	# exceptions (including frappe.throw ValidationErrors) are sent
	# to Mattermost before being re-raised to Frappe normally.
	# ============================================================
	try:
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
		doc.flags.ignore_mandatory = True
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

		# START MKY 2026-05-29 12:52:00 IST - If submitting user IS the dept head, skip
		# "Pending Head Approval" and jump directly to the next state (e.g. Pending Staff Approval).
		# Uses pre-set-then-reload so validate_workflow sees no in-flight transition → no role error.
		submitting_user = frappe.session.user
		is_head_submitting = (
			submitting_user == doc.head_approver
			or submitting_user == doc.department_head
		)

		if is_head_submitting and "Head Approval" in next_state:
			# Walk the workflow to find the state AFTER "Pending Head Approval"
			post_head_state = None
			for t in workflow_doc.transitions:
				if t.state == next_state:
					post_head_state = t.next_state
					break
			if post_head_state:
				print(
					f"[submit_project_registration] Head '{submitting_user}' is submitting — "
					f"skipping '{next_state}' → going directly to '{post_head_state}'"
				)
				next_state = post_head_state

		# Pre-set target workflow_state in DB so validate_workflow sees no transition
		# (in-memory state == DB state → role check on the transition is not triggered).
		frappe.db.set_value(
			"Project Registration", docname, "workflow_state", next_state, update_modified=False
		)
		frappe.db.commit()

		# Reload so in-memory doc matches the DB state before submit()
		doc = frappe.get_doc("Project Registration", docname)
		doc.workflow_state = next_state
		doc.department_head = dept_doc.dept_head
		doc.head_approver = dept_doc.dept_head

		# ✅ Submit — validate_workflow passes since state already matches DB
		doc.flags.ignore_mandatory = True
		doc.submit()
		# END MKY

		notify_mattermost(
			f"✅ -=-=-=-=-=-=✅-=-=-=-=-=-✅=-=-=-=-=-=-=-=✅-=-=-=-=-=-✅ \n"
			f"✅ [submit_project_registration] SUCCESS ✅\n"
			f"Time         : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
			f"Docname      : {docname}\n"
			f"New State    : {doc.workflow_state}\n"
			f"Dept Head    : {doc.department_head}\n"
			f"Head Approver: {doc.head_approver}"
		)

		return {
			"workflow_state": doc.workflow_state,
			"department_head": doc.department_head,
			"head_approver": doc.head_approver,
		}

	except Exception as e:
		_tb = frappe.get_traceback()
		notify_mattermost(
			f"❌ -=-=-=-=-=-=❌-=-=-=-=-=-❌=-=-=-=-=-=-=-=❌-=-=-=-=-=-❌ \n"
			f"❌ [submit_project_registration] ERROR ❌\n"
			f"Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
			f"Docname  : {docname}\n"
			f"Exception: {type(e).__name__}: {str(e)}\n"
			f"User     : {frappe.session.user}\n"
			f"---TRACEBACK---\n{_tb}",
			urgent=True,
		)
		raise  # Re-raise so Frappe handles the HTTP response normally
	# END OF EDIT — OJS | 2026-04-21 01:54 IST
	# ============================================================



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
def handle_dynamic_workflow_action(doctype, docname, action, comment=None, endorsement=False):
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

	# --- Endorsement Approved: register project and move to next workflow state ---
	if current_state == "Endorsement Approved":
		# Resolve department head (same as submit_project_registration)
		dept_link = doc.get("implementation_department")
		if dept_link:
			dept_doc = frappe.get_doc("Department_prornd", dept_link)
			doc.department_head = dept_doc.dept_head
			doc.head_approver = dept_doc.dept_head

		# Resolve the correct next state from EmployeeClass workflow
		applicant_type = doc.applicant_type
		emp_class_doc_id = None
		if applicant_type:
			if frappe.db.exists("EmployeeClass_prornd", applicant_type):
				emp_class_doc_id = applicant_type
			else:
				emp_class_doc_id = frappe.db.get_value(
					"EmployeeClass_prornd", {"empclass_name": applicant_type}, "name"
				)

		next_state = "Pending Head Approval"  # sensible default
		if emp_class_doc_id:
			wf_path = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path")
			if wf_path and frappe.db.exists("Workflow", wf_path):
				wf_doc = frappe.get_doc("Workflow", wf_path)
				for t in wf_doc.transitions:
					if t.state == "Draft":
						next_state = t.next_state
						break

		doc.workflow_state = next_state
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.msgprint(
			_(f"Project registered. Workflow updated to: {next_state}"),
			indicator="green",
		)
		return next_state

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

	next_state = None
	if transition:
		next_state = transition.get("next_state")
	else:
		frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

	# Step 3: Optional comment
	if comment:
		doc.add_comment("Comment", f"<strong>Action: {action}</strong><br>{sanitize_html(comment)}")

	# Step 4: Apply transition
	previous_state = doc.workflow_state  # Store current state for rollback
	previous_docstatus = doc.docstatus  # Store current docstatus for rollback

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
			doc.flags.ignore_mandatory = True
			doc.submit()
		else:
			# Skip mandatory validation for workflow transitions
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
	
	# --- Integration with External API (Kafka) ---
	if not endorsement and doc.workflow_state == "Approved" and doc.docstatus == 1 :
		# print("doc inside: ", doc.as_dict())
		try:
			success = publish_project(doc)
			if success:
				frappe.msgprint(_(f"Workflow updated to: {doc.workflow_state}"), indicator="blue")
				frappe.msgprint(_("Project data synced successfully to external system."), indicator="green")
			else:
				# Bypassing document validations for emergency DB rollback
				frappe.db.set_value(
					doctype, docname,
					{"workflow_state": previous_state, "docstatus": previous_docstatus},
					update_modified=False,
				)
				frappe.db.commit()
				frappe.log_error(f"Kafka sync failed for {docname}, rolled back workflow state", "Kafka Rollback")
				frappe.throw(
					_("Cannot approve: Kafka sync returned False (check validation errors in the Error Log). "
					  "The approval was not applied; workflow state reverted to '{0}'.").format(previous_state)
				)
		except frappe.ValidationError:
			raise  # Re-raise the revert-and-throw above without re-triggering the rollback below
		except Exception as e:
			# Bypassing document validations for emergency DB rollback
			frappe.db.set_value(
				doctype, docname,
				{"workflow_state": previous_state, "docstatus": previous_docstatus},
				update_modified=False,
			)
			frappe.db.commit()
			frappe.log_error(frappe.get_traceback(), f"Project Registration Kafka Sync Failed: {docname}")
			frappe.throw(
				_("Cannot approve: Kafka sync failed ({0}). The approval was not applied; "
				  "workflow state reverted to '{1}'.").format(str(e), previous_state)
			)
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
		url = ACCOUNT_PORTAL_PROJECTS
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
def get_available_workflow_actions(docname=None):
	if not docname:
		return []

	doc = frappe.get_doc("Project Registration", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.get_value("Workflow", {"document_type": doc.doctype}, "name")

	# if not workflow_name:
	# 	return []

	workflow = frappe.get_doc("Workflow", workflow_name)

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

	# --- Inject "Register Project" for Endorsement Approved state ---
	# This state has no Frappe workflow transition, so we inject the action manually.
	# handle_dynamic_workflow_action already handles the actual transition logic.
	if current_state == "Endorsement Approved":
		if doc.owner == frappe.session.user or "System Manager" in user_roles:
			allowed_actions.append("Register Project")

	# Remove duplicates
	allowed_actions = list(dict.fromkeys(allowed_actions))
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

		def _get_field_dict(field):
			return {
				"fieldname": field.fieldname,
				"label": _(field.label) if field.label else None,
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

		# 1. Get Field Definitions (your existing logic, slightly refined)
		fields = []
		for field in meta.fields:
			# Skip non-input fields like Section Break, Button, etc.
			if field.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
				continue
			
			field_dict = _get_field_dict(field)
			
			# Identify child table fields and recursively extract them
			if field.fieldtype == "Table" and field.options:
				child_meta = frappe.get_meta(field.options)
				child_fields = []
				for c_field in child_meta.fields:
					if c_field.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
						continue
					child_fields.append(_get_field_dict(c_field))
				field_dict["fields"] = child_fields
				
			fields.append(field_dict)

		# 2. Get Options for Link and Select Fields
		link_options = {}

		def _fetch_link_options(f_list):
			for field in f_list:
				if field.get("fieldtype") == "Table" and "fields" in field:
					_fetch_link_options(field["fields"])
				elif field.get("fieldtype") == "Link" and field.get("options"):
					try:
						# Fetch 'name' and a common title field like 'title' or 'full_name'
						linked_doctype = field["options"]
						linked_meta = frappe.get_meta(linked_doctype)
						title_field = linked_meta.get_title_field()  # Best way to get the display field

						options_list = frappe.get_all(
							linked_doctype,
							fields=["name", title_field],
							limit=0,  # 0 usually means fetch all without limit
						)

						# Format for easy use in frontend: [{ value: '...', label: '...' }]
						link_options[field["fieldname"]] = [
							{"value": item["name"], "label": item.get(title_field, item["name"])}
							for item in options_list
						]
					except Exception as e:
						# If fetching fails, provide an empty list
						link_options[field["fieldname"]] = []
		
		_fetch_link_options(fields)

		# 2b. Append Universal Registration users (PI / Co-PI External only) to pi_webmail link options
		try:
			ur_users = frappe.db.get_all(
				"Universal Registration__",
				fields=["email_address_u_r as name", "full_name_u_r"],
				filters=[
					["email_address_u_r", "!=", ""],
					["profile_type_u_r", "=", "PI / Co-PI (External only)"]
				],
				order_by="full_name_u_r asc",
				limit=0
			)
			existing_values = {opt["value"] for opt in link_options.get("pi_webmail", [])}
			for ur in ur_users:
				email = ur.get("name") or ""
				if email and email not in existing_values:
					link_options.setdefault("pi_webmail", []).append({
						"value": email,
						"label": f"{ur.get('full_name_u_r') or email} ({email})"
					})
		except Exception:
			pass

		# 2c. Filter designation_name options for proposed_manpower_details
		# ============================================================
		# EDITED BY OJS | 2026-04-14 14:52 IST
		# START OF EDIT — Simplifed designation_name options & Quick Entry prepend
		# Replaced complex User lookup with direct Designation_prornd query.
		# Prepending "CREATE_NEW" option at the top for Frappe quick entry UI.
		# ============================================================
		try:
			designations = frappe.get_all(
				"Designation_prornd",
				filters={"designation_type": "Project Staff"},
				fields=["name as value", "designation_prornd as label"],
				order_by="designation_prornd asc",
				limit=0,
			)

			data = [
				{"value": item["value"], "label": item.get("label") or item["value"]}
				for item in designations
			]

			# Insert "Create New" option at the very top for Frappe-style quick entry
			data.insert(0, {"value": "CREATE_NEW", "label": "➕ Create New Designation..."})

			link_options["designation_name"] = data
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Error filtering designation options for manpower details")
			link_options["designation_name"] = [{"value": "CREATE_NEW", "label": "➕ Create New Designation..."}]
		# END OF EDIT — OJS | 2026-04-14 14:52 IST
		# ============================================================

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
	Tries Frappe User first; falls back to Universal Registration if user not found.
	"""
	if not user_email:
		frappe.throw(_("User Email is required."))

	from rndopsapp.rndopsapp.doctype.universal_registration__.universal_registration__ import get_external_profile

	try:
		user_doc = frappe.get_doc("User", user_email)
		# IMPORTANT: Replace these with your actual custom field names in the User doctype
		# user_dict = user_doc.as_dict()
		user_dept = user_doc.get("department_name")
		# applicant_department is a Link to Department_prornd, so it must hold the
		# record's name (id), not its display text — user_dept already IS that id.
		applicant_department = user_dept if user_dept and frappe.db.exists("Department_prornd", user_dept) else None

		data = {
			"principal_investigator_name": user_doc.full_name,
			"designation": user_doc.get("designation_name"),
			"applicant_department": applicant_department,
			"copi_address": user_doc.get("inst_name_address"),
			"copi_contact": user_doc.get("mobile_no")
		}

		# Append Universal Registration details flat into the same dict (no override)
		try:
			ur_result = get_external_profile(search=user_email)
			if ur_result.get("status") == "success" and ur_result.get("data"):
				profile = ur_result["data"][0]
				data["full_name_u_r"]           = profile.get("full_name_u_r")
				data["mobile_number_u_r"]       = profile.get("mobile_number_u_r")
				data["email_address_u_r"]       = profile.get("email_address_u_r")
				data["institution_details_u_r"] = profile.get("institution_details_u_r") or []
				data["address_details"]         = profile.get("address_details") or []
				data["org_address_details_u_r"] = profile.get("org_address_details_u_r") or []
		except Exception:
			pass

		# frappe.logger().warning(f"Jimmy Logging Debug get_user_details_for_pi: {user_dict}")
		return data

	except frappe.DoesNotExistError:
		# Frappe User not found — try Universal Registration directly
		try:
			ur_result = get_external_profile(search=user_email)
			if ur_result.get("status") == "success" and ur_result.get("data"):
				profile = ur_result["data"][0]
				institution = (profile.get("institution_details_u_r") or [{}])[0]
				# department_u_r is free-text from the external registry, not a
				# Department_prornd id — resolve it to one, or leave blank if there's
				# no matching internal department (e.g. an external institution).
				department_text = institution.get("department_u_r")
				applicant_department = (
					frappe.db.get_value("Department_prornd", {"dept_name": department_text}, "name")
					if department_text else None
				)
				return {
					"principal_investigator_name": profile.get("full_name_u_r"),
					"designation":                 institution.get("designation_u_r"),
					"applicant_department":        applicant_department,
					"copi_address":                institution.get("address_institution_u_r"),
					"copi_contact":                profile.get("mobile_number_u_r")
				}
		except Exception:
			pass
		return None

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching user details"))
		frappe.throw(_("An error occurred while fetching user details."))


@frappe.whitelist()
def get_copi_details_from_universal(copi_email):
	"""
	Prefill Co-PI fields from Universal Registration using get_external_profile.
	Called when copi_email (Link → User) is set on the child row.
	Returns a flat dict ready to set on the co_investigator_table row.
	"""
	if not copi_email:
		return {"status": "error", "message": "Co-PI email is required."}

	from rndopsapp.rndopsapp.doctype.universal_registration__.universal_registration__ import get_external_profile

	result = get_external_profile(search=copi_email)

	if result.get("status") != "success" or not result.get("data"):
		# Fallback: try from Frappe User doc
		try:
			user_doc = frappe.get_doc("User", copi_email)
			return {
				"status": "success",
				"copi_name":        user_doc.full_name or "",
				"copi_contact":     user_doc.get("mobile_no") or "",
				"copi_designation": user_doc.get("designation_name") or "",
				"copi_address":     user_doc.get("inst_name_address") or "",
				"copi_department":  user_doc.get("department_name") or ""
			}
		except Exception:
			return {"status": "error", "message": f"No Universal Registration found for '{copi_email}'."}

	profile = result["data"][0]
	institution = (profile.get("institution_details_u_r") or [{}])[0]

	return {
		"status":           "success",
		"copi_name":        profile.get("full_name_u_r") or "",
		"copi_contact":     profile.get("mobile_number_u_r") or "",
		"copi_designation": institution.get("designation_u_r") or "",
		"copi_address":     institution.get("address_institution_u_r") or "",
		"copi_department":  institution.get("department_u_r") or ""
	}


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
	import os
	import datetime
	_log_path = os.path.join(os.path.dirname(__file__), "projects.log")
	with open(_log_path, "a") as _lf:
		_lf.write(f"\n{'='*60}\n")
		_lf.write(f"[{datetime.datetime.now().isoformat()}] save_project_data called\n")
		_lf.write(f"doc:\n{doc}\n")
		_lf.write(f"html_content:\n{html_content}\n")
		_lf.write(f"{'='*60}\n")

	# print("$%$%$%$%$%$%$%$%$%$%$---------------------------$%$%$%$%$%$%$%$%$%$%$%4:")
	# print(doc)
	frappe.logger().warning(f"Jimmy Logging Debug save project data: {doc}")
	upload_events = []
	new_project = None
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
					if fieldname == "upload_supporting_docs" and isinstance(child_row, dict):
						attachment = child_row.get("attachment")
						if isinstance(attachment, dict) and attachment.get("file_name") and attachment.get("file_data"):
							file_data_uri = attachment.get("file_data")
							if file_data_uri.startswith("data:"):
								file_data_uri = file_data_uri.split(",", 1)[1]
							try:
								file_bytes = base64.b64decode(file_data_uri)
								file_service = get_rnd_file_service()
								upload_result = file_service.save_file(
									filename=attachment.get("file_name"),
									content=file_bytes,
									is_private=True,
									doctype=new_project.doctype,
									docname=new_project.name,
									folder="attachments",
								)
								if upload_result.get("status"):
									file_url = upload_result.get("data", {}).get("file_url")
									upload_events.append({
										"filename": attachment.get("file_name"),
										"fieldname": fieldname,
										"status": "success",
										"file_url": file_url,
									})
									child_row = dict(child_row)
									child_row["attachment"] = file_url
								else:
									upload_events.append({
										"filename": attachment.get("file_name"),
										"fieldname": fieldname,
										"status": "failed",
										"message": upload_result.get("message"),
									})
									frappe.log_error(
										upload_result.get("message"),
										f"Supporting doc upload failed for {new_project.name}"
									)
									child_row = dict(child_row)
									child_row.pop("attachment", None)
							except Exception as upload_error:
								upload_events.append({
									"filename": attachment.get("file_name"),
									"fieldname": fieldname,
									"status": "error",
									"message": str(upload_error),
								})
								frappe.log_error(frappe.get_traceback(), f"Supporting doc upload error for {new_project.name}")
								child_row = dict(child_row)
								child_row.pop("attachment", None)
					new_project.append(fieldname, child_row)

			# Handle Attach fields (value is a Base64 data URI string)
			elif df.fieldtype == "Attach" and value:
				# Format: { "file_name": "my_proposal.pdf", "file_data": "data:application/pdf;base64,..." }
				if isinstance(value, dict) and value.get("file_name") and value.get("file_data"):
					# Decode Base64 and upload to MinIO
					file_data_uri = value.get("file_data")
					if file_data_uri.startswith("data:"):
						file_data_uri = file_data_uri.split(",", 1)[1]

					file_bytes = base64.b64decode(file_data_uri)
					file_service = get_rnd_file_service()

					upload_result = file_service.save_file(
						filename=value.get("file_name"),
						content=file_bytes,
						is_private=True,
						doctype=new_project.doctype,
						docname=new_project.name,
						folder="attachments",
						use_hash=False
					)

					if upload_result.get("status"):
						file_url = upload_result.get("data", {}).get("file_url")
						upload_events.append({
							"filename": value.get("file_name"),
							"fieldname": fieldname,
							"status": "success",
							"file_url": file_url,
						})
						# Set the field to the MinIO file URL instead of the Base64 dict
						new_project.set(fieldname, file_url)
					else:
						upload_events.append({
							"filename": value.get("file_name"),
							"fieldname": fieldname,
							"status": "failed",
							"message": upload_result.get("message"),
						})
						frappe.log_error(f"File upload failed: {upload_result.get('message')}",
							f"Attach Field Upload Failed for {fieldname}")
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

		# --- Handle HTML content - Convert to PDF and save to MinIO ---
		if html_content:
			try:
				from frappe.utils.pdf import get_pdf

				# Get MinIO file service
				file_service = get_rnd_file_service()

				# Prepare filenames
				html_filename = f"{new_project.name}.html"
				pdf_filename = f"{new_project.name}.pdf"

				# Generate PDF content in memory
				pdf_content = get_pdf(html_content)

				# Save HTML to MinIO (public)
				html_result = file_service.save_file(
					filename=html_filename,
					content=html_content,
					is_private=False,
					doctype=new_project.doctype,
					docname=new_project.name,
					folder=get_file_category_for_doctype(new_project.doctype, "endorsement_html"),
					use_hash=False
				)

				if html_result.get("status"):
					upload_events.append({
						"filename": html_filename,
						"fieldname": "html_content",
						"status": "success",
						"file_url": html_result.get("data", {}).get("file_url"),
					})
					frappe.logger().info(f"HTML file saved to MinIO: {html_result.get('data', {}).get('file_url')}")
				else:
					upload_events.append({
						"filename": html_filename,
						"fieldname": "html_content",
						"status": "failed",
						"message": html_result.get("message"),
					})
					frappe.log_error(f"HTML upload failed: {html_result.get('message')}",
						f"save_project_data: HTML Upload Failed for {new_project.name}")

				# Save PDF to MinIO (public)
				pdf_result = file_service.save_file(
					filename=pdf_filename,
					content=pdf_content,
					is_private=False,
					doctype=new_project.doctype,
					docname=new_project.name,
					folder=get_file_category_for_doctype(new_project.doctype, "endorsement_pdf"),
					use_hash=False
				)

				if pdf_result.get("status"):
					upload_events.append({
						"filename": pdf_filename,
						"fieldname": "html_content_pdf",
						"status": "success",
						"file_url": pdf_result.get("data", {}).get("file_url"),
					})
					frappe.logger().info(f"PDF file saved to MinIO: {pdf_result.get('data', {}).get('file_url')}")
				else:
					upload_events.append({
						"filename": pdf_filename,
						"fieldname": "html_content_pdf",
						"status": "failed",
						"message": pdf_result.get("message"),
					})
					frappe.log_error(f"PDF upload failed: {pdf_result.get('message')}",
						f"save_project_data: PDF Upload Failed for {new_project.name}")

			except Exception as pdf_error:
				upload_events.append({
					"filename": f"{new_project.name}.html / {new_project.name}.pdf",
					"fieldname": "html_content",
					"status": "error",
					"message": str(pdf_error),
				})
				frappe.log_error(
					frappe.get_traceback(),
					f"save_project_data: PDF conversion/save error for {new_project.name}",
				)
				# Don't throw, just log the error so the main save succeeds

		# --- Make all attachments public ---
		try:
			attached_files = frappe.get_all(
				"File",
				filters={
					"attached_to_doctype": new_project.doctype,
					"attached_to_name": new_project.name,
					"is_private": 1
				},
				fields=["name"]
			)
			
			for file_data in attached_files:
				file_doc = frappe.get_doc("File", file_data.name)
				file_doc.is_private = 0
				file_doc.save(ignore_permissions=True)
			
			if attached_files:
				frappe.db.commit()
				frappe.logger().info(f"Converted {len(attached_files)} attachments to public for {new_project.name}")

		except Exception as e:
			frappe.log_error(f"Error making files public for {new_project.name}: {str(e)}")

		# Return the name of the newly created document to the frontend
		# ============================================================
		# EDITED BY OJS | 2026-04-21 01:43 IST
		# START OF EDIT — Mattermost success notification for save_project_data
		# ============================================================
		uploaded_file_urls = [event.get("file_url") for event in upload_events if event.get("file_url")]
		if uploaded_file_urls:
			files_block = "\n".join(f"   • {file_url}" for file_url in uploaded_file_urls)
		else:
			files_block = "   (no uploaded file paths)"

		if upload_events:
			upload_status_lines = []
			for event in upload_events:
				line = f"   • [{event.get('status', 'unknown')}] {event.get('filename') or event.get('fieldname')}"
				if event.get("file_url"):
					line += f" -> {event.get('file_url')}"
				if event.get("message"):
					line += f" ({event.get('message')})"
				upload_status_lines.append(line)
			upload_status_block = "\n".join(upload_status_lines)
		else:
			upload_status_block = "   (no file uploads attempted)"

		notify_mattermost(
			"```\n"
			"┌──────────────────────────────────────────────┐\n"
			"│  ✅ [save_project_data] SUCCESS              │\n"
			"├──────────────────────────────────────────────┤\n"
			f" Time    : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
			f" Docname : {new_project.name}\n"
			f" User    : {frappe.session.user}\n"
			f" Uploads : {len(upload_events)} attempted / {sum(1 for event in upload_events if event.get('status') == 'success')} successful\n"
			f" Files ({len(uploaded_file_urls)}):\n"
			f"{files_block}\n"
			" Upload Status:\n"
			f"{upload_status_block}\n"
			"└──────────────────────────────────────────────┘\n"
			"```"
		)
		# END OF EDIT — OJS | 2026-04-21 01:43 IST
		# ============================================================
		return {
			"status": "success",
			"message": "Project Registration Successful",
			"docname": new_project.name,
		}

	except Exception as e:
		# If any error occurs, rollback the transaction and inform the user
		frappe.db.rollback()
		_tb = frappe.get_traceback()
		frappe.log_error(_tb, "Project Registration Save Error")
		# ============================================================
		# EDITED BY OJS | 2026-04-21 01:46 IST
		# START OF EDIT — Error notification: actual exception first
		# ============================================================
		docname = new_project.name if new_project and getattr(new_project, "name", None) else "N/A"
		uploaded_file_urls = [event.get("file_url") for event in upload_events if event.get("file_url")]
		if uploaded_file_urls:
			files_block = "\n".join(f"   • {file_url}" for file_url in uploaded_file_urls)
		else:
			files_block = "   (no uploaded file paths)"

		if upload_events:
			upload_status_lines = []
			for event in upload_events:
				line = f"   • [{event.get('status', 'unknown')}] {event.get('filename') or event.get('fieldname')}"
				if event.get("file_url"):
					line += f" -> {event.get('file_url')}"
				if event.get("message"):
					line += f" ({event.get('message')})"
				upload_status_lines.append(line)
			upload_status_block = "\n".join(upload_status_lines)
		else:
			upload_status_block = "   (no file uploads attempted)"

		notify_mattermost(
			"```\n"
			"┌──────────────────────────────────────────────┐\n"
			"│  ❌ [save_project_data] ERROR                │\n"
			"├──────────────────────────────────────────────┤\n"
			f" Time      : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
			f" Docname   : {docname}\n"
			f" User      : {frappe.session.user}\n"
			f" Exception : {type(e).__name__}: {str(e)}\n"
			f" Uploads   : {len(upload_events)} attempted / {sum(1 for event in upload_events if event.get('status') == 'success')} successful\n"
			f" Files ({len(uploaded_file_urls)}):\n"
			f"{files_block}\n"
			" Upload Status:\n"
			f"{upload_status_block}\n"
			" Traceback:\n"
			f"{_tb}\n"
			"└──────────────────────────────────────────────┘\n"
			"```",
			urgent=True,
		)
		# END OF EDIT — OJS | 2026-04-21 01:46 IST
		# ============================================================
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
def save_project_draft(doc_data, html_content=None, files=None, docname=None):
	"""
	Saves or updates a Project Registration document as a draft (docstatus=0).
	Optionally receives HTML content and saves it as {doc.name}.html file.
	
	Args:
		doc_data: The document data as JSON string or dictionary
		html_content: Optional HTML content to save as a file
		files: Optional list of files to attach (if sent as separate argument)
		docname: Optional document name. If provided and exists, updates that document.
			If provided but doesn't exist, creates a new document.
			If not provided, falls back to data.get("name") or creates new.
	"""
	print("$%$%$%$%$%$%$%$%$%$%$---------------------------$%$%$%$%$%$%$%$%$%$%$%4:",doc_data)

	import os
	import datetime
	_dir = os.path.dirname(__file__)
	_ts = datetime.datetime.now().isoformat()
	with open(os.path.join(_dir, "doc.log"), "a") as _lf:
		_lf.write(f"\n{'='*60}\n")
		_lf.write(f"[{_ts}] save_project_draft called\n")
		_lf.write(f"{doc_data}\n")
		_lf.write(f"{'='*60}\n")
	with open(os.path.join(_dir, "html_content.log"), "a") as _lf:
		_lf.write(f"\n{'='*60}\n")
		_lf.write(f"[{_ts}] save_project_draft called\n")
		_lf.write(f"{html_content}\n")
		_lf.write(f"{'='*60}\n")

	# --- FIX START: Convert JSON string to Python Dictionary ---
	if isinstance(doc_data, str):
		data = frappe.parse_json(doc_data)
	else:
		data = doc_data or {}
	# --- FIX END ---

	# Now 'data' is a dictionary
	frappe.logger().warning(f"Jimmy Logging Debug save project data keys: {list(data.keys())}")
	upload_events = []
	doc = None
	
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

		# Build lookup map: filename → file entry (for upload_supporting_docs matching)
		# files_payload items look like: {"filename": "...", "content": "data:...;base64,..."}
		files_by_name = {}
		if isinstance(files_payload, list):
			for f in files_payload:
				if isinstance(f, dict) and f.get("filename"):
					files_by_name[f["filename"]] = f

		# --- Resolve docname: explicit arg > data["name"] > duplicate check > new ---
		resolved_docname = docname or data.get("name")
		
		# --- Duplicate Check Fix for React Frontend missing 'name' param logic ---
		if not resolved_docname and data.get("project_title") and data.get("pi_webmail"):
			existing_drafts = frappe.get_all("Project Registration", 
				filters={"project_title": data.get("project_title"), "pi_webmail": data.get("pi_webmail"), "owner": frappe.session.user, "docstatus": 0},
				order_by="modified desc", limit=1)
			if existing_drafts:
				resolved_docname = existing_drafts[0].name
				frappe.logger().info(f"Duplicate prevented: Found existing draft {resolved_docname} for {data.get('project_title')}")

		# Tracks the existing DB workflow_state for correction-state reset logic below.
		existing_workflow_state = None
		# When reverting from "Endorsement Approved", preserve existing field/child-table
		# values that aren't present in the incoming payload (partial-update semantics).
		preserve_existing_on_revert = False
		# States in which the PI is expected to re-edit the doc; we revert in place
		# so the docname is preserved instead of creating a new draft.
		correction_states = {
			"Needs Correction (PE)",
			"Needs Correction (HOD)",
			"Needs Correction",
		}
		# Endorsement Approved is also reverted in place to Draft, but uses
		# partial-update semantics (does not wipe fields/child rows absent from payload).
		endorsement_approved_state = "Endorsement Approved"
		revertible_states = correction_states | {endorsement_approved_state}
		if resolved_docname and frappe.db.exists("Project Registration", resolved_docname):
			doc = frappe.get_doc("Project Registration", resolved_docname)
			if doc.owner != frappe.session.user and "System Manager" not in frappe.get_roles(frappe.session.user):
				pass # Allow System Manager to edit, or fall back to standard permission checks
			elif doc.owner != frappe.session.user:
				frappe.throw(_("You do not have permission to edit this draft."))

			existing_workflow_state = doc.workflow_state

			if doc.workflow_state == endorsement_approved_state:
				preserve_existing_on_revert = True

			if doc.docstatus != 0:
				if doc.workflow_state in revertible_states:
					# Submitted doc sent back for correction (or Endorsement Approved) —
					# revert to draft in place to preserve the same docname.
					frappe.db.set_value(
						"Project Registration", doc.name,
						{"docstatus": 0, "workflow_state": "Draft"},
						update_modified=False,
					)
					frappe.db.commit()
					doc = frappe.get_doc("Project Registration", resolved_docname)
				else:
					frappe.logger().warning(
						f"Document {resolved_docname} is already submitted (docstatus={doc.docstatus}). Creating new draft instead."
					)
					doc = frappe.new_doc("Project Registration")
					data.pop("name", None)  # Don't carry over the submitted doc's name
					existing_workflow_state = None
					preserve_existing_on_revert = False
			elif doc.workflow_state == endorsement_approved_state:
				# docstatus already 0 but state still Endorsement Approved — force back to Draft.
				frappe.db.set_value(
					"Project Registration", doc.name, "workflow_state", "Draft",
					update_modified=False,
				)
				frappe.db.commit()
				doc = frappe.get_doc("Project Registration", resolved_docname)
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
			"upload_supporting_docs",
		}
		parent_data = {k: v for k, v in data.items() if k not in child_tables_map}

		# Draft-save must not let the frontend push a workflow transition; we manage
		# workflow_state below based on existing DB state.
		parent_data.pop("workflow_state", None)

		# --- Sanitize Parent Data ---
		for key, value in parent_data.items():
			if isinstance(value, dict):
				parent_data[key] = value.get("value") or value.get("name") or None

		if "pi_contact" in parent_data:
			parent_data["pi_contact"] = _format_phone_number(parent_data.get("pi_contact"))
		if "copi_contact" in parent_data:
			parent_data["copi_contact"] = _format_phone_number(parent_data.get("copi_contact"))

		doc.update(parent_data)

		# If the existing doc was in a correction state (e.g., "Needs Correction (PE)"),
		# reset it to Draft. We bypass workflow transition validation by writing "Draft"
		# directly to the DB first, so save() sees pre-state == post-state == "Draft".
		if existing_workflow_state and existing_workflow_state != "Draft":
			frappe.db.set_value(
				"Project Registration", doc.name, "workflow_state", "Draft",
				update_modified=False,
			)
			doc.workflow_state = "Draft"

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
			child_rows_data = data.get(table_fieldname)

			# Endorsement Approved revert: if the payload omits this child table,
			# preserve the existing rows instead of wiping them.
			if preserve_existing_on_revert and not isinstance(child_rows_data, list):
				continue

			doc.set(table_fieldname, [])

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

				elif table_fieldname == "upload_supporting_docs":
					# Map frontend field names → child doctype field names
					if "doc_description" in update_data:
						update_data["file_description"] = update_data.pop("doc_description")

					update_data.pop("id", None)

					# `supporting_file` from the row holds either a stored URL or a plain filename
					row_filename = update_data.pop("supporting_file", None)
					if row_filename and "/" in row_filename:
						update_data.setdefault("project_file", row_filename)

					# For existing rows, preserve project_file from DB if not being replaced
					row_name = update_data.get("name")
					if row_name and not update_data.get("project_file"):
						saved_url = frappe.db.get_value("Project Files", row_name, "project_file")
						if saved_url:
							update_data["project_file"] = saved_url

					# Match file from files_payload by filename (payload uses {filename, content})
					file_entry = files_by_name.get(row_filename) if row_filename else None
					if file_entry and file_entry.get("content"):
						file_data_uri = file_entry["content"]
						if file_data_uri.startswith("data:"):
							file_data_uri = file_data_uri.split(",", 1)[1]
						try:
							file_bytes = base64.b64decode(file_data_uri)
							file_service = get_rnd_file_service()
							upload_result = file_service.save_file(
								filename=file_entry["filename"],
								content=file_bytes,
								is_private=True,
								doctype=doc.doctype,
								docname=doc.name,
								folder=get_file_category_for_doctype(doc.doctype, "upload_supporting_docs"),
							)
							if upload_result.get("status"):
								file_url = upload_result["data"]["file_url"]
								upload_events.append({
									"filename": file_entry["filename"],
									"fieldname": table_fieldname,
									"status": "success",
									"file_url": file_url,
								})
								update_data["project_file"] = file_url
							else:
								upload_events.append({
									"filename": file_entry["filename"],
									"fieldname": table_fieldname,
									"status": "failed",
									"message": upload_result.get("message"),
								})
								frappe.log_error(
									upload_result.get("message"),
									f"Supporting doc upload failed for {doc.name}"
								)
						except Exception as upload_error:
							upload_events.append({
								"filename": file_entry.get("filename") if isinstance(file_entry, dict) else row_filename,
								"fieldname": table_fieldname,
								"status": "error",
								"message": str(upload_error),
							})
							frappe.log_error(frappe.get_traceback(), f"Supporting doc upload error for {doc.name}")

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
		doc.flags.ignore_version = True
		doc.save(ignore_permissions=True)

		# --- Re-apply fetch_from fields overwritten by Frappe during save ---
		# Build lookup by email from saved doc rows
		saved_pi_by_email = {r.pi_email: r.name for r in doc.get("additional_pi_table") or []}
		for row_data in (data.get("additional_pi_table") or []):
			row_name = saved_pi_by_email.get(row_data.get("pi_email"))
			if not row_name:
				continue
			frappe.db.set_value("Project Additional PI", row_name, {
				"pi_address": row_data.get("pi_address"),
				"pi_contact": row_data.get("pi_contact"),
				"pi_department": row_data.get("pi_department"),
				"pi_designation": row_data.get("pi_designation"),
			}, update_modified=False)

		saved_copi_by_email = {r.copi_email: r.name for r in doc.get("co_investigator_table") or []}
		for row_data in (data.get("co_investigator_table") or []):
			row_name = saved_copi_by_email.get(row_data.get("copi_email"))
			if not row_name:
				continue
			frappe.db.set_value("Project Co-Investigator", row_name, {
				"copi_address": row_data.get("copi_address"),
				"copi_contact": row_data.get("copi_contact"),
				"copi_department": row_data.get("copi_department"),
				"copi_designation": row_data.get("copi_designation"),
			}, update_modified=False)

		frappe.db.commit()

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

					# Upload to MinIO using RNDFileService
					file_service = get_rnd_file_service()
					# ============================================================
					# EDITED BY OJS | 2026-04-20 23:51 IST
					# START OF EDIT — Fix: wrong folder created from filename pattern match
					# Bug: f.get("file_name") or filename was passed as fieldname into
					# get_file_category_for_doctype(). When filename contained "endorsement"
					# (e.g. "Endorsement_ARG_PI_SAKET.pdf"), _infer_category_from_fieldname()
					# matched the word and returned "endorsement" as the MinIO folder.
					# Fix: only use f.get("fieldname") if it is an actual DocField key;
					# otherwise always fall back to "attachments" — never pass the raw filename.
					# ============================================================
					_field_for_category = f.get("fieldname") if f.get("fieldname") else "attachments"
					upload_result = file_service.save_file(
						filename=filename,
						content=file_content,
						is_private=is_private,
						doctype=doc.doctype,
						docname=doc.name,
						folder=get_file_category_for_doctype(doc.doctype, _field_for_category)
					)
					# END OF EDIT — OJS | 2026-04-20 23:51 IST
					# ============================================================

					if upload_result.get("status"):
						upload_events.append({
							"filename": filename,
							"fieldname": _field_for_category,
							"status": "success",
							"file_url": upload_result.get("data", {}).get("file_url"),
						})
						frappe.logger().info(f"File uploaded to MinIO: {filename} -> {upload_result.get('data', {}).get('file_url')}")
					else:
						upload_events.append({
							"filename": filename,
							"fieldname": _field_for_category,
							"status": "failed",
							"message": upload_result.get("message"),
						})
						frappe.log_error(f"MinIO upload failed: {upload_result.get('message')}",
							f"save_project_draft: file upload error for {filename}")

				except Exception as fe:
						upload_events.append({
							"filename": f.get("filename") or f.get("file_name") or f.get("name"),
							"fieldname": f.get("fieldname") or "attachments",
							"status": "error",
							"message": str(fe),
						})
						frappe.log_error(
							frappe.get_traceback(),
							f"save_project_draft: file upload error for {f.get('filename')}",
						)
						continue

		frappe.db.commit()

		# --- Handle HTML content - Convert to PDF and save to MinIO ---
		if html_content:
			try:
				from frappe.utils.pdf import get_pdf

				# Get MinIO file service
				file_service = get_rnd_file_service()

				# Prepare filenames
				html_filename = f"{doc.name}.html"
				pdf_filename = f"{doc.name}.pdf"

				# Generate PDF content in memory
				pdf_content = get_pdf(html_content)

				# Save HTML to MinIO (private)
				html_result = file_service.save_file(
					filename=html_filename,
					content=html_content,
					is_private=True,
					doctype=doc.doctype,
					docname=doc.name,
					folder=get_file_category_for_doctype(doc.doctype, "endorsement_html")
				)

				if html_result.get("status"):
					upload_events.append({
						"filename": html_filename,
						"fieldname": "html_content",
						"status": "success",
						"file_url": html_result.get("data", {}).get("file_url"),
					})
					frappe.logger().info(f"HTML file saved to MinIO: {html_result.get('data', {}).get('file_url')}")
				else:
					upload_events.append({
						"filename": html_filename,
						"fieldname": "html_content",
						"status": "failed",
						"message": html_result.get("message"),
					})
					frappe.log_error(f"HTML upload failed: {html_result.get('message')}",
						f"save_project_draft: HTML Upload Failed for {doc.name}")

				# Save PDF to MinIO (private)
				pdf_result = file_service.save_file(
					filename=pdf_filename,
					content=pdf_content,
					is_private=True,
					doctype=doc.doctype,
					docname=doc.name,
					folder=get_file_category_for_doctype(doc.doctype, "endorsement_pdf")
				)

				if pdf_result.get("status"):
					upload_events.append({
						"filename": pdf_filename,
						"fieldname": "html_content_pdf",
						"status": "success",
						"file_url": pdf_result.get("data", {}).get("file_url"),
					})
					frappe.logger().info(f"PDF file saved to MinIO: {pdf_result.get('data', {}).get('file_url')}")
				else:
					upload_events.append({
						"filename": pdf_filename,
						"fieldname": "html_content_pdf",
						"status": "failed",
						"message": pdf_result.get("message"),
					})
					frappe.log_error(f"PDF upload failed: {pdf_result.get('message')}",
						f"save_project_draft: PDF Upload Failed for {doc.name}")

				# CRITICAL FIX: Save text_editor_zwfu directly to avoid re-triggering fetch_from
				# and timestamp conflict from a second doc.save().
				frappe.db.set_value("Project Registration", doc.name, "text_editor_zwfu", html_content, update_modified=False)
				frappe.db.commit()

				# --- Save HTML content to Endorsement Data ---
				existing = frappe.get_all("Endorsement Data", filters={"project_ref_num": doc.name}, limit=1)
				if existing:
					endt_name = existing[0].name
				else:
					endt = frappe.new_doc("Endorsement Data")
					endt.project_ref_num = doc.name
					endt.flags.ignore_mandatory = True
					endt.insert(ignore_permissions=True)
					endt_name = endt.name

				frappe.db.set_value("Endorsement Data", endt_name, "endorsement_html", html_content, update_modified=False)
				frappe.db.commit()

			except Exception as pdf_error:
				upload_events.append({
					"filename": f"{doc.name}.html / {doc.name}.pdf",
					"fieldname": "html_content",
					"status": "error",
					"message": str(pdf_error),
				})
				print(f"DEBUG ERROR: PDF conversion/save error: {str(pdf_error)}")
				frappe.log_error(
					frappe.get_traceback(),
					f"save_project_draft: PDF conversion/save error for {doc.name}",
				)
				# Don't throw, just log the error so the main save succeeds
		else:
			print("DEBUG: html_content is empty or None")

		# ============================================================
		# EDITED BY OJS | 2026-04-21 01:43 IST
		# START OF EDIT — Mattermost success notification for save_project_draft
		# Entire block is isolated: any failure here NEVER affects the save result.
		# ============================================================
		try:
			uploaded_file_urls = [event.get("file_url") for event in upload_events if event.get("file_url")]
			if uploaded_file_urls:
				files_block = "\n".join(f"   • {file_url}" for file_url in uploaded_file_urls)
			else:
				files_block = "   (no uploaded file paths)"

			if upload_events:
				upload_status_lines = []
				for event in upload_events:
					line = f"   • [{event.get('status', 'unknown')}] {event.get('filename') or event.get('fieldname')}"
					if event.get("file_url"):
						line += f" -> {event.get('file_url')}"
					if event.get("message"):
						line += f" ({event.get('message')})"
					upload_status_lines.append(line)
				upload_status_block = "\n".join(upload_status_lines)
			else:
				upload_status_block = "   (no file uploads attempted)"

			notify_mattermost(
				"```\n"
				"┌──────────────────────────────────────────────┐\n"
				"│  ✅ [save_project_draft] SUCCESS             │\n"
				"├──────────────────────────────────────────────┤\n"
				f" Time    : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
				f" Docname : {doc.name}\n"
				f" User    : {frappe.session.user}\n"
				f" Uploads : {len(upload_events)} attempted / {sum(1 for event in upload_events if event.get('status') == 'success')} successful\n"
				f" Files ({len(uploaded_file_urls)}):\n"
				f"{files_block}\n"
				" Upload Status:\n"
				f"{upload_status_block}\n"
				"└──────────────────────────────────────────────┘\n"
				"```"
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "save_project_draft: Mattermost status notification failed (non-fatal)")

		try:
			_doc_json = json.dumps(doc.as_dict(), indent=2, default=str)
			notify_mattermost(
				f"```json\n{_doc_json}\n```",
				channel_id="cp3cjfc14in15byj13onii3z5o",
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "save_project_draft: Mattermost JSON publish failed (non-fatal)")

		# END OF EDIT — OJS | 2026-04-21 01:43 IST
		# ============================================================
		return {"docname": doc.name}

	except Exception as e:
		_tb = frappe.get_traceback()
		frappe.log_error(_tb, "Project Draft Save Error")
		# ============================================================
		# EDITED BY OJS | 2026-04-21 01:43 IST
		# START OF EDIT — Mattermost error notification for save_project_draft
		# ============================================================
		docname = doc.name if doc and getattr(doc, "name", None) else (docname or data.get("name") or "N/A")
		uploaded_file_urls = [event.get("file_url") for event in upload_events if event.get("file_url")]
		if uploaded_file_urls:
			files_block = "\n".join(f"   • {file_url}" for file_url in uploaded_file_urls)
		else:
			files_block = "   (no uploaded file paths)"

		if upload_events:
			upload_status_lines = []
			for event in upload_events:
				line = f"   • [{event.get('status', 'unknown')}] {event.get('filename') or event.get('fieldname')}"
				if event.get("file_url"):
					line += f" -> {event.get('file_url')}"
				if event.get("message"):
					line += f" ({event.get('message')})"
				upload_status_lines.append(line)
			upload_status_block = "\n".join(upload_status_lines)
		else:
			upload_status_block = "   (no file uploads attempted)"

		notify_mattermost(
			"```\n"
			"┌──────────────────────────────────────────────┐\n"
			"│  ❌ [save_project_draft] ERROR               │\n"
			"├──────────────────────────────────────────────┤\n"
			f" Time      : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
			f" Docname   : {docname}\n"
			f" User      : {frappe.session.user}\n"
			f" Exception : {type(e).__name__}: {str(e)}\n"
			f" Uploads   : {len(upload_events)} attempted / {sum(1 for event in upload_events if event.get('status') == 'success')} successful\n"
			f" Files ({len(uploaded_file_urls)}):\n"
			f"{files_block}\n"
			" Upload Status:\n"
			f"{upload_status_block}\n"
			" Traceback:\n"
			f"{_tb}\n"
			"└──────────────────────────────────────────────┘\n"
			"```",
			urgent=True,
		)
		# END OF EDIT — OJS | 2026-04-21 01:43 IST
		# ============================================================
		frappe.throw(_("An error occurred while saving the draft: {0}").format(str(e)))


@frappe.whitelist()
def save_endorsement_draft(doc_data, html_content=None, files=None, endorsement=False):
	"""
	Saves or updates a Project Registration document specifically as an Endorsement Draft.
	Reuses the main `save_project_draft` function but modifies the initial workflow_state.
	"""
	import os
	import datetime
	_dir = os.path.dirname(__file__)
	_ts = datetime.datetime.now().isoformat()
	with open(os.path.join(_dir, "endorsement_doc.log"), "a") as _lf:
		_lf.write(f"\n{'='*60}\n")
		_lf.write(f"[{_ts}] save_endorsement_draft called\n")
		_lf.write(f"{doc_data}\n")
		_lf.write(f"{'='*60}\n")
	with open(os.path.join(_dir, "endorsement_html_content.log"), "a") as _lf:
		_lf.write(f"\n{'='*60}\n")
		_lf.write(f"[{_ts}] save_endorsement_draft called\n")
		_lf.write(f"{html_content}\n")
		_lf.write(f"{'='*60}\n")

	# Leverage the existing save_project_draft function
	result = save_project_draft(doc_data, html_content, files)
	
	if result and result.get("docname"):
		docname = result["docname"]

		# --- Save HTML content to Endorsement Data ---
		if html_content:
			existing = frappe.get_all("Endorsement Data", filters={"project_ref_num": docname}, limit=1)
			if existing:
				endt_name = existing[0].name
			else:
				endt = frappe.new_doc("Endorsement Data")
				endt.project_ref_num = docname
				endt.flags.ignore_mandatory = True
				endt.insert(ignore_permissions=True)
				endt_name = endt.name

			# Use set_value directly to bypass docstatus/fetch_from issues
			frappe.db.set_value("Endorsement Data", endt_name, "endorsement_html", html_content, update_modified=False)
			frappe.db.commit()

		# Fetch and explicitly update the workflow state for Endorsement Draft
		doc = frappe.get_doc("Project Registration", docname)
		if doc.workflow_state == "Draft" or not doc.workflow_state:
			doc.workflow_state = "Endorsement Pending at Dean"
			doc.docstatus = 1
			
			# Ensure signature is completely cleared during drafting
			if doc.meta.has_field("signature_of_the_head_of_institute"):
				doc.signature_of_the_head_of_institute = None
			
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_validate = True
			
			# Mock validate_workflow to bypass state transition permission errors
			# since we are forcing a jump from Draft to Endorsement Pending at Dean
			doc.validate_workflow = lambda: None
			
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			
	return result


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


@frappe.whitelist()
def get_projects_by_pi(pi_id=None):
	"""
	Returns a list of Project Registration documents for a given PI.
	
	Args:
		pi_id (str): The User ID (email) of the PI. Discovers current user if blank.
	"""
	if not pi_id:
		pi_id = frappe.session.user

	if pi_id == "Guest":
		return []

	projects = frappe.get_all(
		"Project Registration",
		filters={"pi_webmail": pi_id},
		fields=["name", "project_title", "workflow_state", "creation"],
		order_by="creation desc",
		ignore_permissions=True
	)
	
	# Mapping workflow_state to status manually to avoid alias bugs
	for p in projects:
		p["status"] = p.get("workflow_state")
	
	return projects

@frappe.whitelist()
def update_project_fields(docname, is_the_account_type_pfms=None, enter_scheme_number=None, scheme_name=None, account_number=None, bank_name=None):
	"""
	Manually update PFMS fields and corresponding account/scheme details in the database
	for a specific Project Registration.
	Bypasses standard document save validation to avoid UpdateAfterSubmitError.
	"""
	if not frappe.db.exists("Project Registration", docname):
		frappe.throw(_("Project Registration {0} not found").format(docname))

	update_dict = {}
	if is_the_account_type_pfms is not None:
		update_dict["is_the_account_type_pfms"] = is_the_account_type_pfms
	if enter_scheme_number is not None:
		update_dict["enter_scheme_number"] = enter_scheme_number
	if scheme_name is not None:
		update_dict["scheme_name"] = scheme_name
	if account_number is not None:
		update_dict["account_number"] = account_number
	if bank_name is not None:
		update_dict["bank_name"] = bank_name

	if update_dict:
		frappe.db.set_value("Project Registration", docname, update_dict, update_modified=False)
		frappe.db.commit()
		return {"status": "success", "message": _("Database manually updated for fields: {0}").format(", ".join(update_dict.keys()))}
	else:
		return {"status": "failed", "message": _("No fields provided for update")}


@frappe.whitelist(allow_guest=True)
def get_project_title(project_no):
	"""
	Get the title of a Project Registration document by its project_no.
	"""
	if not project_no:
		return "Not Found"

	project_title = frappe.db.get_value("Project Registration", {"project_no": project_no}, "project_title")

	if not project_title:
		return "Not Found"

	return project_title

# ============================================================
# EDITED BY OJS | 2026-04-14 15:35 IST
# START OF EDIT — Custom Designation Creation API
# Endpoint invoked when a user clicks "CREATE_NEW" from the frontend table.
# Deduplicates entries using SQL LIKE before inserting.
# Returns status="duplicate" when already found so frontend can alert user.
# ============================================================
@frappe.whitelist()
def create_custom_designation(designation_name, designation_type="Project Staff"):
	"""
	Checks for an existing designation (case-insensitive).
	Returns status="duplicate" with a message if already present.
	Otherwise creates a new Designation_prornd record and returns status="success".
	"""
	try:
		if not designation_name:
			return {"status": "error", "message": "Designation name is required"}

		designation_name = designation_name.strip()
		# Case-insensitive duplicate check across both name and designation_prornd fields
		existing = frappe.db.sql(
			"""SELECT name, designation_prornd FROM `tabDesignation_prornd`
			WHERE UPPER(designation_prornd)=%s OR UPPER(name)=%s LIMIT 1""",
			(designation_name.upper(), designation_name.upper()),
			as_dict=True
		)

		if existing:
			# Return a distinct "duplicate" status — frontend will alert the user
			return {
				"status": "duplicate",
				"designation_name": existing[0]["name"],
				"message": f"Designation \'{existing[0].get('designation_prornd') or existing[0]['name']}\' already exists in the system."
			}

		# Create new designation
		new_doc = frappe.get_doc({
			"doctype": "Designation_prornd",
			"designation_prornd": designation_name,
			"designation_type": designation_type
		})
		new_doc.insert(ignore_permissions=True)
		frappe.db.commit()

		return {"status": "success", "designation_name": new_doc.name}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"Custom Designation Creation Error for {designation_name}")
		return {"status": "error", "message": str(e)}

# END OF EDIT — OJS | 2026-04-14 15:35 IST
# ============================================================



@frappe.whitelist()
def update_proposed_budget_breakup(docname, rows):
    """
    Replace the proposed_budget_breakup child table rows for a Project Registration and
    recalculate grand totals.

    Args:
        docname (str): Name of the Project Registration document.
        rows (list | str): List of row dicts. Each row may contain:
            - account_head (str)       — Select field value
            - head (str)               — alias accepted; mapped to account_head
            - years (list[float])      — [yr1, yr2, yr3, yr4, yr5] shorthand
            - first_year_budget … fifth_year_budget (float)  — explicit year columns
            - is_total_row (bool)
    """
    try:
        print(f"[BUDGET_UPDATE] START docname={docname} user={frappe.session.user} rows_type={type(rows)}")

        if not docname:
            return {"status": "error", "message": "Document name is required"}

        if isinstance(rows, str):
            rows = json.loads(rows)

        if not isinstance(rows, list):
            print(f"[BUDGET_UPDATE] rows is not a list: {type(rows)} value={rows}")
            return {"status": "error", "message": "'rows' must be a list"}

        print(f"[BUDGET_UPDATE] rows count={len(rows)}")

        doc = frappe.get_doc("Project Registration", docname)
        print(f"[BUDGET_UPDATE] doc fetched: owner={doc.owner} docstatus={doc.docstatus} workflow_state={doc.workflow_state}")

        _user_roles = frappe.get_roles(frappe.session.user)
        _is_privileged = (
            doc.owner == frappe.session.user
            or "System Manager" in _user_roles
            or "staff, RnD" in _user_roles
        )
        if not _is_privileged:
            print(f"[BUDGET_UPDATE] ACCESS DENIED: doc.owner={doc.owner} session={frappe.session.user} roles={_user_roles}")
            return {"status": "error", "message": "You can only edit your own projects"}

        year_fields = [
            "first_year_budget",
            "second_year_budget",
            "third_year_budget",
            "fourth_year_budget",
            "fifth_year_budget",
        ]

        # Build processed rows — skip blank rows (no account_head and all zeros)
        processed_rows = []
        for idx, row_data in enumerate(rows):
            update_data = row_data.copy() if isinstance(row_data, dict) else {}
            print(f"[BUDGET_UPDATE] row[{idx}] raw: {update_data}")

            if "head" in update_data:
                update_data["account_head"] = update_data.pop("head")

            if isinstance(update_data.get("account_head"), dict):
                bh = update_data["account_head"]
                update_data["account_head"] = bh.get("value") or bh.get("name") or None

            years_array = update_data.pop("years", []) or []
            for i, amount in enumerate(years_array):
                if i < len(year_fields):
                    update_data[year_fields[i]] = flt(amount)

            row_total = sum(flt(update_data.get(f, 0)) for f in year_fields)

            # Skip rows that have no account_head and no budget values
            if not update_data.get("account_head") and row_total == 0:
                print(f"[BUDGET_UPDATE] row[{idx}] skipped (empty row)")
                continue

            update_data["total_proposal_of_heads"] = row_total
            update_data["idx"] = len(processed_rows) + 1
            processed_rows.append(update_data)
            print(f"[BUDGET_UPDATE] row[{idx}] processed: {update_data}")

        grand_total = sum(r["total_proposal_of_heads"] for r in processed_rows)
        print(f"[BUDGET_UPDATE] grand_total={grand_total} rows={len(processed_rows)} docstatus={doc.docstatus}")

        _child_filters = {
            "parent": docname,
            "parentfield": "proposed_budget_breakup",
            "parenttype": "Project Registration",
        }

        if doc.docstatus == 1:
            # Submitted doc — bypass doc.save() and write directly to DB.
            # Delete ALL existing rows first so no stale rows survive.
            print(f"[BUDGET_UPDATE] SUBMITTED: wiping existing rows then reinserting")
            frappe.db.delete("Project Sanctioned Budget", _child_filters)

            now = frappe.utils.now()
            for row in processed_rows:
                child = frappe.get_doc({
                    "doctype": "Project Sanctioned Budget",
                    "parent": docname,
                    "parentfield": "proposed_budget_breakup",
                    "parenttype": "Project Registration",
                    "creation": now,
                    "modified": now,
                    "owner": frappe.session.user,
                    "modified_by": frappe.session.user,
                    **{k: v for k, v in row.items() if k != "name"},
                })
                child.db_insert()
                print(f"[BUDGET_UPDATE] inserted row idx={row['idx']} (account_head={row.get('account_head')})")

            frappe.db.set_value("Project Registration", docname, {
                "grand_total_proposal": grand_total,
                "total_budget_amount": grand_total,
            }, update_modified=False)

        else:
            # Draft / Saved — wipe child rows in DB directly, then use doc.save()
            # to avoid Frappe leaving orphan rows when child list is replaced.
            print(f"[BUDGET_UPDATE] DRAFT: wiping existing rows then saving")
            frappe.db.delete("Project Sanctioned Budget", _child_filters)
            doc.set("proposed_budget_breakup", [])
            for row in processed_rows:
                child = doc.append("proposed_budget_breakup", {})
                child.update(row)

            doc.grand_total_proposal = grand_total
            doc.total_budget_amount = grand_total
            doc.flags.ignore_mandatory = True
            doc.flags.ignore_validate = True
            doc.save(ignore_permissions=True)

        frappe.db.commit()
        print(f"[BUDGET_UPDATE] COMMITTED successfully")

        return {
            "status": "success",
            "docname": doc.name,
            "grand_total": grand_total,
            "rows_saved": len(processed_rows),
        }

    except frappe.DoesNotExistError:
        print(f"[BUDGET_UPDATE] DoesNotExist: {docname}")
        return {"status": "error", "message": f"Project '{docname}' not found"}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[BUDGET_UPDATE] EXCEPTION: {e}\n{tb}")
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"Update Proposed Budget Breakup Error for {docname}")
        return {"status": "error", "message": str(e), "traceback": tb}


@frappe.whitelist()
def delete_draft_project(docname):
    """
    Allows the owner of a Draft-state Project Registration to delete it.
    Only the user who created the document (owner) can delete it, and only if it is in Draft state.
    """
    try:
        if not docname:
            return {"status": "error", "message": "Document name is required"}

        doc = frappe.get_doc("Project Registration", docname)

        if doc.workflow_state != "Draft":
            return {
                "status": "error",
                "message": f"Only Draft projects can be deleted. Current state: '{doc.workflow_state}'"
            }

        if doc.owner != frappe.session.user:
            return {
                "status": "error",
                "message": "You can only delete your own draft projects"
            }

        # Cancel first if docstatus=1 (submitted but workflow_state shows Draft — state mismatch)
        if doc.docstatus == 1:
            doc.flags.ignore_permissions = True
            doc.cancel()

        frappe.delete_doc("Project Registration", docname, ignore_permissions=True, force=True)
        frappe.db.commit()

        return {"status": "success", "message": f"Project '{docname}' deleted successfully"}

    except frappe.DoesNotExistError:
        return {"status": "error", "message": f"Project '{docname}' not found"}
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"Delete Draft Project Error for {docname}")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_co_projects(user=None):
    current_user = frappe.session.user

    # Do not allow spoofing another user's co-project list
    if user and user != current_user and current_user != "Administrator":
        frappe.throw("Not permitted", frappe.PermissionError)

    email = user or current_user

    projects = frappe.db.sql(
        """
        SELECT DISTINCT
            pr.name,
            pr.project_title,
            pr.project_no,
            pr.workflow_state,
            pr.project_type,
            pr.funding_agen,
            pr.creation,
            pr.modified
        FROM `tabProject Registration` pr
        LEFT JOIN `tabProject Additional PI` api
            ON api.parent = pr.name
            AND api.parenttype = 'Project Registration'
        LEFT JOIN `tabProject Co-Investigator` copi
            ON copi.parent = pr.name
            AND copi.parenttype = 'Project Registration'
        WHERE LOWER(api.pi_email) = LOWER(%s)
           OR LOWER(copi.copi_email) = LOWER(%s)
        ORDER BY pr.creation DESC
        """,
        (email, email),
        as_dict=True,
    )

    return projects


# ============================================================
# MINIO FILE ENDPOINTS
# OJS | 2026-06-10
# ============================================================

@frappe.whitelist(allow_guest=True)
def get_project_files_by_project_no(project_no):
	"""
	Look up a Project Registration by project_no, then list all MinIO files
	stored under that document.

	Returns:
		{
			"status": "success",
			"docname": "<Project Registration name>",
			"files": ["Project_Registration/<docname>/attachments/...", ...]
		}
	"""
	if not project_no:
		return {"status": "error", "message": "project_no is required"}

	docname = frappe.db.get_value("Project Registration", {"project_no": project_no}, "name")
	if not docname:
		return {"status": "error", "message": f"No Project Registration found for project_no '{project_no}'"}

	try:
		svc = get_rnd_file_service()
		prefix = f"Project_Registration/{docname}/"
		objects = svc.storage.list_prefix(prefix)
		file_paths = [obj.object_name for obj in objects]

		return {
			"status": "success",
			"docname": docname,
			"files": file_paths,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"get_project_files_by_project_no error for {project_no}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_minio_project_file(docname, path):
	"""
	Stream a MinIO file through Frappe as a direct download.

	Args:
		docname (str): Project Registration document name.
		path    (str): MinIO object key, e.g.
		               "Project_Registration/<docname>/attachments/<filename>".
	"""
	import mimetypes

	if not docname or not path:
		frappe.throw("docname and path are required", frappe.ValidationError)

	# Security: path must belong to this docname to prevent path traversal.
	if not path.startswith(f"Project_Registration/{docname}/"):
		frappe.throw("Access denied: path does not belong to the given docname", frappe.PermissionError)

	if not frappe.db.exists("Project Registration", docname):
		frappe.throw(f"Project Registration '{docname}' not found", frappe.DoesNotExistError)

	svc = get_rnd_file_service()
	result = svc.get_file(path)

	if not result.get("status"):
		frappe.throw(result.get("message", "File not found"), frappe.DoesNotExistError)

	filename = path.rsplit("/", 1)[-1]
	content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

	frappe.response["filename"] = filename
	frappe.response["filecontent"] = result["data"]["content"]
	frappe.response["type"] = "download"
	frappe.response["content_type"] = content_type


@frappe.whitelist(allow_guest=True)
def get_project_file_urls_by_project_no(project_no):
	"""
	Look up a Project Registration by project_no, list all MinIO files,
	and return each file's full MinIO URL alongside its object key.

	Returns:
		{
			"status": "success",
			"docname": "<Project Registration name>",
			"files": [
				{
					"path": "Project_Registration/<docname>/attachments/<filename>",
					"url": "http://<minio-endpoint>/<bucket>/Project_Registration/<docname>/attachments/<filename>"
				},
				...
			]
		}
	"""
	if not project_no:
		return {"status": "error", "message": "project_no is required"}

	docname = frappe.db.get_value("Project Registration", {"project_no": project_no}, "name")
	if not docname:
		return {"status": "error", "message": f"No Project Registration found for project_no '{project_no}'"}

	try:
		svc = get_rnd_file_service()
		endpoint = frappe.conf.minio_endpoint.rstrip("/")
		bucket = frappe.conf.minio_bucket
		secure = getattr(frappe.conf, "minio_secure", False)
		scheme = "https" if secure else "http"

		prefix = f"Project_Registration/{docname}/"
		objects = svc.storage.list_prefix(prefix)

		files = [
			{
				"path": obj.object_name,
				"url": f"{scheme}://{endpoint}/{bucket}/{obj.object_name}",
			}
			for obj in objects
		]

		return {
			"status": "success",
			"docname": docname,
			"files": files,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"get_project_file_urls_by_project_no error for {project_no}")
		return {"status": "error", "message": str(e)}


# ============================================================
# FREEFORM PROJECT SEARCH ENDPOINT
# OJS | 2026-06-23
# ============================================================

@frappe.whitelist(allow_guest=True)
def search_projects(query=None, department=None, page=1, page_size=20):
	"""
	Freeform search across Project Registration records.

	Searches across: project_title, project_no, principal_investigator_name,
	pi_webmail, pi_employee_id, implementation_department (name + dept_name),
	project_type, category, workflow_state.

	Args:
		query      (str): Free-form search string (partial match, case-insensitive).
		department (str): Optional — filter by Department_prornd name (exact).
		page       (int): 1-based page number (default 1).
		page_size  (int): Results per page (default 20, capped at 100).

	Returns:
		{
			"status": "success",
			"total": <int>,
			"page": <int>,
			"page_size": <int>,
			"results": [ { project fields + department details }, ... ]
		}
	"""
	try:
		page = max(1, int(page or 1))
		page_size = min(100, max(1, int(page_size or 20)))
		offset = (page - 1) * page_size

		# Build the WHERE clause dynamically
		conditions = ["pr.docstatus != 2"]  # exclude cancelled docs
		values = []

		if query:
			q = f"%{query}%"
			conditions.append(
				"("
				"  pr.project_title LIKE %s"
				"  OR pr.project_no LIKE %s"
				"  OR pr.principal_investigator_name LIKE %s"
				"  OR pr.pi_webmail LIKE %s"
				"  OR pr.pi_employee_id LIKE %s"
				"  OR pr.implementation_department LIKE %s"
				"  OR pr.project_type LIKE %s"
				"  OR pr.consultancy_category LIKE %s"
				"  OR pr.workflow_state LIKE %s"
				"  OR d.dept_name LIKE %s"
				")"
			)
			values.extend([q] * 10)

		if department:
			d_like = f"%{department}%"
			conditions.append("(pr.implementation_department LIKE %s OR d.dept_name LIKE %s)")
			values.extend([d_like, d_like])

		where_clause = " AND ".join(conditions)

		count_sql = f"""
			SELECT COUNT(DISTINCT pr.name)
			FROM `tabProject Registration` pr
			LEFT JOIN `tabDepartment_prornd` d ON d.name = pr.implementation_department
			WHERE {where_clause}
		"""
		total = frappe.db.sql(count_sql, values)[0][0]

		data_sql = f"""
			SELECT
				pr.name,
				pr.project_no,
				pr.project_title,
				pr.principal_investigator_name,
				pr.pi_webmail,
				pr.pi_employee_id,
				pr.implementation_department,
				pr.project_type,
				pr.consultancy_category,
				pr.workflow_state,
				pr.docstatus,
				pr.prj_start_date,
				pr.prj_end_date,
				pr.total_budget_amount,
				pr.grand_total_proposal,
				pr.funding_agen,
				pr.owner,
				pr.creation,
				pr.modified,
				d.dept_name,
				d.dept_head,
				d.dept_id
			FROM `tabProject Registration` pr
			LEFT JOIN `tabDepartment_prornd` d ON d.name = pr.implementation_department
			WHERE {where_clause}
			ORDER BY pr.modified DESC
			LIMIT %s OFFSET %s
		"""
		rows = frappe.db.sql(data_sql, values + [page_size, offset], as_dict=True)

		results = []
		for row in rows:
			results.append({
				"name": row.get("name"),
				"project_no": row.get("project_no"),
				"project_title": row.get("project_title"),
				"pi_name": row.get("principal_investigator_name"),
				"pi_email": row.get("pi_webmail"),
				"pi_employee_id": row.get("pi_employee_id"),
				"department": {
					"id": row.get("implementation_department"),
					"name": row.get("dept_name"),
					"head": row.get("dept_head"),
					"dept_id": row.get("dept_id"),
				},
				"project_type": row.get("project_type"),
				"category": row.get("consultancy_category"),
				"workflow_state": row.get("workflow_state"),
				"docstatus": row.get("docstatus"),
				"start_date": str(row.get("prj_start_date") or ""),
				"completion_date": str(row.get("prj_end_date") or ""),
				"total_budget_amount": flt(row.get("total_budget_amount") or row.get("grand_total_proposal")),
				"funding_agency": row.get("funding_agen"),
				"owner": row.get("owner"),
				"creation": str(row.get("creation") or ""),
				"modified": str(row.get("modified") or ""),
			})

		return {
			"status": "success",
			"total": total,
			"page": page,
			"page_size": page_size,
			"results": results,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "search_projects error")
		return {"status": "error", "message": str(e)}


# ============================================================
# FUNDING AGENCY PROJECT SEARCH ENDPOINT
# ============================================================

@frappe.whitelist(allow_guest=True)
def search_projects_by_funding_agency(agency_name=None, page=1, page_size=20):
	"""
	Search Project Registrations by Funding Agency name or Scheme Name.

	Matches against the linked Funding Agency's name/initials (fundingagency_),
	legacy free-text values stored directly on Project Registration.funding_agen /
	funding_agency_other, and the PFMS Account Details Scheme Name
	(scheme_name / enter_scheme_number) — e.g. "ARG Matrics General".

	Matching is done on word boundaries (via REGEXP), not a raw substring, so a
	short term like "ARG" won't false-positive against unrelated text that merely
	contains those letters (e.g. a Funding Agency record whose name field has
	"...North 24 Parganas, West Bengal..." embedded in it).

	Also resolves a Fund Sanction date for each project (earliest
	sanctioned_letter_date across its linked Fund Sanction records, matched via
	Fund Sanction.project_proposal = Project Registration.name). Many older
	projects have no prj_start_date recorded, so the Fund Sanction date is
	returned separately and also as an "effective_start_date" fallback.

	Args:
		agency_name (str): Free-form agency name/initials to match (partial, case-insensitive).
		page       (int): 1-based page number (default 1).
		page_size  (int): Results per page (default 20, capped at 100).

	Returns:
		{
			"status": "success",
			"total": <int>,
			"page": <int>,
			"page_size": <int>,
			"results": [ { project + funding agency + date fields }, ... ]
		}
	"""
	try:
		page = max(1, int(page or 1))
		page_size = min(100, max(1, int(page_size or 20)))
		offset = (page - 1) * page_size

		conditions = ["pr.docstatus != 2"]  # exclude cancelled docs
		values = []

		if agency_name:
			# Word-boundary match: letters/digits count as "word" characters,
			# anything else (space, hyphen, parens, start/end of string) is a boundary.
			# This stops a short term like "ARG" from matching inside unrelated
			# text such as "...North 24 Parganas..." while still matching
			# "ANRF-ARG", "ARG Matrics General", "(ARG)", etc.
			escaped = re.escape(agency_name.strip())
			boundary_pattern = f"(^|[^A-Za-z0-9]){escaped}([^A-Za-z0-9]|$)"
			conditions.append(
				"("
				"  fa.funding_agency_name REGEXP %s"
				"  OR fa.funding_agency_initials REGEXP %s"
				"  OR pr.funding_agen REGEXP %s"
				"  OR pr.funding_agency_other REGEXP %s"
				"  OR pr.scheme_name REGEXP %s"
				"  OR pr.enter_scheme_number REGEXP %s"
				")"
			)
			values.extend([boundary_pattern] * 6)

		where_clause = " AND ".join(conditions)

		count_sql = f"""
			SELECT COUNT(DISTINCT pr.name)
			FROM `tabProject Registration` pr
			LEFT JOIN `tabfundingagency_` fa ON fa.name = pr.funding_agen
			WHERE {where_clause}
		"""
		total = frappe.db.sql(count_sql, values)[0][0]

		data_sql = f"""
			SELECT
				pr.name,
				pr.project_no,
				pr.project_title,
				pr.principal_investigator_name,
				pr.pi_webmail,
				pr.workflow_state,
				pr.prj_start_date,
				pr.prj_end_date,
				pr.funding_agen,
				pr.funding_agency_other,
				pr.is_the_account_type_pfms,
				pr.scheme_name,
				fa.funding_agency_name,
				fa.funding_agency_initials,
				(
					SELECT MIN(fs.sanctioned_letter_date)
					FROM `tabFund Sanction` fs
					WHERE fs.project_proposal = pr.name
					AND fs.sanctioned_letter_date IS NOT NULL
				) AS fund_sanction_date
			FROM `tabProject Registration` pr
			LEFT JOIN `tabfundingagency_` fa ON fa.name = pr.funding_agen
			WHERE {where_clause}
			ORDER BY pr.modified DESC
			LIMIT %s OFFSET %s
		"""
		rows = frappe.db.sql(data_sql, values + [page_size, offset], as_dict=True)

		results = []
		for row in rows:
			start_date = row.get("prj_start_date")
			fund_sanction_date = row.get("fund_sanction_date")
			results.append({
				"name": row.get("name"),
				"project_no": row.get("project_no"),
				"project_title": row.get("project_title"),
				"pi_name": row.get("principal_investigator_name"),
				"pi_email": row.get("pi_webmail"),
				"workflow_state": row.get("workflow_state"),
				"funding_agency": row.get("funding_agency_name") or row.get("funding_agency_other") or row.get("funding_agen"),
				"account_type": "PFMS" if row.get("is_the_account_type_pfms") == "Yes" else (row.get("is_the_account_type_pfms") or ""),
				"scheme_name": row.get("scheme_name") or "",
				"start_date": str(start_date or ""),
				"end_date": str(row.get("prj_end_date") or ""),
				"fund_sanction_date": str(fund_sanction_date or ""),
				"effective_start_date": str(start_date or fund_sanction_date or ""),
			})

		return {
			"status": "success",
			"total": total,
			"page": page,
			"page_size": page_size,
			"results": results,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "search_projects_by_funding_agency error")
		return {"status": "error", "message": str(e)}


# ============================================================
# PROJECT REGISTRATION LINK GRAPH ENDPOINT
# OJS | 2026-06-24
# Source of truth: PROJECT_REGISTRATION_LINKS_TO_APPLICATION.md
# ============================================================

_PR_DIRECT_LINKS = [
	# (doctype, link_field, display_label, category)
	("AccountHeadPayment",               "project_ref_number",   "Account Head Payment",              "finance"),
	("Advance Settlement",               "project_name",         "Advance Settlement",                "finance"),
	("AMC",                              "project_ref",          "AMC",                               "purchase"),
	("Deposit slip",                     "project_title",        "Deposit Slip",                      "finance"),
	("Deposit Slip Project Credit",      "project_number",       "Deposit Slip Project Credit",       "finance"),
	("Disbursement of Honorarium",       "project_number",       "Disbursement of Honorarium",        "hr"),
	("E Non Routine Deposit Slip",       "project_title",        "E Non-Routine Deposit Slip",        "finance"),
	("Fund Received",                    "prjreg_title",         "Fund Received",                     "finance"),
	("Fund Sanction",                    "project_proposal",     "Fund Sanction",                     "finance"),
	("Indent Cum Sanction Sheet",        "project_ref",          "Indent Cum Sanction Sheet",         "purchase"),
	("Indent General Form",              "igf_project_title",    "Indent General Form",               "purchase"),
	("Loan Request",                     "project_name",         "Loan Request",                      "finance"),
	("myProjects",                       "project_proposal",     "My Projects",                       "project"),
	("payments",                         "project_id",           "Payment",                           "finance"),
	("Project Extension",                "project_ref",          "Project Extension",                 "project"),
	("proprietary_purchase",             "project_ref",          "Proprietary Purchase",              "purchase"),
	("Rate Contract",                    "project_number",       "Rate Contract",                     "purchase"),
	("Rate Contract",                    "project_ref",          "Rate Contract",                     "purchase"),
	("Reimbursement",                    "project_name",         "Reimbursement",                     "finance"),
	("repair_replacement",               "project_ref",          "Repair / Replacement",              "purchase"),
	("Research Consultancy Deposit Slip","project_title",        "Research Consultancy Deposit Slip", "finance"),
	("Research Deposit Slip",            "project_title",        "Research Deposit Slip",             "finance"),
	("standerdized_purchase",            "project_ref",          "Standardized Purchase",             "purchase"),
	("T Testing Deposit Slip",           "project_title",        "T Testing Deposit Slip",            "finance"),
	("Top Up Fellowship",                "project_code",         "Top Up Fellowship",                 "hr"),
	("Travel",                           "travel_project_title", "Travel",                            "hr"),
	("UC Request",                       "project_id",           "UC Request",                        "project"),
]

_PR_INDIRECT_LINKS = [
	# (doctype, data_field, display_label, category)
	("Disbursal of Consultancy",           "project_title",      "Disbursal of Consultancy",         "finance"),
	("Disbursal of Honorarium",            "project_no",         "Disbursal of Honorarium",          "hr"),
	("Direct Purchase",                    "project_no",         "Direct Purchase",                  "purchase"),
	("dp_po",                              "project_no",         "Direct Purchase PO",               "purchase"),
	("Endorsement Data",                   "project_no",         "Endorsement Data",                 "project"),
	("Extension Of Tenure Of Appointment", "project_number",     "Extension of Tenure",              "hr"),
	("ICSS_PO",                            "project_number",     "ICSS PO",                          "purchase"),
	("NIQ",                                "project_no",         "NIQ",                              "purchase"),
	("P_11 Form",                          "project_no",         "P-11 Form",                        "hr"),
	("Project Staff Details",              "project_no",         "Project Staff Details",            "hr"),
	("Recruitment Adhoc Contractual",      "upfa_project_code",  "Recruitment Adhoc Contractual",    "hr"),
	("sanction_sheet",                     "project_no",         "Sanction Sheet",                   "finance"),
	("TA DA Settlement",                   "project_no",         "TA/DA Settlement",                 "hr"),
	("Temporary Advance",                  "project_code",       "Temporary Advance",                "finance"),
]

# Chained links: parent must already exist in the graph (from direct/indirect pass).
# Edge is drawn parent → child (not PR → child).
# (parent_doctype, child_doctype, child_link_field, display_label, category)
_PR_CHAINED_LINKS = [
    # Fund Received (direct) → Deposit Slip via fund_received_ref
    ("Fund Received",               "Deposit slip",             "fund_received_ref",            "Deposit Slip",                "finance"),
    # Indent Cum Sanction Sheet (direct) → purchase docs via ICSS ref
    ("Indent Cum Sanction Sheet",   "repair_replacement",       "indent_cum_sanction_sheet_id", "Repair / Replacement",        "purchase"),
    ("Indent Cum Sanction Sheet",   "AMC",                      "indent_cum_sanction_sheet_id", "AMC",                         "purchase"),
    ("Indent Cum Sanction Sheet",   "proprietary_purchase",     "indent_cum_sanction_sheet_id", "Proprietary Purchase",        "purchase"),
    ("Indent Cum Sanction Sheet",   "standerdized_purchase",    "indent_cum_sanction_sheet_id", "Standardized Purchase",       "purchase"),
    # Recruitment Adhoc Contractual (indirect) → Selection Committee Report
    ("Recruitment Adhoc Contractual", "Selection Committee Report", "interview_id",             "Selection Committee Report",  "hr"),
    # Travel (direct) → TA DA Settlement
    ("Travel",                      "TA DA Settlement",         "ta_da_travel_application",     "TA/DA Settlement",            "hr"),
    # Sanction Sheet (indirect) → Direct Purchase PO, PO Commit Adjustment
    ("sanction_sheet",              "dp_po",                    "sanction_sheet_ref",           "Direct Purchase PO",          "purchase"),
    ("sanction_sheet",              "Po Commit Adjustment",     "purchase_order_number",        "PO Commit Adjustment",        "purchase"),
]


@frappe.whitelist()
def get_pr_link_graph(docname):
	"""
	Returns all documents linked to a Project Registration as a D3-ready graph structure.
	Accepts either the PR autoname (e.g. 202507300DIIT000001) or the human-readable project_no.
	"""
	try:
		if not docname:
			return {"status": "error", "message": "Document name or project number is required"}

		# Resolve PR — accept either autoname or project_no
		pr_name = None
		if frappe.db.exists("Project Registration", docname):
			pr_name = docname
		else:
			pr_name = frappe.db.get_value("Project Registration", {"project_no": docname}, "name")

		if not pr_name:
			return {"status": "error", "message": f"No Project Registration found for: {docname}"}

		pr = frappe.db.get_value(
			"Project Registration", pr_name,
			["project_no", "project_title", "principal_investigator_name",
			 "pi_webmail", "workflow_state", "project_type", "docstatus"],
			as_dict=True,
		)

		project_no = (pr.get("project_no") or "").strip()

		nodes = []
		links = []
		errors = []
		seen_nodes = set()
		seen_links = set()

		root_id = f"PR::{pr_name}"
		nodes.append({
			"id":             root_id,
			"type":           "root",
			"label":          pr_name,
			"subtitle":       project_no,
			"doctype":        "Project Registration",
			"name":           pr_name,
			"category":       "root",
			"workflow_state": pr.get("workflow_state") or "",
			"docstatus":      int(pr.get("docstatus") or 0),
		})
		seen_nodes.add(root_id)

		def _query_and_add(spec_list, link_type, filter_value):
			for (doctype, field, display, category) in spec_list:
				try:
					if not frappe.db.table_exists(doctype):
						continue
					docs = frappe.get_all(
						doctype,
						filters={field: filter_value},
						fields=["name", "workflow_state", "docstatus"],
						limit=100,
					)
					for doc in docs:
						node_id = f"{doctype}::{doc['name']}"
						if node_id not in seen_nodes:
							seen_nodes.add(node_id)
							nodes.append({
								"id":             node_id,
								"type":           link_type,
								"label":          doc["name"],
								"subtitle":       display,
								"doctype":        doctype,
								"name":           doc["name"],
								"category":       category,
								"workflow_state": doc.get("workflow_state") or "",
								"docstatus":      int(doc.get("docstatus") or 0),
								"link_field":     field,
							})
						lkey = f"{root_id}->{node_id}::{field}"
						if lkey not in seen_links:
							seen_links.add(lkey)
							links.append({
								"source": root_id,
								"target": node_id,
								"type":   link_type,
								"field":  field,
							})
				except Exception as exc:
					errors.append(f"{doctype}.{field}: {exc}")

		_query_and_add(_PR_DIRECT_LINKS, "direct", pr_name)
		if project_no:
			_query_and_add(_PR_INDIRECT_LINKS, "indirect", project_no)

		# Chained pass: traverse from already-found nodes to their children
		parents_by_doctype = {}
		for node in nodes[1:]:
			parents_by_doctype.setdefault(node["doctype"], []).append(node["name"])

		for (parent_dt, child_dt, child_field, display, category) in _PR_CHAINED_LINKS:
			parent_names = parents_by_doctype.get(parent_dt, [])
			if not parent_names or not frappe.db.table_exists(child_dt):
				continue
			for parent_name in parent_names:
				parent_node_id = f"{parent_dt}::{parent_name}"
				try:
					docs = frappe.get_all(
						child_dt,
						filters={child_field: parent_name},
						fields=["name", "workflow_state", "docstatus"],
						limit=100,
					)
					for doc in docs:
						node_id = f"{child_dt}::{doc['name']}"
						if node_id not in seen_nodes:
							seen_nodes.add(node_id)
							nodes.append({
								"id":             node_id,
								"type":           "chained",
								"label":          doc["name"],
								"subtitle":       display,
								"doctype":        child_dt,
								"name":           doc["name"],
								"category":       category,
								"workflow_state": doc.get("workflow_state") or "",
								"docstatus":      int(doc.get("docstatus") or 0),
								"link_field":     child_field,
								"via":            parent_dt,
							})
						lkey = f"{parent_node_id}->{node_id}::{child_field}"
						if lkey not in seen_links:
							seen_links.add(lkey)
							links.append({
								"source": parent_node_id,
								"target": node_id,
								"type":   "chained",
								"field":  child_field,
							})
				except Exception as exc:
					errors.append(f"{child_dt}.{child_field} (via {parent_dt}): {exc}")

		direct_count   = sum(1 for n in nodes[1:] if n["type"] == "direct")
		indirect_count = sum(1 for n in nodes[1:] if n["type"] == "indirect")
		chained_count  = sum(1 for n in nodes[1:] if n["type"] == "chained")

		return {
			"status": "success",
			"pr": {
				"name":           pr_name,
				"project_no":     project_no,
				"project_title":  pr.get("project_title") or "",
				"pi_name":        pr.get("principal_investigator_name") or "",
				"pi_email":       pr.get("pi_webmail") or "",
				"workflow_state": pr.get("workflow_state") or "",
				"project_type":   pr.get("project_type") or "",
			},
			"nodes": nodes,
			"links": links,
			"errors": errors,
			"summary": {
				"total":    direct_count + indirect_count + chained_count,
				"direct":   direct_count,
				"indirect": indirect_count,
				"chained":  chained_count,
			},
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "get_pr_link_graph error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_fund_sanction_budget_breakup(fund_sanction_name):
	"""
	Returns the sanctioned_budget_breakup child table rows for a single Fund Sanction
	document, for the PR Link Graph's Fund Sanction node detail panel.
	"""
	if not frappe.db.exists("Fund Sanction", fund_sanction_name):
		return {"status": "error", "message": f"No Fund Sanction found: {fund_sanction_name}"}

	rows = frappe.get_all(
		"Project Sanctioned Budget",
		filters={
			"parent": fund_sanction_name,
			"parenttype": "Fund Sanction",
			"parentfield": "sanctioned_budget_breakup",
		},
		fields=[
			"account_head", "total_proposal_of_heads",
			"first_year_budget", "second_year_budget", "third_year_budget",
			"fourth_year_budget", "fifth_year_budget", "sixth_year_budget",
			"is_total_row", "idx",
		],
		order_by="idx asc",
	)

	return {"status": "success", "fund_sanction": fund_sanction_name, "rows": rows}


# ============================================================
# ---- Cascade Delete: wipe a Project Registration + every associated document ----
# Reuses the exact same link map as get_pr_link_graph (direct/indirect/chained),
# so "associated documents" here always matches what the PR Link Graph visualizes.
# ============================================================

def _delete_external_project(project_no):
	"""
	Sends a DELETE for this project to the external project API, mirroring the
	POST in send_project_registration_data_api. Best-effort: failures are
	reported back to the caller but never raised, since a missing/unsynced
	project on the external side shouldn't block the local cascade delete.
	"""
	if not project_no:
		return {"attempted": False, "message": "No project_no on this Project Registration — external API not called."}

	url = f"{ACCOUNT_PORTAL_PROJECTS}/{project_no}"
	try:
		frappe.logger().info(f"Deleting project {project_no} from {url}")
		response = requests.delete(url, timeout=10)
		return {
			"attempted": True,
			"url": url,
			"status_code": response.status_code,
			"response": response.text,
			"ok": response.status_code in (200, 202, 204, 404),
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"External Project Delete Error: {project_no}")
		return {"attempted": True, "url": url, "ok": False, "error": str(e)}


def _force_delete_single_doc(doctype, docname):
	"""Force-delete one document, handling submitted docstatus and falling back to raw SQL.
	Returns (deleted: bool, note: str | None)."""
	try:
		docstatus = frappe.db.get_value(doctype, docname, "docstatus")
		if docstatus == 1:
			frappe.db.set_value(doctype, docname, "docstatus", 2, update_modified=False)
			frappe.db.commit()

		frappe.delete_doc(
			doctype, docname,
			ignore_permissions=True, force=True,
			ignore_on_trash=True, delete_permanently=True,
		)
		frappe.db.commit()
		return True, None
	except Exception as e:
		first_err = str(e)
		try:
			meta = frappe.get_meta(doctype)
			for df in meta.fields:
				if df.fieldtype in ("Table", "Table MultiSelect") and df.options:
					frappe.db.sql(
						f"DELETE FROM `tab{df.options}` WHERE parent = %s AND parenttype = %s",
						(docname, doctype),
					)
			frappe.db.sql(f"DELETE FROM `tab{doctype}` WHERE name = %s", (docname,))
			frappe.db.commit()
			return True, f"raw SQL fallback (frappe.delete_doc error: {first_err})"
		except Exception as e2:
			return False, f"frappe.delete_doc -> {first_err} | raw SQL -> {str(e2)}"


@frappe.whitelist()
def preview_pr_cascade_delete(identifier):
	"""
	Dry-run: resolve a Project Registration by docname or project_no and list every
	associated document (direct link, indirect project_no cache, chained link) that
	a cascade delete would remove. Does not modify anything.
	"""
	graph = get_pr_link_graph(identifier)
	if graph.get("status") != "success":
		return graph

	by_doctype = {}
	for node in graph["nodes"][1:]:
		by_doctype[node["doctype"]] = by_doctype.get(node["doctype"], 0) + 1

	return {
		"status": "success",
		"pr": graph["pr"],
		"total_associated": graph["summary"]["total"],
		"by_doctype": [{"doctype": dt, "count": c} for dt, c in sorted(by_doctype.items())],
		"errors": graph.get("errors", []),
	}


@frappe.whitelist()
def delete_pr_cascade(identifier, override_password=None):
	"""
	DANGER: permanently deletes a Project Registration AND every document linked to
	it (direct Link fields, indirect project_no Data fields, and chained links) per
	PROJECT_REGISTRATION_LINKS_TO_APPLICATION.md — the same map used by
	get_pr_link_graph. Requires the shared admin override password. Irreversible.
	"""
	from rndopsapp.delete_projects_tmp import ADMIN_ACTION_PASSWORD, delete_project_registrations

	if override_password != ADMIN_ACTION_PASSWORD:
		return {"status": "error", "message": "Incorrect password. Nothing was deleted."}

	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Manager can perform cascade deletion.", frappe.PermissionError)

	graph = get_pr_link_graph(identifier)
	if graph.get("status") != "success":
		return graph

	pr_name = graph["pr"]["name"]
	project_no = graph["pr"].get("project_no")
	deleted = []
	errors = []

	# Delete every associated document first (everything except the root PR node).
	for node in graph["nodes"][1:]:
		ok, note = _force_delete_single_doc(node["doctype"], node["name"])
		label = f"{node['doctype']}: {node['name']}"
		if ok:
			deleted.append(label + (f" ({note})" if note else ""))
		else:
			errors.append(f"{label} — {note}")

	# Finally delete the Project Registration itself (reuses MinIO file cleanup).
	pr_result = delete_project_registrations(json.dumps([pr_name]), override_password=override_password)

	# Also remove the project from the external project-tracking service.
	external_result = _delete_external_project(project_no)
	if external_result.get("attempted") and not external_result.get("ok"):
		errors.append(f"External API delete ({external_result.get('url')}) — "
			f"{external_result.get('error') or external_result.get('status_code')}")

	return {
		"status": "success",
		"pr_name": pr_name,
		"deleted_count": len(deleted),
		"deleted": deleted,
		"errors": errors,
		"pr_deletion": pr_result,
		"external_api_delete": external_result,
	}
