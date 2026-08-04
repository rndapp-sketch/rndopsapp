import json
import os

import requests

import frappe
from frappe import _
from frappe.utils import sanitize_html
from frappe.utils.file_manager import save_file

# Re-export so callers using rndopsapp.rndopsapp.api.* still resolve correctly
from rndopsapp.rndopsapp.doctype.fund_received.fund_received import (
	get_fund_received_by_prjreg,
)

# -------------------------- SCRIPT-DRIVEN WORKFLOW FUNCTIONS {MKY-V1- 19-09-2025}-------------------------------


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
	doc_str = ""

	for key, value in doc_dict.items():
		doc_str += f"{key}: {value}\n"

	# Define file name and path
	file_name = f"{doc.name}.txt"
	file_path = os.path.join(frappe.get_site_path("private", "files"), file_name)

	# Write string to file
	with open(file_path, "w", encoding="utf-8") as f:
		f.write(doc_str)

	# Log the saved content (using frappe logger)
	logger = frappe.logger("project_registration")  # you can name your logger as you want
	logger.info(f"Saved Project Registration document as text file: {file_name}")
	logger.info(f"Content:\n{doc_str}")

	return {"file_path": file_path, "file_url": f"/private/files/{file_name}"}


@frappe.whitelist()
def submit_project_registration(docname):
	# Fetch the Project Registration document
	doc = frappe.get_doc("Project Registration", docname)

	# Convert to dict for reference
	data = doc.as_dict()
	print(f"Implementation Department: {data.get('implementation_department')}")

	# --- Fetch linked Department_prornd document ---
	dept_doc = frappe.get_doc("Department_prornd", data.get("implementation_department"))
	print(f"Department Name: {dept_doc.dept_name}")
	print(f"Department Head: {dept_doc.dept_head}")

	# ✅ Update Project Registration fields from Department_prornd
	doc.department_head = dept_doc.dept_head
	doc.head_approver = dept_doc.dept_head  # You can change this logic if needed

	# Save the updated values before submission
	# Use flags to skip mandatory validation for fields not yet populated
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

	# ✅ Update workflow and submit
	doc.workflow_state = next_state
	doc.submit()

	return {
		"workflow_state": doc.workflow_state,
		"department_head": doc.department_head,
		"head_approver": doc.head_approver,
	}


@frappe.whitelist()
def get_user_empclass(user):
	"""Return both empclass ID and Name for a given User"""
	empclass_id = frappe.db.get_value("User", user, "empclass")
	if empclass_id:
		empclass_name = frappe.db.get_value("EmployeeClass_prornd", empclass_id, "empclass_name")
		return {
			"empclass_id": empclass_id,  # e.g. EMP-0001 (valid Link ID)
			"empclass_name": empclass_name,  # e.g. PI - Principal Investigator
		}
	return {}


def get_workflow_states(doctype):
	"""
	Fetches all workflow states for a given DocType.

	:param doctype: The target DocType
	:return: List of state names
	:raises: frappe.DoesNotExistError if no workflow found
	"""
	workflow_name = frappe.get_value("Workflow", {"document_type": doctype}, "name")

	if not workflow_name:
		frappe.throw(f"No workflow found for DocType: {doctype}")

	workflow = frappe.get_doc("Workflow", workflow_name)
	return [state.state for state in workflow.states]


# --- Helper functions for document sharing --- Jimmy
def share_document(doctype, name, user):
	"""Shares a document with a user, giving them read and write access."""
	frappe.share.add(doctype, name, user, read=1, write=1, notify=1)


# ---------- MKY 20-09-25 COMMENTED ABOVE AND REPLACED WITH BELOW (unshare_document)------------------
def unshare_document(doctype, name, user):
	"""Revokes a user's share permissions from a document without deleting the DocShare row."""
	try:
		shares = frappe.get_all(
			"DocShare", filters={"share_doctype": doctype, "share_name": name, "user": user}, pluck="name"
		)
		for s in shares:
			frappe.db.set_value(
				"DocShare",
				s,
				{"read": 0, "write": 0, "share": 0},
				update_modified=False,
				ignore_permissions=True,
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "unshare_document failed")


# --- UTILITY FUNCTIONS (OPTIONAL BUT RECOMMENDED) --- jimmy


@frappe.whitelist()
def get_project_activity(doctype, docname):
	"""
	Fetches all comments and communications for a given document.
	"""
	# Log the docname being fetched
	frappe.logger().warning(f"Jimmy get_project_activity Logging Debug: docname = {docname}")

	try:
		# Fetch comments for the given document
		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": doctype, "reference_name": docname},
			fields=["content", "owner", "creation", "comment_type"],
			order_by="creation desc",
		)

		# Log the fetched comments
		frappe.logger().warning(f"Jimmy get_project_activity Logging Debug: comments = {comments}")

		return comments
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_project_activity failed")
		return []


@frappe.whitelist(allow_guest=True)
def get_activity_test(doctype, docname):
	"""
	Fetches all comments and communications for a given document.
	"""
	# Log the docname being fetched
	frappe.logger().warning(f"Jimmy get_project_activity Logging Debug: docname = {docname}")

	try:
		# Fetch comments for the given document
		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": doctype, "reference_name": docname},
			fields=["content", "owner", "creation", "comment_type"],
			order_by="creation desc",
		)

		# Log the fetched comments
		frappe.logger().warning(f"Jimmy get_project_activity Logging Debug: comments = {comments}")

		return comments
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_project_activity failed")
		return []


@frappe.whitelist()
def add_project_comment(doctype, docname, content):
	"""
	Adds a sanitized comment to a given document.
	"""
	if not content or not content.strip():
		frappe.throw("Comment content cannot be empty.")

	try:
		doc = frappe.get_doc(doctype, docname)
		comment = doc.add_comment("Comment", sanitize_html(content))

		# Return the created comment with proper structure
		return {
			"owner": comment.owner,
			"creation": comment.creation,
			"content": comment.content,
			"comment_type": comment.comment_type,
		}

	except Exception:
		frappe.log_error(frappe.get_traceback(), "add_project_comment failed")
		frappe.throw("Could not add comment.")


@frappe.whitelist()
def get_user_roles(user=None):
	"""
	Returns a list of roles for the given user.
	If no user is specified, returns roles for the currently logged-in user.
	"""
	try:
		if not user:
			user = frappe.session.user

		if not frappe.db.exists("User", user):
			frappe.throw(f"User '{user}' does not exist.")

		roles = frappe.get_roles(user)
		return roles

	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_user_roles failed")
		frappe.throw("Could not fetch user roles.")


# ----------------- MKY (23-10-25) ADDED NEW FUNCTION TO CREATE RESEARCH PROJECT AND APPROVE PROPOSAL ---------------
@frappe.whitelist()
def create_research_project_and_approve(proposal_docname, id_components, comment=None):
	"""
	1. Creates a new 'Research Project' document.
	2. Generates and sets the Project ID.
	3. Links the Research Project back to the Proposal.
	4. Approves the proposal, moving it to the next state.
	"""
	proposal_doc = frappe.get_doc("Project Registration", proposal_docname)

	# Security check
	if "staff, RnD" not in frappe.get_roles():
		frappe.throw("Permission Denied: Only Staff, RnD can perform this action.")

	# --- 1. Generate the Project ID ---
	vals = frappe._dict(id_components)
	project_id = f"{vals.dept_initial}{vals.category}{vals.funding_agency_code}{vals.emp_id}{vals.emp_initial}{vals.project_no}"

	if len(project_id) != 23:
		frappe.throw(f"Generated Project ID has an incorrect length. Please check components.")

	# Check for duplicates on the new doctype
	if frappe.db.exists("Research Project", {"project_id": project_id}):
		frappe.throw(f"A Research Project with the ID {project_id} already exists.")

	# --- 2. Create the new 'Research Project' Document ---
	new_project = frappe.new_doc("Research Project")  # CORRECTED DOCTYPE NAME
	new_project.project_id = project_id
	new_project.project_title = proposal_doc.project_title
	new_project.project_proposal = proposal_doc.name
	new_project.principal_investigator = proposal_doc.pi_webmail
	new_project.department = proposal_doc.implementation_department
	new_project.insert(ignore_permissions=True)
	# new_project.submit() # Optional: submit the new master project

	# --- 3. Link the Research Project back to the Proposal ---
	proposal_doc.db_set("research_project", new_project.name)  # CORRECTED FIELDNAME

	# --- 4. Approve the Proposal (using our existing function) ---
	from . import handle_approval_action

	handle_approval_action(proposal_doc.name, "Approve", comment)

	return new_project


# ------------- Added by MKY (09/10/2025) --------------
@frappe.whitelist()
def get_fund_sanction_fields(project_proposal=None):
	"""
	Returns the doctype fields and link options for the Fund Sanction form.
	Prefills the project link if a project_proposal name is provided.
	"""
	fund_sanction_meta = frappe.get_meta("Fund Sanction")
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
		for f in fund_sanction_meta.get("fields")
	]

	prefill_data = {"project_proposal": project_proposal} if project_proposal else {}

	link_options = {
		"project_proposal": frappe.get_all(
			"Project Registration", fields=["name as value", "project_title as label"]
		),
		"amended_from": frappe.get_all(
			"Fund Sanction", fields=["name as value", "sanctioned_letter_no as label"]
		),
	}

	return {"fields": fields, "prefill_data": prefill_data, "link_options": link_options}


@frappe.whitelist()
def get_fund_received_fields(fund_sanction):
	"""
	Returns fields for the Fund Received form.
	It MUST receive a fund_sanction docname to pre-fill key details.
	"""
	if not fund_sanction:
		frappe.throw("A valid Fund Sanction document is required.")

	fund_received_meta = frappe.get_meta("Fund Received")
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
		for f in fund_received_meta.get("fields")
	]

	# Fetch data from the parent Fund Sanction to pre-fill and link
	sanction_doc = frappe.get_doc("Fund Sanction", fund_sanction)

	prefill_data = {
		"sqnction_letter_no": sanction_doc.name,
		"prjreg_refnum": sanction_doc.project_proposal,
		"prj_type": sanction_doc.project_type_linked,
	}

	link_options = {
		"amended_from": frappe.get_all(
			"Fund Received", filters={"sqnction_letter_no": fund_sanction}, fields=["name as value"]
		)
	}

	return {"fields": fields, "prefill_data": prefill_data, "link_options": link_options}


# ----------------------------------------


