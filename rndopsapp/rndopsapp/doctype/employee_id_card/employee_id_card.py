# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import base64
import json
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document


# =============================================================================
# DOCUMENT CONTROLLER
# =============================================================================


class EmployeeIDCard(Document):
	def validate(self):
		self._set_user_info()
		self._validate_phone()
		self._validate_dates()
		self._validate_spouse()

	def _set_user_info(self):
		if not self.get("email__"):
			self.set("email__", frappe.session.user)

	def _validate_phone(self):
		phone = self.get("phone__")
		if phone:
			phone_str = str(phone).strip()
			if not phone_str.isdigit() or len(phone_str) != 10:
				frappe.throw(
					_("Phone number must be exactly 10 digits."),
					title=_("Invalid Phone Number"),
				)

		emergency_phone = self.get("emergency_phone__")
		if emergency_phone:
			emer = str(emergency_phone).strip()
			if not emer.isdigit() or len(emer) > 12:
				frappe.throw(
					_("Emergency phone must be at most 12 digits."),
					title=_("Invalid Emergency Phone"),
				)

	def _validate_dates(self):
		issue_date = self.get("issue_date__")
		valid_upto = self.get("valid_upto__")
		if issue_date and valid_upto:
			if str(valid_upto) < str(issue_date):
				frappe.throw(
					_("'Valid Upto' cannot be before 'Issue Date'."),
					title=_("Invalid Date Range"),
				)

	def _validate_spouse(self):
		if self.get("marital_status__") == "Married" and not self.get("spouse_name__"):
			frappe.throw(
				_("Spouse Name is required when Marital Status is Married."),
				title=_("Missing Spouse Name"),
			)


# =============================================================================
# HELPERS
# =============================================================================


def extract_eval_expression(expression):
	if not expression:
		return None
	expression = str(expression).strip()
	if expression.startswith("eval:"):
		return expression[5:].strip()
	return expression


def _find_matching_transition(workflow, current_state, action):
	"""Find the first workflow transition that matches state, action, and role."""
	user_roles = frappe.get_roles(frappe.session.user)

	transitions = workflow.get("transitions") or []
	for t in transitions:
		t_state = t.get("state") if hasattr(t, "get") else getattr(t, "state", None)
		t_action = t.get("action") if hasattr(t, "get") else getattr(t, "action", None)
		t_allowed = t.get("allowed") if hasattr(t, "get") else getattr(t, "allowed", None)

		if t_state != current_state or t_action != action:
			continue

		# Check role
		if t_allowed and t_allowed not in user_roles and "System Manager" not in user_roles:
			continue

		return t

	return None


def _upload_file_to_storage(file_data, doctype, docname, category):
	"""
	Upload a base64-encoded file (dict or data URI string) to MinIO or standard Frappe File storage.
	Returns the file URL string or None on failure.
	"""
	if not file_data:
		return None

	filename = f"{category}.png"
	raw_data = None

	if isinstance(file_data, dict):
		filename = file_data.get("file_name") or f"{category}.png"
		raw_data = file_data.get("file_data")
	elif isinstance(file_data, str):
		if file_data.startswith("data:"):
			raw_data = file_data
			if "jpeg" in file_data or "jpg" in file_data:
				filename = f"{category}.jpg"
			else:
				filename = f"{category}.png"
		elif file_data.startswith("/") or file_data.startswith("http"):
			# Already a valid URL path
			return file_data

	if not raw_data:
		return None

	try:
		# Strip data URI prefix if present
		if isinstance(raw_data, str) and "," in raw_data:
			raw_data = raw_data.split(",", 1)[1]

		content = base64.b64decode(raw_data)

		# 1. Try MinIO upload
		try:
			from rndopsapp.minio import get_rnd_file_service

			svc = get_rnd_file_service()
			result = svc.save_file(
				filename=filename,
				content=content,
				is_private=False,
				doctype=doctype,
				docname=docname,
				folder=category,
			)

			if result.get("status"):
				return result["data"]["file_url"]
		except Exception as minio_err:
			frappe.log_error(
				f"MinIO upload error for {category}/{filename}, falling back to Frappe File: {str(minio_err)}",
				"Employee ID Card File Upload",
			)

		# 2. Fallback: Save as standard Frappe File
		file_doc = frappe.get_doc({
			"doctype": "File",
			"file_name": f"{docname}_{category}_{filename}",
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
			"content": content,
			"is_private": 0,
		})
		file_doc.insert(ignore_permissions=True)
		return file_doc.get("file_url")

	except Exception as e:
		frappe.log_error(
			f"File upload error for {category}/{filename}: {str(e)}",
			"Employee ID Card File Upload",
		)
		return None


