# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class UtilityAssignment(Document):
	pass


# import frappe


@frappe.whitelist()
def get_all_available_utilities():
	"""
	Returns a list of all possible utilities that can be assigned.
	In a real system, these might come from a separate DocType (e.g., 'Utility Master')
	or be hardcoded initially.
	"""
	# This list should match the full list of utilities from your screenshots
	utilities = [
		{"utility_name": "Add Local Supplier", "utility_key": "add_local_supplier"},
		{"utility_name": "Add New User", "utility_key": "add_new_user"},
		{"utility_name": "Add Principal and Local Supplier", "utility_key": "add_principal_local_supplier"},
		{"utility_name": "Adhoc", "utility_key": "adhoc"},
		{"utility_name": "Application History", "utility_key": "application_history"},
		{"utility_name": "Apply Leave", "utility_key": "apply_leave"},
		{"utility_name": "Assign Utilities", "utility_key": "assign_utilities"},
		{"utility_name": "Attendance Report History", "utility_key": "attendance_report_history"},
		{"utility_name": "Bill Generation", "utility_key": "bill_generation"},
		{"utility_name": "Calculate Salary", "utility_key": "calculate_salary"},
		{"utility_name": "Committee Member Change Request", "utility_key": "committee_member_change_request"},
		{"utility_name": "Compliance to NIQ terms", "utility_key": "compliance_niq_terms"},
		{"utility_name": "Contractual", "utility_key": "contractual"},
		{"utility_name": "Departure", "utility_key": "departure"},
		{"utility_name": "Direct purchase upto 10 Lakhs", "utility_key": "direct_purchase_10l"},
		{"utility_name": "Disbursal of Consultancy", "utility_key": "disbursal_consultancy"},
		{"utility_name": "Disbursement of Honorarium", "utility_key": "disbursement_honorarium"},
		{"utility_name": "Edit Purchase Order Number", "utility_key": "edit_purchase_order_number"},
		{"utility_name": "Export Report", "utility_key": "export_report"},
		{"utility_name": "Extension of Tenure", "utility_key": "extension_of_tenure"},
		{"utility_name": "Form Tracking", "utility_key": "form_tracking"},
		{"utility_name": "Fresh Proposal Submission", "utility_key": "fresh_proposal_submission"},
		{"utility_name": "General Indent", "utility_key": "general_indent"},
		{"utility_name": "Generate Database Dump", "utility_key": "generate_database_dump"},
		{"utility_name": "Generate NIQ", "utility_key": "generate_niq"},
		{"utility_name": "Generate Report", "utility_key": "generate_report"},
		{"utility_name": "IPR Search", "utility_key": "ipr_search"},
		{"utility_name": "IPR", "utility_key": "ipr"},
		{"utility_name": "Incharge Assignment", "utility_key": "incharge_assignment"},
		{"utility_name": "Indent cum Sanction Sheet", "utility_key": "indent_cum_sanction_sheet"},
		{"utility_name": "Inspection Report", "utility_key": "inspection_report"},
		{"utility_name": "Legal Vetting", "utility_key": "legal_vetting"},
		{"utility_name": "Manage Funding Agencies", "utility_key": "manage_funding_agencies"},
		{"utility_name": "Mark Attendance", "utility_key": "mark_attendance"},
		{"utility_name": "My Project", "utility_key": "my_project"},
		{"utility_name": "NOC Generation", "utility_key": "noc_generation"},
		{"utility_name": "No Objection Certificate", "utility_key": "no_objection_certificate"},
		# {"utility_name": "One Time Assistantship", "utility_key": "one_time_assistantship"},
		{"utility_name": "Pending Form Status", "utility_key": "pending_form_status"},
		{"utility_name": "Pending TA", "utility_key": "pending_ta"},
		{"utility_name": "Profile", "utility_key": "profile"},
		{"utility_name": "Project Registration", "utility_key": "project_registration"},
		{"utility_name": "Project Search", "utility_key": "project_search"},
		{"utility_name": "Project Staff Joining", "utility_key": "project_staff_joining"},
		{"utility_name": "Project Staff Salary Deduction", "utility_key": "project_staff_salary_deduction"},
		{"utility_name": "Project Staff", "utility_key": "project_staff"},
		{"utility_name": "R&D Staff Performance Ranking", "utility_key": "rnd_staff_performance_ranking"},
		{"utility_name": "R&D Staff Reallocation", "utility_key": "rnd_staff_reallocation"},
		{"utility_name": "Rate Contract", "utility_key": "rate_contract"},
		{"utility_name": "Reimbursement", "utility_key": "reimbursement"},
		{"utility_name": "Rejoining", "utility_key": "rejoining"},
		{"utility_name": "Reports", "utility_key": "reports"},
		{"utility_name": "Resignation", "utility_key": "resignation"},
		{"utility_name": "Revised Proposal Submission", "utility_key": "revised_proposal_submission"},
		{"utility_name": "Salary Slip", "utility_key": "salary_slip"},
		{"utility_name": "Selection Committee Report", "utility_key": "selection_committee_report"},
		{"utility_name": "Start-Up Grant Proposal", "utility_key": "startup_grant_proposal"},
		{"utility_name": "Sug Send Mail", "utility_key": "sug_send_mail"},
		{"utility_name": "TA-DA Settle", "utility_key": "tada_settle"},
		{"utility_name": "Temporary Advance Apply", "utility_key": "temporary_advance_apply"},
		{"utility_name": "Temporary Advance Settle", "utility_key": "temporary_advance_settle"},
		{"utility_name": "Top Up Fellowship", "utility_key": "top_up_fellowship"},
		{"utility_name": "Update Status", "utility_key": "update_status"},
		{"utility_name": "Update project Fund", "utility_key": "update_project_fund"},
		{"utility_name": "Upload No-Dues", "utility_key": "upload_no_dues"},
		{
			"utility_name": "Uploads(Director/Medical/Agreement)",
			"utility_key": "uploads_director_medical_agreement",
		},
		{"utility_name": "View ID Card", "utility_key": "view_id_card"},
		{
			"utility_name": "View Interview Candidate Details",
			"utility_key": "view_interview_candidate_details",
		},
	]
	return utilities


