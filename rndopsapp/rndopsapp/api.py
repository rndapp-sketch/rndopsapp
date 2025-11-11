import frappe
from frappe.utils import sanitize_html
import json
import os
# @frappe.whitelist()
# def submit_project_registration(docname):
#     """
#     Handles initial submission with dynamic applicant type lookup AND intelligent self-approval bypass.
#     """
#     doc = frappe.get_doc("Project Registration", docname)

#     # --- Step 1: Standard Security Checks ---
#     if doc.owner != frappe.session.user:
#         frappe.throw("Permission Denied: You are not the owner of this document.")
#     if doc.docstatus != 0:
#         frappe.throw("This document has already been submitted.")
#     if not doc.applicant_type:
#         frappe.throw("Cannot submit: Applicant Type (Employee Class) is missing.")

#     # --- Step 2: Dynamically Find the Employee Class ID ---
#     applicant_type_identifier = doc.applicant_type
#     emp_class_doc_id = None
#     if frappe.db.exists("EmployeeClass_prornd", applicant_type_identifier):
#         emp_class_doc_id = applicant_type_identifier
#     else:
#         emp_class_doc_id = frappe.db.get_value("EmployeeClass_prornd", {"empclass_name": applicant_type_identifier}, "name")

#     if not emp_class_doc_id:
#         frappe.throw(f"Invalid Applicant Type: Could not find an Employee Class matching '{applicant_type_identifier}'.")

#     # --- Step 3: Determine the Intended Workflow Path from Data ---
#     workflow_path = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path")
#     next_state = ""

#     if workflow_path == "Senior Staff Path":
#         next_state = "Pending Staff Approval"
#     elif workflow_path == "HoD Path":
#         next_state = "Pending HoD Approval"
#     else:
#         empclass_name = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "empclass_name")
#         frappe.throw(f"Could not find a valid approval path. The Employee Class '{empclass_name}' has an unconfigured or missing Workflow Path.")

#     # --- Step 4: NEW - Check for Self-Approval and Override the Path if Necessary ---
#     applicant_user = doc.owner
#     intended_approver = doc.head_approver

#     # This check ONLY runs if the intended path was to the HoD.
#     if next_state == "Pending HoD Approval" and applicant_user == intended_approver:
#         # SELF-APPROVAL SCENARIO: The applicant is their own approver.
#         # Override the next_state to skip the HoD step.
#         next_state = "Pending Staff Approval"

#         # Add a comment to the document for a clear audit trail.
#         doc.add_comment("Comment", f"Applicant ({applicant_user}) is the designated Head Approver. Skipping Head Approval step and moving directly to Staff Approval.")

#     # --- Step 5: Execute the Final Action ---
#     if next_state == "Pending HoD Approval":
#         # If we are still on the HoD Path, perform the share.
#         if not intended_approver:
#             frappe.throw("Cannot submit: The designated Department Head approver has not been determined.")
#         share_document(doc.doctype, doc.name, intended_approver)

#     # Update the state and submit the document.
#     doc.workflow_state = next_state
#     doc.submit()
#     return doc.workflow_state
#     frappe.throw(f"next workflow state ({next_state})")


# @frappe.whitelist()
# def get_user_empclass(user):
#     """Return both empclass ID and Name for a given User"""
#     empclass_id = frappe.db.get_value("User", user, "empclass")
#     if empclass_id:
#         empclass_name = frappe.db.get_value("EmployeeClass_prornd", empclass_id, "empclass_name")
#         return {
#             "empclass_id": empclass_id,          # e.g. EMP-0001 (valid Link ID)
#             "empclass_name": empclass_name       # e.g. PI - Principal Investigator
#         }
#     return {}

# # @frappe.whitelist()
# # def handle_approval_action(docname, action, comment=None):
# #     """
# #     Handles all subsequent workflow actions: Approve, Reject, Put Back, Resubmit.
# #     This is our main "State Machine" engine.
# #     """
# #     doc = frappe.get_doc("Project Registration", docname)
# #     current_state = doc.workflow_state
# #     next_state = ""

# #     # --- CORRECTED Security Validation ---
# #     is_allowed = False
# #     # Get the roles of the user making the request
# #     user_roles = frappe.get_roles(frappe.session.user)

# #     if current_state == "Pending HoD Approval" and frappe.session.user == doc.head_approver:
# #         is_allowed = True
# #     elif current_state == "Pending Staff Approval" and "staff, RnD" in user_roles:
# #         is_allowed = True
# #     elif current_state == "Pending HoS Approval" and "Hos, RnD (Head of Section, RnD)" in user_roles:
# #         is_allowed = True
# #     elif current_state == "Pending Dean Approval" and "Dean, RnD" in user_roles:
# #         is_allowed = True
# #     elif current_state == "Needs Correction" and frappe.session.user == doc.owner:
# #         is_allowed = True

