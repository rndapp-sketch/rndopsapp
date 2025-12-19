import base64

import frappe


@frappe.whitelist()
def get_user_roles(user=None):
	"""
	Returns a list of roles for the given user.
	If no user is specified, returns roles for the currently logged-in user.
	"""
	try:
		# Use current session user if not explicitly provided
		if not user:
			user = frappe.session.user

		# Ensure the user exists
		if not frappe.db.exists("User", user):
			frappe.throw(f"User '{user}' does not exist.")

		# Fetch user roles
		roles = frappe.get_roles(user)
		return {"message": roles}

	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_user_roles failed")
		frappe.throw("Could not fetch user roles.")


@frappe.whitelist()
def get_fund_sanction_form_data(project_proposal=None):
	"""
	Returns the doctype fields, pre-fill data, and link options
	for the Fund Sanction form.
	"""
	fund_sanction_meta = frappe.get_meta("Fund Sanction")

	# --- MODIFICATION: Add the new table field to the list ---
	form_fieldnames = [
		"project_proposal",
		"refnum_prj_num",
		"total_sanctioned_amount",
		"sanctioned_letter_no",
		"sanctioned_letter_date",
		"sanctioned_budget_breakup",
		"sanction_related_files",  # <-- ADD THIS LINE
	]
	# --- END MODIFICATION ---

	fields = []
	for f in fund_sanction_meta.get("fields"):
		if f.fieldname in form_fieldnames:
			fields.append(
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
			)

	prefill_data = {}
	if project_proposal:
		prefill_data["project_proposal"] = project_proposal
		prefill_data["refnum_prj_num"] = project_proposal

	link_options = {
		"project_proposal": frappe.get_all(
			"Project Registration", fields=["name as value", "project_title as label"]
		)
	}

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
	}


import json

import frappe
import requests
from frappe.utils import flt

API_URL = "http://172.16.135.27:18080/api/sanction-details/addSanctionDetails"


def send_sanction_details_to_api(doc):
	"""
	Prepare and send Fund Sanction data to the external API endpoint.
	"""

	try:
		# --- Build JSON payload ---
		payload = {
			"projectNumber": doc.refnum_prj_num,
			"sanctionLetterNo": doc.sanctioned_letter_no,
			"sanctionLetterDate": str(doc.sanctioned_letter_date),
			"totalSanctionAmount": flt(doc.total_sanctioned_amount),
			"budgetBreakups": [],
		}

		# --- Prepare budget breakup list ---
		for row in doc.sanctioned_budget_breakup:
			total = (
				flt(row.first_year_budget)
				+ flt(row.second_year_budget)
				+ flt(row.third_year_budget)
				+ flt(row.fourth_year_budget)
				+ flt(row.fifth_year_budget)
			)

			payload["budgetBreakups"].append(
				{
					"accountHeadId": row.idx,  # or map based on actual account_head_id if available
					"accountHeadAmount": total,
				}
			)

		frappe.logger().info(f"Sending Sanction Details Payload: {payload}")

		# --- Send POST request ---
		response = requests.post(API_URL, json=payload, timeout=10)

		if response.status_code == 200:
			frappe.logger().info(f"✅ Sanction details sent successfully: {response.text}")
		else:
			frappe.log_error(
				f"Failed to send sanction details. Status: {response.status_code}, Response: {response.text}",
				"Send Sanction Details API Error",
			)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Send Sanction Details Exception")
		print(f"❌ Error sending sanction details: {e}")


