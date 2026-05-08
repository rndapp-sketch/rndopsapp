# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json
import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff


class LeaveModule(Document):
	def validate(self):
		self._set_user_info()
		self._validate_dates()
		self._validate_leave_type_fields()
		self._validate_leave_balance()

	def on_trash(self):
		"""Return leave balance when a leave application is deleted."""
		if self.workflow_state and self.workflow_state != "Draft":
			if self.leave_type in ("EL", "CL"):
				leave_days = _get_leave_days(self)
				if leave_days > 0:
					if "reject" not in (self.workflow_state or "").lower():
						_update_leave_balance(self.email, self.leave_type, leave_days, deduct=False)

	def _set_user_info(self):
		if not self.email:
			self.email = frappe.session.user

		if self.email:
			self.empclass = frappe.db.get_value("User", self.email, "empclass") or ""
			self.is_rnd_staff = 1 if "staff, RnD" in frappe.get_roles(self.email) else 0

	def _validate_dates(self):
		if self.leave_type in ("EL", "On Duty Leave"):
			if self.from_date and self.to_date:
				if self.from_date > self.to_date:
					frappe.throw(
						_("'From Date' cannot be after 'To Date'."),
						title=_("Invalid Date Range"),
					)

			if self.station_leave_permission == "Required":
				if self.sl_from_date and self.sl_to_date:
					if self.sl_from_date > self.sl_to_date:
						frappe.throw(
							_("'Station Leave From' cannot be after 'Station Leave To'."),
							title=_("Invalid Station Leave Date Range"),
						)

		if self.leave_type == "CL":
			if self.station_leave_permission == "Required":
				if self.sl_from_date and self.sl_to_date:
					if self.sl_from_date > self.sl_to_date:
						frappe.throw(
							_("'Station Leave From' cannot be after 'Station Leave To'."),
							title=_("Invalid Station Leave Date Range"),
						)

	def _validate_leave_type_fields(self):
		if self.leave_type == "CL":
			if not self.get("cl_dates_table") or len(self.cl_dates_table) == 0:
				frappe.throw(
					_("Please select at least one CL date."),
					title=_("Missing CL Dates"),
				)

		elif self.leave_type in ("EL", "On Duty Leave"):
			if not self.from_date:
				frappe.throw(
					_("'From Date' is required for {0} leave.").format(self.leave_type),
					title=_("Missing From Date"),
				)
			if not self.to_date:
				frappe.throw(
					_("'To Date' is required for {0} leave.").format(self.leave_type),
					title=_("Missing To Date"),
				)

	def _validate_leave_balance(self):
		"""Block leave application if actual balance (after deducting absents) is exhausted."""
		if self.leave_type not in ("EL", "CL"):
			return

		email = self.email or frappe.session.user
		username = frappe.db.get_value("User", email, "username")
		if not username:
			return

		leave_data = frappe.db.get_value(
			"Leave Data",
			{"emp_username": username},
			["el", "cl"],
			as_dict=True,
		)
		if not leave_data:
			return

		raw_cl = leave_data.cl or 0
		raw_el = leave_data.el or 0

		total_absents = 0
		try:
			import requests

			resp = requests.get(
				f"http://localhost:3000/attendance/absents/{username}",
				timeout=5,
			)
			result = resp.json()
			if result.get("success") and result.get("data"):
				total_absents = result["data"].get("totalAbsents", 0)
		except Exception:
			pass

		remaining = total_absents
		actual_cl = raw_cl
		actual_el = raw_el

		if remaining > 0:
			cl_deduction = min(remaining, raw_cl)
			actual_cl = raw_cl - cl_deduction
			remaining -= cl_deduction

		if remaining > 0:
			actual_el = raw_el - math.ceil(remaining)

		if self.leave_type == "CL" and actual_cl <= 0:
			frappe.throw(
				_(
					"Cannot apply for CL — your actual Casual Leave balance is 0 "
					"(after deducting {0} absents from CL balance of {1})."
				).format(total_absents, raw_cl),
				title=_("Insufficient CL Balance"),
			)

		if self.leave_type == "EL" and actual_el <= 0:
			frappe.throw(
				_(
					"Cannot apply for EL — your actual Earned Leave balance is 0 "
					"(after deducting overflow absents from EL balance of {0})."
				).format(raw_el),
				title=_("Insufficient EL Balance"),
			)


