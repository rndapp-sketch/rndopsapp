# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

# Copyright (c) 2026, Your Organization and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import money_in_words

@frappe.whitelist()
def get_amount_in_words(amount, currency=None):
    """Convert amount to words"""
    if not amount:
        return ""
    
    try:
        amount = float(amount)
        return money_in_words(amount, currency)
    except Exception as e:
        frappe.log_error(f"Error converting amount to words: {str(e)}")
        return ""


def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	"""
	if not expression:
		return None

	expression = str(expression).strip()

	if expression.startswith("eval:"):
		return expression[5:].strip()

	return expression


class TemporaryAdvance(Document):

	def validate(self):
		"""Validate and set dynamic fields"""
		self.resolve_project_code()
		self.set_applicant_details()
		self.set_pi_mentor_details()

	def resolve_project_code(self):
		"""Resolve project_code to the actual project_no from Project Registration.

		When the frontend sends the Project Registration document name
		(e.g. '2026021801MeiTy000473') as project_code/project_name,
		look up the real project_no and store that instead.
		"""
		project_ref = self.project_name or self.project_code
		if not project_ref:
			return

		# Check if the value is a Project Registration document name
		if frappe.db.exists("Project Registration", project_ref):
			project_no = frappe.db.get_value(
				"Project Registration", project_ref, "project_no"
			)
			if project_no:
				self.project_code = project_no

	def set_applicant_details(self):
		"""Set applicant details based on whether applying for someone else"""
		if self.applying_for_select == "Yes" and self.advance_for_id:
			# Get details from the person being applied for
			user_details = frappe.db.get_value(
				"User",
				self.advance_for_id,
				["empclass", "department_name", "designation_name", "piheadmentor_user_id"],
				as_dict=True
			)

			if user_details:
				self.other_applicant_category = user_details.empclass
				self.advance_for_department = user_details.department_name
				self.advance_for_designation = user_details.designation_name

				if user_details.piheadmentor_user_id:
					self.pi_mentor_user = user_details.piheadmentor_user_id

		elif self.applicant_webmail:
			# Get details from the applicant themselves
			user_details = frappe.db.get_value(
				"User",
				self.applicant_webmail,
				["empclass", "department_name", "designation_name", "piheadmentor_user_id"],
				as_dict=True
			)

			if user_details:
				self.applicant_category = user_details.empclass
				self.applicant_department = user_details.department_name
				self.applicant_designation = user_details.designation_name

				if user_details.piheadmentor_user_id:
					self.pi_mentor_user = user_details.piheadmentor_user_id

	def set_pi_mentor_details(self):
		"""Fetch and store PI/Mentor details dynamically"""
		# This is already handled in set_applicant_details
		pass

	def on_update(self):
		"""Set permissions dynamically based on workflow state"""
		self.set_dynamic_permissions()

	def set_dynamic_permissions(self):
		"""Grant permissions to specific users based on workflow state"""
		try:
			# Clear existing shares for this document (except system shares)
			existing_shares = frappe.get_all(
				"DocShare",
				filters={
					"share_doctype": self.doctype,
					"share_name": self.name
				},
				pluck="name"
			)

			for share in existing_shares:
				frappe.delete_doc("DocShare", share, ignore_permissions=True)

			# Share with creator (read-only after submission in most states)
			if self.owner:
				write_access = 1 if self.workflow_state == "Draft" else 0
				frappe.share.add(
					self.doctype,
					self.name,
					self.owner,
					write=write_access,
					submit=1,
					share=1,
					notify=0
				)

			# If applying for someone, share with that person WITH EDIT ACCESS during acknowledgment
			if self.applying_for_select == "Yes" and self.advance_for_id:
				if self.workflow_state == "Pending Applicant Acknowledgment":
					frappe.share.add(
						self.doctype,
						self.name,
						self.advance_for_id,
						write=1,  # FULL EDIT ACCESS
						submit=1,
						share=1,
						notify=1
					)

					# Send email notification with edit permission
					self.send_acknowledgment_notification()

			# Share with PI/Mentor when in their approval state
			if self.pi_mentor_user:
				if self.workflow_state in ["Pending PI Approval", "Pending Mentor Approval"]:
					frappe.share.add(
						self.doctype,
						self.name,
						self.pi_mentor_user,
						write=1,
						submit=1,
						share=1,
						notify=1
					)

			frappe.db.commit()

		except Exception as e:
			frappe.log_error(f"Error in set_dynamic_permissions: {str(e)}", "Temporary Advance Permissions")

	def send_acknowledgment_notification(self):
		"""Send email notification to the person for whom form is being filled"""
		try:
			user_email = frappe.db.get_value("User", self.advance_for_id, "email")
			if user_email:
				frappe.sendmail(
					recipients=[user_email],
					subject=f"Action Required: Temporary Advance Application - {self.name}",
					message=f"""
					<p>Dear {frappe.db.get_value("User", self.advance_for_id, "full_name")},</p>
					
					<p>A Temporary Advance application has been created on your behalf by {frappe.db.get_value("User", self.owner, "full_name")}.</p>
					
					<p><strong>Application Details:</strong></p>
					<ul>
						<li>Application ID: {self.name}</li>
						<li>Amount: ₹{self.amount}</li>
						<li>Project: {self.project_name or 'N/A'}</li>
					</ul>
					
					<p><strong>Required Action:</strong></p>
					<p>Please review and update (if needed) the application details, then acknowledge to proceed with the approval workflow.</p>
					
					<p><strong>You can:</strong></p>
					<ul>
						<li>Edit any details in the form</li>
						<li>Click "Acknowledge" to proceed</li>
						<li>Click "Reject" to decline this application</li>
					</ul>
					
					<p><a href="{frappe.utils.get_url()}/app/temporary-advance/{self.name}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">View Application</a></p>
					
					<p>Regards,<br>RnD System</p>
					""",
					reference_doctype=self.doctype,
					reference_name=self.name
				)
		except Exception as e:
			frappe.log_error(f"Error sending acknowledgment notification: {str(e)}", "Temporary Advance Notification")


# =============================================================================
# PERMISSION CONTROLLER
# =============================================================================

def has_permission(doc, ptype, user):
	"""Custom permission check"""
	if not doc:
		return True

	user = user or frappe.session.user

	# Administrator has all permissions
	if user == "Administrator":
		return True

	# Creator has permission
	if doc.owner == user:
		return True

	# Person being applied for has FULL EDIT PERMISSION in acknowledgment state
	if doc.applying_for_select == "Yes" and doc.advance_for_id == user:
		if doc.workflow_state == "Pending Applicant Acknowledgment":
			# Full read and write permission
			if ptype in ["read", "write", "submit"]:
				return True

	# PI/Mentor has permission in their approval state
	pi_mentor = doc.get('pi_mentor_user')
	if pi_mentor == user:
		if doc.workflow_state in ["Pending PI Approval", "Pending Mentor Approval"]:
			return True

	# Check if user has role-based permission
	user_roles = frappe.get_roles(user)

	if doc.workflow_state == "Pending Staff Approval" and "staff, RnD" in user_roles:
		return True

	if doc.workflow_state == "Pending HoS Approval" and "Hos, RnD (Head of Section, RnD)" in user_roles:
		return True

	if doc.workflow_state == "Pending Associate Dean" and "Ado_RnD" in user_roles:
		return True

	if doc.workflow_state == "Pending Dean Approval" and "Dean, RnD" in user_roles:
		return True

	return False


# =============================================================================
# API ENDPOINTS
# =============================================================================

@frappe.whitelist()
def get_temporary_advance_fields(project_code=None):
	"""
	API to return Temporary Advance field metadata and prefill data
	based on a Project Registration ref number (project_code).
	"""
	temporary_advance_meta = frappe.get_meta("Temporary Advance")

	fields = []
	for f in temporary_advance_meta.get("fields"):
		fields.append({
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
		})

	prefill_data = {}
	link_options = {}
	related_project_data = {}

	# Pre-fill current user details from User doctype
	user = frappe.session.user
	if user and user != "Guest":
		try:
			user_doc = frappe.get_doc("User", user)

			# Applicant details from User doctype
			prefill_data["applicant_webmail"] = user_doc.email
			prefill_data["applicant_department"] = user_doc.department_name  # Link to Department_prornd
			prefill_data["applicant_designation"] = user_doc.designation_name

			# Also try to get bank details if available (from User Bank doctype)
			try:
				user_bank = frappe.get_all(
					"User Bank",
					filters={"user": user},
					fields=["bank_name", "account_number", "ifsc_code", "account_holder_name"],
					limit_page_length=1,
				)
				if user_bank:
					prefill_data["bank_name"] = user_bank[0].get("bank_name")
					prefill_data["bank_account_number"] = user_bank[0].get("account_number")
					prefill_data["ifsc_code"] = user_bank[0].get("ifsc_code")
					prefill_data["account"] = user_bank[0].get("account_holder_name")
			except Exception:
				pass
		except Exception:
			pass

	# If project_code is provided, fetch project details
	if project_code:
		project_code = str(project_code).strip('"').strip("'")

		project_doc = frappe.db.get_value(
			"Project Registration",
			project_code,
			["name", "project_title", "project_type"],
			as_dict=True
		)

		if project_doc:
			related_project_data = project_doc
			prefill_data["project_code"] = project_doc.name
			prefill_data["project_name"] = project_doc.project_title

	# ===== Link options for dropdowns =====

	# Project Registration options (for project_code and project_name)
	try:
		projects = frappe.get_all(
			"Project Registration",
			fields=["name as value", "project_title as label"],
			limit_page_length=500
		)
		link_options["project_code"] = projects
		link_options["project_name"] = projects
	except Exception:
		link_options["project_code"] = []
		link_options["project_name"] = []

	# Users list (for webmail fields - advance_for_id and applicant_webmail)
	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=500,
		)
		link_options["advance_for_id"] = users
		link_options["applicant_webmail"] = users
	except Exception:
		link_options["advance_for_id"] = []
		link_options["applicant_webmail"] = []

	# Department options (for advance_for_department and applicant_department)
	try:
		departments = frappe.get_all(
			"Department_prornd",
			fields=["name as value", "dept_name as label"],
			limit_page_length=500,
		)
		link_options["advance_for_department"] = departments
		link_options["applicant_department"] = departments
	except Exception:
		link_options["advance_for_department"] = []
		link_options["applicant_department"] = []

	# Designation options (from Designation_prornd doctype)
	try:
		designations = frappe.get_all(
			"Designation_prornd",
			fields=["name as value", "designation_name as label"],
			limit_page_length=500,
		)
		link_options["advance_for_designation"] = designations
		link_options["applicant_designation"] = designations
	except Exception:
		# Fallback: Get unique designations from User records
		try:
			designations_raw = frappe.get_all(
				"User",
				filters={"enabled": 1},
				fields=["designation_name"],
				limit_page_length=1000,
			)
			unique_designations = list(set(
				d.get("designation_name") for d in designations_raw
				if d.get("designation_name")
			))
			designations = [{"value": d, "label": d} for d in sorted(unique_designations)]
			link_options["advance_for_designation"] = designations
			link_options["applicant_designation"] = designations
		except Exception:
			link_options["advance_for_designation"] = []
			link_options["applicant_designation"] = []

	# Account Head (Budget Head) options
	try:
		account_heads = frappe.get_all(
			"Budget Head",
			fields=["name as value", "budget_head as label"],
			limit_page_length=500,
		)
		# If budget_head is empty, use name as label
		link_options["account_head"] = [
			{"value": r["value"], "label": r.get("label") or r["value"]} for r in account_heads
		]
	except Exception:
		link_options["account_head"] = []

	# Fetch Client Scripts from Frappe (stored in database)
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": "Temporary Advance", "enabled": 1},
			fields=["name", "script", "view"]
		)
		for script in scripts:
			client_scripts.append({
				"name": script.name,
				"script": script.script,
				"view": script.view
			})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_project_data": related_project_data,
		"client_scripts": client_scripts,
	}


@frappe.whitelist()
def get_user_details(user_email):
	"""
	Fetches details for a specific user to populate advance form fields.
	Returns the user document with resolved department name and employee class.
	"""
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
def save_temporary_advance(doc_data):
	"""
	Saves the Temporary Advance data from the form.
	"""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Temporary Advance:", data)  # Debug log

		# Determine if updating existing or creating new
		doc_name = data.pop("name", None)

		if doc_name:
			# Update existing document
			doc = frappe.get_doc("Temporary Advance", doc_name)
			doc.update(data)
		else:
			# Create new document
			doc = frappe.new_doc("Temporary Advance")

			# Field mapping
			field_mapping = [
				"applying_for_select",
				"advance_for_id",
				"advance_for_department",
				"advance_for_designation",
				"other_applicant_category",
				"applicant_webmail",
				"applicant_department",
				"applicant_designation",
				"applicant_category",
				"bank_name",
				"account",
				"bank_account_number",
				"ifsc_code",
				"project_code",
				"project_name",
				"account_head",
				"amount",
				"justification",
				"documents",
				"comments",
			]

			# Update document with mapped data
			for field in field_mapping:
				if field in data and data[field] not in [None, ""]:
					doc.set(field, data[field])

		# Disable strict validation for flexibility
		doc.flags.ignore_validate = False  # Keep validation active for workflow
		doc.flags.ignore_mandatory = False
		doc.flags.ignore_links = False

		# Save the document
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved Temporary Advance: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Temporary Advance Save Error")
		frappe.throw(f"Failed to save Temporary Advance: {str(e)}")


@frappe.whitelist()
def get_temporary_advance_by_project(project_code: str = "", limit: int = 200, start: int = 0):
	"""
	Returns Temporary Advance docs for a given project_code.
	"""
	from frappe.utils import cint

	limit = int(cint(limit) or 200)
	start = int(cint(start) or 0)
	project_code = (project_code or "").strip()

	if not project_code:
		return {"message": []}

	results = []
	try:
		names = frappe.get_all(
			"Temporary Advance",
			filters={"project_code": project_code},
			fields=["name"],
			limit_start=start,
			limit_page_length=limit,
			order_by="modified desc",
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_temporary_advance_by_project: failed to query")
		return {"message": []}

	if not names:
		return {"message": []}

	for row in names:
		name = row.get("name")
		try:
			doc = frappe.get_doc("Temporary Advance", name)
			doc_dict = doc.as_dict()
			results.append(doc_dict)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"get_temporary_advance_by_project: error loading {name}")
			continue

	return {"message": results}


@frappe.whitelist()
def get_temporary_advance_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Temporary Advance", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype dynamically
	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": "Temporary Advance", "is_active": 1},
		"name"
	)

	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue

		# Check roles on the transition
		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]

		# User can perform action if they have allowed role
		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			# Check condition if exists
			if transition.condition:
				try:
					# Safe eval the condition with doc context
					if not frappe.safe_eval(transition.condition, None, {"doc": doc}):
						continue
				except Exception:
					continue

			allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def perform_temporary_advance_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Temporary Advance", docname)
		current_state = doc.workflow_state or "Draft"
		user_roles = frappe.get_roles(frappe.session.user)

		# Fetch the workflow for this doctype dynamically
		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": "Temporary Advance", "is_active": 1},
			"name"
		)

		if not workflow_name:
			frappe.throw("No active workflow found for Temporary Advance.")

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		transition = None

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				# Check roles
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]

				if not (any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles):
					continue

				# Check condition
				if t.condition:
					try:
						if not frappe.safe_eval(t.condition, None, {"doc": doc}):
							continue
					except Exception as e:
						frappe.log_error(f"Workflow condition error: {str(e)}", "Workflow Error")
						continue

				# Found a valid transition
				next_state = t.next_state
				transition = t
				break

		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}' matching your role and conditions.")

		# Update workflow state
		doc.workflow_state = next_state

		# Check if next state requires submission (docstatus=1)
		state_doc = next((s for s in workflow.states if s.state == next_state), None)

		if state_doc and state_doc.doc_status == "1" and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == "2" and doc.docstatus != 2:
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_temporary_advance_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Temporary Advance Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_temporary_advance(docname):
	"""
	Submit a Temporary Advance document using Workflow transitions.
	"""
	return perform_temporary_advance_action(docname, "Submit")