@frappe.whitelist()
def get_user_assignments(user):
	"""
	Fetches the current utility assignments for a given user.
	"""
	# This is a placeholder. You'd query your database or a custom link table
	# to find what utilities are currently assigned to this user.
	# For now, let's return some dummy data, pre-assigning 'Application History'
	# and 'Apply Leave' for demonstration.
	all_utilities = get_all_available_utilities()
	assignments = []
	for util in all_utilities:
		is_assigned = 0
		if util["utility_name"] in ["Application History", "Apply Leave"]:  # Example pre-assignments
			is_assigned = 1
		assignments.append({"utility_name": util["utility_name"], "is_assigned": is_assigned})
	return assignments


@frappe.whitelist()
def get_role_assignments(role):
	"""
	Fetches the current utility assignments for a given role.
	"""
	# Similar to get_user_assignments, but for roles.
	all_utilities = get_all_available_utilities()
	assignments = []
	for util in all_utilities:
		is_assigned = 0
		if util["utility_name"] == "Assign Utilities" and role == "System Manager":  # Example
			is_assigned = 1
		assignments.append({"utility_name": util["utility_name"], "is_assigned": is_assigned})
	return assignments


@frappe.whitelist()
def update_assignments(doc_name):
	"""
	Processes the assignments from the Utility Assignment DocType and applies them.
	This is where you'd implement the actual logic to:
	1. Determine the assignment type (user, role, or employee class).
	2. Iterate through the child table 'utilities'.
	3. For each assigned utility, you might:
	   a. Add a new 'User Permission' entry in Frappe for the specific user/role and utility.
	   b. Store this assignment in a custom linking table (e.g., `UserUtilityLink` DocType).
	   c. Modify existing permissions or roles based on the selected checkboxes.
	"""
	doc = frappe.get_doc("Utility Assignment", doc_name)

	if doc.assignment_type == "Employee ID based":
		target_entity = doc.user
		entity_type = "User"
	elif doc.assignment_type == "Profile based":
		target_entity = doc.role_profile
		entity_type = "Role"
	elif doc.assignment_type == "Employee Class based":
		target_entity = doc.employee_class
		entity_type = "Employee Class"
	else:
		frappe.throw("Invalid Assignment Type")

	frappe.msgprint(f"Updating assignments for {entity_type}: <b>{target_entity}</b>")

	# Example: print assigned utilities
	assigned_count = 0
	for item in doc.utilities:
		if item.is_assigned:
			assigned_count += 1
			frappe.msgprint(f"  - Assigned: {item.utility_name}")
			# --- IMPORTANT: IMPLEMENT YOUR ACTUAL PERMISSION/ROLE UPDATE LOGIC HERE ---
			# This is highly dependent on how your "utilities" map to Frappe permissions.
			# You might update User Permissions, Role Permissions, or a custom mechanism.
			# Example (conceptual, requires careful mapping):
			# if entity_type == "User":
			#     # Add User Permission for this utility (e.g., grant access to a specific document or report)
			#     frappe.get_doc({
			#         "doctype": "User Permission",
			#         "user": target_entity,
			#         "allow": "Your Doctype related to " + item.utility_name, # Map utility to a DocType
			#         "for_value": "all", # Or a specific value if applicable
			#     }).insert(ignore_permissions=True, ignore_if_duplicate=True)
			# elif entity_type == "Role":
			#     # Potentially update Role Permissions (more complex, usually done via Role Permission Manager)
			#     # Or add a custom link indicating this role has this utility
			#     pass

	frappe.msgprint(f"Successfully processed {assigned_count} assigned utilities.")
	return f"Assignments for {target_entity} updated successfully."