@frappe.whitelist()
def get_project_details(docname):
	"""
	Fetches project details and all associated Fund Received records with their budget breakups.
	"""
	if not docname:
		frappe.throw(_("Project Registration ID (docname) is required."))

	try:
		# 1. Fetch Project Registration Document
		project_doc = frappe.get_doc("Project Registration", docname)

		# Extract basic project details
		project_data = {
			"name": project_doc.name,
			"project_title": project_doc.project_title,
			"project_type": project_doc.project_type,
			"principal_investigator_name": project_doc.principal_investigator_name,
			"pi_employee_id": project_doc.pi_employee_id,
			"pi_webmail": project_doc.pi_webmail,
			"implementation_department": project_doc.implementation_department,
			"workflow_state": project_doc.workflow_state,
			"total_budget_amount": project_doc.total_budget_amount,
			"creation": project_doc.creation,
		}

		# 2. Fetch All Linked Fund Received Documents
		# Filter by 'prjreg_title' which links to Project Registration
		funds = frappe.get_all(
			"Fund Received",
			filters={"prjreg_title": docname, "docstatus": 0},
			fields=[
				"name",
				"fund_received_amt",
				"creation",
				"bank_account",
				"invoice_no",
				"gst_invoice_issued",
				"docstatus",
			],
		)

		funds_data = []
		for fund in funds:
			# Fetch the full doc to get the child table 'received_amt_breakup'
			fund_doc = frappe.get_doc("Fund Received", fund.name)

			fund_info = {
				"name": fund_doc.name,
				"fund_received_amt": fund_doc.fund_received_amt,
				"creation": fund_doc.creation,
				"bank_account": fund_doc.bank_account,
				"invoice_no": fund_doc.invoice_no,
				"gst_invoice_issued": fund_doc.gst_invoice_issued,
				"docstatus": fund_doc.docstatus,
				"budget_breakup": [],
			}

			# Extract child table details
			for row in fund_doc.received_amt_breakup:
				fund_info["budget_breakup"].append(
					{
						"account_head": row.account_head,
						"amount_received": row.amount_received,
						"remarks": row.remarks,
					}
				)

			funds_data.append(fund_info)

		return {"project_details": project_data, "funds": funds_data}

	except frappe.DoesNotExistError:
		frappe.throw(_("Project Registration not found."), title="Not Found")
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"Error fetching details for {docname}")
		frappe.throw(_("An error occurred while fetching project details."))


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
def get_recruitment_adhoc_contractual_by_webmail(webmail_id):
	"""
	Get all Recruitment Adhoc Contractual documents for a specific webmail ID.
	"""
	try:
		doc_names = frappe.get_all(
			"Recruitment Adhoc Contractual", filters={"webmail_id": webmail_id}, pluck="name"
		)

		docs = [frappe.get_doc("Recruitment Adhoc Contractual", name).as_dict() for name in doc_names]

		return {"status": "success", "data": docs}
	except Exception as e:
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def delete_doctype_records(doctype, docnames, override_password=None):
	"""
	Delete one or more documents from any DocType.
	Accepts docnames as a JSON list or comma/newline-separated string.
	Only accessible by System Manager.
	"""
	import json
	from rndopsapp.delete_projects_tmp import ADMIN_ACTION_PASSWORD

	if override_password != ADMIN_ACTION_PASSWORD:
		return {"status": "error", "message": "Incorrect password. No records were deleted."}

	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Manager can delete documents.", frappe.PermissionError)

	if not doctype:
		frappe.throw("doctype is required.")

	if not frappe.db.exists("DocType", doctype):
		frappe.throw(f"DocType '{doctype}' does not exist.")

	# Parse docnames
	if isinstance(docnames, str):
		docnames = docnames.strip()
		if docnames.startswith("["):
			docnames = json.loads(docnames)
		else:
			docnames = [d.strip() for d in docnames.replace("\n", ",").split(",") if d.strip()]
	elif not isinstance(docnames, list):
		docnames = [str(docnames)]

	deleted = []
	not_found = []
	errors = []

	table_name = f"tab{doctype}"

	# Collect child table names for this doctype (used in raw SQL fallback)
	meta = frappe.get_meta(doctype)
	child_tables = [
		(df.options, f"tab{df.options}")
		for df in meta.fields
		if df.fieldtype in ("Table", "Table MultiSelect") and df.options
	]

	for docname in docnames:
		if not frappe.db.exists(doctype, docname):
			not_found.append(docname)
			continue

		first_err = None
		try:
			docstatus = frappe.db.get_value(doctype, docname, "docstatus")
			if docstatus == 1:
				frappe.db.set_value(doctype, docname, "docstatus", 2)
				frappe.db.commit()

			frappe.delete_doc(
				doctype,
				docname,
				ignore_permissions=True,
				force=True,
				ignore_on_trash=True,
				delete_permanently=True,
			)
			frappe.db.commit()
			deleted.append(docname)
		except Exception as e:
			first_err = str(e)
			try:
				# Delete child table rows first
				for _child_dt, child_table in child_tables:
					frappe.db.sql(
						f"DELETE FROM `{child_table}` WHERE parent = %s AND parenttype = %s",
						(docname, doctype),
					)
				# Delete parent row
				frappe.db.sql(f"DELETE FROM `{table_name}` WHERE name = %s", (docname,))
				frappe.db.commit()
				deleted.append(f"{docname} (raw SQL; frappe.delete_doc error: {first_err})")
			except Exception as e2:
				errors.append(f"{docname}: frappe.delete_doc → {first_err} | raw SQL → {str(e2)}")

	return {"deleted": deleted, "not_found": not_found, "errors": errors}


# Bench log files that are known to grow unbounded and are safe to truncate:
# - terminal.log: re-appended in full on every "terminal" tab poll in kafka_control.html
#   (see rndopsapp.rndopsapp.kafka.log_reader.get_kafka_logs), so it never shrinks on its own.
# - worker.error.log: filled almost entirely with harmless rq/datetime.utcnow() deprecation
#   warnings emitted on every background job.
CLEARABLE_BENCH_LOGS = ["terminal.log", "worker.error.log"]


@frappe.whitelist()
def get_bench_log_file_sizes():
	"""
	Current on-disk size of each file in CLEARABLE_BENCH_LOGS. Read-only, no password
	gate — used by the Danger Zone UI to show what a "Clear Log Files" click would free.
	"""
	from frappe.utils import get_bench_path

	log_dir = os.path.join(get_bench_path(), "logs")

	sizes = []
	for filename in CLEARABLE_BENCH_LOGS:
		path = os.path.join(log_dir, filename)
		sizes.append({
			"file": filename,
			"size_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
		})

	return {"files": sizes}


@frappe.whitelist()
def clear_bench_log_files(override_password=None):
	"""
	Truncate the bench-level log files in CLEARABLE_BENCH_LOGS (in place, so any process
	still holding the file open keeps writing correctly). Only accessible by System Manager,
	gated by the shared Danger Zone password.
	"""
	from frappe.utils import get_bench_path
	from rndopsapp.delete_projects_tmp import ADMIN_ACTION_PASSWORD

	if override_password != ADMIN_ACTION_PASSWORD:
		return {"status": "error", "message": "Incorrect password. No files were cleared."}

	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Manager can clear bench log files.", frappe.PermissionError)

	log_dir = os.path.join(get_bench_path(), "logs")

	cleared = []
	for filename in CLEARABLE_BENCH_LOGS:
		path = os.path.join(log_dir, filename)
		if not os.path.exists(path):
			continue
		freed_bytes = os.path.getsize(path)
		with open(path, "w", encoding="utf-8"):
			pass
		cleared.append({"file": filename, "freed_bytes": freed_bytes})

	return {"status": "cleared", "files": cleared}


@frappe.whitelist()
def terminate_user_sessions(user):
	"""
	Force-logout a user by clearing every one of their active sessions
	(from the `Sessions` table) — the same effect as them clicking "Log out"
	themselves, just triggered by an admin. Only accessible by System Manager.
	Reversible: the user can simply log back in.
	"""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Manager can terminate another user's sessions.", frappe.PermissionError)

	if not user:
		frappe.throw("user is required.")

	if not frappe.db.exists("User", user):
		frappe.throw(f"User '{user}' does not exist.")

	from frappe.sessions import clear_sessions

	clear_sessions(user=user, keep_current=(user == frappe.session.user), force=True)

	frappe.get_doc({
		"doctype": "Activity Log",
		"subject": f"{frappe.session.user} force-logged out {user}",
		"status": "Success",
		"operation": "Logout",
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	return {"status": "success", "message": f"Terminated all sessions for {user}."}


@frappe.whitelist()
def get_system_monitoring_stats():
	"""
	Point-in-time snapshot of host resource usage (CPU, memory, swap, disk,
	load average, uptime, process count) for the admin dashboard's monitoring
	graphs. The frontend polls this repeatedly and keeps its own rolling
	history in memory to draw trend lines — this endpoint only ever reports
	the current instant.
	"""
	import shutil
	import time

	import psutil

	cpu_percent = psutil.cpu_percent(interval=0.3)
	cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)

	vm = psutil.virtual_memory()
	swap = psutil.swap_memory()

	disk_path = frappe.utils.get_bench_path()
	disk = shutil.disk_usage(disk_path)

	try:
		load1, load5, load15 = os.getloadavg()
	except (OSError, AttributeError):
		load1 = load5 = load15 = None

	boot_time = psutil.boot_time()
	uptime_seconds = max(0, int(time.time() - boot_time))

	net = psutil.net_io_counters()

	return {
		"timestamp": frappe.utils.now(),
		"cpu": {
			"percent": cpu_percent,
			"per_core": cpu_per_core,
			"core_count": psutil.cpu_count(logical=True),
		},
		"memory": {
			"total": vm.total,
			"used": vm.used,
			"free": vm.free,
			"shared": getattr(vm, "shared", 0),
			"buff_cache": getattr(vm, "buffers", 0) + getattr(vm, "cached", 0),
			"available": vm.available,
			"percent": vm.percent,
		},
		"swap": {
			"total": swap.total,
			"used": swap.used,
			"free": swap.free,
			"percent": swap.percent,
		},
		"disk": {
			"total": disk.total,
			"used": disk.used,
			"free": disk.free,
			"percent": round(disk.used / disk.total * 100, 1) if disk.total else 0,
		},
		"load_average": {"1min": load1, "5min": load5, "15min": load15},
		"uptime_seconds": uptime_seconds,
		"process_count": len(psutil.pids()),
		"network": {
			"bytes_sent": net.bytes_sent,
			"bytes_recv": net.bytes_recv,
		},
	}


@frappe.whitelist()
def clear_system_cache():
	"""
	Clears Frappe cache and executes 'sudo sh -c "sync && echo 3 > /proc/sys/vm/drop_caches"'
	to free OS pagecache, dentries and inodes.
	"""
	import subprocess
	msg = []

	try:
		frappe.clear_cache()
		msg.append("Frappe cache cleared")
	except Exception as e:
		msg.append(f"Frappe cache: {e}")

	try:
		subprocess.run(["sync"], check=False)
		res = subprocess.run(
			"echo root@4321 | sudo -S sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'",
			shell=True,
			capture_output=True,
			text=True,
			timeout=10
		)
		if res.returncode == 0:
			msg.append("OS drop_caches executed (echo 3 > /proc/sys/vm/drop_caches)")
		else:
			msg.append(f"OS drop_caches executed (returncode {res.returncode})")
	except Exception as e:
		msg.append(f"OS drop_caches: {e}")

	return {"status": "success", "message": " | ".join(msg)}


@frappe.whitelist(allow_guest=True)
def execute_database_sql(sql_query):
	"""
	Executes raw SQL safely for admin/ready-mode usage.
	"""
	try:
		if not sql_query:
			frappe.throw("SQL query is required")

		is_select = sql_query.strip().upper().startswith(("SELECT", "SHOW", "DESC"))

		if is_select:
			result = frappe.db.sql(sql_query, as_dict=True)
			return {"status": "success", "result": result}
		else:
			frappe.db.sql(sql_query)
			frappe.db.commit()
			return {"status": "success", "result": []}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "execute_database_sql failed")
		return {"status": "error", "message": str(e)}


# -------------------- Rndopsapp Doctype Explorer (SQL console helper) --------------------

_EXPLORER_MODULE = "Rndopsapp"


@frappe.whitelist()
def list_rndopsapp_doctypes():
	"""Return every DocType registered under the Rndopsapp module, for the SQL console's Doctype Explorer."""
	doctypes = frappe.get_all(
		"DocType",
		filters={"module": _EXPLORER_MODULE},
		fields=["name", "istable", "issingle"],
		order_by="name asc",
	)
	return {"status": "success", "doctypes": doctypes}


@frappe.whitelist()
def list_doctype_documents(doctype, search=None, limit=100):
	"""
	Lightweight document picker for a Rndopsapp-module doctype: latest documents
	(optionally name-filtered), for the Document Editor's doctype -> document list.
	"""
	from frappe.utils import cint

	module = frappe.db.get_value("DocType", doctype, "module")
	if module != _EXPLORER_MODULE:
		return {"status": "error", "message": f"'{doctype}' is not part of the {_EXPLORER_MODULE} module."}

	meta = frappe.get_meta(doctype)
	fields = ["name", "modified"]
	if meta.has_field("workflow_state"):
		fields.append("workflow_state")

	filters = {}
	if search:
		filters["name"] = ["like", f"%{search}%"]

	safe_limit = min(cint(limit) or 100, 500)
	documents = frappe.get_all(doctype, filters=filters, fields=fields, order_by="modified desc", limit=safe_limit)
	total = frappe.db.count(doctype, filters=filters)

	return {"status": "success", "doctype": doctype, "documents": documents, "shown": len(documents), "total": total}


