import base64

import frappe


@frappe.whitelist()
def get_all_user_roles():
    """
    Returns a list of all users and their roles.
    Bypasses the child-table REST API restriction.
    """
    # Optional: Restricted to System Managers for security
    if "System Manager" not in frappe.get_roles():
        frappe.throw("You do not have permission to access the role list.", frappe.PermissionError)

    return frappe.get_all("Has Role", fields=["parent", "role"], limit_page_length=10000)


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
from rndopsapp.config import ACCOUNT_PORTAL_SANCTION_DETAILS

API_URL = ACCOUNT_PORTAL_SANCTION_DETAILS


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


# ================================ UNIVERSAL REGISTRATION API ================================

import json

def map_frontend_fields_to_doctype_ur(data):
	"""
	Map frontend field names to DocType field names for Universal Registration.
	"""
	field_mapping = {
		# Personal Information
		"email": "email_address_u_r",
		"full_name": "full_name_u_r",
		"parent_guardian_name": "guardian_name_u_r",
		"guardian_name": "guardian_name_u_r",
		"date_of_birth": "dob_u_r",
		"dob": "dob_u_r",
		"gender": "gender_u_r",
		"nationality": "nationality_u_r",
		"mobile_number": "mobile_number_u_r",
		"phone": "mobile_number_u_r",
		"whatsapp_number": "whatsapp_number_u_r",
		"alternate_mobile": "alternate_mobile_number_u_r",
		"same_as_mobile": "same_as_mobile_number_u_r",
		
		# Organization Information
		"organization_name": "org_name_u_r",
		"org_name": "org_name_u_r",
		"establishment_date": "est_date_u_r",
		"incorporation_date": "est_date_u_r",
		"business_nature": "nature_of_business_u_r",
		"nature_of_business": "nature_of_business_u_r",
		"website": "website_u_r",
		"contact_person": "contact_person_u_r",
		"contact_designation": "contact_designation",
		"organization_email": "email_oraganization__contact_person_u_r",
		"org_email": "email_oraganization__contact_person_u_r",
		"org_phone": "org_contact_number_u_r",
		"organization_phone": "org_contact_number_u_r",
		"org_mobile": "organization_mobile_number_u_r",
		"organization_mobile": "organization_mobile_number_u_r",
		
		# Profile & Classification
		"profile_type": "profile_type_u_r",
		"org_sub_type": "organization_sub_type_u_r",
		"organization_sub_type": "organization_sub_type_u_r",
		
		# Financial & Documents
		"bank_details": "bank_details_u_r",
		"documents": "uploaded_documents_u_r",
		"uploaded_documents": "uploaded_documents_u_r",
		"addresses": "address_details",
		"address_details": "address_details",
		"org_addresses": "org_address_details_u_r",
		"org_address_details": "org_address_details_u_r",
		"qualifications": "qualifications_u_r",
		"education_qualifications": "qualifications_u_r",
		"education": "qualifications_u_r",
		"experiences": "experiences_u_r",
		"experience": "experiences_u_r",
		
		# Vendor & Compliance
		"type_of_business": "type_of_business_u_r",
		"nature_of_org": "nature_of_org",
		"organization_nature": "nature_of_org",
		"pan_number": "pan_number_org_u_r",
		"gst_status": "gst_status_u_r",
		"gst_number": "gst_number_u_r",
		"other_registration": "other_registration_u_r",
		"overhead_percentage": "overhead_percentage_u_r",
		"discount_percentage": "discount_percentage_u_r",
		"agreement_number": "agreement_number_u_r",
		
		# Signatory
		"signatory_name": "signatory_name_u_r",
		"signatory_designation": "signatory_designation_u_r",
		"date_of_signing": "date_of_signing_u_r",
		"declaration": "decl_info_true_u_r",
		"info_declaration": "decl_info_true_u_r",
		
		# User email
		"user_email": "email_address_u_r"
	}
	
	mapped_data = {}
	for frontend_field, value in data.items():
		doctype_field = field_mapping.get(frontend_field, frontend_field)
		mapped_data[doctype_field] = value
	
	return mapped_data


