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


# @frappe.whitelist()
# def get_fund_sanction_form_data(project_proposal=None):
#     """
#     Returns the doctype fields, pre-fill data, and link options
#     for the Fund Sanction form. This is the backend source of truth.
#     """
#     fund_sanction_meta = frappe.get_meta("Fund Sanction")

#     # Define exactly which fields the form should display
#     form_fieldnames = [
#         'project_proposal', 'refnum_prj_num', 'total_sanctioned_amount',
#         'sanctioned_letter_no', 'sanctioned_letter_date', 'sanctioned_budget_breakup'
#     ]

#     fields = []
#     for f in fund_sanction_meta.get("fields"):
#         if f.fieldname in form_fieldnames:
#             fields.append({
#                 "fieldname": f.fieldname,
#                 "label": f.label,
#                 "fieldtype": f.fieldtype,
#                 "options": f.options,
#                 "mandatory": f.reqd,
#                 "hidden": f.hidden,
#                 "read_only": f.read_only,
#                 "description": f.description,
#             })

#     # Pre-fill the project proposal and ref number if provided
#     prefill_data = {}
#     if project_proposal:
#         prefill_data['project_proposal'] = project_proposal
#         prefill_data['refnum_prj_num'] = project_proposal

#     # Provide the list of projects for the 'project_proposal' Link field
#     link_options = {
#         "project_proposal": frappe.get_all("Project Registration", fields=["name as value", "project_title as label"])
#     }

#     return {
#         "fields": fields,
#         "prefill_data": prefill_data,
#         "link_options": link_options,
#     }


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


# @frappe.whitelist()
# def save_fund_sanction_data(doc):
# 	"""Saves the fund sanction data from the React form."""
# 	try:
# 		data = json.loads(doc)
# 		print("sanction manish:", data)

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

# import json
# import frappe


# @frappe.whitelist()
# def save_fund_sanction_data(**data):
# 	"""
# 	Saves Fund Sanction data, correctly handling child tables and file uploads
# 	by separating them and saving the parent document in stages.
# 	"""
# 	try:
# 		# 1. Separate BOTH child tables from the main data dictionary.
# 		budget_data = data.pop("sanctioned_budget_breakup", [])
# 		files_data = data.pop("sanction_related_files", [])
# 		submit = data.pop("submit", False)

# 		# --- DEBUG: Print the main data after popping child tables ---
# 		print("--- Main Document Data Keys (after popping ALL child tables) ---")
# 		print(list(data.keys()))
# 		print("---------------------------------------------------------------")

# 		# 2. Create or load the main document object using ONLY top-level fields.
# 		if data.get("name"):
# 			doc = frappe.get_doc("Fund Sanction", data.get("name"))
# 			doc.update(data)
# 			# Explicitly clear old child table data
# 			doc.set("sanctioned_budget_breakup", [])
# 			doc.set("sanction_related_files", [])
# 		else:
# 			data["doctype"] = "Fund Sanction"
# 			doc = frappe.get_doc(data)

# 		# 3. *** CRITICAL STEP 1 ***
# 		# Save the main document WITHOUT any child table data. This generates the `doc.name`.
# 		doc.save(ignore_permissions=True)
# 		print(f"SUCCESS: First save complete. Parent Doc Name: {doc.name}")

# 		# 4. Now that `doc.name` exists, manually append rows to the child tables.

# 		# Append budget breakup rows
# 		if budget_data:
# 			print("--- Appending Budget Breakup Rows ---")
# 			for row in budget_data:
# 				doc.append("sanctioned_budget_breakup", row)
# 			print(f"Appended {len(budget_data)} budget rows.")

# 		# Process and append file rows
# 		if files_data:
# 			print("--- Appending Sanction File Rows ---")
# 			for file_obj in files_data:
# 				if not file_obj.get("file_name") or not file_obj.get("file_data"):
# 					continue

# 				saved_file = frappe.get_doc(
# 					{
# 						"doctype": "File",
# 						"file_name": file_obj.get("file_name"),
# 						"attached_to_doctype": doc.doctype,
# 						"attached_to_name": doc.name,
# 						"content": file_obj.get("file_data").split(",", 1)[1],
# 						"decode": True,
# 					}
# 				)
# 				saved_file.save(ignore_permissions=True)

# 				doc.append(
# 					"sanction_related_files",
# 					{"description": file_obj.get("description"), "sanction_file": saved_file.file_url},
# 				)
# 			print(f"Appended {len(files_data)} file link rows.")

# 		# 5. *** CRITICAL STEP 2 ***
# 		# Save the parent document AGAIN to persist ALL the newly added child table rows.
# 		print("Attempting second save to persist all child tables...")
# 		doc.save(ignore_permissions=True)
# 		print("SUCCESS: Second save complete.")

# 		if submit:
# 			doc.submit()

# 		return {"status": "success", "docname": doc.name}

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Save Error")
# 		frappe.throw(f"An error occurred while saving the document: {str(e)}")

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
def save_fund_sanction_data(**data):
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


import frappe
import base64  # Import the base64 library


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