def _get_real_table_columns(doctype):
	"""
	Real DB column names for a doctype's table, straight from information_schema.
	DocType meta can list fields that haven't been migrated into the DB table yet
	(schema drift), so anything selected in the query builder must also be checked
	against this before being sent to SQL.
	"""
	try:
		return set(frappe.db.get_table_columns(doctype))
	except Exception:
		return None


@frappe.whitelist()
def get_doctype_schema_and_data(doctype, limit=50):
	"""
	Return the field schema and a live data preview for a Rndopsapp-module DocType.
	Restricted to the Rndopsapp module so this can't be used to browse arbitrary
	system/core doctypes (User, Role, etc.).
	"""
	from frappe.utils import cint

	module = frappe.db.get_value("DocType", doctype, "module")
	if module != _EXPLORER_MODULE:
		return {"status": "error", "message": f"'{doctype}' is not part of the {_EXPLORER_MODULE} module."}

	meta = frappe.get_meta(doctype)
	skip_types = {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}
	table_types = {"Table", "Table MultiSelect"}
	table_columns = _get_real_table_columns(doctype)
	fields = [
		{
			"fieldname": df.fieldname,
			"label": df.label or df.fieldname,
			"fieldtype": df.fieldtype,
			"options": df.options or "",
		}
		for df in meta.fields
		if df.fieldtype not in skip_types
		and df.fieldtype not in table_types
		and (table_columns is None or df.fieldname in table_columns)
	]
	if meta.istable:
		std_child_fields = [
			f for f in ("parent", "parentfield", "parenttype") if table_columns is None or f in table_columns
		]
		fields = [{"fieldname": f, "label": f, "fieldtype": "Data", "options": ""} for f in std_child_fields] + fields

	child_tables = [
		{
			"fieldname": df.fieldname,
			"label": df.label or df.fieldname,
			"child_doctype": df.options,
		}
		for df in meta.fields
		if df.fieldtype in table_types and df.options
	]

	linked_doctypes = []
	for df in meta.fields:
		if df.fieldtype != "Link" or not df.options:
			continue
		target_module = frappe.db.get_value("DocType", df.options, "module")
		if target_module != _EXPLORER_MODULE:
			continue
		linked_doctypes.append(
			{"fieldname": df.fieldname, "label": df.label or df.fieldname, "linked_doctype": df.options}
		)

	safe_limit = min(cint(limit) or 50, 500)

	try:
		rows = frappe.db.sql(
			f"SELECT * FROM `tab{doctype}` ORDER BY modified DESC LIMIT {safe_limit}", as_dict=True
		)
	except Exception as e:
		return {"status": "error", "message": f"Failed to read table data: {e}"}

	total = frappe.db.count(doctype)

	return {
		"status": "success",
		"doctype": doctype,
		"fields": fields,
		"child_tables": child_tables,
		"linked_doctypes": linked_doctypes,
		"data": rows,
		"total_records": total,
		"shown": len(rows),
	}


_QUERY_BUILDER_OPS = {
	"=": "=",
	"!=": "!=",
	">": ">",
	"<": "<",
	">=": ">=",
	"<=": "<=",
	"like": "LIKE",
	"is": "IS",
	"is not": "IS NOT",
}


def _valid_fieldnames_for(meta, table_types):
	"""Selectable/filterable fieldnames for a doctype: real DB columns, minus Table fields."""
	standard_fields = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}
	if meta.istable:
		standard_fields |= {"parent", "parentfield", "parenttype"}
	valid_fieldnames = {df.fieldname for df in meta.fields if df.fieldtype not in table_types} | standard_fields
	table_columns = _get_real_table_columns(meta.name)
	if table_columns is not None:
		valid_fieldnames &= table_columns
	return valid_fieldnames


@frappe.whitelist()
def run_query_builder(doctype, columns=None, filters=None, limit=100, child_tables=None):
	"""
	No-code query builder backing the Doctype Explorer: builds and runs a safe,
	parameterized SELECT from structured columns + filters (never raw SQL from the
	client), and returns the generated SQL text alongside the rows.

	columns: JSON list of fieldnames to select from the main doctype.
	filters: JSON list of {"field": str, "operator": str, "value": str}.
	         operator must be one of _QUERY_BUILDER_OPS' keys. Applies to the main doctype only.
	child_tables: JSON list of {"fieldname": str, "columns": [str, ...]}. "fieldname" must be
	              one of the doctype's own Table/Table MultiSelect fields; each entry becomes a
	              LEFT JOIN against that child doctype's table (matched on parent/parentfield),
	              so the result has one row per parent+child-row combination, with the chosen
	              child columns included as `<fieldname>__<column>`.
	"""
	import json

	from frappe.utils import cint

	module = frappe.db.get_value("DocType", doctype, "module")
	if module != _EXPLORER_MODULE:
		return {"status": "error", "message": f"'{doctype}' is not part of the {_EXPLORER_MODULE} module."}

	meta = frappe.get_meta(doctype)
	table_types = {"Table", "Table MultiSelect"}
	valid_fieldnames = _valid_fieldnames_for(meta, table_types)

	if isinstance(columns, str):
		columns = json.loads(columns) if columns else []
	columns = [c for c in (columns or []) if c in valid_fieldnames]
	if not columns:
		columns = ["name"]

	if isinstance(filters, str):
		filters = json.loads(filters) if filters else []

	where_clauses = []
	where_params = []
	for f in filters or []:
		field = (f or {}).get("field")
		op = ((f or {}).get("operator") or "=").lower()
		value = (f or {}).get("value", "")

		if field not in valid_fieldnames or op not in _QUERY_BUILDER_OPS:
			continue

		sql_op = _QUERY_BUILDER_OPS[op]
		qualified_field = f"`tab{doctype}`.`{field}`"
		if sql_op in ("IS", "IS NOT"):
			where_clauses.append(f"{qualified_field} {sql_op} NULL")
		elif sql_op == "LIKE":
			where_clauses.append(f"{qualified_field} LIKE %s")
			where_params.append(f"%{value}%")
		else:
			where_clauses.append(f"{qualified_field} {sql_op} %s")
			where_params.append(value)

	# -- child table joins: fieldname must be a real Table field on this doctype's own meta,
	# never trusted from the client directly, so the child doctype/alias are always ours. --
	table_fields_by_name = {
		df.fieldname: df for df in meta.fields if df.fieldtype in table_types and df.options
	}

	if isinstance(child_tables, str):
		child_tables = json.loads(child_tables) if child_tables else []

	join_sql_parts = []
	join_params = []
	child_col_sql_parts = []
	output_child_columns = []
	for entry in child_tables or []:
		fieldname = (entry or {}).get("fieldname")
		df = table_fields_by_name.get(fieldname)
		if not df:
			continue
		child_doctype = df.options
		child_meta = frappe.get_meta(child_doctype)
		child_valid = _valid_fieldnames_for(child_meta, table_types)

		requested_cols = [c for c in (entry.get("columns") or []) if c in child_valid]
		if not requested_cols:
			continue

		alias = f"cj_{fieldname}"
		join_sql_parts.append(
			f" LEFT JOIN `tab{child_doctype}` `{alias}` ON `{alias}`.`parent` = `tab{doctype}`.`name`"
			f" AND `{alias}`.`parentfield` = %s"
		)
		join_params.append(fieldname)
		for c in requested_cols:
			out_name = f"{fieldname}__{c}"
			child_col_sql_parts.append(f"`{alias}`.`{c}` AS `{out_name}`")
			output_child_columns.append(out_name)

	safe_limit = min(cint(limit) or 100, 1000)
	col_sql = ", ".join([f"`tab{doctype}`.`{c}`" for c in columns] + child_col_sql_parts)
	join_sql = "".join(join_sql_parts)
	where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
	query = (
		f"SELECT {col_sql} FROM `tab{doctype}`{join_sql}{where_sql} "
		f"ORDER BY `tab{doctype}`.`modified` DESC LIMIT {safe_limit}"
	)

	try:
		rows = frappe.db.sql(query, tuple(join_params + where_params), as_dict=True)
	except Exception as e:
		return {"status": "error", "message": str(e), "query": query}

	columns = columns + output_child_columns

	return {
		"status": "success",
		"doctype": doctype,
		"query": query,
		"columns": columns,
		"result": rows,
		"row_count": len(rows),
	}


# -------------------- PROJECT REGISTRATION FIELD UPDATE --------------------


@frappe.whitelist()
def update_project_registration(docname, fields):
	"""
	Update fields on a Project Registration document bypassing UpdateAfterSubmitError.
	Uses frappe.db.set_value directly so submitted documents can be corrected.
	Workflow state, docstatus, and other system fields are always protected.
	"""
	import json

	PROTECTED = {
		"workflow_state",
		"workflow_action",
		"docstatus",
		"name",
		"owner",
		"creation",
		"doctype",
		"idx",
		"amended_from",
	}

	if isinstance(fields, str):
		fields = json.loads(fields)

	if not docname or not fields:
		return {"status": "error", "message": "docname and fields are required"}

	if not frappe.db.exists("Project Registration", docname):
		return {"status": "error", "message": f"Document '{docname}' not found"}

	safe_fields = {k: v for k, v in fields.items() if k not in PROTECTED}

	if not safe_fields:
		return {"status": "error", "message": "No updatable fields after removing protected fields"}

	try:
		now = frappe.utils.now()
		user = frappe.session.user

		for field, value in safe_fields.items():
			frappe.db.set_value("Project Registration", docname, field, value, update_modified=False)

		frappe.db.set_value(
			"Project Registration", docname, {"modified": now, "modified_by": user}, update_modified=False
		)

		frappe.db.commit()

		return {
			"status": "success",
			"updated_fields": list(safe_fields.keys()),
			"modified": now,
			"modified_by": user,
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "update_project_registration failed")
		return {"status": "error", "message": str(e)}


# -------------------- GENERIC DOCUMENT EDITOR (any Rndopsapp doctype + child tables) --------------------
# Backs the /document_edit page: load any Rndopsapp-module document (including its
# child table rows) for editing, then write back only the fields that actually
# changed via frappe.db.set_value — never a full-document overwrite — so fields the
# editor didn't render (or the user didn't touch) can never be silently wiped.

_DOC_EDIT_PROTECTED_FIELDS = {
	"name", "owner", "creation", "modified", "modified_by", "doctype",
	"docstatus", "idx", "workflow_state", "workflow_action", "amended_from",
}
_DOC_EDIT_SKIP_TYPES = {"Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"}


def _doc_edit_field_list(meta, table_types):
	"""
	Editable field metadata for a doctype: real DB columns, minus Table/structural fields.
	Each field carries the label of the Section Break it falls under (if any), so the
	Document Editor can group the flat field list into the doctype's real form sections.
	"""
	table_columns = _get_real_table_columns(meta.name)
	fields = []
	current_section = None
	for df in meta.fields:
		if df.fieldtype == "Section Break":
			current_section = df.label or None
			continue
		if (
			df.fieldtype in _DOC_EDIT_SKIP_TYPES
			or df.fieldtype in table_types
			or (table_columns is not None and df.fieldname not in table_columns)
		):
			continue
		fields.append({
			"fieldname": df.fieldname,
			"label": df.label or df.fieldname,
			"fieldtype": df.fieldtype,
			"options": df.options or "",
			"reqd": bool(df.reqd),
			"read_only": bool(df.read_only) or df.fieldname in _DOC_EDIT_PROTECTED_FIELDS,
			"description": df.description or "",
			"section": current_section,
		})
	return fields