# #     if not is_allowed and "System Manager" not in user_roles:
# #         frappe.throw(f"Permission Denied: You are not authorized to perform the action '{action}' in the current state '{current_state}'.")

# #     # Add comment to a log if provided
# #     if comment:
# #         doc.add_comment("Comment", f"<strong>Action: {action}</strong><br>{sanitize_html(comment)}")

# #     # State Machine Logic (This part remains the same)
# #     if action == "Approve":
# #         if current_state == "Pending HoD Approval": next_state = "Pending Staff Approval"
# #         elif current_state == "Pending Staff Approval": next_state = "Pending HoS Approval"
# #         elif current_state == "Pending HoS Approval": next_state = "Pending Dean Approval"
# #         elif current_state == "Pending Dean Approval": next_state = "Approved"

# #         if current_state == "Pending HoD Approval":
# #             unshare_document(doc.doctype, doc.name, doc.head_approver)

# #     elif action == "Reject":
# #         next_state = "Rejected"
# #         doc.cancel()

# #     elif action == "Put Back":
# #         if current_state == "Pending Dean Approval": next_state = "Pending HoS Approval"
# #         elif current_state == "Pending HoS Approval": next_state = "Pending Staff Approval"
# #         elif current_state == "Pending Staff Approval": next_state = "Pending HoD Approval"
# #         elif current_state == "Pending HoD Approval": next_state = "Needs Correction"

# #         if current_state == "Pending HoD Approval":
# #             unshare_document(doc.doctype, doc.name, doc.head_approver)

# #     elif action == "Resubmit":
# #         if current_state == "Needs Correction":
# #             next_state = "Pending Staff Approval"

# #     if next_state and doc.docstatus != 2:
# #         doc.workflow_state = next_state
# #         doc.save(ignore_permissions=True)

# #     return doc.workflow_state


# # import frappe
# # from frappe.utils.html_utils import sanitize_html
# # from frappe.share import unshare_document


# working
# @frappe.whitelist()
# def handle_approval_action(docname, action, comment=None):
#     """
#     Handles all subsequent workflow actions: Approve, Reject, Put Back, Resubmit.
#     Acts as the main "State Machine" for Project Registration workflow.
#     """

#     doc = frappe.get_doc("Project Registration", docname)
#     current_state = doc.workflow_state
#     next_state = ""

#     # --- Role → Workflow State Mapping ---
#     ROLE_STATE_MAP = {
#         "Pending Staff Approval": ["staff, RnD"],
#         "Pending HoS Approval": ["Hos, RnD (Head of Section, RnD)"],
#         "Pending Dean Approval": ["Dean, RnD"],
#     }

#     # --- Security Validation ---
#     is_allowed = False
#     user_roles = frappe.get_roles(frappe.session.user)

#     # Special case: HoD approval assigned to a specific user
#     if current_state == "Pending HoD Approval" and frappe.session.user == doc.head_approver:
#         is_allowed = True
#     # Needs Correction can only be resubmitted by owner
#     elif current_state == "Needs Correction" and frappe.session.user == doc.owner:
#         is_allowed = True
#     # Generic role-based checks
#     elif current_state in ROLE_STATE_MAP:
#         if any(role in user_roles for role in ROLE_STATE_MAP[current_state]):
#             is_allowed = True

#     # System Manager override
#     if not is_allowed and "System Manager" not in user_roles:
#         frappe.throw(
#             f"🚫 Permission Denied: You are not authorized to perform '{action}' "
#             f"in the current state '{current_state}'."
#         )

#     # --- Optional Comment Logging ---
#     if comment:
#         doc.add_comment(
#             "Comment",
#             f"<strong>Action: {action}</strong><br>{sanitize_html(comment)}"
#         )

#     # --- Workflow State Machine ---
#     if action == "Approve":
#         if current_state == "Pending HoD Approval":
#             next_state = "Pending Staff Approval"
#             unshare_document(doc.doctype, doc.name, doc.head_approver)
#         elif current_state == "Pending Staff Approval":
#             next_state = "Pending HoS Approval"
#         elif current_state == "Pending HoS Approval":
#             next_state = "Pending Dean Approval"
#         elif current_state == "Pending Dean Approval":
#             next_state = "Approved"

#     elif action == "Reject":
#         next_state = "Rejected"
#         doc.cancel()