# ──────────────────────────────────────────────────────────
#  Leave Balance Helpers
# ──────────────────────────────────────────────────────────


def _get_leave_days(doc):
	"""Calculate the number of leave days based on leave type."""
	if doc.leave_type == "EL":
		if doc.from_date and doc.to_date:
			return date_diff(doc.to_date, doc.from_date) + 1
		return 0
	elif doc.leave_type == "CL":
		total = 0
		for row in doc.get("cl_dates_table") or []:
			if row.day_type in ("Forenoon", "Afternoon"):
				total += 0.5
			else:
				total += 1
		return total
	return 0


def _update_leave_balance(email, leave_type, days, deduct=True):
	if leave_type not in ("EL", "CL") or days <= 0:
		return

	username = frappe.db.get_value("User", email, "username")
	if not username:
		frappe.log_error(
			f"No username found for user {email}",
			"Leave Balance Update",
		)
		return

	leave_data_name = frappe.db.get_value("Leave Data", {"emp_username": username}, "name")
	if not leave_data_name:
		frappe.log_error(
			f"No Leave Data record found for username '{username}' (email: {email})",
			"Leave Balance Update",
		)
		return

	field = "el" if leave_type == "EL" else "cl"
	current_balance = frappe.db.get_value("Leave Data", leave_data_name, field) or 0

	if deduct:
		new_balance = current_balance - days
	else:
		new_balance = current_balance + days

	frappe.db.set_value("Leave Data", leave_data_name, field, new_balance)


# ──────────────────────────────────────────────────────────
#  Generic helpers
# ──────────────────────────────────────────────────────────


def extract_eval_expression(expression):
	if not expression:
		return None
	expression = str(expression).strip()
	if expression.startswith("eval:"):
		return expression[5:].strip()
	return expression


def _find_matching_transition(workflow, current_state, action, doc):
	"""Find the first workflow transition that matches state, action, role, and condition."""
	doc_dict = doc.as_dict()
	user_roles = frappe.get_roles(frappe.session.user)

	for t in workflow.transitions:
		if t.state != current_state or t.action != action:
			continue

		# Check role
		if t.allowed and t.allowed not in user_roles and "System Manager" not in user_roles:
			continue

		# Check condition
		if t.condition:
			try:
				if not frappe.safe_eval(
					t.condition,
					dict(frappe=frappe._dict(session=frappe.session)),
					dict(doc=doc_dict),
				):
					continue
			except Exception:
				continue

		return t

	return None


# ──────────────────────────────────────────────────────────
#  Whitelisted API methods
# ──────────────────────────────────────────────────────────


@frappe.whitelist()
def get_leave_module_fields(doc_name=None):
	meta = frappe.get_meta("Leave Module")

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

		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				child_fields = []
				for cf in child_meta.fields:
					child_fields.append(
						{
							"fieldname": cf.fieldname,
							"label": cf.label,
							"fieldtype": cf.fieldtype,
							"options": cf.options,
							"mandatory": cf.reqd,
							"hidden": cf.hidden,
							"read_only": cf.read_only,
							"in_list_view": cf.in_list_view,
							"default": cf.default,
						}
					)
				field_data["child_fields"] = child_fields
			except Exception:
				pass

		fields.append(field_data)

	prefill_data = {}

	if doc_name:
		try:
			doc = frappe.get_doc("Leave Module", doc_name)
			prefill_data = doc.as_dict()
		except Exception:
			pass
	else:
		user = frappe.session.user
		if user and user not in ("Guest", "Administrator"):
			prefill_data["email"] = user
			try:
				user_doc = frappe.get_doc("User", user)
				prefill_data["username"] = user_doc.username or user_doc.full_name
				prefill_data["pi"] = getattr(user_doc, "piheadmentor_user_id", None)
			except Exception:
				pass

		prefill_data.setdefault("station_leave_permission", "Not Required")

	link_options = {}

	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=0,
		)
		link_options["email"] = users
	except Exception:
		link_options["email"] = []

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
	}