def _doc_edit_link_options(meta):
	"""
	{fieldname: [{value, label}, ...]} for every Link field on this doctype, capped at 200
	rows each — same "fetch the linked doctype's name + title" pattern already used by
	e_non_routine_deposit_slip.get_e_non_routine_deposit_slip_fields for its link_options.
	"""
	options = {}
	for df in meta.fields:
		if df.fieldtype != "Link" or not df.options:
			continue
		linked_doctype = df.options
		try:
			if linked_doctype == "User":
				rows = frappe.get_all(
					linked_doctype, fields=["name as value", "full_name as label"],
					limit=200, order_by="modified desc",
				)
			else:
				linked_meta = frappe.get_meta(linked_doctype)
				title_field = linked_meta.title_field
				label_expr = f"{title_field} as label" if title_field and title_field != "name" else "name as label"
				rows = frappe.get_all(
					linked_doctype, fields=["name as value", label_expr],
					limit=200, order_by="modified desc",
				)
		except Exception:
			rows = []
		options[df.fieldname] = rows
	return options


def _doc_edit_schema(doctype, meta, table_types):
	"""Field + child-table schema shared by get_document_for_edit and get_new_document_schema."""
	fields = _doc_edit_field_list(meta, table_types)
	link_options = _doc_edit_link_options(meta)

	child_tables = []
	for df in meta.fields:
		if df.fieldtype not in table_types or not df.options:
			continue
		child_doctype = df.options
		child_meta = frappe.get_meta(child_doctype)
		child_tables.append({
			"fieldname": df.fieldname,
			"label": df.label or df.fieldname,
			"child_doctype": child_doctype,
			"fields": _doc_edit_field_list(child_meta, table_types),
			"link_options": _doc_edit_link_options(child_meta),
		})

	return fields, child_tables, link_options


@frappe.whitelist()
def get_document_for_edit(doctype, docname):
	"""
	Returns editable field schema + current values for a Rndopsapp-module document,
	including its child tables, for the Document Editor page.
	"""
	module = frappe.db.get_value("DocType", doctype, "module")
	if module != _EXPLORER_MODULE:
		return {"status": "error", "message": f"'{doctype}' is not part of the {_EXPLORER_MODULE} module."}

	if not frappe.db.exists(doctype, docname):
		return {"status": "error", "message": f"'{docname}' not found in {doctype}."}

	meta = frappe.get_meta(doctype)
	table_types = {"Table", "Table MultiSelect"}
	fields, child_tables, link_options = _doc_edit_schema(doctype, meta, table_types)

	select_fieldnames = list(dict.fromkeys([f["fieldname"] for f in fields] + ["name"]))
	data = frappe.db.get_value(doctype, docname, select_fieldnames, as_dict=True) or {}

	for ct in child_tables:
		child_select = list(dict.fromkeys([cf["fieldname"] for cf in ct["fields"]] + ["name", "idx"]))
		ct["rows"] = frappe.get_all(
			ct["child_doctype"],
			filters={"parent": docname, "parenttype": doctype, "parentfield": ct["fieldname"]},
			fields=child_select,
			order_by="idx asc",
		)

	return {
		"status": "success",
		"doctype": doctype,
		"docname": docname,
		"fields": fields,
		"data": data,
		"child_tables": child_tables,
		"link_options": link_options,
	}


@frappe.whitelist()
def get_new_document_schema(doctype):
	"""
	Same shape as get_document_for_edit, but for a brand-new (not yet created)
	Rndopsapp-module document: no existing data, empty child table rows.
	"""
	module = frappe.db.get_value("DocType", doctype, "module")
	if module != _EXPLORER_MODULE:
		return {"status": "error", "message": f"'{doctype}' is not part of the {_EXPLORER_MODULE} module."}

	meta = frappe.get_meta(doctype)
	table_types = {"Table", "Table MultiSelect"}
	fields, child_tables, link_options = _doc_edit_schema(doctype, meta, table_types)
	for ct in child_tables:
		ct["rows"] = []

	return {
		"status": "success",
		"doctype": doctype,
		"docname": None,
		"fields": fields,
		"data": {},
		"child_tables": child_tables,
		"link_options": link_options,
	}


@frappe.whitelist()
def create_document(doctype, values=None, child_table_rows=None):
	"""
	Creates a brand-new Rndopsapp-module document from the Document Editor's "+ New"
	form. Only whitelisted (real-column, non-Table) fields are set; child table rows
	are appended the same way get_document_for_edit/update_document_fields shape them.

	values: JSON dict {fieldname: value} for the new document.
	child_table_rows: JSON list of {"fieldname": <Table field>, "rows": [{field: value, ...}, ...]}
	"""
	if isinstance(values, str):
		values = json.loads(values) if values else {}
	if isinstance(child_table_rows, str):
		child_table_rows = json.loads(child_table_rows) if child_table_rows else []

	module = frappe.db.get_value("DocType", doctype, "module")
	if module != _EXPLORER_MODULE:
		return {"status": "error", "message": f"'{doctype}' is not part of the {_EXPLORER_MODULE} module."}

	meta = frappe.get_meta(doctype)
	table_types = {"Table", "Table MultiSelect"}
	valid_fieldnames = _valid_fieldnames_for(meta, table_types) - _DOC_EDIT_PROTECTED_FIELDS
	table_fields_by_name = {
		df.fieldname: df for df in meta.fields if df.fieldtype in table_types and df.options
	}

	try:
		doc = frappe.new_doc(doctype)
		for field, value in (values or {}).items():
			if field in valid_fieldnames:
				doc.set(field, value)

		for entry in child_table_rows or []:
			fieldname = (entry or {}).get("fieldname")
			df = table_fields_by_name.get(fieldname)
			if not df:
				continue
			child_doctype = df.options
			child_meta = frappe.get_meta(child_doctype)
			child_valid = _valid_fieldnames_for(child_meta, table_types) - {
				"parent", "parentfield", "parenttype",
			}
			for row in entry.get("rows") or []:
				row_data = {f: v for f, v in (row or {}).items() if f in child_valid}
				if row_data:
					doc.append(fieldname, row_data)

		doc.insert(ignore_permissions=True)
		frappe.db.commit()

		return {"status": "success", "doctype": doctype, "docname": doc.name}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "create_document failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_document_fields(doctype, docname, changes=None, child_table_changes=None):
	"""
	Applies only the changed fields to a Rndopsapp-module document (and optionally its
	child tables) via frappe.db.set_value per field — every other field is left
	completely untouched.

	changes: JSON dict {fieldname: new_value} for the parent document.
	child_table_changes: JSON list of
	    {"fieldname": <Table field on the parent doctype>,
	     "updated": [{"name": <child row name>, "changes": {field: value}}, ...],
	     "inserted": [{field: value, ...}, ...],
	     "deleted": [<child row name>, ...]}
	"""
	if isinstance(changes, str):
		changes = json.loads(changes) if changes else {}
	if isinstance(child_table_changes, str):
		child_table_changes = json.loads(child_table_changes) if child_table_changes else []

	module = frappe.db.get_value("DocType", doctype, "module")
	if module != _EXPLORER_MODULE:
		return {"status": "error", "message": f"'{doctype}' is not part of the {_EXPLORER_MODULE} module."}

	if not frappe.db.exists(doctype, docname):
		return {"status": "error", "message": f"'{docname}' not found in {doctype}."}

	meta = frappe.get_meta(doctype)
	table_types = {"Table", "Table MultiSelect"}
	valid_fieldnames = _valid_fieldnames_for(meta, table_types) - _DOC_EDIT_PROTECTED_FIELDS
	table_fields_by_name = {
		df.fieldname: df for df in meta.fields if df.fieldtype in table_types and df.options
	}

	def _row_belongs_here(child_doctype, row_name, fieldname):
		owner = frappe.db.get_value(child_doctype, row_name, ["parent", "parentfield"], as_dict=True)
		return bool(owner) and owner.parent == docname and owner.parentfield == fieldname

	updated_fields = []
	child_summary = []

	try:
		for field, value in (changes or {}).items():
			if field not in valid_fieldnames:
				continue
			frappe.db.set_value(doctype, docname, field, value, update_modified=False)
			updated_fields.append(field)

		for entry in child_table_changes or []:
			fieldname = (entry or {}).get("fieldname")
			df = table_fields_by_name.get(fieldname)
			if not df:
				continue
			child_doctype = df.options
			child_meta = frappe.get_meta(child_doctype)
			child_valid = _valid_fieldnames_for(child_meta, table_types) - {
				"parent", "parentfield", "parenttype",
			}

			n_updated = n_inserted = n_deleted = 0

			for row in entry.get("updated") or []:
				row_name = (row or {}).get("name")
				row_changes = (row or {}).get("changes") or {}
				if not row_name or not _row_belongs_here(child_doctype, row_name, fieldname):
					continue
				for cfield, cvalue in row_changes.items():
					if cfield not in child_valid:
						continue
					frappe.db.set_value(child_doctype, row_name, cfield, cvalue, update_modified=False)
				n_updated += 1

			if entry.get("inserted"):
				max_idx = frappe.db.sql(
					f"SELECT COALESCE(MAX(idx), 0) FROM `tab{child_doctype}` WHERE parent=%s AND parentfield=%s",
					(docname, fieldname),
				)[0][0]
				for new_row in entry.get("inserted") or []:
					max_idx += 1
					row_doc = frappe.new_doc(child_doctype)
					row_doc.parent = docname
					row_doc.parenttype = doctype
					row_doc.parentfield = fieldname
					row_doc.idx = max_idx
					for cfield, cvalue in (new_row or {}).items():
						if cfield in child_valid:
							row_doc.set(cfield, cvalue)
					row_doc.insert(ignore_permissions=True)
					n_inserted += 1

			for row_name in entry.get("deleted") or []:
				if not _row_belongs_here(child_doctype, row_name, fieldname):
					continue
				frappe.db.sql(f"DELETE FROM `tab{child_doctype}` WHERE name=%s", (row_name,))
				n_deleted += 1

			if n_updated or n_inserted or n_deleted:
				child_summary.append({
					"fieldname": fieldname, "updated": n_updated, "inserted": n_inserted, "deleted": n_deleted,
				})

		now = frappe.utils.now()
		user = frappe.session.user
		frappe.db.set_value(doctype, docname, {"modified": now, "modified_by": user}, update_modified=False)
		frappe.db.commit()

		return {
			"status": "success",
			"doctype": doctype,
			"docname": docname,
			"updated_fields": updated_fields,
			"child_tables": child_summary,
			"modified": now,
			"modified_by": user,
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "update_document_fields failed")
		return {"status": "error", "message": str(e)}


# -------------------- MATTERMOST NOTIFICATION API (MKY) --------------------

_MM_BASE = "http://172.16.135.118:8065/api/v4"
_MM_URL = f"{_MM_BASE}/posts"
_MM_FILES_URL = f"{_MM_BASE}/files"
_MM_TOKEN = "Bearer fmjih41b4iymicttnuhinsqime"
_MM_DEFAULT_CHANNEL = "ihmkbbfq9ibzugfpy9rncq5yke"

# Channel name → Mattermost channel ID mapping (used for dropdowns)
_MM_CHANNELS = {
	"kafka logs": "yh7piky97iycjrdytia1hqy99a",
	"Feedback PRORND": "jnkacpywbjnh9frhg1bb8gs85y",
	"logs": "ihmkbbfq9ibzugfpy9rncq5yke",
}


@frappe.whitelist(allow_guest=True)
def get_mattermost_channel_list():
	"""Return the channel list for frontend dropdowns."""
	return [{"label": name, "value": cid} for name, cid in _MM_CHANNELS.items()]