#     elif action == "Put Back":
#         if current_state == "Pending Dean Approval":
#             next_state = "Pending HoS Approval"
#         elif current_state == "Pending HoS Approval":
#             next_state = "Pending Staff Approval"
#         elif current_state == "Pending Staff Approval":
#             next_state = "Pending HoD Approval"
#         elif current_state == "Pending HoD Approval":
#             next_state = "Needs Correction"
#             unshare_document(doc.doctype, doc.name, doc.head_approver)

#     elif action == "Resubmit":
#         if current_state == "Needs Correction":
#             next_state = "Pending Staff Approval"

#     # --- Save State Change ---
#     if next_state and doc.docstatus != 2:  # avoid cancelled docs
#         doc.workflow_state = next_state
#         doc.save(ignore_permissions=True)

#     return doc.workflow_state


# # --- Helper functions for document sharing ---
# def share_document(doctype, name, user):
#     """Shares a document with a user, giving them read and write access."""
#     frappe.share.add(doctype, name, user, read=1, write=1, notify=1)

# def unshare_document(doctype, name, user):
#     """Removes a user's share permissions from a document."""
#     frappe.share.remove(doctype, name, user)


# # --- UTILITY FUNCTIONS (OPTIONAL BUT RECOMMENDED) ---

# @frappe.whitelist()
# def get_project_activity(doctype, docname):
#     """
#     Fetches all comments and communications for a given document.
#     """
#     try:
#         # This function is useful if you want to build a custom activity timeline view.
#         # It is not strictly necessary for the workflow but is good to keep.
#         comments = frappe.get_all(
#             "Comment",
#             filters={"reference_doctype": doctype, "reference_name": docname},
#             fields=["content", "owner", "creation", "comment_type"],
#             order_by="creation desc"
#         )
#         return comments
#     except Exception:
#         frappe.log_error(frappe.get_traceback(), "get_project_activity failed")
#         return []

# @frappe.whitelist()
# def add_project_comment(doctype, docname, content):
#     """
#     Adds a sanitized comment to a given document.
#     """
#     if not content or not content.strip():
#         frappe.throw("Comment content cannot be empty.")

#     try:
#         doc = frappe.get_doc(doctype, docname)
#         doc.add_comment("Comment", sanitize_html(content))
#         return doc.get("comments")[-1] # Return the newly created comment
#     except Exception:
#         frappe.log_error(frappe.get_traceback(), "add_project_comment failed")
#         frappe.throw("Could not add comment.")


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


# # static define
# @frappe.whitelist()
# def submit_project_registration(docname):
#     """
#     Handles the initial submission of a Project Registration.
#     This version dynamically handles the applicant_type being either an ID or a Name.
#     """
#     doc = frappe.get_doc("Project Registration", docname)
#     # file_info = save_doc_as_text_file(doc)

#     # Security Check: Only the owner of the draft can submit it.
#     if doc.owner != frappe.session.user:
#         frappe.throw("Permission Denied: You are not the owner of this document.")

#     if doc.docstatus != 0:
#         frappe.throw("This document has already been submitted.")

#     applicant_type_identifier = doc.applicant_type
#     if not applicant_type_identifier:
#         frappe.throw("Cannot submit: Applicant Type (Employee Class) is missing.")

#     # --- DYNAMIC LOOKUP LOGIC ---
#     emp_class_doc_id = None

#     # Case 1: The identifier is a valid DocType Name (ID). This is the fast path.
#     if frappe.db.exists("EmployeeClass_prornd", applicant_type_identifier):
#         emp_class_doc_id = applicant_type_identifier
#     else:
#         # Case 2: The identifier is not an ID, so it must be a name. Let's look it up.
#         found_id = frappe.db.get_value("EmployeeClass_prornd", {"empclass_name": applicant_type_identifier}, "name")
#         if found_id:
#             emp_class_doc_id = found_id

#     # If we still haven't found a valid ID, throw an error.
#     if not emp_class_doc_id:
#         frappe.throw(f"Invalid Applicant Type: Could not find an Employee Class matching '{applicant_type_identifier}'.")

#     # --- DATA-DRIVEN WORKFLOW ROUTING ---
#     # Now that we have the guaranteed ID, fetch the workflow path from the data.
#     workflow_path = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path")
#     next_state = ""

# if workflow_path == "Senior Staff Path":
#     next_state = "Pending Staff Approval"
# elif workflow_path == "HoD Path":
#     next_state = "Pending Head Approval"
#     if not doc.head_approver:
#         frappe.throw("Cannot submit: The designated Department Head approver has not been determined.")
#     share_document(doc.doctype, doc.name, doc.head_approver)
# else:
#     empclass_name = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "empclass_name")
#     frappe.throw(f"Could not find a valid approval path. The Employee Class '{empclass_name}' has an unconfigured or missing Workflow Path.")

# doc.workflow_state = next_state
# doc.submit()
# return doc.workflow_state