# ---- Child-table row field-name mappings ----
# These map frontend row keys -> actual child-doctype fieldnames (which carry _u_r suffixes)
CHILD_ROW_FIELD_MAPPINGS = {
	"Universal Bank Details__": {
		# Frontend key                  -> Doctype fieldname
		"beneficiary_name":              "beneficiary_name_u_r",
		"account_holder_name":           "beneficiary_name_u_r",   # frontend alias
		"account_number":                "account_number_u_r",
		"confirm_account_number":        "confirm_account_number_u_r",
		"ifsc_code":                     "ifsc_code_u_r",
		"bank_name":                     "bank_name_u_r",
		"branch_name":                   "branch_name_u_r",
		"bank_branch":                   "branch_name_u_r",         # frontend alias
		"account_type":                  "account_type_u_r",
		"is_primary":                    "is_primary_u_r",
		"primary_account":               "is_primary_u_r",          # frontend alias
		"attachment":                    "attachment_u_r",
		"cancelled_cheque":              "attachment_u_r",
		"bank_passbook_front_page":      "bank_passbook_front_page_u_r",
		"passbook_front_page":           "bank_passbook_front_page_u_r",
	},
	"Personal Qualification__": {
		# Frontend key         -> Doctype fieldname
		"level":                "level_u_r",
		"qualification_level":  "level_u_r",              # frontend alias
		"course_name":          "course_name_u_r",
		"degree_name":          "course_name_u_r",        # frontend alias
		"specialization":       "specialization_u_r",
		"institution":          "institution_u_r",
		"institution_name":     "institution_u_r",        # frontend alias
		"university":           "university_u_r",
		"board":                "university_u_r",
		"board_university":     "university_u_r",         # frontend alias
		"year_of_passing":      "year_of_passing_u_r",
		"passing_year":         "year_of_passing_u_r",
		"result_type":          "result_type_u_r",
		"score":                "score_u_r",
		"certificate_file":     "certificate_file_u_r",
		"certificate":          "certificate_file_u_r",
	},
	"Personal Experience__": {
		# Frontend key                          -> Doctype fieldname
		"organization":                          "organization_u_r",
		"company":                               "organization_u_r",
		"employment_type":                       "employment_type_u_r",
		"designation":                           "designation_u_r",
		"department":                            "department_u_r",
		"from_date":                             "from_date_u_r",
		"start_date":                            "from_date_u_r",
		"to_date":                               "to_date_u_r",
		"end_date":                              "to_date_u_r",
		"total_experience":                      "total_experience_u_r",
		"nature_of_work":                        "nature_of_work__responsibilities_u_r",
		"responsibilities":                      "nature_of_work__responsibilities_u_r",
		"nature_of_work_responsibilities":       "nature_of_work__responsibilities_u_r",
		"work_nature":                           "nature_of_work__responsibilities_u_r",  # frontend alias
		"currently_working":                     "currently_working_u_r",
		"exp_certificate":                       "exp_certificate_u_r",
		"experience_certificate":                "exp_certificate_u_r",
	},
	"Universal Address__": {
		"address_line_1":  "address_line_1_u_r",
		"house_no":        "address_line_1_u_r",
		"address_line_2":  "address_line_2_u_r",
		"street_area":     "address_line_2_u_r",
		"landmark":        "landmark_u_r",
		"pin_code":        "pincode_u_r",
		"postal_code":     "pincode_u_r",
		"pincode":         "pincode_u_r",
		"city":            "city_u_r",
		"state":           "state_u_r",
		"district":        "district_u_r",
	},
}


def map_child_row_fields(child_doctype, row_data):
	"""
	Remap child table row field names from frontend keys to the actual
	DocType field names. Falls back to the original key if no mapping exists.
	"""
	mapping = CHILD_ROW_FIELD_MAPPINGS.get(child_doctype, {})
	if not mapping:
		return row_data  # No mapping defined - return as-is

	remapped = {}
	for key, value in row_data.items():
		# Skip internal Frappe keys that shouldn't be passed
		if key in ('doctype', 'parent', 'parentfield', 'parenttype', 'idx'):
			continue
		doctype_key = mapping.get(key, key)
		remapped[doctype_key] = value
	return remapped


# ---- Flat-field assemblers for Bank / Education / Experience ----
# The frontend sometimes sends individual fields at the top level of formData
# (same pattern as address fields). These sets define which top-level keys belong
# to each child table. _assemble_flat_child_rows() collects them, maps them to
# _u_r fieldnames, and injects them as child-table rows (removing originals so
# the parent doc does not receive unknown fields).

_BANK_FLAT_FIELDS = {
	"account_holder_name", "account_number", "confirm_account_number",
	"ifsc_code", "bank_branch", "account_type", "primary_account",
	"bank_name",
}

_EDUCATION_FLAT_FIELDS = {
	"qualification_level", "degree_name", "specialization", "year_of_passing",
	"institution_name", "board_university", "result_type", "score",
}

_EXPERIENCE_FLAT_FIELDS = {
	"organization", "employment_type", "designation", "department",
	"from_date", "to_date", "currently_working", "work_nature",
}


