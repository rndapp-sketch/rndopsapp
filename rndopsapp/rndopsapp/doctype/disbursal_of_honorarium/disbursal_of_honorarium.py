# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document
from frappe import _

class DisbursalofHonorarium(Document):
	def validate(self):
		"""
		Intercept file uploads: if any Attach field has a local /files/ URL,
		migrate it to MinIO under Project_Registration/{project}/disbursal_of_honorarium/.
		This fires on every doc.save(), catching files uploaded via Frappe's upload_file.
		"""
		self._process_attach_fields()

	def _process_attach_fields(self):
		project_docname = self.get("project_name")
		if not project_docname:
			return

		meta = frappe.get_meta(self.doctype)
		for df in meta.fields:
			if df.fieldtype == "Attach":
				fieldname = df.fieldname
				file_url = self.get(fieldname)
				if file_url and (file_url.startswith("/files/") or file_url.startswith("/private/files/")):
					print(f"[HONORARIUM_FILE_DEBUG] validate() migrating {fieldname}: {file_url}")
					try:
						from rndopsapp.file_handler import migrate_local_file_to_minio

						result = migrate_local_file_to_minio(
							file_url=file_url,
							doctype="Project Registration",
							docname=project_docname,
							fieldname="disbursal_of_honorarium"
						)
						print(f"[HONORARIUM_FILE_DEBUG] validate() migration result: {result}")
						if result.get("status"):
							self.set(fieldname, result.get("file_url"))
						else:
							frappe.log_error(
								f"MinIO migration failed for {fieldname}: {result.get('message')}",
								"Disbursal Honorarium MinIO Migration"
							)
					except Exception as e:
						print(f"[HONORARIUM_FILE_DEBUG] validate() migration error: {str(e)}")
						frappe.log_error(frappe.get_traceback(), f"MinIO Migration Error for {fieldname}")

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
def save_disbursal_of_honorarium_data(data, files=None):
	"""
	Save Disbursal of Honorarium data.
	Expects 'data' as a JSON string or dict.
	'files' is an optional list of file objects with {filename, content, fieldname} for MinIO upload.
	"""
	import base64 as _b64

	if isinstance(data, str):
		data = json.loads(data)

	# Parse files payload
	files_payload = files
	if isinstance(files_payload, str):
		try:
			files_payload = json.loads(files_payload)
		except Exception:
			files_payload = None

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
		]

		for field in simple_fields:
			if field in data:
				val = data[field]
				doc.set(field, val if val != "null" else None)

		# Resolve project docname for MinIO path
		project_docname = data.get("project_name") or doc.get("project_name")
		print(f"[HONORARIUM_FILE_DEBUG] project_docname={project_docname}, files_payload type={type(files_payload)}, files_payload={files_payload}")
		print(f"[HONORARIUM_FILE_DEBUG] data keys={list(data.keys())}")
		print(f"[HONORARIUM_FILE_DEBUG] attached_approvals in data={('attached_approvals' in data)}, val={repr(data.get('attached_approvals', 'NOT_PRESENT'))[:200]}")
		print(f"[HONORARIUM_FILE_DEBUG] additional_documents in data={('additional_documents' in data)}, val={repr(data.get('additional_documents', 'NOT_PRESENT'))[:200]}")

		# --- Handle File Upload fields (Attach) — upload to MinIO ---
		# attached_approvals, additional_documents
		file_fields = ["attached_approvals", "additional_documents"]
		for field in file_fields:
			if field in data:
				val = data[field]
				print(f"[HONORARIUM_FILE_DEBUG] field={field}, val type={type(val).__name__}, val={repr(val)[:200]}")
				# Case 1: Base64 dict from frontend (e.g. {file_name: "x.pdf", file_data: "base64..."})
				if isinstance(val, dict) and val.get("file_name") and val.get("file_data"):
					print(f"[HONORARIUM_FILE_DEBUG] -> Case 1: base64 dict upload for {field}")
					minio_url = _upload_base64_to_minio(val, project_docname, field)
					if minio_url:
						doc.set(field, minio_url)
						print(f"[HONORARIUM_FILE_DEBUG] -> MinIO URL set: {minio_url}")
					else:
						print(f"[HONORARIUM_FILE_DEBUG] -> base64 upload returned None!")
				elif isinstance(val, str):
					# Case 2: Local file URL from Frappe's upload_file — migrate to MinIO
					if val.startswith("/files/") or val.startswith("/private/files/"):
						print(f"[HONORARIUM_FILE_DEBUG] -> Case 2: local file migration for {field}: {val}")
						migrated_url = _migrate_local_to_minio(val, project_docname, field)
						doc.set(field, migrated_url)
						print(f"[HONORARIUM_FILE_DEBUG] -> Migrated URL: {migrated_url}")
					else:
						# Case 3: Already a MinIO URL or empty
						print(f"[HONORARIUM_FILE_DEBUG] -> Case 3: existing URL for {field}: {val}")
						doc.set(field, val)
				else:
					print(f"[HONORARIUM_FILE_DEBUG] -> UNHANDLED type for {field}: {type(val).__name__}")

		# --- Handle files parameter (list of base64 file objects) ---
		if files_payload and isinstance(files_payload, list):
			from rndopsapp.minio import get_rnd_file_service
			for f in files_payload:
				try:
					filename = f.get("filename") or f.get("file_name") or f.get("name")
					content_b64 = f.get("content") or f.get("file_data") or f.get("data") or ""
					target_field = f.get("fieldname") or f.get("field")

					if not (filename and content_b64):
						continue

					if content_b64.startswith("data:"):
						content_b64 = content_b64.split(",", 1)[1]

					file_content = _b64.b64decode(content_b64)

					upload_result = get_rnd_file_service().save_file(
						filename=filename,
						content=file_content,
						is_private=False,
						doctype="Project Registration",
						docname=project_docname,
						folder="disbursal_of_honorarium"
					)

					if upload_result.get("status"):
						file_url = upload_result.get("data", {}).get("file_url")
						if target_field and target_field in file_fields:
							doc.set(target_field, file_url)
						frappe.logger().info(f"File uploaded to MinIO via files param: {filename} -> {file_url}")
					else:
						frappe.log_error(
							f"MinIO upload failed for {filename}: {upload_result.get('message')}",
							"Disbursal of Honorarium File Upload"
						)
				except Exception as fe:
					frappe.log_error(frappe.get_traceback(), f"File upload error for {f.get('filename')}")
					continue
		
		# Handle Child Table: table_weoy (Honorarium Table)
		items_data = data.get("table_weoy", [])
		if isinstance(items_data, str):
			items_data = json.loads(items_data)
			
		if items_data:
			doc.set("table_weoy", []) # Clear existing
			for item in items_data:
				doc.append("table_weoy", item)

		# total_amount is always derived server-side from the honorarium rows,
		# never trusted from the client (previously a client-computed value could
		# desync from the row amounts, e.g. comma-formatted "24,000" parsing as 24).
		doc.total_amount = sum(frappe.utils.flt(row.amount) for row in doc.table_weoy)

		# Save
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Disbursal of Honorarium Save Error")
		return {"status": "error", "message": str(e)}


