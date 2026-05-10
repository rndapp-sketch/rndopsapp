import frappe
from frappe.utils import sanitize_html
from frappe.utils.file_manager import save_file
import json
import os
from frappe import _

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
			"creation": project_doc.creation
		}

		# 2. Fetch All Linked Fund Received Documents
		# Filter by 'prjreg_title' which links to Project Registration
		funds = frappe.get_all(
			"Fund Received",
			filters={"prjreg_title": docname, "docstatus": 0}, 
			fields=["name", "fund_received_amt", "creation", "bank_account", "invoice_no", "gst_invoice_issued", "docstatus"]
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
				"budget_breakup": []
			}
			
			# Extract child table details
			for row in fund_doc.received_amt_breakup:
				fund_info["budget_breakup"].append({
					"account_head": row.account_head, 
					"amount_received": row.amount_received,           
					"remarks": row.remarks  
				})
			
			funds_data.append(fund_info)

		return {
			"project_details": project_data,
			"funds": funds_data
		}

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
			"Recruitment Adhoc Contractual",
			filters={"webmail_id": webmail_id},
			pluck="name"
		)
		
		docs = [frappe.get_doc("Recruitment Adhoc Contractual", name).as_dict() for name in doc_names]
			
		return {
			"status": "success",
			"data": docs
		}
	except Exception as e:
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def delete_doctype_records(doctype, docnames):
	"""
	Delete one or more documents from any DocType.
	Accepts docnames as a JSON list or comma/newline-separated string.
	Only accessible by System Manager.
	"""
	import json

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
				doctype, docname,
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

	return {
		"deleted": deleted,
		"not_found": not_found,
		"errors": errors
	}


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


# -------------------- MATTERMOST NOTIFICATION API (MKY) --------------------

_MM_BASE = "http://172.16.135.118:8065/api/v4"
_MM_URL = f"{_MM_BASE}/posts"
_MM_FILES_URL = f"{_MM_BASE}/files"
_MM_TOKEN = "Bearer fmjih41b4iymicttnuhinsqime"
_MM_DEFAULT_CHANNEL = "ihmkbbfq9ibzugfpy9rncq5yke"