def _assemble_flat_child_rows(data):
	"""
	Detect flat bank / education / experience fields at the top level of data
	and assemble them into child-table rows (with correct _u_r field names),
	exactly the same way the address block already works.
	Mutates `data` in place and returns it.
	"""
	# -- Bank Details --
	bank_row_raw = {k: data[k] for k in _BANK_FLAT_FIELDS if k in data and data[k] not in (None, "")}
	if bank_row_raw:
		for k in list(bank_row_raw.keys()):
			data.pop(k, None)
		bank_row = map_child_row_fields("Universal Bank Details__", bank_row_raw)
		if not isinstance(data.get("bank_details_u_r"), list):
			data["bank_details_u_r"] = []
		if not data["bank_details_u_r"]:
			data["bank_details_u_r"].append(bank_row)
		else:
			data["bank_details_u_r"][0].update(bank_row)

	# -- Education Qualifications --
	edu_row_raw = {k: data[k] for k in _EDUCATION_FLAT_FIELDS if k in data and data[k] not in (None, "")}
	if edu_row_raw:
		for k in list(edu_row_raw.keys()):
			data.pop(k, None)
		edu_row = map_child_row_fields("Personal Qualification__", edu_row_raw)
		if not isinstance(data.get("qualifications_u_r"), list):
			data["qualifications_u_r"] = []
		if not data["qualifications_u_r"]:
			data["qualifications_u_r"].append(edu_row)
		else:
			data["qualifications_u_r"][0].update(edu_row)

	# -- Work Experience --
	exp_row_raw = {k: data[k] for k in _EXPERIENCE_FLAT_FIELDS if k in data and data[k] not in (None, "")}
	if exp_row_raw:
		for k in list(exp_row_raw.keys()):
			data.pop(k, None)
		exp_row = map_child_row_fields("Personal Experience__", exp_row_raw)
		if not isinstance(data.get("experiences_u_r"), list):
			data["experiences_u_r"] = []
		if not data["experiences_u_r"]:
			data["experiences_u_r"].append(exp_row)
		else:
			data["experiences_u_r"][0].update(exp_row)

	return data


# ---- KYC / Identity flat-field assembler ----
# The frontend sends Aadhaar / PAN / Other ID as flat fields at the top level.
# The backend stores them as rows in the uploaded_documents_u_r child table
# (Universal Documents__ doctype) using document_name_u_r + id_number_u_r.

_KYC_FLAT_FIELDS = {
	# frontend key         : (document_name_u_r value, document_type_u_r value)
	"aadhaar_number":       ("Aadhaar", "Identity"),
	"pan_number":           ("PAN",     "Tax"),
	"other_identity_number": ("Other",  "Identity"),
}


def _assemble_kyc_child_rows(data):
	"""
	Convert flat KYC identity fields into rows inside the
	uploaded_documents_u_r child table (Universal Documents__).

	For each KYC key found in data:
	  - Remove the flat key from data
	  - Add / update a row in data['uploaded_documents_u_r'] that has
	    document_name_u_r = <name>, document_type_u_r = <type>,
	    id_number_u_r = <value>

	Mutates `data` in place and returns it.
	"""
	new_rows = []
	for flat_key, (doc_name, doc_type) in _KYC_FLAT_FIELDS.items():
		value = data.pop(flat_key, None)
		if value not in (None, ""):
			new_rows.append({
				"document_name_u_r": doc_name,
				"document_type_u_r": doc_type,
				"id_number_u_r": str(value),
			})

	if not new_rows:
		return data

	existing = data.get("uploaded_documents_u_r", [])
	if not isinstance(existing, list):
		existing = []

	# Build an index of already-present rows by document_name so we can update
	# in-place rather than duplicate them.
	existing_idx = {row.get("document_name_u_r"): i for i, row in enumerate(existing)}

	for row in new_rows:
		doc_name = row["document_name_u_r"]
		if doc_name in existing_idx:
			existing[existing_idx[doc_name]].update(row)
		else:
			existing.append(row)

	data["uploaded_documents_u_r"] = existing
	return data


@frappe.whitelist(allow_guest=True)
def get_universal_user_by_email(email):
	"""
	Fetch Universal User ID by email address.
	Returns the user ID (like U_U_20260223_205330) for a given email.
	
	@param email: Email address to look up
	@return: user_id if found, None otherwise
	"""
	try:
		if not email:
			return None
		
		# Query the Universal User doctype
		# Note: Universal User uses "email_u_r" as the email field name
		user_id = frappe.db.get_value(
			"Universal User__",
			{"email_u_r": email},
			"name"
		)
		
		if user_id:
			print(f"[DEBUG] ✓ Found Universal User {user_id} for email {email}")
			return {"status": "success", "data": user_id}
		else:
			print(f"[DEBUG] ✗ No Universal User found for email {email}")
			return {"status": "success", "data": None}
			
	except Exception as e:
		error_msg = str(e)
		frappe.log_error(error_msg, "get_universal_user_by_email")
		print(f"[ERROR] get_universal_user_by_email: {error_msg}")
		return {"status": "error", "message": error_msg}