def _upload_base64_to_minio(val, project_docname, field):
	"""Upload a base64 file dict to MinIO. Returns the MinIO URL or None."""
	import base64 as _b64
	try:
		from rndopsapp.minio import get_rnd_file_service

		filename = val["file_name"]
		content_b64 = val["file_data"]

		if isinstance(content_b64, str) and content_b64.startswith("data:"):
			content_b64 = content_b64.split(",", 1)[1]

		file_content = _b64.b64decode(content_b64)

		upload_result = get_rnd_file_service().save_file(
			filename=filename,
			content=file_content,
			is_private=False,
			doctype="Project Registration",
			docname=project_docname,
			folder="disbursal_of_honorarium"
		)

		if upload_result.get("status"):
			file_url = upload_result.get("data", {}).get("file_url")
			frappe.logger().info(f"File uploaded to MinIO for {field}: {file_url}")
			return file_url
		else:
			frappe.log_error(
				f"MinIO upload failed for {field}: {upload_result.get('message')}",
				"Disbursal of Honorarium MinIO Upload"
			)
	except Exception as e:
		frappe.log_error(f"Error saving file for {field}: {str(e)}", "Disbursal of Honorarium File Upload")
	return None


def _migrate_local_to_minio(file_url, project_docname, field):
	"""Migrate a local /files/ URL to MinIO. Returns MinIO URL or original URL as fallback."""
	try:
		from rndopsapp.file_handler import migrate_local_file_to_minio

		print(f"[HONORARIUM_FILE_DEBUG] _migrate_local_to_minio called: file_url={file_url}, project={project_docname}, field={field}")

		result = migrate_local_file_to_minio(
			file_url=file_url,
			doctype="Project Registration",
			docname=project_docname,
			fieldname="disbursal_of_honorarium"
		)
		print(f"[HONORARIUM_FILE_DEBUG] migrate_local_file_to_minio result: {result}")

		if result.get("status"):
			frappe.logger().info(f"Migrated local file to MinIO for {field}: {result.get('file_url')}")
			return result.get("file_url")
		else:
			print(f"[HONORARIUM_FILE_DEBUG] MIGRATION FAILED: {result.get('message')}")
			frappe.log_error(
				f"MinIO migration failed for {field}: {result.get('message')}",
				"Disbursal of Honorarium MinIO Migration"
			)
	except Exception as e:
		print(f"[HONORARIUM_FILE_DEBUG] MIGRATION EXCEPTION: {str(e)}")
		frappe.log_error(f"Error migrating file for {field}: {str(e)}", "Disbursal of Honorarium File Migration")
	return file_url  # Fallback to original local URL