# Channel name → Mattermost channel ID mapping (used for dropdowns)
_MM_CHANNELS = {
	"kafka logs":       "yh7piky97iycjrdytia1hqy99a",
	"Feedback PRORND":  "jnkacpywbjnh9frhg1bb8gs85y",
	"logs":             "ihmkbbfq9ibzugfpy9rncq5yke",
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
				file_ids.extend(
					f["id"] for f in upload_resp.json().get("file_infos", [])
				)
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
			is_feedback_channel = (channel_id == _MM_CHANNELS.get("Feedback PRORND"))
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
):
	"""
	Delete posts in a Mattermost channel identified by its name.

	Params:
	  channel_name – friendly channel name (matched against _MM_CHANNELS or Mattermost search)
	  date_from    – optional ISO date string (YYYY-MM-DD); delete posts on/after this date
	  date_to      – optional ISO date string (YYYY-MM-DD); delete posts on/before this date

	Returns:
	  {"status": "cleared", "deleted": <int>}
	  {"status": "error",   "error": …}
	"""
	import requests as _req
	from datetime import datetime, timezone

	channel_name = (channel_name or "").strip()
	if not channel_name:
		frappe.throw("channel_name is required.")

	# Convert date strings to millisecond UTC timestamps (Mattermost uses ms epoch)
	ts_from = None
	ts_to = None
	if date_from:
		ts_from = int(datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
	if date_to:
		# Include the full last day (end of day 23:59:59)
		ts_to = int(datetime.strptime(date_to + " 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)

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
				(c for c in channels if c.get("name") == channel_name or c.get("display_name") == channel_name),
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
		"Comment":              ("comment",    "commented"),
		"Edit":                 ("edit",       "edited this"),
		"Info":                 ("edit",       "edited this"),
		"Label":                ("edit",       "edited this"),
		"Workflow":             ("workflow",   "updated the workflow"),
		"Assigned":             ("assignment", "was assigned"),
		"Assignment Completed": ("assignment", "completed assignment"),
		"Shared":               ("share",      "shared this"),
		"Unshared":             ("share",      "unshared this"),
		"Attachment":           ("attachment", "added an attachment"),
		"Attachment Removed":   ("attachment", "removed an attachment"),
		"Like":                 ("like",       "liked this"),
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
	doc_row = frappe.db.get_value(
		doctype, docname, ["owner", "creation"], as_dict=True
	)

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
			"type":       ctype,
			"label":      clabel,
			"user":       resolve(c.owner),
			"user_email": c.owner,
			"timestamp":  str(c.creation),
		}
		if ctype in ("comment", "workflow", "assignment", "share", "attachment"):
			entry["content"] = frappe.utils.strip_html_tags(c.content or "").strip()
		entries.append(entry)

	# Add "last edited" from Version table only if no Edit comment already covers it
	if last_version and not has_edit_comment:
		entries.append({
			"type":       "edit",
			"label":      "last edited this",
			"user":       resolve(last_version.owner),
			"user_email": last_version.owner,
			"timestamp":  str(last_version.creation),
		})

	# Creation entry always at the bottom
	entries.append({
		"type":       "creation",
		"label":      "created this",
		"user":       resolve(doc_row.owner),
		"user_email": doc_row.owner,
		"timestamp":  str(doc_row.creation),
	})

	# Sort newest first
	entries.sort(key=lambda x: x["timestamp"], reverse=True)

	return entries


def auto_clear_old_mattermost_posts():
	"""
	Scheduled daily task.
	Permanently deletes posts older than 6 months from all channels in _MM_CHANNELS.
	"""
	from datetime import datetime, timezone, timedelta

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

@frappe.whitelist()
def setup_travel_putback_transitions():
    """Install fan-out Put Back transitions on Travel_Workflow."""
    workflow_name = "Travel_Workflow"
    if not frappe.db.exists("Workflow", workflow_name):
        frappe.throw(f"Workflow '{workflow_name}' not found")

    # (state, action_label, next_state, allowed_role)
    desired = [
        # Pending Dean Approval
        ("Pending Dean Approval", "Put Back to HoS",   "Pending HoS Approval",     "Dean, RnD"),
        ("Pending Dean Approval", "Put Back to Staff", "Pending Staff Approval",   "Dean, RnD"),
        ("Pending Dean Approval", "Put Back to Head",  "Pending Head Approval",    "Dean, RnD"),
        ("Pending Dean Approval", "Put Back to PI",    "Pending PI Approval",      "Dean, RnD"),
        # Pending Associate Dean
        ("Pending Associate Dean", "Put Back to HoS",   "Pending HoS Approval",    "Ado_RnD"),
        ("Pending Associate Dean", "Put Back to Staff", "Pending Staff Approval",  "Ado_RnD"),
        ("Pending Associate Dean", "Put Back to Head",  "Pending Head Approval",   "Ado_RnD"),
        ("Pending Associate Dean", "Put Back to PI",    "Pending PI Approval",     "Ado_RnD"),
        # Pending HoS Approval
        ("Pending HoS Approval", "Put Back to Staff", "Pending Staff Approval",    "Hos, RnD (Head of Section, RnD)"),
        ("Pending HoS Approval", "Put Back to Head",  "Pending Head Approval",     "Hos, RnD (Head of Section, RnD)"),
        ("Pending HoS Approval", "Put Back to PI",    "Pending PI Approval",       "Hos, RnD (Head of Section, RnD)"),
        # Pending Staff Approval
        ("Pending Staff Approval", "Put Back to Head", "Pending Head Approval",   "staff, RnD"),
        ("Pending Staff Approval", "Put Back to PI",   "Pending PI Approval",     "staff, RnD"),
        # Pending Head Approval
        ("Pending Head Approval", "Put Back to PI", "Pending PI Approval",        "head_approver_1"),
    ]

    # Ensure each new action name exists as a Workflow Action Master,
    # otherwise the Workflow Transition link-validation will fail.
    unique_actions = {action for _, action, _, _ in desired}
    for action_name in unique_actions:
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action_name,
            }).insert(ignore_permissions=True)

    wf = frappe.get_doc("Workflow", workflow_name)
    existing = {
        (t.state, t.action, t.next_state, t.allowed)
        for t in wf.transitions
    }

    added = []
    for state, action, next_state, allowed in desired:
        key = (state, action, next_state, allowed)
        if key in existing:
            continue
        wf.append("transitions", {
            "state": state,
            "action": action,
            "next_state": next_state,
            "allowed": allowed,
            "allow_self_approval": 1,
            "send_email_to_creator": 0,
        })
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