# -=-=-=-==-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
#  Dynanmic submit
# @frappe.whitelist()
# def submit_project_registration(docname):
#     """
#     Handles initial submission of Project Registration dynamically
#     based on workflow_path and configured transitions.
#     """
#     doc = frappe.get_doc("Project Registration", docname)

#     # Security: Only owner can submit draft
#     if doc.owner != frappe.session.user:
#         frappe.throw("Permission Denied: You are not the owner of this document.")

#     if doc.docstatus != 0:
#         frappe.throw("This document has already been submitted.")

#     applicant_type_identifier = doc.applicant_type
#     if not applicant_type_identifier:
#         frappe.throw("Cannot submit: Applicant Type (Employee Class) is missing.")

#     # Resolve EmployeeClass_prornd docname from either ID or name
#     emp_class_doc_id = None
#     if frappe.db.exists("EmployeeClass_prornd", applicant_type_identifier):
#         emp_class_doc_id = applicant_type_identifier
#     else:
#         found_id = frappe.db.get_value("EmployeeClass_prornd", {"empclass_name": applicant_type_identifier}, "name")
#         if found_id:
#             emp_class_doc_id = found_id

#     if not emp_class_doc_id:
#         frappe.throw(f"Invalid Applicant Type: Could not find an Employee Class matching '{applicant_type_identifier}'.")

#     # Get the workflow path identifier
#     workflow_path = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path")
#     if not workflow_path:
#         empclass_name = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "empclass_name")
#         frappe.throw(f"Employee Class '{empclass_name}' does not have a configured workflow path.")

#     # Fetch the Workflow document linked to this workflow path name
#     workflow_doc = frappe.get_doc("Workflow", workflow_path)
#     if not workflow_doc:
#         frappe.throw(f"Workflow '{workflow_path}' is not configured in the system.")

#     # Determine the current state, usually Draft or Not Started for new submission
#     current_state = doc.workflow_state or "Draft"

#     # Find the next transition based on the current state
#     next_transition = None
#     for t in workflow_doc.transitions:
#         if t.state == current_state:
#             next_transition = t
#             break

#     if not next_transition:
#         frappe.throw(f"No transition found from current state '{current_state}' in workflow '{workflow_path}'.")

#     next_state = next_transition.next_state

#     # Optional: dynamic handling of approver roles if needed
#     # For example, if next_state requires head_approver or similar, check here dynamically:
#     if "Head Approval" in next_state:
#         if not doc.head_approver:
#             frappe.throw("Cannot submit: The designated Department Head approver has not been determined.")
#         # Share document with head_approver dynamically
#         share_document(doc.doctype, doc.name, doc.head_approver)

#     # Update doc workflow state and submit
#     doc.workflow_state = next_state
#     doc.submit()

#     return doc.workflow_state

# ori
# @frappe.whitelist()
# def submit_project_registration(docname):
# 	"""
# 	Handles initial submission of Project Registration dynamically
# 	based on workflow_path and configured transitions.
# 	"""
# 	doc = frappe.get_doc("Project Registration", docname)
# 	frappe.msgprint(f"current_state DOC: <b>{doc}</b>")
# 	if not doc.workflow_state:
# 		doc.workflow_state = "Draft"
# 	# Security: Only owner can submit draft
# 	if doc.owner != frappe.session.user:
# 		frappe.throw("Permission Denied: You are not the owner of this document.")

# 	if doc.docstatus != 0:
# 		frappe.throw("This document has already been submitted.")

# 	applicant_type_identifier = doc.applicant_type
# 	if not applicant_type_identifier:
# 		frappe.throw("Cannot submit: Applicant Type (Employee Class) is missing.")

# 	# Resolve EmployeeClass_prornd docname from either ID or name
# 	emp_class_doc_id = None
# 	if frappe.db.exists("EmployeeClass_prornd", applicant_type_identifier):
# 		emp_class_doc_id = applicant_type_identifier
# 	else:
# 		found_id = frappe.db.get_value(
# 			"EmployeeClass_prornd", {"empclass_name": applicant_type_identifier}, "name"
# 		)
# 		if found_id:
# 			emp_class_doc_id = found_id

# 	if not emp_class_doc_id:
# 		frappe.throw(
# 			f"Invalid Applicant Type: Could not find an Employee Class matching '{applicant_type_identifier}'."
# 		)

# 	# Get the workflow path identifier
# 	workflow_path = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path")

# 	# --- FIX: If invalid or missing, default to pending_approval_prjReg ---
# 	if not workflow_path or not frappe.db.exists("Workflow", workflow_path):
# 		frappe.msgprint(
# 			f"⚠️ Employee Class '{applicant_type_identifier}' has invalid workflow path "
# 			f"('{workflow_path}'). Defaulting to 'pending_approval_prjReg'."
# 		)
# 		workflow_path = "pending_approval_prjReg"
# 		frappe.db.set_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path", workflow_path)
# 		frappe.db.commit()