@frappe.whitelist()
def perform_disbursal_of_honorarium_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Disbursal of Honorarium", docname)
		current_state = doc.workflow_state or "Draft"

		# Director-PDF gate: cannot Approve from Pending Director Approval
		# until Staff has uploaded the Director-signed scan (mirrors Indent
		# General Form's hardcopy flow — see attach_director_pdf_honorarium).
		if (
			action == "Approve"
			and current_state == "Pending Director Approval"
			and not (doc.get("director_signed_pdf") or "").strip()
		):
			frappe.throw(
				"Cannot approve: the Director-signed PDF has not been uploaded by Staff yet."
			)

		# Fetch the workflow for this doctype
		workflow_name = frappe.get_value("Workflow", {"document_type": "Disbursal of Honorarium"}, "name")
		
		if not workflow_name:
			frappe.throw("Workflow not found for Disbursal of Honorarium.")

		workflow = frappe.get_doc("Workflow", workflow_name)
		
		next_state = None

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				condition = getattr(t, "condition", None)
				if condition:
					try:
						if not frappe.safe_eval(condition, None, {"doc": doc}):
							continue
					except Exception:
						continue
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
		# API callers lack the desk roles (e.g. "RnD Staff", "Dean") assigned
		# in the workflow definition, so get_transitions() returns [] and
		# Frappe throws "transition not allowed from X to Draft" (it resets
		# to Draft as the default allowed state).
		#
		# Solution: write workflow_state + docstatus directly to the DB,
		# which completely bypasses validate_workflow().
		# -------------------------------------------------------------------

		# Find the next state config (docstatus / update_field)
		next_state_row = next(
			(s for s in workflow.states if s.state == next_state), None
		)
		new_docstatus = int(next_state_row.doc_status or 0) if next_state_row else 0

		workflow_field = workflow.workflow_state_field or "workflow_state"
		update_fields = {workflow_field: next_state}

		# Include docstatus only when it changes (e.g. Approved=1, Rejected=2)
		if new_docstatus != int(doc.docstatus):
			update_fields["docstatus"] = new_docstatus

		# Handle any extra field the workflow state row wants updated
		# IMPORTANT: Skip if update_field is the workflow_state_field itself
		# (all states in this workflow have update_field="workflow_state" with
		# update_value=NULL, which would overwrite the correct state with None)
		if (
			next_state_row
			and getattr(next_state_row, "update_field", None)
			and next_state_row.update_field != workflow_field
			and next_state_row.update_value is not None
		):
			update_fields[next_state_row.update_field] = next_state_row.update_value

		# Write directly to DB — bypasses validate_workflow completely
		frappe.db.set_value(
			"Disbursal of Honorarium",
			docname,
			update_fields,
			update_modified=True,
		)

		# Add a workflow comment so the timeline reflects the transition
		doc.reload()
		doc.add_comment("Workflow", _(next_state))

		# --- Data Pipeline Integration ---
		# When the document reaches "Approved" (by either Dean or Director),
		# publish any pending staged commit payloads to Kafka.
		# NOTE: Since perform_action uses frappe.db.set_value (bypasses ORM),
		# the on_update hook (check_workflow_and_publish) does NOT fire.
		# We must publish staged commits explicitly here.
		if next_state == "Approved":
			try:
				from rndopsapp.rndopsapp.kafka.producer.reimbursement import publish_commit as kafka_publish_commit

				staging_docs = frappe.get_all("Kafka Commit Staging", filters={
					"reference_doctype": "Disbursal of Honorarium",
					"reference_name": docname,
					"status": ["in", ["PENDING_APPROVAL", "FAILED"]]
				})

				for st in staging_docs:
					staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
					try:
						import json as _json
						payload = _json.loads(staging_doc.payload)

						success = kafka_publish_commit(
							doc=doc,
							commit_amount=payload.get("commit_amount"),
							budget_head=payload.get("budget_head"),
							project_name=payload.get("project_name"),
							bmr=payload.get("bmr"),
							bill_amount=payload.get("bill_amount"),
							frap_app_id=payload.get("frap_app_id"),
							ref_details=payload.get("ref_details"),
							commit_particular=payload.get("commit_particular")
						)

						if success:
							staging_doc.db_set("status", "PUBLISHED")
							frappe.logger().info(f"Published staged commit for {docname} to Kafka.")
						else:
							staging_doc.db_set("status", "FAILED")
							staging_doc.db_set("error_message", "kafka_publish_commit returned False")
							frappe.log_error(f"Failed to publish staged commit for {docname}.", "Kafka Publish Error")

					except Exception as e:
						frappe.log_error(frappe.get_traceback(), "Process Staged Commit Error")
						staging_doc.db_set("status", "FAILED")
						staging_doc.db_set("error_message", str(e))

			except Exception as e:
				frappe.log_error(f"Error processing staged commits for {docname}: {str(e)}", "Data Pipeline Error")
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
	# Fetch the workflow for this doctype
	workflow_name = frappe.get_value("Workflow", {"document_type": "Disbursal of Honorarium"}, "name")

	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)

	# Filter actions by the current user's roles so each user
	# only sees the action buttons they are allowed to perform.
	user_roles = frappe.get_roles(frappe.session.user)

	actions = [
		t.action
		for t in workflow.transitions
		if t.state == current_state and t.allowed in user_roles
	]
	return list(dict.fromkeys(actions))


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