@frappe.whitelist(allow_guest=True)
def publish_to_mattermost(
	message: str,
	channel_id: str = _MM_DEFAULT_CHANNEL,
	channel_name: str = None,
	date_from: str = None,
	date_to: str = None,
	urgent: bool = False,
	feedback: bool = False,
	current_user_email: str = None,
	files=None,
):
	"""
	Whitelisted API endpoint to post a message to Mattermost.

	Params:
	  message            – text to post (required)
	  channel_id         – target channel ID; overridden by channel_name if provided
	  channel_name       – friendly channel name from the dropdown (see get_mattermost_channel_list)
	  date_from          – optional ISO date string (YYYY-MM-DD) — informational, included in message
	  date_to            – optional ISO date string (YYYY-MM-DD) — informational, included in message
	  urgent             – if True, sends with Mattermost urgent priority flag
	  feedback           – if True and current_user_email is set, also sends email
	  current_user_email – caller's email address; used only when feedback=True
	  files              – list of (filename, bytes, content_type) tuples to attach

	Returns:
	  {"status": "sent",   "http_status": <int>}
	  {"status": "failed", "http_status": <int>, "error": …}
	  {"status": "error",  "error": …}
	"""
	import requests as _req

	message = (message or "").strip()
	if not message:
		frappe.throw("message is required and cannot be blank.")

	# Append date range to message if provided
	if date_from or date_to:
		date_range_str = f"{date_from or '?'} → {date_to or '?'}"
		message = f"{message}\n📅 Date Range: {date_range_str}"

	# Normalise bools coming in as strings from HTTP query params
	if isinstance(urgent, str):
		urgent = urgent.lower() in ("1", "true", "yes")
	if isinstance(feedback, str):
		feedback = feedback.lower() in ("1", "true", "yes")

	# Resolve channel_name → channel_id from the predefined list
	if channel_name and channel_name.strip():
		channel_id = _MM_CHANNELS.get(channel_name.strip(), channel_id)

	# Fall back to default channel if caller passed an empty string
	if not channel_id or not channel_id.strip():
		channel_id = _MM_DEFAULT_CHANNEL

	# Collect files from the parameter (Python calls) and from HTTP multipart uploads
	raw_files = list(files or [])
	request_files = getattr(frappe.request, "files", None)
	if request_files:
		for _field, fs in request_files.items(multi=True):
			raw_files.append((fs.filename, fs.read(), fs.content_type or "application/octet-stream"))

	# Upload each file to Mattermost and collect file_ids
	mm_headers = {"Authorization": _MM_TOKEN}
	file_ids = []
	for filename, content, content_type in raw_files:
		try:
			upload_resp = _req.post(
				_MM_FILES_URL,
				data={"channel_id": channel_id},
				files={"files": (filename, content, content_type)},
				headers=mm_headers,
				timeout=(5, 15),
			)
			if upload_resp.ok:
				file_ids.extend(f["id"] for f in upload_resp.json().get("file_infos", []))
			else:
				frappe.log_error(
					f"Mattermost file upload failed – {upload_resp.status_code}: {upload_resp.text[:300]}",
					"publish_to_mattermost",
				)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "publish_to_mattermost file upload")

	# Prepend sender identity — same pattern as the email body
	if current_user_email:
		message = f"From: {current_user_email}\n\n{message}"

	payload = {
		"channel_id": channel_id,
		"message": message,
	}

	if file_ids:
		payload["file_ids"] = file_ids

	if urgent:
		payload["metadata"] = {
			"priority": {
				"priority": "urgent",
				"requested_ack": False,
				"persistent_notifications": False,
			}
		}

	headers = {
		"Authorization": _MM_TOKEN,
		"Content-Type": "application/json",
	}

	try:
		resp = _req.post(_MM_URL, json=payload, headers=headers, timeout=(2, 3))

		if resp.ok:
			is_feedback_channel = channel_id == _MM_CHANNELS.get("Feedback PRORND")
			if (feedback and current_user_email) or is_feedback_channel:
				subject = "🚨 [URGENT] PRORND Feedback" if urgent else "PRORND Feedback"
				sender_line = f"From: {current_user_email}\n\n" if current_user_email else ""
				frappe.enqueue(
					"rndopsapp.rndopsapp.email_service.send_email",
					queue="short",
					subject=subject,
					message=f"{sender_line}{message}",
					attachments=raw_files if raw_files else None,
				)
			return {"status": "sent", "http_status": resp.status_code}

		frappe.log_error(
			f"Mattermost post failed – HTTP {resp.status_code}: {resp.text[:500]}",
			"publish_to_mattermost",
		)
		return {
			"status": "failed",
			"http_status": resp.status_code,
			"error": resp.text[:500],
		}

	except _req.exceptions.Timeout:
		frappe.log_error("Mattermost request timed out.", "publish_to_mattermost")
		return {"status": "error", "error": "Request timed out"}

	except Exception as exc:
		frappe.log_error(frappe.get_traceback(), "publish_to_mattermost")
		return {"status": "error", "error": str(exc)}


@frappe.whitelist(allow_guest=True)
def clear_mattermost_channel(
	channel_name: str,
	date_from: str = None,
	date_to: str = None,
	override_password: str = None,
):
	"""
	Delete posts in a Mattermost channel identified by its name.

	Params:
	  channel_name – friendly channel name (matched against _MM_CHANNELS or Mattermost search)
	  date_from    – optional ISO date string (YYYY-MM-DD); delete posts on/after this date
	  date_to      – optional ISO date string (YYYY-MM-DD); delete posts on/before this date
	  override_password – required admin gate password

	Returns:
	  {"status": "cleared", "deleted": <int>}
	  {"status": "error",   "error": …}
	"""
	from datetime import datetime, timezone

	import requests as _req
	from rndopsapp.delete_projects_tmp import ADMIN_ACTION_PASSWORD

	if override_password != ADMIN_ACTION_PASSWORD:
		return {"status": "error", "error": "Incorrect password. Channel was not cleared."}

	channel_name = (channel_name or "").strip()
	if not channel_name:
		frappe.throw("channel_name is required.")

	# Convert date strings to millisecond UTC timestamps (Mattermost uses ms epoch)
	ts_from = None
	ts_to = None
	if date_from:
		ts_from = int(
			datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000
		)
	if date_to:
		# Include the full last day (end of day 23:59:59)
		ts_to = int(
			datetime.strptime(date_to + " 23:59:59", "%Y-%m-%d %H:%M:%S")
			.replace(tzinfo=timezone.utc)
			.timestamp()
			* 1000
		)

	headers = {
		"Authorization": _MM_TOKEN,
		"Content-Type": "application/json",
	}

	try:
		# Resolve channel_name → channel_id via _MM_CHANNELS first, then fall back to search
		channel_id = _MM_CHANNELS.get(channel_name)

		if not channel_id:
			search_resp = _req.post(
				f"{_MM_BASE}/channels/search",
				json={"term": channel_name},
				headers=headers,
				timeout=(3, 5),
			)
			if not search_resp.ok:
				return {"status": "error", "error": f"Channel search failed: {search_resp.text[:300]}"}

			channels = search_resp.json()
			channel = next(
				(
					c
					for c in channels
					if c.get("name") == channel_name or c.get("display_name") == channel_name
				),
				None,
			)
			if not channel:
				return {"status": "error", "error": f"Channel '{channel_name}' not found."}
			channel_id = channel["id"]

		deleted_count = 0
		page = 0

		# Paginate through all posts and delete those within the date range
		while True:
			posts_resp = _req.get(
				f"{_MM_BASE}/channels/{channel_id}/posts",
				params={"page": page, "per_page": 200},
				headers=headers,
				timeout=(3, 10),
			)
			if not posts_resp.ok:
				return {"status": "error", "error": f"Failed to fetch posts: {posts_resp.text[:300]}"}

			posts_data = posts_resp.json()
			posts = posts_data.get("posts", {})
			if not posts:
				break

			for post_id, post in posts.items():
				create_at = post.get("create_at", 0)
				if ts_from and create_at < ts_from:
					continue
				if ts_to and create_at > ts_to:
					continue
				del_resp = _req.delete(
					f"{_MM_BASE}/posts/{post_id}",
					params={"permanent": "true"},
					headers=headers,
					timeout=(2, 5),
				)
				if del_resp.ok:
					deleted_count += 1
				else:
					frappe.log_error(
						f"Failed to delete post {post_id}: {del_resp.text[:200]}",
						"clear_mattermost_channel",
					)

			if len(posts) < 200:
				break
			page += 1

		return {"status": "cleared", "deleted": deleted_count}

	except Exception as exc:
		frappe.log_error(frappe.get_traceback(), "clear_mattermost_channel")
		return {"status": "error", "error": str(exc)}


@frappe.whitelist()
def get_declaration_html(doctype):
	"""
	Returns the content of every fieldtype="HTML" DocField on `doctype`
	(e.g. Travel's applicant-declaration paragraph and its unrelated SCL-balance
	placeholder, or TA DA Settlement's document-submission instructions),
	keyed by fieldname — the same fields the on-screen <DeclarationFields>
	widget shows — for reuse in print-PDF generators. Returning a per-field
	map (rather than one concatenated string) lets a caller route specific
	fields to a different print section instead of lumping everything under
	"Declaration" (e.g. Travel's travel_leave_balance_html belongs under
	"Special Casual Leave & Leave Period", not the declaration text).

	"DocField" has no DocPerm rows of its own (it's metadata, not document
	data), so a direct frappe.client.get_list("DocField", ...) call — what
	<DeclarationFields> and the print generators used before — returns a
	PermissionError for any role other than System Manager, leaving the
	Declaration section blank for everyone else. This whitelisted method
	bypasses that restriction for this one safe, read-only lookup.
	"""
	if not doctype:
		return {"status": "error", "message": "doctype is required"}

	fields = frappe.get_all(
		"DocField",
		filters={"parent": doctype, "fieldtype": "HTML"},
		fields=["fieldname", "label", "options"],
		order_by="idx",
		ignore_permissions=True,
	)
	field_html = {f.fieldname: (f.options or "").strip() for f in fields if (f.options or "").strip()}
	return {"status": "success", "fields": field_html}


@frappe.whitelist()
def get_user_designation(email):
	"""
	Returns a User's designation_name for the given email.

	"User" read permission is restricted to System Manager / Permanent
	Employee (see DocPerm), so a plain frappe.client.get_value REST call
	403s for many approver roles (e.g. Dean, RnD) — this bypasses that via
	frappe.db.get_value (a raw lookup, not permission-checked) for this one
	safe, non-sensitive field, used to label commenters in the Activity Log
	print section.
	"""
	if not email:
		return {"status": "error", "message": "email is required"}
	designation = frappe.db.get_value("User", email, "designation_name")
	return {"status": "success", "designation_name": designation or ""}