# 	# Fetch the Workflow document linked to this workflow path name
# 	workflow_doc = frappe.get_doc("Workflow", workflow_path)

# 	# Determine the current state, usually Draft or Not Started for new submission
# 	current_state = doc.workflow_state or "Draft"
# 	frappe.msgprint(f"current_state Workflow Name: <b>{current_state}</b>")
# 	# Find the next transition based on the current state
# 	next_transition = None
# 	for t in workflow_doc.transitions:
# 		if t.state == current_state:
# 			next_transition = t
# 			break

# 	if not next_transition:
# 		frappe.throw(
# 			f"No transition found from current state '{current_state}' in workflow '{workflow_path}'."
# 		)

# 	next_state = next_transition.next_state

# 	# Optional: dynamic handling of approver roles if needed
# 	if "Head Approval" in next_state:
# 		if not doc.head_approver:
# 			frappe.throw("Cannot submit: The designated Department Head approver has not been determined.")
# 		share_document(doc.doctype, doc.name, doc.head_approver)

# 	# Update doc workflow state and submit
# 	doc.workflow_state = next_state
# 	doc.submit()

# 	return doc.workflow_state


# implementation_department
#


# base code
# @frappe.whitelist()
# def submit_project_registration(docname):
# 	doc = frappe.get_doc("Project Registration", docname)

# 	# Convert to dict for inspection
# 	data = doc.as_dict()
# 	print(f"Implementation Department: {data.get('implementation_department')}")

# 	# Fetch the linked Department_prornd document
# 	doc = frappe.get_doc("Department_prornd", data.get("implementation_department"))
# 	print(f"Department Name: {doc.dept_name}")
# 	print(f"Department Head: {doc.dept_head}")
# 	if not doc.workflow_state:
# 		doc.workflow_state = "Draft"

# 	# Security: Only owner can submit draft
# 	if doc.owner != frappe.session.user:
# 		frappe.throw("Permission Denied: You are not the owner of this document.")

# 	if doc.docstatus != 0:
# 		frappe.throw("This document has already been submitted.")

# 	# Resolve workflow path
# 	emp_class_doc_id = None
# 	applicant_type_identifier = doc.applicant_type

# 	if not applicant_type_identifier:
# 		frappe.throw("Cannot submit: Applicant Type (Employee Class) is missing.")

# 	if frappe.db.exists("EmployeeClass_prornd", applicant_type_identifier):
# 		emp_class_doc_id = applicant_type_identifier
# 	else:
# 		found_id = frappe.db.get_value(
# 			"EmployeeClass_prornd", {"empclass_name": applicant_type_identifier}, "name"
# 		)
# 		if found_id:
# 			emp_class_doc_id = found_id

# 	if not emp_class_doc_id:
# 		frappe.throw(
# 			f"Invalid Applicant Type: Could not find an Employee Class matching '{applicant_type_identifier}'."
# 		)

# 	workflow_path = frappe.db.get_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path")
# 	if not workflow_path or not frappe.db.exists("Workflow", workflow_path):
# 		workflow_path = "pending_approval_prjReg"
# 		frappe.db.set_value("EmployeeClass_prornd", emp_class_doc_id, "workflow_path", workflow_path)
# 		frappe.db.commit()

# 	workflow_doc = frappe.get_doc("Workflow", workflow_path)
# 	current_state = doc.workflow_state

# 	# Find the next transition
# 	next_transition = None
# 	for t in workflow_doc.transitions:
# 		if t.state == current_state:
# 			next_transition = t
# 			break

# 	if not next_transition:
# 		frappe.throw(
# 			f"No transition found from current state '{current_state}' in workflow '{workflow_path}'."
# 		)

# 	next_state = next_transition.next_state

# 	# Optional approver handling
# 	if "Head Approval" in next_state and not doc.head_approver:
# 		frappe.throw("Cannot submit: The designated Department Head approver has not been determined.")
# 		# share_document(doc.doctype, doc.name, doc.head_approver)  # if needed

# 	doc.workflow_state = next_state
# 	doc.submit()
# 	return doc.workflow_state


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


# @frappe.whitelist()
# def handle_approval_action(docname, action, comment=None):
#     """
#     Handles all subsequent workflow actions: Approve, Reject, Put Back, Resubmit.
#     This is our main "State Machine" engine.
#     """
#     doc = frappe.get_doc("Project Registration", docname)
#     current_state = doc.workflow_state
#     next_state = ""