@frappe.whitelist()
def save_leave_module_data(data):
	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		is_new = False

		if doc_name and frappe.db.exists("Leave Module", doc_name):
			doc = frappe.get_doc("Leave Module", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled leave application."))
		else:
			doc = frappe.new_doc("Leave Module")
			is_new = True
			doc.workflow_state = "Draft"

		simple_fields = [
			"email",
			"username",
			"pi",
			"leave_type",
			"from_date",
			"to_date",
			"station_leave_permission",
			"sl_from_date",
			"sl_to_date",
			"reason_for_leave",
			"address_on_leave",
			"contact_number",
			"additional_remarks",
		]

		for field in simple_fields:
			if field in data:
				val = data[field]
				doc.set(field, val if val != "null" else None)

		cl_dates = data.get("cl_dates_table", [])
		if isinstance(cl_dates, str):
			cl_dates = json.loads(cl_dates)

		if cl_dates:
			doc.set("cl_dates_table", [])
			for row in cl_dates:
				for key in [
					"name",
					"creation",
					"modified",
					"owner",
					"modified_by",
					"docstatus",
					"parent",
					"parentfield",
					"parenttype",
				]:
					row.pop(key, None)
				doc.append("cl_dates_table", row)

		onduty_file = data.get("onduty_leave_docs")
		if onduty_file:
			if isinstance(onduty_file, dict) and onduty_file.get("file_data"):
				import base64

				try:
					filename = onduty_file.get("file_name", "onduty_document")
					content_b64 = onduty_file["file_data"]

					if isinstance(content_b64, str) and content_b64.startswith("data:"):
						content_b64 = content_b64.split(",", 1)[1]

					file_content = base64.b64decode(content_b64)

					file_doc = frappe.get_doc(
						{
							"doctype": "File",
							"file_name": filename,
							"attached_to_doctype": "Leave Module",
							"attached_to_name": doc.name,
							"content": file_content,
							"is_private": 1,
						}
					)
					file_doc.save(ignore_permissions=True)
					doc.onduty_leave_docs = file_doc.file_url

				except Exception as e:
					frappe.log_error(
						f"File upload error for onduty_leave_docs: {str(e)}",
						"Leave Module File Upload",
					)
			elif isinstance(onduty_file, str):
				doc.onduty_leave_docs = onduty_file

		doc.flags.ignore_permissions = True
		if is_new:
			doc.insert(ignore_mandatory=True)
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Leave Module Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_leave_module(docname):
	try:
		doc = frappe.get_doc("Leave Module", docname)
		current_state = doc.workflow_state or "Draft"

		if current_state != "Draft":
			return {
				"status": "info",
				"message": f"Leave application '{docname}' is already in state '{current_state}'.",
				"docname": docname,
				"workflow_state": current_state,
			}

		return perform_leave_module_action(docname, "Submit")

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Leave Module Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_leave_module_workflow_actions(docname):
	doc = frappe.get_doc("Leave Module", docname)
	current_state = doc.workflow_state or "Draft"
	doc_dict = doc.as_dict()
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": "Leave Module", "is_active": 1},
		"name",
	)

	if not workflow_name:
		return []

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
					dict(doc=doc_dict),
				)
				if not result:
					continue
			except Exception:
				continue

		allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def perform_leave_module_action(docname, action, comment=None):
	try:
		doc = frappe.get_doc("Leave Module", docname)
		current_state = doc.workflow_state or "Draft"

		print(
			f"\n--- [LEAVE_MODULE] perform_action: docname={docname}, action={action}, "
			f"current_state={current_state}, user={frappe.session.user}"
		)

		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": "Leave Module", "is_active": 1},
			"name",
		)

		if not workflow_name:
			frappe.throw(_("No active workflow found for Leave Module."))

		workflow = frappe.get_doc("Workflow", workflow_name)

		transition = _find_matching_transition(workflow, current_state, action, doc)

		if not transition:
			frappe.throw(
				_("No valid transition found for action '{0}' from state '{1}'.").format(
					action, current_state
				)
			)

		next_state = transition.next_state

		print(f"    Transition: '{current_state}' --[{action}]--> '{next_state}'")

		next_state_row = next((s for s in workflow.states if s.state == next_state), None)
		new_docstatus = int(next_state_row.doc_status or 0) if next_state_row else 0

		workflow_field = workflow.workflow_state_field or "workflow_state"
		update_fields = {workflow_field: next_state}

		if new_docstatus != int(doc.docstatus):
			update_fields["docstatus"] = new_docstatus

		frappe.db.set_value(
			"Leave Module",
			docname,
			update_fields,
			update_modified=True,
		)

		doc.reload()
		doc.add_comment("Workflow", _(next_state))

		if comment and comment.strip():
			doc.add_comment("Comment", comment.strip())

		# ── Leave balance adjustment ──
		if doc.leave_type in ("EL", "CL"):
			leave_days = _get_leave_days(doc)
			if leave_days > 0:
				if current_state == "Draft":
					_update_leave_balance(doc.email, doc.leave_type, leave_days, deduct=True)
				elif "reject" in next_state.lower() or "cancel" in next_state.lower():
					_update_leave_balance(doc.email, doc.leave_type, leave_days, deduct=False)

		frappe.db.commit()

		print(f"    [SUCCESS] New state: '{next_state}', docstatus: {new_docstatus}")

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_leave_module_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Leave Module Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_my_leaves(limit=50, start=0):
	from frappe.utils import cint

	limit = cint(limit) or 50
	start = cint(start) or 0
	current_user = frappe.session.user

	try:
		names = frappe.get_all(
			"Leave Module",
			filters={"email": current_user},
			fields=["name"],
			limit_start=start,
			limit_page_length=limit,
			order_by="modified desc",
		)

		results = []
		for row in names:
			try:
				doc = frappe.get_doc("Leave Module", row.name)
				results.append(doc.as_dict())
			except Exception:
				continue

		return results

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Leave Module - Get My Leaves Error")
		return []