@frappe.whitelist()
def get_document_activity(doctype, docname):
	"""
	Returns a unified, chronologically-sorted activity timeline for a document.

	Each entry contains:
	  type        – comment | edit | workflow | assignment | attachment | share | creation
	  label       – human-readable action phrase, e.g. "commented", "created this"
	  user        – full name of the actor
	  user_email  – raw owner/email
	  timestamp   – ISO datetime string
	  content     – message text (only present for comment/workflow entries)
	"""
	if not frappe.db.exists(doctype, docname):
		frappe.throw(f"{doctype} '{docname}' not found.", frappe.DoesNotExistError)

	if not frappe.has_permission(doctype, "read", docname):
		frappe.throw("Not permitted.", frappe.PermissionError)

	# --- 1. Fetch all Comment rows for this document ---
	comment_type_map = {
		"Comment": ("comment", "commented"),
		"Edit": ("edit", "edited this"),
		"Info": ("edit", "edited this"),
		"Label": ("edit", "edited this"),
		"Workflow": ("workflow", "updated the workflow"),
		"Assigned": ("assignment", "was assigned"),
		"Assignment Completed": ("assignment", "completed assignment"),
		"Shared": ("share", "shared this"),
		"Unshared": ("share", "unshared this"),
		"Attachment": ("attachment", "added an attachment"),
		"Attachment Removed": ("attachment", "removed an attachment"),
		"Like": ("like", "liked this"),
	}

	raw_comments = frappe.get_all(
		"Comment",
		filters={"reference_doctype": doctype, "reference_name": docname},
		fields=["owner", "creation", "content", "comment_type"],
		order_by="creation desc",
	)

	# --- 2. Fetch last Version entry (for "last edited" when no Edit comment exists) ---
	last_version = None
	meta = frappe.get_meta(doctype)
	if meta.track_changes:
		versions = frappe.get_all(
			"Version",
			filters={"ref_doctype": doctype, "docname": docname},
			fields=["owner", "creation"],
			order_by="creation desc",
			limit=1,
		)
		if versions:
			last_version = versions[0]

	# --- 3. Document creation row ---
	doc_row = frappe.db.get_value(doctype, docname, ["owner", "creation"], as_dict=True)

	# --- 4. Collect all unique owners so we can batch-resolve full names ---
	all_owners = {c.owner for c in raw_comments}
	all_owners.add(doc_row.owner)
	if last_version:
		all_owners.add(last_version.owner)

	name_map = {}
	if all_owners:
		rows = frappe.get_all(
			"User",
			filters={"name": ["in", list(all_owners)]},
			fields=["name", "full_name"],
		)
		name_map = {r.name: r.full_name or r.name for r in rows}

	def resolve(email):
		return name_map.get(email, email)

	# --- 5. Build timeline entries ---
	entries = []

	has_edit_comment = False
	for c in raw_comments:
		ctype, clabel = comment_type_map.get(c.comment_type, ("info", c.comment_type.lower()))
		if ctype == "edit":
			has_edit_comment = True
		entry = {
			"type": ctype,
			"label": clabel,
			"user": resolve(c.owner),
			"user_email": c.owner,
			"timestamp": str(c.creation),
		}
		if ctype in ("comment", "workflow", "assignment", "share", "attachment"):
			entry["content"] = frappe.utils.strip_html_tags(c.content or "").strip()
		entries.append(entry)

	# Add "last edited" from Version table only if no Edit comment already covers it
	if last_version and not has_edit_comment:
		entries.append(
			{
				"type": "edit",
				"label": "last edited this",
				"user": resolve(last_version.owner),
				"user_email": last_version.owner,
				"timestamp": str(last_version.creation),
			}
		)

	# Creation entry always at the bottom
	entries.append(
		{
			"type": "creation",
			"label": "created this",
			"user": resolve(doc_row.owner),
			"user_email": doc_row.owner,
			"timestamp": str(doc_row.creation),
		}
	)

	# Sort newest first
	entries.sort(key=lambda x: x["timestamp"], reverse=True)

	return entries


# ============================================================
# Delegate User API — whitelisted wrappers
# All logic lives in delegate_user/delegate_user.py
# Frontend calls: rndopsapp.rndopsapp.api.<method>
# ============================================================


@frappe.whitelist()
def search_delegate_users(query=""):
	from rndopsapp.rndopsapp.delegate_user.delegate_user import search_delegate_users as _impl

	return _impl(query=query)


@frappe.whitelist()
def get_delegate_scope(user=None):
	from rndopsapp.rndopsapp.delegate_user.delegate_user import get_delegate_scope as _impl

	return _impl(user=user)


@frappe.whitelist()
def get_active_delegations(user=None):
	from rndopsapp.rndopsapp.delegate_user.delegate_user import get_active_delegations as _impl

	return _impl(user=user)


@frappe.whitelist()
def delegate_user(
	delegate_user,
	delegation_type=None,
	scope_type=None,
	project_names=None,
	applications=None,
	valid_from=None,
	valid_to=None,
):
	from rndopsapp.rndopsapp.delegate_user.delegate_user import delegate_user as _impl

	return _impl(
		delegate_user=delegate_user,
		delegation_type=delegation_type,
		scope_type=scope_type,
		project_names=project_names,
		applications=applications,
		valid_from=valid_from,
		valid_to=valid_to,
	)


@frappe.whitelist()
def undelegate_user(delegation_name):
	from rndopsapp.rndopsapp.delegate_user.delegate_user import undelegate_user as _impl

	return _impl(delegation_name=delegation_name)


def auto_clear_old_mattermost_posts():
	"""
	Scheduled daily task.
	Permanently deletes posts older than 6 months from all channels in _MM_CHANNELS.
	"""
	from datetime import datetime, timedelta, timezone

	cutoff = datetime.now(timezone.utc) - timedelta(days=180)
	date_to = cutoff.strftime("%Y-%m-%d")

	total_deleted = 0
	for channel_name in _MM_CHANNELS:
		result = clear_mattermost_channel(channel_name=channel_name, date_to=date_to)
		count = result.get("deleted", 0)
		total_deleted += count
		if count:
			frappe.logger("mattermost").info(
				f"auto_clear: removed {count} posts older than 6 months from '{channel_name}'"
			)

	frappe.logger("mattermost").info(
		f"auto_clear_old_mattermost_posts complete — total deleted: {total_deleted}"
	)


# ============================================================
# Travel multi-target Put Back — workflow setup
# ============================================================
# Adds explicit "Put Back to <Role>" transitions on Travel_Workflow so
# Dean / Ado / HoS / Staff / Head can pick which previous state to send
# the doc back to. Run once after deploy:
#     bench --site <site> execute rndopsapp.rndopsapp.api.setup_travel_putback_transitions
# Idempotent — re-running has no effect.


@frappe.whitelist(allow_guest=True)
def get_project_staff_details_count(filters=None):
	"""
	Returns the total number of entries in the "Project Staff Details" doctype.
	Guest-accessible (no API token required) since it only reads a count.

	Optional `filters` (JSON string or dict) can be passed to count a subset.
	"""
	if filters and isinstance(filters, str):
		filters = frappe.parse_json(filters)

	count = frappe.db.count("Project Staff Details", filters=filters or None)
	return {"doctype": "Project Staff Details", "count": count}


@frappe.whitelist()
def setup_travel_putback_transitions():
	"""Install fan-out Put Back transitions on Travel_Workflow."""
	workflow_name = "Travel_Workflow"
	if not frappe.db.exists("Workflow", workflow_name):
		frappe.throw(f"Workflow '{workflow_name}' not found")

	# (state, action_label, next_state, allowed_role)
	desired = [
		# Pending Dean Approval
		("Pending Dean Approval", "Put Back to HoS", "Pending HoS Approval", "Dean, RnD"),
		("Pending Dean Approval", "Put Back to Staff", "Pending Staff Approval", "Dean, RnD"),
		("Pending Dean Approval", "Put Back to Head", "Pending Head Approval", "Dean, RnD"),
		("Pending Dean Approval", "Put Back to PI", "Pending PI Approval", "Dean, RnD"),
		# Pending Associate Dean
		("Pending Associate Dean", "Put Back to HoS", "Pending HoS Approval", "Ado_RnD"),
		("Pending Associate Dean", "Put Back to Staff", "Pending Staff Approval", "Ado_RnD"),
		("Pending Associate Dean", "Put Back to Head", "Pending Head Approval", "Ado_RnD"),
		("Pending Associate Dean", "Put Back to PI", "Pending PI Approval", "Ado_RnD"),
		# Pending HoS Approval
		(
			"Pending HoS Approval",
			"Put Back to Staff",
			"Pending Staff Approval",
			"Hos, RnD (Head of Section, RnD)",
		),
		(
			"Pending HoS Approval",
			"Put Back to Head",
			"Pending Head Approval",
			"Hos, RnD (Head of Section, RnD)",
		),
		("Pending HoS Approval", "Put Back to PI", "Pending PI Approval", "Hos, RnD (Head of Section, RnD)"),
		# Pending Staff Approval
		("Pending Staff Approval", "Put Back to Head", "Pending Head Approval", "staff, RnD"),
		("Pending Staff Approval", "Put Back to PI", "Pending PI Approval", "staff, RnD"),
		# Pending Head Approval
		("Pending Head Approval", "Put Back to PI", "Pending PI Approval", "head_approver_1"),
	]

	# Ensure each new action name exists as a Workflow Action Master,
	# otherwise the Workflow Transition link-validation will fail.
	unique_actions = {action for _, action, _, _ in desired}
	for action_name in unique_actions:
		if not frappe.db.exists("Workflow Action Master", action_name):
			frappe.get_doc(
				{
					"doctype": "Workflow Action Master",
					"workflow_action_name": action_name,
				}
			).insert(ignore_permissions=True)

	wf = frappe.get_doc("Workflow", workflow_name)
	existing = {(t.state, t.action, t.next_state, t.allowed) for t in wf.transitions}

	added = []
	for state, action, next_state, allowed in desired:
		key = (state, action, next_state, allowed)
		if key in existing:
			continue
		wf.append(
			"transitions",
			{
				"state": state,
				"action": action,
				"next_state": next_state,
				"allowed": allowed,
				"allow_self_approval": 1,
				"send_email_to_creator": 0,
			},
		)
		added.append(f"{state} --[{action}]--> {next_state} ({allowed})")

	if added:
		wf.save(ignore_permissions=True)
		frappe.db.commit()

	return {
		"status": "success",
		"added": added,
		"skipped_existing": len(desired) - len(added),
	}


# ============================================================
# ---- PR Lookup: resolve Project Registration from any application docname ----

_PR_FIELDS = [
    "name", "project_no", "project_title", "project_type", "other_project_type_name",
    "principal_investigator_name", "pi_webmail", "pi_userid",
    "implementation_department", "funding_agen", "funding_agency_schemes",
    "workflow_state", "docstatus", "total_budget_amount", "total_sanctioned_amount",
    "prj_start_date", "prj_end_date", "project_duration_months",
    "sanctioned_letter_no", "sanctioned_letter_date",
    "creation", "modified", "modified_by", "owner",
]

# Maps application DocType → (link_field, kind)
# kind "link"       → field stores PR name directly
# kind "project_no" → field stores project_no; need secondary lookup
_DOCTYPE_PR_MAP = {
    "AccountHeadPayment":                ("project_ref_number",    "link"),
    "Advance Settlement":                ("project_name",          "link"),
    "AMC":                               ("project_ref",           "link"),
    "Deposit slip":                      ("project_title",         "link"),
    "Deposit Slip Project Credit":       ("project_number",        "link"),
    "Disbursement of Honorarium":        ("project_number",        "link"),
    "E Non Routine Deposit Slip":        ("project_title",         "link"),
    "Fund Received":                     ("prjreg_title",          "link"),
    "Fund Sanction":                     ("project_proposal",      "link"),
    "Indent Cum Sanction Sheet":         ("project_ref",           "link"),
    "Indent General Form":               ("igf_project_title",     "link"),
    "Loan Request":                      ("project_name",          "link"),
    "myProjects":                        ("project_proposal",      "link"),
    "payments":                          ("project_id",            "link"),
    "Project Extension":                 ("project_ref",           "link"),
    "proprietary_purchase":              ("project_ref",           "link"),
    "Rate Contract":                     ("project_number",        "link"),
    "Reimbursement":                     ("project_name",          "link"),
    "repair_replacement":                ("project_ref",           "link"),
    "Research Consultancy Deposit Slip": ("project_title",         "link"),
    "Research Deposit Slip":             ("project_title",         "link"),
    "standerdized_purchase":             ("project_ref",           "link"),
    "T Testing Deposit Slip":            ("project_title",         "link"),
    "Top Up Fellowship":                 ("project_code",          "link"),
    "Travel":                            ("travel_project_title",  "link"),
    "UC Request":                        ("project_id",            "link"),
    # Indirect — stores project_no in a plain Data field
    "Disbursal of Consultancy":          ("project_title",         "project_no"),
    "Disbursal of Honorarium":           ("project_no",            "project_no"),
    "Direct Purchase":                   ("project_no",            "project_no"),
    "dp_po":                             ("project_no",            "project_no"),
    "Endorsement Data":                  ("project_no",            "project_no"),
    "Extension Of Tenure Of Appointment":("project_number",        "project_no"),
    "ICSS_PO":                           ("project_number",        "project_no"),
    "NIQ":                               ("project_no",            "project_no"),
    "P_11 Form":                         ("project_no",            "project_no"),
    "Project Staff Details":             ("project_no",            "project_no"),
    "Recruitment Adhoc Contractual":     ("upfa_project_code",     "project_no"),
    "sanction_sheet":                    ("project_no",            "project_no"),
    "Selection Committee Report":        ("project_number",        "project_no"),
    "TA DA Settlement":                  ("project_no",            "project_no"),
    "Temporary Advance":                 ("project_code",          "project_no"),
}