#     # --- CORRECTED Security Validation ---
#     is_allowed = False
#     # Get the roles of the user making the request
#     user_roles = frappe.get_roles(frappe.session.user)
#     frappe.msgprint(f"User Roles: {user_roles}")

#     if current_state == "Pending HoD Approval" and frappe.session.user == doc.head_approver:
#         is_allowed = True
#     elif current_state == "Pending Staff Approval" and "staff, RnD" in user_roles:
#         is_allowed = True
#     elif current_state == "Pending HoS Approval" and "Hos, RnD (Head of Section, RnD)" in user_roles:
#         is_allowed = True
#     elif current_state == "Pending Dean Approval" and "Dean, RnD" in user_roles:
#         is_allowed = True
#     elif current_state == "Needs Correction" and frappe.session.user == doc.owner:
#         is_allowed = True

#     if not is_allowed and "System Manager" not in user_roles:
#         frappe.throw(f"Permission Denied: You are not authorized to perform the action '{action}' in the current state '{current_state}'.")

#     # Add comment to a log if provided
#     if comment:
#         doc.add_comment("Comment", f"<strong>Action: {action}</strong><br>{sanitize_html(comment)}")

#     # State Machine Logic (This part remains the same)
#     if action == "Approve":
#         if current_state == "Pending HoD Approval": next_state = "Pending Staff Approval"
#         elif current_state == "Pending Staff Approval": next_state = "Pending HoS Approval"
#         elif current_state == "Pending HoS Approval": next_state = "Pending Dean Approval"
#         elif current_state == "Pending Dean Approval": next_state = "Approved"

#         if current_state == "Pending HoD Approval":
#             unshare_document(doc.doctype, doc.name, doc.head_approver)

#     elif action == "Reject":
#         next_state = "Rejected"
#         doc.cancel()

#     elif action == "Put Back":
#         if current_state == "Pending Dean Approval": next_state = "Pending HoS Approval"
#         elif current_state == "Pending HoS Approval": next_state = "Pending Staff Approval"
#         elif current_state == "Pending Staff Approval": next_state = "Pending HoD Approval"
#         elif current_state == "Pending HoD Approval": next_state = "Needs Correction"

#         if current_state == "Pending HoD Approval":
#             unshare_document(doc.doctype, doc.name, doc.head_approver)

#     elif action == "Resubmit":
#         if current_state == "Needs Correction":
#             next_state = "Pending Staff Approval"

#     if next_state and doc.docstatus != 2:
#         doc.workflow_state = next_state
#         doc.save(ignore_permissions=True)