@frappe.whitelist(allow_guest=True)
def get_existing_registration(email):
	"""
	Check if a Universal Registration already exists for a user by email.
	Returns the docname (like UNIREG-00008) if found.
	
	@param email: Email address to check
	@return: docname if exists, None otherwise
	"""
	try:
		if not email:
			return {"status": "success", "data": None}
		
		# Query the Universal Registration doctype
		existing = frappe.db.get_value(
			"Universal Registration__",
			{"email_address_u_r": email},
			"name"
		)
		
		if existing:
			print(f"[DEBUG] Found existing registration {existing} for email {email}")
			return {"status": "success", "data": existing}
		else:
			print(f"[DEBUG] No registration found for email {email}")
			return {"status": "success", "data": None}
			
	except Exception as e:
		error_msg = str(e)
		frappe.log_error(error_msg, "get_existing_registration")
		print(f"[ERROR] get_existing_registration: {error_msg}")
		return {"status": "error", "message": error_msg}

@frappe.whitelist(allow_guest=True)
def get_or_load_user_registration():
	"""
	Fetch the current user's existing Universal Registration.
	Returns the registration data if it exists, empty response if not.
	Helps populate the form with saved data when user returns.
	Searches by: universal_user_u_r, email, or user email.
	"""
	try:
		current_user = frappe.session.user
		print(f"[DEBUG] Load registration for user: {current_user}")
		
		# Don't search for Guest user
		if current_user == "Guest":
			return {"status": "success", "data": None, "message": "No existing registration found for guest user"}
		
		docname = None
		lookup_method = None
		
		# Strategy 1: Search for existing registration by universal_user_u_r field (which links to user)
		try:
			existing = frappe.db.get_list(
				"Universal Registration__",
				filters={"universal_user_u_r": current_user},
				fields=["name"],
				limit=1
			)
			
			if existing:
				docname = existing[0]["name"]
				lookup_method = "universal_user_u_r"
				print(f"[DEBUG] ✓ Found registration by user link: {docname}")
		except Exception as e:
			print(f"[DEBUG] ✗ Search by user link failed: {e}")
		
		# Strategy 2: Try by user's email
		if not docname:
			try:
				user_doc = frappe.get_doc("User", current_user)
				if user_doc.email:
					existing = frappe.db.get_list(
						"Universal Registration__",
						filters={"email_address_u_r": user_doc.email},
						fields=["name"],
						limit=1
					)
					if existing:
						docname = existing[0]["name"]
						lookup_method = "user_email"
						print(f"[DEBUG] ✓ Found registration by user email: {docname}")
			except Exception as e:
				print(f"[DEBUG] ✗ Search by user email failed: {e}")
		
		# Return found registration
		if docname:
			doc = frappe.get_doc("Universal Registration__", docname)
			return {
				"status": "success",
				"data": doc.as_dict(),
				"docname": doc.name,
				"lookup_method": lookup_method,
				"message": f"Existing registration found (via {lookup_method})"
			}
		else:
			print(f"[DEBUG] No existing registration found for user")
			return {"status": "success", "data": None, "message": "No existing registration found"}
			
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get User Registration Error")
		print(f"ERROR in get_or_load_user_registration: {str(e)}")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def save_universal_registration_data(data=None, **kwargs):
	"""
	Save Universal Registration data (parent + child tables).
	Automatically maps frontend field names to DocType field names.
	Allows guest users to register.
	"""
	try:
		# Handle different input formats - extract actual form data
		form_data = None
		
		# Try to get data from the explicit 'data' parameter
		if data is not None:
			if isinstance(data, str):
				try:
					form_data = json.loads(data)
				except:
					form_data = data
			elif isinstance(data, dict):
				form_data = data
		
		# If no data found in explicit parameter, check kwargs for 'data' key or use kwargs
		if not form_data:
			if 'data' in kwargs and isinstance(kwargs['data'], dict):
				form_data = kwargs['data']
			else:
				form_data = {k: v for k, v in kwargs.items() if k not in ['cmd', 'doctype', 'name_field', 'data']}
		
		# If still no data, return error
		if not form_data:
			return {"status": "error", "message": "No data provided"}
		
		# Ensure data is a dictionary
		if not isinstance(form_data, dict):
			form_data = {}
		
		# Create clean data dict by filtering out system parameters
		# Remove: cmd, doctype, name_field, data (wrapper key), and any other system fields
		system_fields_to_skip = {'cmd', 'doctype', 'name_field', 'data', 'user_id', 'section', 'csrf_token', '__isrevision', '__version_fields', ''}
		data = {k: v for k, v in form_data.items() if k not in system_fields_to_skip and k and v is not None}
		
		# *** Extract KYC flat fields FIRST, before field-name mapping renames pan_number → pan_number_org_u_r ***
		data = _assemble_kyc_child_rows(data)

		# Map frontend field names to doctype field names
		data = map_frontend_fields_to_doctype_ur(data)
		
		# Double-check: Remove any remaining system fields after mapping
		system_fields_to_skip = {'cmd', 'doctype', 'name_field', 'data', 'user_id', 'section', 'csrf_token', '__isrevision', '__version_fields', ''}
		data = {k: v for k, v in data.items() if k not in system_fields_to_skip and k}

		# CRITICAL FIX: Restructure address fields from parent level to child table
		# Frontend sends individual address fields at parent level, but they need to be in address_details child table
		# Also map them to the correct Universal Address__ field names
		address_field_mapping = {
			'house_no': 'address_line_1_u_r',
			'street_area': 'address_line_2_u_r',
			'landmark': 'landmark_u_r',
			'pin_code': 'pincode_u_r',
			'postal_code': 'pincode_u_r',
			'city': 'city_u_r',
			'state': 'state_u_r',
			'district': 'district_u_r',
			'address_line_1': 'address_line_1_u_r',
			'address_line_2': 'address_line_2_u_r',
			'country': 'country',
		}
		
		# Extract and map address fields
		address_fields_in_data = {}
		for frontend_field, child_table_value in list(data.items()):
			if frontend_field in address_field_mapping:
				doctype_field = address_field_mapping[frontend_field]
				address_fields_in_data[doctype_field] = child_table_value
		
		if address_fields_in_data:
			# Remove address fields from parent data
			data = {k: v for k, v in data.items() if k not in address_field_mapping}
			
			# Create or update address_details child table
			if 'address_details' not in data or not isinstance(data['address_details'], list):
				data['address_details'] = []
			
			# Add address fields to first row of child table if it doesn't exist
			if not data['address_details']:
				data['address_details'].append(address_fields_in_data)
			else:
				# Update existing first row
				data['address_details'][0].update(address_fields_in_data)

		# Assemble any flat bank / education / experience fields into child-table rows
		data = _assemble_flat_child_rows(data)

		docname = data.get("name") or data.get("docname")
		
		if docname:
			doc = frappe.get_doc("Universal Registration__", docname)
		else:
			doc = frappe.new_doc("Universal Registration__")
		
		# Get metadata to filter valid fields
		meta = frappe.get_meta("Universal Registration__")

		# Iterate over data and set fields
		for fieldname, value in data.items():
			# Skip empty fieldnames and system fields
			if not fieldname or fieldname in {'cmd', 'doctype', 'name_field', 'data', 'user_id', 'section', 'csrf_token', '__isrevision', '__version_fields'}:
				continue
			
			if not meta.has_field(fieldname):
				continue
			
			# Skip empty values
			if value is None or value == "":
				continue
				
			df = meta.get_field(fieldname)
			
			# Handle Phone fields
			if df.fieldtype == "Phone" and value:
				phone_str = str(value).strip()
				if not phone_str.startswith("+"):
					value = f"+91-{phone_str}"
				else:
					value = phone_str
			
			# Handle Child Tables
			if df.fieldtype == "Table" and isinstance(value, list):
				doc.set(fieldname, [])
				child_doctype = df.options
				child_meta = frappe.get_meta(child_doctype)
				child_valid_fields = {cf.fieldname for cf in child_meta.fields}
				
				for child_row in value:
					if not isinstance(child_row, dict):
						continue
					
					# Remap frontend field names → actual doctype field names
					child_row = map_child_row_fields(child_doctype, child_row)
					
					# Filter to only fields that exist in the child doctype
					child_row = {k: v for k, v in child_row.items() if k in child_valid_fields}
					
					if not child_row:
						continue
						
					# Handle Phone fields in child table
					for cf in child_meta.fields:
						if cf.fieldtype == "Phone" and child_row.get(cf.fieldname):
							p_val = child_row[cf.fieldname]
							if not str(p_val).startswith("+"):
								child_row[cf.fieldname] = f"+91-{p_val}"

					doc.append(fieldname, child_row)
					
			# Handle Attach fields (Base64) - Store in MinIO
			elif df.fieldtype in ["Attach", "Attach Image"] and isinstance(value, dict) and value.get("file_data"):
				try:
					from rndopsapp.minio import get_rnd_file_service
					from rndopsapp.file_handler import get_file_category_for_doctype
					file_bytes = base64.b64decode(value["file_data"]) if isinstance(value["file_data"], str) else value["file_data"]
					file_service = get_rnd_file_service()
					folder = get_file_category_for_doctype(doc.doctype, fieldname)
					upload_result = file_service.save_file(
						filename=value.get("file_name", "attached_file"),
						content=file_bytes,
						is_private=False,
						doctype=doc.doctype,
						docname=doc.name,
						folder=folder,
						use_hash=True,
					)
					if upload_result.get("status"):
						doc.set(fieldname, upload_result["data"]["file_url"])
				except Exception as e:
					frappe.log_error(f"File Upload Error: {str(e)}")
					pass
				
			# Standard fields
			else:
				doc.set(fieldname, value)

		# *** CRITICAL: Set universal_user_u_r correctly based on Universal User__ doctype, NOT Frappe User ***
		# The universal_user_u_r field is a Link to "Universal User__" doctype, not regular User doctype
		# Only set it if we have a valid Universal User ID
		
		user_email = data.get("email_address_u_r")
		# Check if universal_user_u_r was already set from the form data
		if not doc.universal_user_u_r and user_email:
			# Try to find the Universal User by email
			try:
				universal_user = frappe.db.get_value(
					"Universal User__",
					{"email_u_r": user_email},
					"name"
				)
				if universal_user:
					doc.universal_user_u_r = universal_user
			except Exception as e:
				pass  # Silently skip if lookup fails
		
		# IMPORTANT: Do NOT set this to Frappe's session.user - that causes validation errors
		# The universal_user_u_r field must be a valid Universal User__ doctype reference

		# For guest users, set owner as system
		if doc.is_new():
			if frappe.session.user == "Guest":
				doc.owner = "Administrator"
			else:
				doc.owner = frappe.session.user

		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_validate = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name, "message": "Saved successfully."}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Universal Registration Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_universal_registration_list(filters=None, limit=None, offset=None):
	"""
	Fetch a list of Universal Registration documents with optional filtering.
	"""
	try:
		if filters and isinstance(filters, str):
			filters = json.loads(filters)
		
		limit = int(limit) if limit else 50
		offset = int(offset) if offset else 0
		
		# Build filter conditions
		filter_conditions = {}
		if filters:
			for key, value in filters.items():
				if value:
					filter_conditions[key] = value
		
		# Fetch documents
		documents = frappe.get_list(
			"Universal Registration__",
			filters=filter_conditions,
			fields=["name", "profile_type_u_r", "full_name_u_r", "email_address_u_r", "mobile_number_u_r", "org_name_u_r", "modified", "owner"],
			order_by="modified desc",
			limit=limit,
			start=offset
		)
		
		# Get total count
		total = frappe.db.count(
			"Universal Registration__",
			filters=filter_conditions
		)
		
		return {
			"status": "success",
			"data": documents,
			"total": total,
			"limit": limit,
			"offset": offset
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Universal Registration List Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_universal_registration_details(docname):
	"""
	Fetch complete details of a Universal Registration document.
	Also injects flat KYC fields (aadhaar_number_u_r, pan_number_u_r,
	other_identity_number_u_r) extracted from uploaded_documents_u_r rows,
	so the frontend API_TO_FORM_MAP can prefill the Identity section.
	"""
	try:
		doc = frappe.get_doc("Universal Registration__", docname)
		doc_dict = doc.as_dict()

		# -- Inject flat KYC fields from uploaded_documents_u_r child rows --
		# Map document_name_u_r → parent-level flat field name
		_DOC_NAME_TO_FLAT = {
			"Aadhaar": "aadhaar_number_u_r",
			"PAN":     "pan_number_u_r",
			"Other":   "other_identity_number_u_r",
		}
		for row in doc_dict.get("uploaded_documents_u_r", []):
			doc_name = row.get("document_name_u_r", "")
			flat_key = _DOC_NAME_TO_FLAT.get(doc_name)
			if flat_key and row.get("id_number_u_r"):
				doc_dict[flat_key] = row["id_number_u_r"]

		return {
			"status": "success",
			"data": doc_dict
		}
	except frappe.DoesNotExistError:
		return {"status": "error", "message": f"Universal Registration document '{docname}' not found."}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Universal Registration Details Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def update_universal_registration_data(docname, data):
	"""
	Update an existing Universal Registration document.
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)
		
		doc = frappe.get_doc("Universal Registration__", docname)
		meta = frappe.get_meta("Universal Registration__")
		
		# *** Extract KYC flat fields FIRST, before field-name mapping renames pan_number → pan_number_org_u_r ***
		data = _assemble_kyc_child_rows(data)

		# Map frontend field names
		data = map_frontend_fields_to_doctype_ur(data)
		
		# Assemble any flat bank / education / experience fields into child-table rows
		data = _assemble_flat_child_rows(data)
		
		# Iterate over data and update fields
		for fieldname, value in data.items():
			if not meta.has_field(fieldname):
				continue
				
			df = meta.get_field(fieldname)
			
			# Handle Phone fields
			if df.fieldtype == "Phone" and value:
				phone_str = str(value).strip()
				if not phone_str.startswith("+"):
					value = f"+91-{phone_str}"
			
			# Handle Child Tables
			if df.fieldtype == "Table" and isinstance(value, list):
				doc.set(fieldname, [])
				child_doctype = df.options
				child_meta = frappe.get_meta(child_doctype)
				child_valid_fields = {cf.fieldname for cf in child_meta.fields}
				
				for child_row in value:
					if not isinstance(child_row, dict):
						continue
					
					# Remap frontend field names → actual doctype field names
					child_row = map_child_row_fields(child_doctype, child_row)
					
					# Filter to only fields that exist in the child doctype
					child_row = {k: v for k, v in child_row.items() if k in child_valid_fields}
					
					if not child_row:
						continue
					
					for cf in child_meta.fields:
						if cf.fieldtype == "Phone" and child_row.get(cf.fieldname):
							p_val = child_row[cf.fieldname]
							if not str(p_val).startswith("+"):
								child_row[cf.fieldname] = f"+91-{p_val}"

					doc.append(fieldname, child_row)
					
			elif df.fieldtype in ["Attach", "Attach Image"] and isinstance(value, dict) and value.get("file_data"):
				try:
					from rndopsapp.minio import get_rnd_file_service
					from rndopsapp.file_handler import get_file_category_for_doctype
					file_bytes = base64.b64decode(value["file_data"]) if isinstance(value["file_data"], str) else value["file_data"]
					file_service = get_rnd_file_service()
					folder = get_file_category_for_doctype(doc.doctype, fieldname)
					upload_result = file_service.save_file(
						filename=value.get("file_name", "attached_file"),
						content=file_bytes,
						is_private=False,
						doctype=doc.doctype,
						docname=doc.name,
						folder=folder,
						use_hash=True,
					)
					if upload_result.get("status"):
						doc.set(fieldname, upload_result["data"]["file_url"])
				except Exception as e:
					frappe.log_error(f"File Upload Error: {str(e)}")

			else:
				doc.set(fieldname, value)

		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name, "message": "Updated successfully."}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Universal Registration Update Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_universal_registration_by_email(email):
	"""
	Fetch a Universal Registration document by email address.
	"""
	try:
		documents = frappe.get_list(
			"Universal Registration__",
			filters={"email_address_u_r": email},
			fields=["name", "profile_type_u_r", "full_name_u_r", "email_address_u_r", "mobile_number_u_r", "org_name_u_r"],
			limit=1
		)
		
		if documents:
			return get_universal_registration_details(documents[0]["name"])
		else:
			return {"status": "error", "message": f"No Universal Registration found with email '{email}'."}
			
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Universal Registration by Email Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_universal_registration_by_phone(phone):
	"""
	Fetch a Universal Registration document by phone number.
	"""
	try:
		documents = frappe.get_list(
			"Universal Registration__",
			filters={"mobile_number_u_r": phone},
			fields=["name", "profile_type_u_r", "full_name_u_r", "email_address_u_r", "mobile_number_u_r", "org_name_u_r"],
			limit=1
		)
		
		if documents:
			return get_universal_registration_details(documents[0]["name"])
		else:
			return {"status": "error", "message": f"No Universal Registration found with phone '{phone}'."}
			
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Universal Registration by Phone Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def search_universal_registration(search_text):
	"""
	Search Universal Registration documents by name, email, or phone.
	"""
	try:
		documents = frappe.get_list(
			"Universal Registration__",
			filters=[
				["name", "like", f"%{search_text}%"],
				"or",
				["full_name_u_r", "like", f"%{search_text}%"],
				"or",
				["email_address_u_r", "like", f"%{search_text}%"],
				"or",
				["mobile_number_u_r", "like", f"%{search_text}%"],
				"or",
				["org_name_u_r", "like", f"%{search_text}%"]
			],
			fields=["name", "profile_type_u_r", "full_name_u_r", "email_address_u_r", "mobile_number_u_r", "org_name_u_r"],
			limit=50
		)
		
		return {
			"status": "success",
			"data": documents,
			"count": len(documents)
		}
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Search Universal Registration Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_universal_registration_by_profile_type(profile_type):
	"""
	Fetch all registrations of a specific profile type (Individual or Organization).
	"""
	try:
		documents = frappe.get_list(
			"Universal Registration__",
			filters={"profile_type_u_r": profile_type},
			fields=["name", "profile_type_u_r", "full_name_u_r", "org_name_u_r", "email_address_u_r", "mobile_number_u_r", "modified"],
			order_by="modified desc",
			limit=100
		)
		
		return {
			"status": "success",
			"profile_type": profile_type,
			"count": len(documents),
			"data": documents
		}
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Registration by Profile Type Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_project_staff_details_count(filters=None):
    """
    Returns the total number of entries in the "Project Staff Details" doctype.
    Guest-accessible (no API token required) since it only reads a count.
    """
    if filters and isinstance(filters, str):
        filters = frappe.parse_json(filters)

    count = frappe.db.count("Project Staff Details", filters=filters or None)
    return {"doctype": "Project Staff Details", "count": count}


@frappe.whitelist(allow_guest=True)
def upload_file():
	"""
	Custom upload file endpoint for universal registration.
	Allows guest uploads without requiring API key/secret or session login.
	Uploads directly to MinIO object storage according to MINIO file structure rules.
	"""
	from rndopsapp.minio import get_rnd_file_service
	from rndopsapp.file_handler import get_file_category_for_doctype

	files = frappe.request.files
	if "file" not in files:
		frappe.throw("No file attached", frappe.ValidationError)

	uploaded_file = files["file"]
	content = uploaded_file.stream.read()
	filename = uploaded_file.filename

	is_private = frappe.utils.cint(frappe.form_dict.get("is_private", 0))
	doctype = frappe.form_dict.get("doctype") or frappe.form_dict.get("attached_to_doctype") or "Universal Registration__"
	docname = frappe.form_dict.get("docname") or frappe.form_dict.get("attached_to_name") or "temp_uploads"
	fieldname = frappe.form_dict.get("fieldname") or frappe.form_dict.get("attached_to_field")
	folder = (
		frappe.form_dict.get("folder")
		or frappe.form_dict.get("category")
		or frappe.form_dict.get("document_type")
		or (get_file_category_for_doctype(doctype, fieldname) if fieldname else "documents")
	)

	file_service = get_rnd_file_service()
	upload_result = file_service.save_file(
		filename=filename,
		content=content,
		is_private=bool(is_private),
		doctype=doctype,
		docname=docname,
		folder=folder,
		use_hash=True,
	)

	if not upload_result.get("status"):
		frappe.throw(f"MinIO Upload failed: {upload_result.get('message')}")

	file_url = upload_result.get("data", {}).get("file_url")
	file_doc_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_doc_name:
		frappe.throw(f"File record not found for URL: {file_url}")
	file_doc = frappe.get_doc("File", str(file_doc_name))

	if doctype or docname or fieldname:
		updates = {}
		if doctype: updates["attached_to_doctype"] = doctype
		if docname: updates["attached_to_name"] = docname
		if fieldname: updates["attached_to_field"] = fieldname
		frappe.db.set_value("File", file_doc.name, updates)
		frappe.db.commit()
		file_doc.update(updates)

	return file_doc.as_dict()


@frappe.whitelist(allow_guest=True)
def migrate_universal_registration_local_files():
	"""
	Migrates all local disk files attached to Universal Registration or orphaned identity documents
	to MinIO object storage.
	"""
	from rndopsapp.file_handler import migrate_local_file_to_minio

	files = frappe.get_all(
		"File",
		filters={"file_url": ["like", "/files/%"]},
		fields=["name", "file_name", "file_url", "attached_to_doctype", "attached_to_name", "attached_to_field"]
	)

	migrated = []
	failed = []

	for f in files:
		file_url = f.get("file_url")
		doctype = f.get("attached_to_doctype") or "Universal Registration__"
		docname = f.get("attached_to_name") or "temp_uploads"
		fieldname = f.get("attached_to_field") or "attachment"

		res = migrate_local_file_to_minio(file_url, doctype, docname, fieldname)
		if res.get("status"):
			migrated.append({"old_url": file_url, "new_url": res.get("file_url")})
		else:
			failed.append({"file_url": file_url, "error": res.get("message")})

	frappe.db.commit()
	return {"migrated_count": len(migrated), "failed_count": len(failed), "migrated": migrated, "failed": failed}


@frappe.whitelist(allow_guest=True)
def get_minio_file(file_url=None, file_path=None, download=False, **kwargs):
	"""
	Stream a MinIO file directly to the client browser by file_url or file_path.
	Supports both inline viewing (PDFs, images) and downloads.
	Allows guest access for universal registration documents.
	"""
	import mimetypes
	import os
	from rndopsapp.minio import get_rnd_file_service

	path_to_fetch = file_url or file_path or kwargs.get("path") or kwargs.get("url")
	if not path_to_fetch:
		frappe.throw("file_url or file_path parameter is required", frappe.ValidationError)

	path_clean = str(path_to_fetch).lstrip("/")
	is_download = frappe.utils.cint(download) or (1 if str(kwargs.get("download")).lower() in ("true", "1") else 0)

	content = None
	filename = path_clean.rsplit("/", 1)[-1]
	content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

	# If path_clean starts with "files/" or "private/files/", try reading local file fallback
	if path_clean.startswith("files/") or path_clean.startswith("private/files/"):
		site_path = frappe.get_site_path()
		local_filepath = os.path.join(site_path, path_clean)
		if os.path.exists(local_filepath):
			with open(local_filepath, "rb") as f:
				content = f.read()
	else:
		svc = get_rnd_file_service()
		result = svc.get_file(path_clean)
		if not result.get("status"):
			err_msg = str(result.get("message") or f"File not found in MinIO for path '{path_clean}'")
			frappe.throw(err_msg, frappe.DoesNotExistError)
		content = result["data"]["content"]

	frappe.response["filename"] = filename
	frappe.response["filecontent"] = content
	frappe.response["content_type"] = content_type
	# Always use "download" type — Frappe's as_raw() respects content_type
	# and supports display_content_as. The "binary" type hardcodes
	# application/octet-stream + Content-Disposition: attachment.
	frappe.response["type"] = "download"

	if is_download:
		frappe.response["display_content_as"] = "attachment"
	else:
		frappe.response["display_content_as"] = "inline"