# ============================================================
# Director hardcopy / PDF flow (mirrors Indent General Form)
# Dean ticks "Send for Director Approval" on a Disbursal of Honorarium.
# Staff uploads the Director-signed scan via attach_director_pdf_honorarium.
# Dean's Approve action from Pending Director Approval unlocks once
# director_signed_pdf is set (see the gate in perform_disbursal_of_honorarium_action).
# ============================================================

@frappe.whitelist()
def update_send_to_director_honorarium(docname, send_to_director):
	"""
	Dean opts the Disbursal of Honorarium into the Director-hardcopy flow.
	One-way (cannot clear). Restricted to "Dean, RnD" / "System Manager".
	Works only from "Pending Dean Approval" state.
	"""
	user_roles = frappe.get_roles(frappe.session.user)
	if "Dean, RnD" not in user_roles and "System Manager" not in user_roles:
		frappe.throw("Not permitted", frappe.PermissionError)

	if not frappe.db.exists("Disbursal of Honorarium", docname):
		frappe.throw("Document not found")

	doc = frappe.get_doc("Disbursal of Honorarium", docname)

	if (doc.workflow_state or "") not in ("Pending Dean Approval", "Pending Director Approval"):
		frappe.throw("Director Approval flag can only be set from 'Pending Dean Approval' state.")

	if frappe.utils.cint(doc.get("send_to_director")):
		return {"status": "success", "docname": docname, "send_to_director": 1}

	if not frappe.utils.cint(send_to_director):
		frappe.throw("send_to_director can only be set, not cleared.")

	frappe.db.set_value(
		"Disbursal of Honorarium", docname, {
			"send_to_director": 1,
			"workflow_state": "Pending Director Approval",
		}
	)
	frappe.db.commit()
	return {"status": "success", "docname": docname, "send_to_director": 1}


@frappe.whitelist()
def attach_director_pdf_honorarium(docname, file_url):
	"""
	Staff binds an already-uploaded file URL to director_signed_pdf.
	Replacing an existing PDF is allowed.
	Restricted to "staff, RnD" / "System Manager".
	"""
	user_roles = frappe.get_roles(frappe.session.user)
	if "staff, RnD" not in user_roles and "System Manager" not in user_roles:
		frappe.throw("Not permitted", frappe.PermissionError)

	if not file_url:
		frappe.throw("file_url is required")

	if not frappe.db.exists("Disbursal of Honorarium", docname):
		frappe.throw("Document not found")

	doc = frappe.get_doc("Disbursal of Honorarium", docname)

	if (doc.workflow_state or "") != "Pending Director Approval":
		frappe.throw("Director PDF can only be attached when document is in 'Pending Director Approval' state.")

	frappe.db.set_value("Disbursal of Honorarium", docname, "director_signed_pdf", file_url)
	frappe.db.commit()
	return {
		"status": "success",
		"docname": docname,
		"director_signed_pdf": file_url,
	}


@frappe.whitelist()
def get_pending_director_uploads_honorarium():
	"""
	Returns Disbursal of Honorarium docs in Pending Director Approval state so
	Staff can upload the signed PDF. Includes both pending uploads and
	already-uploaded docs.
	"""
	docs = frappe.get_all(
		"Disbursal of Honorarium",
		filters={
			"workflow_state": "Pending Director Approval",
			"docstatus": 0,
		},
		fields=[
			"name",
			"project_name",
			"project_no",
			"account_head",
			"total_amount",
			"webmail_id",
			"name_of_applicant",
			"applicant_department",
			"director_signed_pdf",
			"send_to_director",
			"modified",
			"workflow_state",
		],
		order_by="modified desc",
	)
	return {"status": "success", "data": docs}
# ============================================================