#     return doc.workflow_state


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

	# Jimmy added -=-=-=-=-=-=-= This sections handle form workflow
	# @frappe.whitelist()
	# def handle_approval_action(docname, action, comment=None):
	#     """
	#     Handles all subsequent workflow actions: Approve, Reject, Put Back, Resubmit.
	#     This is our main "State Machine" engine.
	#     """
	#     doc = frappe.get_doc("Project Registration", docname)
	#     current_state = doc.workflow_state
	#     next_state = ""
	#     # --- DEBUG: Print workflow states ---
	#     state_names = get_workflow_states("Project Registration")
	#     # frappe.msgprint(f"Workflow States for {doc.doctype}:<br><br>" + "<br>".join(state_names))

	#     # --- CORRECTED Security Validation ---
	#     is_allowed = False
	#     user_roles = frappe.get_roles(frappe.session.user)

	#     # Uncomment for development debug:
	#     frappe.msgprint(f"User Roles: {user_roles}")

	#     if current_state == "Pending HoD Approval" and frappe.session.user == doc.head_approver:
	#         is_allowed = True
	#     elif current_state == "Pending Staff Approval" and "staff, RnD" in user_roles:
	#         is_allowed = True
	#     elif current_state == "Pending HoS Approval" and "Hos, RnD (Head of Section, RnD)" in user_roles:
	#         is_allowed = True
	#     elif current_state == "Pending Dean Approval" and "Dean, RnD" in user_roles:
	#         is_allowed = True
	#     elif current_state == "Needs Correction" and frappe.session.user == doc.owner:
	#         is_allowed = True

	#     # Allow System Manager override
	#     if not is_allowed and "System Manager" not in user_roles:
	#         frappe.throw(f"Permission Denied: You are not authorized to perform the action '{action}' in the current state '{current_state}'.")

	#     # Log comment if provided
	#     if comment:
	#         doc.add_comment("Comment", f"<strong>Action: {action}</strong><br>{sanitize_html(comment)}")

	#     # --- STATE MACHINE LOGIC ---
	#     if action == "Approve":
	#         if current_state == "Pending HoD Approval":
	#             next_state = "Pending Staff Approval"
	#             unshare_document(doc.doctype, doc.name, doc.head_approver)
	#         elif current_state == "Pending Staff Approval":
	#             next_state = "Pending HoS Approval"
	#         elif current_state == "Pending HoS Approval":
	#             next_state = "Pending Dean Approval"
	#         elif current_state == "Pending Dean Approval":
	#             next_state = "Approved"

	#     elif action == "Reject":
	#         next_state = "Rejected"
	#         doc.cancel()

	#     elif action == "Put Back":
	#         if current_state == "Pending Dean Approval":
	#             next_state = "Pending HoS Approval"
	#         elif current_state == "Pending HoS Approval":
	#             next_state = "Pending Staff Approval"
	#         elif current_state == "Pending Staff Approval":
	#             next_state = "Pending HoD Approval"
	#         elif current_state == "Pending HoD Approval":
	#             next_state = "Needs Correction"
	#             unshare_document(doc.doctype, doc.name, doc.head_approver)

	#     elif action == "Resubmit":
	#         if current_state == "Needs Correction":
	#             next_state = "Pending Staff Approval"

	#     # Update state if valid
	#     if next_state and doc.docstatus != 2:
	#         doc.workflow_state = next_state
	#         doc.save(ignore_permissions=True)

	#     return doc.workflow_state

	# jimmy added -=-=-=-=-=-=-= Dynamic workflow handle approval
	# @frappe.whitelist()
	# def handle_approval_action(doctype, docname, action, comment=None):
	#     """
	#     Generic dynamic workflow state handler for any DocType using Frappe's Workflow system.
	#     """
	#     doc = frappe.get_doc(doctype, docname)
	#     current_state = doc.workflow_state
	#     user = frappe.session.user
	#     user_roles = frappe.get_roles(user)

	#     # Get associated workflow for this DocType
	#     workflow = frappe.get_value("Workflow Document State", {"parenttype": "Workflow", "parent": ["like", "%"], "doctype": doctype}, "parent")
	#     if not workflow:
	#         frappe.throw(f"No workflow configured for DocType {doctype}.")

	#     workflow_doc = frappe.get_doc("Workflow", workflow)

	#     # --- PERMISSION VALIDATION ---
	#     is_allowed = False
	#     valid_transitions = []

	#     for transition in workflow_doc.transitions:
	#         if transition.current_state == current_state and transition.action == action:
	#             valid_transitions.append(transition)

	#             # Role-based check
	#             allowed_roles = [
	#                 state.allow_edit for state in workflow_doc.states
	#                 if state.state == transition.current_state
	#             ]
	#             if allowed_roles:
	#                 allowed_roles = allowed_roles[0] if isinstance(allowed_roles[0], list) else [allowed_roles[0]]
	#                 if any(role in user_roles for role in allowed_roles):
	#                     is_allowed = True

	#     if not valid_transitions:
	#         frappe.throw(f"Invalid action '{action}' from state '{current_state}'.")

	#     if not is_allowed and "System Manager" not in user_roles:
	#         frappe.throw(f"Permission Denied: You are not authorized to perform the action '{action}' in the current state '{current_state}'.")

	# Log comment
	if comment:
		doc.add_comment("Comment", f"<strong>Action: {action}</strong><br>{sanitize_html(comment)}")


#     # --- TRANSITION STATE ---
#     transition = valid_transitions[0]  # assume one match for simplicity
#     next_state = transition.next_state

#     # Cancel if rejected (optional logic)
#     if action.lower() == "reject":
#         doc.cancel()

#     # Update workflow state and save
#     if next_state and doc.docstatus != 2:
#         doc.workflow_state = next_state
#         doc.save(ignore_permissions=True)

#     return doc.workflow_state


# --- Helper functions for document sharing --- Jimmy
def share_document(doctype, name, user):
	"""Shares a document with a user, giving them read and write access."""
	frappe.share.add(doctype, name, user, read=1, write=1, notify=1)


# def unshare_document(doctype, name, user):
#     """Removes a user's share permissions from a document."""
#     frappe.share.remove(doctype, name, user)


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


# @frappe.whitelist()
# def get_project_activity(doctype, docname):
# 	"""
# 	Fetches all comments and communications for a given document.
# 	"""
# 	# frappe.logger().warning(f"Jimmy get_project_activity Logging Debug: {docname}")
# #
# 	try:

# 		# This function is useful if you want to build a custom activity timeline view.
# 		# It is not strictly necessary for the workflow but is good to keep.
# 		comments = frappe.get_all(
# 			"Comment",
# 			filters={"reference_doctype": doctype, "reference_name": docname},
# 			fields=["content", "owner", "creation", "comment_type"],
# 			order_by="creation desc",
# 		)
# 	    # frappe.logger().warning(f"Jimmy get_project_activity Logging Debug: {comments}")
# #
# 		return comments
# 	except Exception:
# 		frappe.log_error(frappe.get_traceback(), "get_project_activity failed")
# 		return []
#


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


