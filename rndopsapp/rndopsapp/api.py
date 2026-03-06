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