def _fetch_pr_summary(pr_name):
    pr = frappe.db.get_value("Project Registration", pr_name, _PR_FIELDS, as_dict=True)
    if not pr:
        frappe.throw(f"Project Registration '{pr_name}' not found.", title="Not Found")
    return pr


@frappe.whitelist()
def lookup_project_from_application(doctype, docname):
    """
    Resolve the Project Registration linked from any application DocType + docname.
    Returns project_no and full PR summary alongside source document metadata.
    """
    if doctype not in _DOCTYPE_PR_MAP:
        return {
            "status": "error",
            "message": f"DocType '{doctype}' is not in the PR link map.",
            "supported_doctypes": sorted(_DOCTYPE_PR_MAP.keys()),
        }

    field_name, field_kind = _DOCTYPE_PR_MAP[doctype]

    if not frappe.db.exists(doctype, docname):
        return {"status": "error", "message": f"{doctype} '{docname}' not found."}

    field_value = frappe.db.get_value(doctype, docname, field_name)
    if not field_value:
        return {
            "status": "error",
            "message": f"Field '{field_name}' in {doctype} '{docname}' is empty — no PR linked.",
        }

    if field_kind == "link":
        pr_name = field_value
    else:
        pr_name = frappe.db.get_value("Project Registration", {"project_no": field_value}, "name")
        if not pr_name:
            return {
                "status": "error",
                "message": f"No Project Registration found with project_no '{field_value}'.",
            }

    pr = _fetch_pr_summary(pr_name)
    return {
        "status": "success",
        "source": {
            "doctype": doctype,
            "docname": docname,
            "link_field": field_name,
            "link_value": field_value,
            "link_kind": field_kind,
        },
        "pr": pr,
    }