@frappe.whitelist()
def draft_fund_sanction_data(**data):
	"""
	Save Fund Sanction data (parent + child tables), skipping all
	ERPNext link validations and saving only file paths.
	"""

	try:
		# Extract child tables and flags
		budget_data = data.pop("sanctioned_budget_breakup", [])
		files_data = data.pop("sanction_related_files", [])
		submit = data.pop("submit", False)

		print(f"\nIncoming Fund Sanction save request. Keys: {list(data.keys())}")
		print(f"Budget rows: {len(budget_data)}, File rows: {len(files_data)}")

		# Create or fetch the main Fund Sanction document
		if data.get("name"):
			doc = frappe.get_doc("Fund Sanction", data.get("name"))
			doc.update(data)
			doc.set("sanctioned_budget_breakup", [])
			doc.set("sanction_related_files", [])
		else:
			data["doctype"] = "Fund Sanction"
			doc = frappe.get_doc(data)

		# Disable validation and permission checks
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True

		# --- Save main document first ---
		doc.save(ignore_permissions=True)
		print(f"✅ Parent doc saved: {doc.name}")

		# --- Add budget breakup rows (raw data, no validation) ---
		if budget_data:
			for row in budget_data:
				# Remove possible invalid link keys
				row.pop("account_head_name", None)
				doc.append("sanctioned_budget_breakup", row)
			print(f"✅ Added {len(budget_data)} budget rows")

		# --- Add file rows (path only) ---
		if files_data:
			for f in files_data:
				file_path = f.get("sanction_file")
				if not file_path:
					continue
				doc.append(
					"sanction_related_files",
					{"description": f.get("description"), "sanction_file": file_path},
				)
			print(f"✅ Added {len(files_data)} sanction file rows")

		# --- Save again with children ---
		doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True)
		print("✅ Second save complete")

		# --- Submit if requested ---
		if submit:
			doc.submit()
			print("✅ Submitted successfully")
		# # --- ✅ Send data to external API ---
		send_sanction_details_to_api(doc)
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Fund Sanction Save Error")
		frappe.throw(f"An error occurred while saving the Fund Sanction: {str(e)}")


@frappe.whitelist()
def get_sanctions_for_project(project_name):
	"""
	Retrieves all Fund Sanction documents for a project,
	and embeds the content of any attached files as a Base64 string.
	"""
	if not project_name:
		return []

	sanction_names = frappe.get_all("Fund Sanction", filters={"project_proposal": project_name}, pluck="name")

	if not sanction_names:
		return []

	sanctions_list = []
	for name in sanction_names:
		# Get the full document as a dictionary
		doc_dict = frappe.get_doc("Fund Sanction", name).as_dict()

		# --- NEW: Process the child table for files ---
		# Check if the 'sanction_related_files' table exists and has entries
		if doc_dict.get("sanction_related_files"):
			# Loop through each file attached to this sanction document
			for file_info in doc_dict.get("sanction_related_files"):
				try:
					# Get the File document from the file_url
					file_url = file_info.get("sanction_file")
					if not file_url:
						continue

					# The actual file document contains the content
					file_doc = frappe.get_doc("File", {"file_url": file_url})

					# Get the raw binary content of the file
					file_content = file_doc.get_content()

					# Encode the binary content into a Base64 string (as utf-8 text)
					base64_content = base64.b64encode(file_content).decode("utf-8")

					# Add the base64 content as a new key to the file's dictionary
					# We also include the file_name for convenience on the frontend
					file_info["file_name"] = file_doc.file_name
					file_info["file_data"] = base64_content

				except Exception as e:
					# If a file is missing from disk or another error occurs, log it
					# and continue without crashing the whole API call.
					print(f"Could not read file for URL {file_url}: {e}")
					file_info["file_data"] = None  # Indicate that the file content is missing

		sanctions_list.append(doc_dict)

	return sanctions_list


@frappe.whitelist()
def get_all_workflow_states(workflow_name=None):
	"""
	Returns:
	  - all workflows with their states and allow_edit roles
	  - OR a specific workflow if workflow_name is passed
	"""

	result = []

	# If specific workflow is requested
	if workflow_name:
		if not frappe.db.exists("Workflow", workflow_name):
			return {"error": f"Workflow '{workflow_name}' does not exist."}

		doc = frappe.get_doc("Workflow", workflow_name)

		states_info = []
		for s in doc.states:
			states_info.append({"state": s.state, "allow_edit": s.allow_edit or []})

		return {"workflow": doc.name, "states": states_info}

	# Else fetch ALL workflows
	workflows = frappe.get_all("Workflow", fields=["name"])

	for wf in workflows:
		doc = frappe.get_doc("Workflow", wf.name)

		states_info = []
		for s in doc.states:
			states_info.append({"state": s.state, "allow_edit": s.allow_edit or []})

		result.append({"workflow": wf.name, "states": states_info})

	return result


@frappe.whitelist()
def get_workflow_transitions(workflow_name):
	"""
	Returns the transitions (paths) for a given workflow.
	"""
	if not workflow_name:
		return []

	if not frappe.db.exists("Workflow", workflow_name):
		frappe.throw(f"Workflow '{workflow_name}' does not exist.")

	doc = frappe.get_doc("Workflow", workflow_name)

	transitions = []
	for t in doc.transitions:
		transitions.append({
			"state": t.state,
			"action": t.action,
			"next_state": t.next_state,
			"allowed": t.allowed,
			"allow_self_approval": t.allow_self_approval,
			"condition": t.condition
		})

	return transitions