# @frappe.whitelist()
# def add_project_comment(doctype, docname, content):
# 	"""
# 	Adds a sanitized comment to a given document.
# 	"""
# 	if not content or not content.strip():
# 		frappe.throw("Comment content cannot be empty.")

# 	try:
# 		doc = frappe.get_doc(doctype, docname)
# 		doc.add_comment("Comment", sanitize_html(content))
# 		return doc.get("comments")[-1]  # Return the newly created comment
# 	except Exception:
# 		frappe.log_error(frappe.get_traceback(), "add_project_comment failed")
# 		frappe.throw("Could not add comment.")


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


# ------------- Added by MKY (08/10/2025) --------------
# @frappe.whitelist()
# def get_reimbursement_form_fields():
# 	"""
# 	Returns the doctype fields, pre-fill data, and link options
# 	for the Reimbursement form, mirroring the ProjectRegistration pattern.
# 	"""
# 	reimbursement_meta = frappe.get_meta("Reimbursement")
# 	fields = []

# 	# We can fetch all fields and let the frontend decide what to show,
# 	# or filter them here if some should never be sent.
# 	for field_doc in reimbursement_meta.get("fields"):
# 		fields.append(
# 			{
# 				"fieldname": field_doc.fieldname,
# 				"label": field_doc.label,
# 				"fieldtype": field_doc.fieldtype,
# 				"options": field_doc.options,
# 				"mandatory": field_doc.reqd,
# 				"hidden": field_doc.hidden,
# 				"read_only": field_doc.read_only,
# 				"description": field_doc.description,
# 				"default": field_doc.default,
# 			}
# 		)

# 	# Pre-fill data for the current user
# 	user_email = frappe.session.user
# 	user_details = frappe.get_all("User", filters={"email": user_email}, fields=["first_name", "last_name"])
# 	user_full_name = (
# 		f"{user_details[0].first_name} {user_details[0].last_name}" if user_details else user_email
# 	)

# 	prefill_data = {
# 		"reimbursement_user": user_email,
# 		"applicat_webmail": user_email,
# 		# You can add more pre-filled data based on user profile if needed
# 	}

# 	# Fetch options for Link fields
# 	link_options = {
# 		"reimbursement_user": frappe.get_all("User", fields=["email as value", "full_name as label"]),
# 		"applicat_webmail": frappe.get_all("User", fields=["email as value", "full_name as label"]),
# 		"project_name": frappe.get_all(
# 			"Project Registration", fields=["name as value", "project_title as label"]
# 		),
# 		"amended_from": frappe.get_all(
# 			"Reimbursement", fields=["name as value", "name as label"]
# 		),  # Shows previous reimbursements
# 	}

# 	return {
# 		"fields": fields,
# 		"prefill_data": prefill_data,
# 		"link_options": link_options,
# 	}


# @frappe.whitelist()
# def submit_reimbursement(doc):
# 	"""
# 	Receives the reimbursement form data from React and creates a new document.
# 	"""
# 	try:
# 		doc_data = frappe.parse_json(doc)

# 		# Create the new reimbursement document
# 		new_reimbursement = frappe.get_doc(
# 			{
# 				"doctype": "Reimbursement",
# 				**doc_data,  # Unpack all fields from the form
# 			}
# 		)

# 		new_reimbursement.insert(
# 			ignore_permissions=True
# 		)  # Or use check_permissions=True if you have workflows
# 		frappe.db.commit()

# 		return {"status": "success", "docname": new_reimbursement.name}
# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Reimbursement Submission Failed")
# 		raise e


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

# You will also need save methods for both doctypes, similar to previous examples.

# Your save_fund_sanction_data needs to handle JSON strings for tables


# @frappe.whitelist()
# def save_fund_sanction_data(doc_data):
# 	"""Saves the fund sanction data from the React form."""
# 	try:
# 		data = json.loads(doc_data)
# 		print("sanction manish:", data)

# 		# If 'name' is present, it's an update; otherwise, it's a new doc.
# 		if data.get("name"):
# 			doc = frappe.get_doc("Fund Sanction", data.get("name"))
# 			doc.update(data)
# 		else:
# 			doc = frappe.new_doc("Fund Sanction")
# 			doc.update(data)

# 		doc.save(ignore_permissions=True)
# 		frappe.db.commit()

# 		return {"status": "success", "docname": doc.name}
# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Save Error")
# 		raise e