@frappe.whitelist()
def lookup_project_direct(identifier):
    """
    Look up a Project Registration by its document name (autoname) or project_no.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return {"status": "error", "message": "Please provide a PR name or project_no."}

    if frappe.db.exists("Project Registration", identifier):
        pr_name = identifier
    else:
        pr_name = frappe.db.get_value("Project Registration", {"project_no": identifier}, "name")

    if not pr_name:
        return {"status": "error", "message": f"No Project Registration found for '{identifier}'."}

    pr = _fetch_pr_summary(pr_name)
    return {"status": "success", "pr": pr}


@frappe.whitelist()
def get_pr_link_map():
    """Return the supported doctype → link-field mapping for the PR lookup page."""
    return {dt: {"field": v[0], "kind": v[1]} for dt, v in _DOCTYPE_PR_MAP.items()}


# ============================================================
# ---- Project No. Replacement: cascade a project_no edit to every dependent DocType ----
#
# Project Registration.project_no is a human-readable Data field. Most application
# DocTypes link to the PR by its autoname (`name`), so they never go stale — but ~19
# of them ALSO cache the project_no value in a plain Data field (populated via
# fetch_from or manual entry, per PROJECT_REGISTRATION_LINKS_TO_APPLICATION.md).
# Editing project_no on the PR alone leaves those caches stale. This map lists every
# such cache field so a single edit can cascade everywhere.
#
# match "link"  -> row located via a Link field that stores the PR's `name`
# match "value" -> no Link field on this doctype; row located by the OLD project_no value itself
# ============================================================

_PROJECT_NO_SYNC_MAP = [
    # --- cache field alongside a genuine Link field ---
    {"doctype": "Advance Settlement", "field": "project_code", "match": "link", "link_field": "project_name"},
    {"doctype": "AMC", "field": "project_no", "match": "link", "link_field": "project_ref"},
    {"doctype": "Indent Cum Sanction Sheet", "field": "project_no", "match": "link", "link_field": "project_ref"},
    {
        "doctype": "Indent General Form",
        "field": "igf_project_code",
        "match": "link",
        "link_field": "igf_project_title",
    },
    {"doctype": "Loan Request", "field": "project_number", "match": "link", "link_field": "project_name"},
    {"doctype": "Project Extension", "field": "prj_num", "match": "link", "link_field": "project_ref"},
    {"doctype": "proprietary_purchase", "field": "project_no", "match": "link", "link_field": "project_ref"},
    {"doctype": "Rate Contract", "field": "project_no", "match": "link", "link_field": "project_ref"},
    {"doctype": "repair_replacement", "field": "project_no", "match": "link", "link_field": "project_ref"},
    {
        "doctype": "Research Consultancy Deposit Slip",
        "field": "project_number",
        "match": "link",
        "link_field": "project_title",
    },
    {
        "doctype": "Research Deposit Slip",
        "field": "project_no",
        "match": "link",
        "link_field": "project_title",
    },
    {"doctype": "standerdized_purchase", "field": "project_no", "match": "link", "link_field": "project_ref"},
    {
        "doctype": "Travel",
        "field": "travel_project_number",
        "match": "link",
        "link_field": "travel_project_title",
    },
    # --- standalone Data field, no Link field on the doctype at all ---
    {"doctype": "Disbursal of Consultancy", "field": "project_title", "match": "value"},
    {"doctype": "Disbursal of Honorarium", "field": "project_no", "match": "value"},
    {"doctype": "Direct Purchase", "field": "project_no", "match": "value"},
    {"doctype": "dp_po", "field": "project_no", "match": "value"},
    {"doctype": "Endorsement Data", "field": "project_no", "match": "value"},
    {"doctype": "Extension Of Tenure Of Appointment", "field": "project_number", "match": "value"},
    {"doctype": "ICSS_PO", "field": "project_number", "match": "value"},
    {"doctype": "NIQ", "field": "project_no", "match": "value"},
    {"doctype": "P_11 Form", "field": "project_no", "match": "value"},
    {"doctype": "Project Staff Details", "field": "project_no", "match": "value"},
    {"doctype": "Recruitment Adhoc Contractual", "field": "upfa_project_code", "match": "value"},
    {"doctype": "sanction_sheet", "field": "project_no", "match": "value"},
    {"doctype": "Selection Committee Report", "field": "project_number", "match": "value"},
    {"doctype": "TA DA Settlement", "field": "project_no", "match": "value"},
    {"doctype": "Temporary Advance", "field": "project_code", "match": "value"},
]


def _resolve_pr_name(identifier):
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if frappe.db.exists("Project Registration", identifier):
        return identifier
    return frappe.db.get_value("Project Registration", {"project_no": identifier}, "name")


def _project_no_sync_where(entry, pr_name, old_value):
    """Return (where_sql, params) selecting the rows in `entry` that need syncing."""
    if entry["match"] == "link":
        return f"`{entry['link_field']}` = %s", (pr_name,)
    return f"`{entry['field']}` = %s", (old_value,)


def _walk_project_no_sync_map(old_value):
    """Yield each configured entry that actually applies on this site."""
    for entry in _PROJECT_NO_SYNC_MAP:
        if not frappe.db.exists("DocType", entry["doctype"]):
            continue
        if entry["match"] == "value" and not old_value:
            # nothing to match against yet — PR has no project_no set
            continue
        yield entry


@frappe.whitelist()
def get_project_no_sync_map():
    """Return the sync map for display (e.g. a reference table on the frontend)."""
    return [e for e in _PROJECT_NO_SYNC_MAP if frappe.db.exists("DocType", e["doctype"])]


@frappe.whitelist()
def preview_project_no_change(identifier, new_project_no=None):
    """
    Dry-run: resolve the PR and count how many records in each dependent DocType
    currently cache its project_no, so an admin can see the blast radius before
    committing to the change. Does not modify anything.
    """
    pr_name = _resolve_pr_name(identifier)
    if not pr_name:
        return {"status": "error", "message": f"No Project Registration found for '{identifier}'."}

    pr = frappe.db.get_value(
        "Project Registration",
        pr_name,
        ["name", "project_no", "project_title", "workflow_state"],
        as_dict=True,
    )
    old_value = pr.project_no

    impact = []
    total = 0
    for entry in _PROJECT_NO_SYNC_MAP:
        if not frappe.db.exists("DocType", entry["doctype"]):
            continue
        if entry["match"] == "value" and not old_value:
            impact.append(
                {**entry, "count": 0, "note": "PR has no project_no set yet — nothing to match on"}
            )
            continue
        where_sql, params = _project_no_sync_where(entry, pr_name, old_value)
        count = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{entry['doctype']}` WHERE {where_sql}", params)[
            0
        ][0]
        impact.append({**entry, "count": count})
        total += count

    new_project_no = (new_project_no or "").strip() or None
    uniqueness_conflict = None
    if new_project_no:
        uniqueness_conflict = frappe.db.get_value(
            "Project Registration", {"project_no": new_project_no, "name": ["!=", pr_name]}, "name"
        )

    return {
        "status": "success",
        "pr": pr,
        "old_project_no": old_value,
        "new_project_no": new_project_no,
        "uniqueness_conflict": uniqueness_conflict,
        "impact": impact,
        "total_affected_records": total,
    }


def _cascade_project_no(pr_name, old_value, new_value):
    """
    Push new_value into every dependent DocType/field that cached old_value
    (per _PROJECT_NO_SYNC_MAP). Assumes Project Registration.project_no has
    already been set to new_value by the caller. Must run inside the caller's
    try/except so a failure here rolls back the PR update too.
    """
    updated = []
    plan = []
    for entry in _walk_project_no_sync_map(old_value):
        where_sql, params = _project_no_sync_where(entry, pr_name, old_value)
        count = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{entry['doctype']}` WHERE {where_sql}", params)[
            0
        ][0]
        plan.append((entry, where_sql, params, count))

    for entry, where_sql, params, count in plan:
        if count:
            frappe.db.sql(
                f"UPDATE `tab{entry['doctype']}` SET `{entry['field']}` = %s WHERE {where_sql}",
                (new_value, *params),
            )
        updated.append({"doctype": entry["doctype"], "field": entry["field"], "count": count})
    return updated


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _sync_external_project_number(
    old_project_no,
    new_project_no,
    reason=None,
    update_archive_tables=True,
    update_audit_tables=True,
    update_beneficiary_project_number=True,
):
    """
    Mirrors the local project_no cascade over to the external account portal
    (172.16.134.81:18080), which exposes its own
    POST /api/projects/{projectNumber}/change-project-number for this. Best-effort,
    like _delete_external_project: a failure here is reported back to the caller
    but never raised, since the portal being unreachable shouldn't block a change
    that already succeeded locally.
    """
    if not old_project_no:
        return {
            "attempted": False,
            "message": "No prior project_no on this Project Registration — external portal not called.",
        }

    url = f"http://172.16.134.81:18080/api/projects/{old_project_no}/change-project-number"
    payload = {
        "newProjectNumber": new_project_no,
        "reason": reason or "",
        "updateArchiveTables": _as_bool(update_archive_tables),
        "updateAuditTables": _as_bool(update_audit_tables),
        "updateBeneficiaryProjectNumber": _as_bool(update_beneficiary_project_number),
    }
    headers = {"Content-Type": "application/json"}

    try:
        frappe.logger().info(
            f"Changing project number on external portal: {old_project_no} -> {new_project_no} ({url})"
        )
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        try:
            body = response.json()
        except ValueError:
            body = response.text

        return {
            "attempted": True,
            "url": url,
            "payload": payload,
            "status_code": response.status_code,
            "response": body,
            "ok": response.status_code in (200, 201, 202),
        }
    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            f"External Project Number Change Error: {old_project_no} -> {new_project_no}",
        )
        return {"attempted": True, "url": url, "payload": payload, "ok": False, "error": str(e)}


def _add_project_no_change_comment(pr_name, old_value, new_value, updated):
    try:
        pr_doc = frappe.get_doc("Project Registration", pr_name)
        pr_doc.add_comment(
            "Info",
            f"project_no changed from '{old_value}' to '{new_value}' by {frappe.session.user}. "
            f"Cascaded to {sum(u['count'] for u in updated)} record(s) across "
            f"{len([u for u in updated if u['count']])} DocType(s).",
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "project_no change: audit comment failed")


@frappe.whitelist()
def apply_project_no_change(
    identifier,
    new_project_no,
    reason=None,
    update_archive_tables=True,
    update_audit_tables=True,
    update_beneficiary_project_number=True,
):
    """
    Change a Project Registration's project_no to a MANUALLY entered value and
    cascade it to every dependent DocType/field that caches it (see
    _PROJECT_NO_SYNC_MAP), in a single transaction, then mirror the change to the
    external account portal (172.16.134.81:18080). Only System Manager can
    perform this — it mutates dozens of tables.
    """
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can change a Project No.", frappe.PermissionError)

    new_project_no = (new_project_no or "").strip()
    if not new_project_no:
        frappe.throw("The new project_no is required.")

    pr_name = _resolve_pr_name(identifier)
    if not pr_name:
        frappe.throw(f"No Project Registration found for '{identifier}'.")

    old_value = frappe.db.get_value("Project Registration", pr_name, "project_no")
    if old_value == new_project_no:
        return {"status": "error", "message": "New project_no is identical to the current value."}

    conflict = frappe.db.get_value(
        "Project Registration", {"project_no": new_project_no, "name": ["!=", pr_name]}, "name"
    )
    if conflict:
        frappe.throw(
            f"project_no '{new_project_no}' is already used by Project Registration '{conflict}'."
        )

    try:
        frappe.db.set_value(
            "Project Registration", pr_name, "project_no", new_project_no, update_modified=False
        )
        updated = _cascade_project_no(pr_name, old_value, new_project_no)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "apply_project_no_change failed")
        raise

    _add_project_no_change_comment(pr_name, old_value, new_project_no, updated)

    external_portal = _sync_external_project_number(
        old_value,
        new_project_no,
        reason=reason,
        update_archive_tables=update_archive_tables,
        update_audit_tables=update_audit_tables,
        update_beneficiary_project_number=update_beneficiary_project_number,
    )
    warnings = []
    if external_portal.get("attempted") and not external_portal.get("ok"):
        warnings.append(
            "Local database updated successfully, but the external account portal sync failed: "
            + (external_portal.get("error") or f"HTTP {external_portal.get('status_code')}")
        )

    return {
        "status": "success",
        "pr_name": pr_name,
        "old_project_no": old_value,
        "new_project_no": new_project_no,
        "updated": updated,
        "total_updated": sum(u["count"] for u in updated),
        "external_portal": external_portal,
        "warnings": warnings,
    }


@frappe.whitelist()
def suggest_generated_project_no(identifier):
    """
    Peek at the next auto-generated project number (Project Number Generation
    series) for this PR, without consuming the sequence or creating any record.
    Wraps get_project_number_generation_fields for the Change Project No. UI.
    """
    from rndopsapp.rndopsapp.doctype.project_number_generation.project_number_generation import (
        get_project_number_generation_fields,
    )

    pr_name = _resolve_pr_name(identifier)
    if not pr_name:
        return {"status": "error", "message": f"No Project Registration found for '{identifier}'."}

    result = get_project_number_generation_fields(doc_name=pr_name)
    if not result.get("final_project_number"):
        return {
            "status": "error",
            "message": "Could not compute a suggested project number for this PR "
            "(check the PI's User record and Implementation Department are set).",
        }

    return {
        "status": "success",
        "pr_name": pr_name,
        "suggested_project_no": result["final_project_number"],
        "prefill_data": result["prefill_data"],
    }


@frappe.whitelist()
def generate_new_project_no_and_apply(
    identifier,
    generation_data=None,
    reason=None,
    update_archive_tables=True,
    update_audit_tables=True,
    update_beneficiary_project_number=True,
):
    """
    Auto-generate a fresh, properly formatted project number via the
    'Project Number Generation' series (consuming the sequence and creating an
    audit record there), set it on the PR, cascade it to every dependent
    DocType/field, then mirror the change to the external account portal
    (172.16.134.81:18080). Only System Manager can perform this.
    """
    import json

    from rndopsapp.rndopsapp.doctype.project_number_generation.project_number_generation import (
        get_project_number_generation_fields,
        save_project_number_generation_data,
    )

    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can change a Project No.", frappe.PermissionError)

    pr_name = _resolve_pr_name(identifier)
    if not pr_name:
        frappe.throw(f"No Project Registration found for '{identifier}'.")

    old_value = frappe.db.get_value("Project Registration", pr_name, "project_no")

    if isinstance(generation_data, str):
        generation_data = json.loads(generation_data)
    if not generation_data:
        generation_data = get_project_number_generation_fields(doc_name=pr_name)["prefill_data"]
        if not generation_data:
            frappe.throw(
                "Could not auto-derive generation fields for this PR. "
                "Check the PI's User record and Implementation Department, or use Manual Entry."
            )

    try:
        save_result = save_project_number_generation_data(data=generation_data, projrefno=pr_name)
        if save_result.get("status") != "success":
            frappe.throw(save_result.get("message") or "Failed to generate a new project number.")

        new_project_no = save_result["docname"]
        updated = _cascade_project_no(pr_name, old_value, new_project_no)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "generate_new_project_no_and_apply failed")
        raise

    _add_project_no_change_comment(pr_name, old_value, new_project_no, updated)

    external_portal = _sync_external_project_number(
        old_value,
        new_project_no,
        reason=reason,
        update_archive_tables=update_archive_tables,
        update_audit_tables=update_audit_tables,
        update_beneficiary_project_number=update_beneficiary_project_number,
    )
    warnings = []
    if external_portal.get("attempted") and not external_portal.get("ok"):
        warnings.append(
            "Local database updated successfully, but the external account portal sync failed: "
            + (external_portal.get("error") or f"HTTP {external_portal.get('status_code')}")
        )

    return {
        "status": "success",
        "pr_name": pr_name,
        "old_project_no": old_value,
        "new_project_no": new_project_no,
        "png_docname": new_project_no,
        "updated": updated,
        "total_updated": sum(u["count"] for u in updated),
        "external_portal": external_portal,
        "warnings": warnings,
    }


# -------------------- USER + UNIVERSAL REGISTRATION COMBINED PROFILE --------------------
# Universal Registration__ does not link to core User directly - it links to
# Universal User__ (via universal_user_u_r), and Universal User__ stores the core
# User.name in auth_user_id_u_r. These helpers walk that chain (falling back to an
# email match on either hop) and flatten User + Universal User__ + Universal
# Registration__ into one dict, since callers just want one combined record per person.


def _build_user_registration_profile(user_doc_name=None, registration_doc_name=None, email_override=None):
	"""
	Flat dict merging whichever of User / Universal User__ / Universal
	Registration__ records exist for one person. Not all three need to exist -
	external/vendor registrations often never get a core Frappe User account -
	so this degrades gracefully instead of requiring a User doc.

	Pass `user_doc_name` (a core User docname, or an email to resolve one from)
	and/or `registration_doc_name` (a Universal Registration__ docname) as the
	known starting point(s). `email_override` forces the email used to bridge
	between the three doctypes when their link fields aren't populated.

	Returns None if none of the three records can be found at all.
	"""
	user_dict = {}
	universal_user_dict = {}
	registration_dict = {}

	if registration_doc_name:
		registration_dict = frappe.get_doc("Universal Registration__", registration_doc_name).as_dict()

	user_name = None
	if user_doc_name:
		user_name = (
			user_doc_name
			if frappe.db.exists("User", user_doc_name)
			else frappe.db.get_value("User", {"email": user_doc_name}, "name")
		)

	lookup_email = (
		email_override
		or (frappe.db.get_value("User", user_name, "email") if user_name else None)
		or (user_doc_name if user_doc_name and not user_name else None)
		or (registration_dict.get("email_address_u_r") if registration_dict else None)
	)

	universal_user_name = registration_dict.get("universal_user_u_r") if registration_dict else None
	if user_name and not universal_user_name:
		universal_user_name = frappe.db.get_value("Universal User__", {"auth_user_id_u_r": user_name}, "name")
	if not universal_user_name and lookup_email:
		universal_user_name = frappe.db.get_value("Universal User__", {"email_u_r": lookup_email}, "name")

	if universal_user_name:
		universal_user_dict = frappe.get_doc("Universal User__", universal_user_name).as_dict()
		if not user_name:
			user_name = universal_user_dict.get("auth_user_id_u_r")

	if not user_name and lookup_email:
		user_name = frappe.db.get_value("User", {"email": lookup_email}, "name")

	if user_name:
		user_dict = frappe.get_doc("User", user_name).as_dict()

	if not registration_dict and universal_user_name:
		registration_name = frappe.db.get_value(
			"Universal Registration__", {"universal_user_u_r": universal_user_name}, "name"
		)
		if registration_name:
			registration_dict = frappe.get_doc("Universal Registration__", registration_name).as_dict()

	if not registration_dict and lookup_email:
		registration_name = frappe.db.get_value(
			"Universal Registration__", {"email_address_u_r": lookup_email}, "name"
		)
		if registration_name:
			registration_dict = frappe.get_doc("Universal Registration__", registration_name).as_dict()

	if not user_dict and not universal_user_dict and not registration_dict:
		return None

	# Append everything into one flat record. Registration/Universal User values
	# win over User's on overlapping keys (name, owner, ...) since they're the
	# more specific record for this profile.
	merged = {}
	merged.update(user_dict)
	merged.update(universal_user_dict)
	merged.update(registration_dict)
	return merged


@frappe.whitelist(allow_guest=True)
def get_user_registration_profile(user=None, email=None, search=None):
	"""
	Combined User + Universal Registration__ profile(s). Any of the three
	underlying records (User, Universal User__, Universal Registration__) may
	be missing for a given person, so this never requires all three to exist.

	Without `search`: returns a single flat dict for `user` (a core User
	docname/email, or the email on a Universal Registration__/Universal
	User__ record that has no core User account; defaults to the logged-in
	user). `email` optionally overrides the email used to bridge the doctypes
	when link fields aren't populated.

	With `search`: returns a list of flat profiles for every person whose User
	(full_name/email/name) or Universal Registration__ (full_name_u_r/
	email_address_u_r/org_name_u_r/mobile_number_u_r) record matches the text.
	"""
	from frappe import _

	if search:
		like = f"%{search}%"

		matched_user_names = frappe.get_all(
			"User",
			or_filters=[
				["full_name", "like", like],
				["email", "like", like],
				["name", "like", like],
			],
			pluck="name",
			limit=50,
		)

		registration_names = frappe.get_all(
			"Universal Registration__",
			or_filters=[
				["full_name_u_r", "like", like],
				["email_address_u_r", "like", like],
				["org_name_u_r", "like", like],
				["mobile_number_u_r", "like", like],
			],
			pluck="name",
			limit=50,
		)

		try:
			profiles = {}
			for u in matched_user_names:
				profile = _build_user_registration_profile(user_doc_name=u)
				if profile:
					profiles[profile.get("name") or u] = profile

			for reg_name in registration_names:
				profile = _build_user_registration_profile(registration_doc_name=reg_name)
				if profile:
					profiles.setdefault(profile.get("name") or reg_name, profile)

			return list(profiles.values())
		except Exception:
			frappe.log_error(frappe.get_traceback(), _("Error searching user registration profiles"))
			frappe.throw(_("An error occurred while searching user registration profiles."))

	user = user or frappe.session.user
	email = str(email).strip('"').strip("'") if email else None

	try:
		profile = _build_user_registration_profile(user_doc_name=user, email_override=email)
	except Exception:
		frappe.log_error(frappe.get_traceback(), _("Error fetching user registration profile"))
		frappe.throw(_("An error occurred while fetching the user's registration profile."))

	if not profile:
		frappe.throw(
			_("No User, Universal User__, or Universal Registration__ record found for '{0}'.").format(user)
		)

	return profile