@frappe.whitelist()
def get_pending_approvals(limit=50, start=0):
	from frappe.utils import cint

	limit = cint(limit) or 50
	start = cint(start) or 0
	current_user = frappe.session.user

	try:
		names = frappe.get_all(
			"Leave Module",
			filters={
				"pi": current_user,
				"workflow_state": ["in", ["Pending PI Approval"]],
				"docstatus": 0,
			},
			fields=["name"],
			limit_start=start,
			limit_page_length=limit,
			order_by="modified desc",
		)

		results = []
		for row in names:
			try:
				doc = frappe.get_doc("Leave Module", row.name)
				doc_dict = doc.as_dict()
				doc_dict["available_actions"] = get_leave_module_workflow_actions(row.name)
				results.append(doc_dict)
			except Exception:
				continue

		return results

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Leave Module - Get Pending Approvals Error")
		return []


@frappe.whitelist()
def get_leave_detail(docname):
	try:
		doc = frappe.get_doc("Leave Module", docname)
		doc_dict = doc.as_dict()

		return {
			"doc": doc_dict,
			"workflow_actions": get_leave_module_workflow_actions(docname),
			"workflow_state": doc.workflow_state or "Draft",
		}

	except frappe.DoesNotExistError:
		return {"error": f"Leave application '{docname}' not found."}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Leave Module - Get Detail Error")
		return {"error": str(e)}


@frappe.whitelist()
def get_leave_balance():
	user = frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		return None

	username = frappe.db.get_value("User", user, "username")
	if not username:
		return None

	leave_data = frappe.db.get_value(
		"Leave Data",
		{"emp_username": username},
		["el", "cl", "emp_id", "emp_class"],
		as_dict=True,
	)

	return leave_data