# =============================================================================
# WHITELISTED API METHODS
# =============================================================================

DOCTYPE = "Employee ID Card"

SIMPLE_FIELDS = [
	"emp_id__",
	"project_number__",
	"full_name__",
	"dob__",
	"blood_group__",
	"phone__",
	"emergency_phone__",
	"marital_status__",
	"spouse_name__",
	"designation__",
	"department_name__",
	"valid_upto__",
	"issue_date__",
	"present_address__",
	"permanent_address__",
]

FILE_FIELDS = {
	"photo_path__": "photo",
	"sign_path__": "signature",
}


def get_latest_hr_comment(docname):
	"""Retrieve the latest HR return comment for an Employee ID Card document (only if in Draft / Put Back state)."""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		state = doc.get("workflow_state") or "Draft"
		if state != "Draft":
			return None

		comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": DOCTYPE,
				"reference_name": docname,
			},
			fields=["content", "comment_type"],
			order_by="creation desc",
			limit=10,
		)
		for comment in comments:
			content = comment.get("content") or ""
			if "HR Return Reason:" in content:
				return content.split("HR Return Reason:", 1)[1].strip()
			elif "Returned to user:" in content:
				return content.split("Returned to user:", 1)[1].strip()
			elif comment.get("comment_type") == "Comment" and content.strip():
				return content.strip()
	except Exception:
		pass
	return None


@frappe.whitelist()
def get_employee_id_card_fields(doc_name=None):
	"""Return field metadata, prefill data, and link options."""
	meta = frappe.get_meta(DOCTYPE)

	fields = []
	for f in meta.get("fields"):
		field_data = {
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"default": f.default,
			"description": f.description,
			"depends_on": f.depends_on,
			"depends_on_eval": extract_eval_expression(f.depends_on),
		}
		fields.append(field_data)

	prefill_data = {}

	if doc_name:
		try:
			doc = frappe.get_doc(DOCTYPE, doc_name)
			prefill_data = doc.as_dict()
			comment = get_latest_hr_comment(doc_name)
			if comment:
				prefill_data["remarks"] = comment
				prefill_data["hr_comments"] = comment
		except Exception:
			pass
	else:
		user = frappe.session.user
		if user and user not in ("Guest", "Administrator"):
			prefill_data["email__"] = user
			try:
				user_doc = frappe.get_doc("User", user)
				prefill_data["username__"] = user_doc.get("username") or user_doc.get("full_name")
			except Exception:
				pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
	}


@frappe.whitelist()
def save_employee_id_card_data(data):
	"""Save or update an Employee ID Card document (Draft or HR Edit)."""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		is_new = False
		user_roles = frappe.get_roles(frappe.session.user)
		is_hr = "staff, RnD" in user_roles or "System Manager" in user_roles

		if doc_name and frappe.db.exists(DOCTYPE, doc_name):
			doc = frappe.get_doc(DOCTYPE, doc_name)
			if doc.docstatus != 0 and not is_hr:
				frappe.throw(_("Cannot edit a submitted or cancelled ID card."))
		else:
			doc = frappe.new_doc(DOCTYPE)
			is_new = True
			doc.set("workflow_state", "Draft")

		# Collect field updates (only DB schema fields)
		update_fields = {}

		# Set simple fields
		for field in SIMPLE_FIELDS:
			if field in data:
				val = data[field]
				clean_val = val if val != "null" else None
				doc.set(field, clean_val)
				update_fields[field] = clean_val

		if "workflow_state" in data and is_hr:
			doc.set("workflow_state", data["workflow_state"])
			update_fields["workflow_state"] = data["workflow_state"]
			if data["workflow_state"] == "Draft":
				doc.set("docstatus", 0)
				update_fields["docstatus"] = 0

		# Set user fields
		if not doc.get("email__"):
			doc.set("email__", frappe.session.user)

		doc.flags.ignore_permissions = True
		if is_new:
			doc.insert(ignore_mandatory=True)
		elif doc.docstatus == 0:
			doc.save(ignore_permissions=True)
		else:
			frappe.db.set_value(DOCTYPE, doc.name, update_fields, update_modified=True)

		# Store remarks/comments in Frappe Comment system if passed
		hr_comment = data.get("remarks") or data.get("hr_comments")
		if hr_comment and str(hr_comment).strip():
			doc.add_comment("Comment", f"HR Return Reason: {str(hr_comment).strip()}")

		# Handle file uploads (photo and signature) after doc has a name
		file_updates = {}
		for field, category in FILE_FIELDS.items():
			file_val = data.get(field)
			if file_val:
				file_url = _upload_file_to_storage(
					file_val, DOCTYPE, doc.name, category
				)
				if file_url:
					doc.set(field, file_url)
					file_updates[field] = file_url
				elif isinstance(file_val, str) and file_val:
					doc.set(field, file_val)
					file_updates[field] = file_val

		if file_updates:
			if doc.docstatus == 0:
				doc.save(ignore_permissions=True)
			else:
				frappe.db.set_value(DOCTYPE, doc.name, file_updates, update_modified=True)

		frappe.db.commit()

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Employee ID Card Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_employee_id_card(docname):
	"""Submit an Employee ID Card — transitions from Draft to Submitted."""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.get("workflow_state") or "Draft"

		if current_state != "Draft":
			return {
				"status": "info",
				"message": f"ID card '{docname}' is already in state '{current_state}'.",
				"docname": docname,
				"workflow_state": current_state,
			}

		return perform_employee_id_card_action(docname, "Submit")

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Employee ID Card Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_employee_id_card_list(filters=None, limit=100, start=0):
	"""Return list of Employee ID Card documents with basic fields."""
	from frappe.utils import cint

	limit = cint(limit) or 100
	start = cint(start) or 0

	try:
		if filters and isinstance(filters, str):
			filters = json.loads(filters)

		records = frappe.get_all(
			DOCTYPE,
			filters=filters or {},
			fields=[
				"name", "emp_id__", "project_number__", "full_name__",
				"designation__", "department_name__", "workflow_state",
				"creation", "modified", "owner",
				"dob__", "blood_group__", "phone__", "emergency_phone__",
				"marital_status__", "spouse_name__", "valid_upto__",
				"issue_date__", "present_address__", "permanent_address__",
				"photo_path__", "sign_path__",
			],
			limit_start=start,
			limit_page_length=limit,
			order_by="modified desc",
		)

		for rec in records:
			c = get_latest_hr_comment(rec["name"])
			if c:
				rec["remarks"] = c
				rec["hr_comments"] = c

		return {"status": "success", "records": records, "total": len(records)}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Employee ID Card List Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_employee_id_card_workflow_actions(docname):
	"""Return available workflow actions for the current user."""
	doc = frappe.get_doc(DOCTYPE, docname)
	current_state = doc.get("workflow_state") or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": DOCTYPE, "is_active": 1},
		"name",
	)

	if not workflow_name:
		# No workflow configured — return default actions based on state
		actions = []
		if current_state == "Draft":
			actions.append("Submit")
		elif current_state == "Submitted" and (
			"staff, RnD" in user_roles or "System Manager" in user_roles
		):
			actions.append("Verify")
		elif current_state in ("Verified", "HR Verified") and (
			"staff, RnD" in user_roles or "System Manager" in user_roles
		):
			actions.append("Generate ID Card")
		return actions

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue

		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]

		role_match = any(role in user_roles for role in transition_roles) or "System Manager" in user_roles

		if not role_match:
			continue

		if transition.condition:
			try:
				result = frappe.safe_eval(
					transition.condition,
					dict(frappe=frappe._dict(session=frappe.session)),
					dict(doc=doc.as_dict()),
				)
				if not result:
					continue
			except Exception:
				continue

		allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def perform_employee_id_card_action(docname, action, comment=None):
	"""Perform a workflow action on an Employee ID Card."""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.get("workflow_state") or "Draft"

		# Handle Return / Send Back to user (Put Back)
		if action in ("Return", "Send Back"):
			next_state = "Draft"
			update_fields: dict[str, Any] = {
				"workflow_state": "Draft",
				"docstatus": 0,
			}

			frappe.db.set_value(
				DOCTYPE,
				docname,
				update_fields,
				update_modified=True,
			)
			doc.reload()
			if comment and comment.strip():
				doc.add_comment("Comment", f"HR Return Reason: {comment.strip()}")

			frappe.db.commit()

			return {
				"status": "success",
				"message": f"Action '{action}' completed. Request put back to user in Draft state.",
				"docname": docname,
				"workflow_state": "Draft",
				"next_actions": ["Submit"],
			}

		# Check for an active workflow
		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": DOCTYPE, "is_active": 1},
			"name",
		)

		if workflow_name:
			# Use workflow-driven transitions
			workflow = frappe.get_doc("Workflow", workflow_name)
			transition = _find_matching_transition(workflow, current_state, action)

			if not transition:
				frappe.throw(
					_("No valid transition found for action '{0}' from state '{1}'.").format(
						action, current_state
					)
				)

			next_state = transition.get("next_state") if hasattr(transition, "get") else getattr(transition, "next_state", None)
			if not next_state:
				frappe.throw(
					_("No next state defined for action '{0}' from state '{1}'.").format(
						action, current_state
					)
				)

			states = workflow.get("states") or []
			next_state_row = next(
				(s for s in states if (s.get("state") if hasattr(s, "get") else getattr(s, "state", None)) == next_state),
				None,
			)
			new_docstatus = int(next_state_row.get("doc_status") or getattr(next_state_row, "doc_status", 0) or 0) if next_state_row else 0

			workflow_field = workflow.get("workflow_state_field") or getattr(workflow, "workflow_state_field", "workflow_state") or "workflow_state"
			update_fields: dict[str, Any] = {workflow_field: next_state}

			if new_docstatus != int(doc.docstatus):
				update_fields["docstatus"] = new_docstatus

			frappe.db.set_value(
				DOCTYPE,
				docname,
				update_fields,
				update_modified=True,
			)

		else:
			# Fallback: simple state machine (no Workflow doctype configured)
			STATE_MAP = {
				("Draft", "Submit"): ("Submitted", 1),
				("Submitted", "Verify"): ("Verified", 1),
				("HR Verified", "Verify"): ("Verified", 1),
				("Verified", "Verify"): ("Verified", 1),
				("Verified", "Generate ID Card"): ("Generated", 1),
				("HR Verified", "Generate ID Card"): ("Generated", 1),
				("ID Generated", "Generate ID Card"): ("Generated", 1),
				("Generated", "Generate ID Card"): ("Generated", 1),
				("Submitted", "Generate ID Card"): ("Generated", 1),
			}

			key = (current_state, action)
			if key not in STATE_MAP:
				frappe.throw(
					_("No valid transition for action '{0}' from state '{1}'.").format(
						action, current_state
					)
				)

			next_state, new_docstatus = STATE_MAP[key]

			update_fields: dict[str, Any] = {"workflow_state": next_state}
			if new_docstatus != int(doc.docstatus):
				update_fields["docstatus"] = new_docstatus

			frappe.db.set_value(
				DOCTYPE,
				docname,
				update_fields,
				update_modified=True,
			)

		doc.reload()
		if next_state:
			doc.add_comment("Workflow", _(next_state))

		if comment and comment.strip():
			doc.add_comment("Comment", comment.strip())

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_employee_id_card_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Employee ID Card Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_my_id_card_details(limit=50, start=0):
	"""Return the current user's ID card requests."""
	from frappe.utils import cint

	limit = cint(limit) or 50
	start = cint(start) or 0
	current_user = frappe.session.user
	if not current_user or current_user == "Guest":
		return []

	try:
		# Search by email__ or owner
		names = frappe.get_all(
			DOCTYPE,
			filters=[["email__", "=", current_user]],
			fields=["name"],
			limit_start=start,
			limit_page_length=limit,
			order_by="modified desc",
		)
		if not names:
			names = frappe.get_all(
				DOCTYPE,
				filters=[["owner", "=", current_user]],
				fields=["name"],
				limit_start=start,
				limit_page_length=limit,
				order_by="modified desc",
			)
		if not names and current_user and "@" in current_user:
			user_prefix = current_user.split("@")[0]
			names = frappe.get_all(
				DOCTYPE,
				filters=[["email__", "like", f"%{user_prefix}%"]],
				fields=["name"],
				limit_start=start,
				limit_page_length=limit,
				order_by="modified desc",
			)

		results = []
		for row in names:
			try:
				doc = frappe.get_doc(DOCTYPE, row.name)
				d = doc.as_dict()
				c = get_latest_hr_comment(row.name)
				if c:
					d["remarks"] = c
					d["hr_comments"] = c
				results.append(d)
			except Exception:
				continue

		return results

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Employee ID Card - Get My Details Error")
		return []


@frappe.whitelist()
def verify_id_card_by_hr(docname):
	"""HR-specific verify action — shortcut for perform_action with 'Verify'."""
	user_roles = frappe.get_roles(frappe.session.user)
	if "staff, RnD" not in user_roles and "System Manager" not in user_roles:
		frappe.throw(_("Only HR (staff, RnD) can verify ID card requests."))

	return perform_employee_id_card_action(docname, "Verify")
