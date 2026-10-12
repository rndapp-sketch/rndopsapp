# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, money_in_words

DOCTYPE = "Acc Head to Head Fund Transfer"
WORKFLOW_NAME = "h2h_workflow"
DEFAULT_STATE = "Draft"

# Fields the frontend is allowed to write through save_acc_head_to_head_fund_transfer_data.
# Read-only/derived fields (name, department, project number/title, amount in words) are
# resolved server-side in validate() so the API can never be fed inconsistent values.
WRITABLE_FIELDS = [
	"h2h_app_webmail",
	"h2h_proj_code",
	"h2h_transfer_from",
	"h2h_transfer_to",
	"h2h_amount",
	"h2h_justification",
	"h2h_supporting_document",
	"h2h_remarks",
	"amended_from",
]


def extract_eval_expression(expression):
	"""Strip the 'eval:' prefix off a Frappe depends_on expression so the
	frontend can evaluate it directly."""
	if not expression:
		return None
	expression = str(expression).strip()
	if expression.startswith("eval:"):
		return expression[5:].strip()
	return expression


def _serialize_field(f):
	return {
		"fieldname": f.fieldname,
		"label": f.label,
		"fieldtype": f.fieldtype,
		"options": getattr(f, "options", None),
		"mandatory": getattr(f, "reqd", False),
		"hidden": getattr(f, "hidden", False),
		"read_only": getattr(f, "read_only", False),
		"in_list_view": getattr(f, "in_list_view", False),
		"description": getattr(f, "description", "") or "",
		"default": getattr(f, "default", None),
		"depends_on": getattr(f, "depends_on", None),
		"mandatory_depends_on": getattr(f, "mandatory_depends_on", None),
		"read_only_depends_on": getattr(f, "read_only_depends_on", None),
		"depends_on_eval": extract_eval_expression(getattr(f, "depends_on", None)),
		"mandatory_depends_on_eval": extract_eval_expression(getattr(f, "mandatory_depends_on", None)),
		"read_only_depends_on_eval": extract_eval_expression(getattr(f, "read_only_depends_on", None)),
	}


def _resolve_project(project_ref):
	"""Resolve a Project Registration by doc name or by the human-readable
	project_no. Returns the project dict or None."""
	if not project_ref:
		return None

	project_ref = str(project_ref).strip('"').strip("'").strip()
	fields = ["name", "project_no", "project_title", "pi_webmail", "implementation_department"]

	project = frappe.db.get_value("Project Registration", project_ref, fields, as_dict=True)
	if project:
		return project

	match = frappe.get_all(
		"Project Registration",
		filters={"project_no": project_ref},
		fields=fields,
		limit_page_length=1,
	)
	return match[0] if match else None


def _resolve_label(doctype, docname, label_field):
	"""Return the human-readable label for a linked master record, falling back
	to the raw value when the link does not resolve."""
	if not docname:
		return ""
	try:
		return frappe.db.get_value(doctype, docname, label_field) or docname
	except Exception:
		return docname


def _budget_head_label(head):
	"""Budget Head names are opaque ids; the readable text lives in `budget_head`."""
	return _resolve_label("Budget Head", head, "budget_head")


def _active_workflow():
	"""The active Workflow doc for this doctype, or None when none is configured."""
	workflow_name = frappe.get_value("Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name")
	return frappe.get_doc("Workflow", workflow_name) if workflow_name else None


class AccHeadtoHeadFundTransfer(Document):
	def before_insert(self):
		if not self.workflow_state:
			self.workflow_state = DEFAULT_STATE

	def validate(self):
		self.resolve_project_details()
		self.set_applicant_details()
		self.validate_transfer()
		self.set_amount_in_words()

	def resolve_project_details(self):
		"""Store the Project Registration doc name in h2h_proj_code and mirror the
		project number/title/PI onto the read-only display fields."""
		project = _resolve_project(self.h2h_proj_code)
		if not project:
			return

		self.h2h_proj_code = project.get("name")
		self.h2h_proj_num = project.get("project_no") or ""
		self.h2h_proj_title = project.get("project_title") or ""
		self.h2h_pi_webmail = project.get("pi_webmail") or None

	def set_applicant_details(self):
		"""Fill applicant name/department/designation/category from the User record."""
		if not self.h2h_app_webmail:
			return

		user = frappe.db.get_value(
			"User",
			self.h2h_app_webmail,
			["full_name", "department_name", "designation_name", "empclass"],
			as_dict=True,
		)
		if not user:
			return

		self.h2h_app_name = user.get("full_name") or self.h2h_app_name
		self.h2h_dept = _resolve_label("Department_prornd", user.get("department_name"), "dept_name")
		self.h2h_app_designation = _resolve_label(
			"Designation_prornd", user.get("designation_name"), "designation_prornd"
		)
		self.h2h_app_category = _resolve_label(
			"EmployeeClass_prornd", user.get("empclass"), "empclass_name"
		)

	def validate_transfer(self):
		if self.h2h_transfer_from and self.h2h_transfer_from == self.h2h_transfer_to:
			frappe.throw(_("The source and destination account heads must be different."))

		if flt(self.h2h_amount) <= 0:
			frappe.throw(_("Amount to Transfer must be greater than zero."))

	def set_amount_in_words(self):
		self.h2h_amount_in_words = (
			money_in_words(flt(self.h2h_amount)) if flt(self.h2h_amount) else ""
		)


# ----------------------------------------------------------------------------
# Frontend endpoints
# ----------------------------------------------------------------------------


@frappe.whitelist()
def get_acc_head_to_head_fund_transfer_fields(doc_name=None, docname=None):
	"""Field metadata + dropdown options + prefill data for the create/edit form.

	- doc_name: Project Registration name or project_no, used to prefill project info.
	- docname: an existing Acc Head to Head Fund Transfer, used to prefill the form
	  for editing.
	"""
	meta = frappe.get_meta(DOCTYPE)
	fields = [_serialize_field(f) for f in meta.get("fields")]

	link_options = {}
	prefill_data = {}
	related_project_data = {}

	# Budget Head options for both account head fields
	try:
		heads = frappe.get_all("Budget Head", fields=["name", "budget_head"], limit_page_length=500)
		head_options = [{"value": h.name, "label": h.budget_head or h.name} for h in heads]
		link_options["h2h_transfer_from"] = head_options
		link_options["h2h_transfer_to"] = head_options
	except Exception:
		link_options["h2h_transfer_from"] = []
		link_options["h2h_transfer_to"] = []

	# Project options
	try:
		projects = frappe.get_all(
			"Project Registration",
			fields=["name", "project_no", "project_title"],
			limit_page_length=500,
		)
		link_options["h2h_proj_code"] = [
			{
				"value": p.name,
				"label": f"{p.project_no or p.name} — {p.project_title}"
				if p.project_title
				else (p.project_no or p.name),
			}
			for p in projects
		]
	except Exception:
		link_options["h2h_proj_code"] = []

	# Prefill the applicant with the logged-in user
	session_user = frappe.session.user
	if session_user and session_user != "Guest":
		prefill_data["h2h_app_webmail"] = session_user
		prefill_data.update(get_applicant_details(session_user) or {})

	if doc_name:
		project = _resolve_project(doc_name)
		if project:
			related_project_data = project
			prefill_data["h2h_proj_code"] = project.get("name")
			prefill_data["h2h_proj_num"] = project.get("project_no") or ""
			prefill_data["h2h_proj_title"] = project.get("project_title") or ""
			prefill_data["h2h_pi_webmail"] = project.get("pi_webmail") or ""

	if docname and frappe.db.exists(DOCTYPE, docname):
		doc = frappe.get_doc(DOCTYPE, docname)
		prefill_data.update(doc.as_dict())
		project = _resolve_project(doc.h2h_proj_code)
		if project:
			related_project_data = project

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_project_data": related_project_data,
	}


@frappe.whitelist()
def get_applicant_details(user_email=None):
	"""Applicant name/department/designation/category for the given (or session) user."""
	user_email = (user_email or frappe.session.user or "").strip('"').strip("'")
	if not user_email or user_email == "Guest":
		return {}

	user = frappe.db.get_value(
		"User",
		user_email,
		["full_name", "department_name", "designation_name", "empclass"],
		as_dict=True,
	)
	if not user:
		return {}

	return {
		"h2h_app_name": user.get("full_name") or "",
		"h2h_dept": _resolve_label("Department_prornd", user.get("department_name"), "dept_name"),
		"h2h_app_designation": _resolve_label(
			"Designation_prornd", user.get("designation_name"), "designation_prornd"
		),
		"h2h_app_category": _resolve_label(
			"EmployeeClass_prornd", user.get("empclass"), "empclass_name"
		),
	}


@frappe.whitelist()
def get_project_account_heads(project_code):
	"""Account heads available on a project, with sanctioned and received amounts.

	Sanctioned amounts come from the Project Registration budget breakup; received
	amounts are summed over the submitted-or-draft Fund Received breakups for the
	project. Returned so the frontend can show what sits under the source head
	before a transfer is requested.
	"""
	project = _resolve_project(project_code)
	if not project:
		frappe.throw(_("Project Registration not found."))

	pr = frappe.get_doc("Project Registration", project["name"])

	heads = {}

	def _bucket(head):
		key = (head or "").strip()
		if not key:
			return None
		return heads.setdefault(
			key, {"account_head": key, "sanctioned_amount": 0.0, "received_amount": 0.0}
		)

	breakup = pr.get("sanctioned_budget_breakup") or pr.get("proposed_budget_breakup") or []
	for row in breakup:
		if getattr(row, "is_total_row", 0):
			continue
		bucket = _bucket(row.account_head)
		if bucket:
			bucket["sanctioned_amount"] += flt(row.total_proposal_of_heads)

	try:
		funds = frappe.get_all(
			"Fund Received",
			filters={"prjreg_title": project["name"], "docstatus": ["<", 2]},
			pluck="name",
			limit_page_length=0,
		)
		for fund_name in funds:
			fund = frappe.get_doc("Fund Received", fund_name)
			for row in fund.get("received_amt_breakup") or []:
				bucket = _bucket(row.account_head)
				if bucket:
					bucket["received_amount"] += flt(row.amount_received)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "H2H Fund Transfer: Fund Received lookup failed")

	return {
		"project": project,
		"account_heads": sorted(heads.values(), key=lambda h: h["account_head"]),
	}


@frappe.whitelist()
def save_acc_head_to_head_fund_transfer_data(data):
	"""Insert or update a transfer request. Expects a JSON string or dict."""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		docname = data.get("name")
		if docname and frappe.db.exists(DOCTYPE, docname):
			doc = frappe.get_doc(DOCTYPE, docname)
		else:
			doc = frappe.new_doc(DOCTYPE)

		for field in WRITABLE_FIELDS:
			if field in data:
				val = data[field]
				doc.set(field, None if val in ("null", "") else val)

		if not doc.h2h_app_webmail:
			doc.h2h_app_webmail = frappe.session.user

		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name, "doc": doc.as_dict()}

	except frappe.ValidationError as e:
		frappe.db.rollback()
		return {"status": "error", "message": str(e)}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "H2H Fund Transfer Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_acc_head_to_head_fund_transfer(docname):
	"""Full document, with readable labels for the linked account heads."""
	if not frappe.db.exists(DOCTYPE, docname):
		frappe.throw(_("Acc Head to Head Fund Transfer not found."))

	doc = frappe.get_doc(DOCTYPE, docname)
	data = doc.as_dict()
	data["h2h_transfer_from_label"] = _budget_head_label(doc.h2h_transfer_from)
	data["h2h_transfer_to_label"] = _budget_head_label(doc.h2h_transfer_to)
	data["workflow_actions"] = get_acc_head_to_head_fund_transfer_workflow_actions(docname)
	return data


@frappe.whitelist()
def list_acc_head_to_head_fund_transfers(
	applicant=None, project_code=None, workflow_state=None, limit=50, start=0
):
	"""List transfer requests for the account portal.

	With no filters, returns the current user's own requests; pass applicant="all"
	to list every request the caller is permitted to read.
	"""
	filters = {}

	if applicant == "all":
		pass
	elif applicant:
		filters["h2h_app_webmail"] = applicant
	else:
		filters["h2h_app_webmail"] = frappe.session.user

	if project_code:
		project = _resolve_project(project_code)
		filters["h2h_proj_code"] = project["name"] if project else project_code

	if workflow_state:
		if isinstance(workflow_state, str) and workflow_state.strip().startswith("["):
			workflow_state = json.loads(workflow_state)
		filters["workflow_state"] = (
			["in", workflow_state] if isinstance(workflow_state, (list, tuple)) else workflow_state
		)

	rows = frappe.get_all(
		DOCTYPE,
		filters=filters,
		fields=[
			"name",
			"h2h_app_webmail",
			"h2h_app_name",
			"h2h_dept",
			"h2h_proj_code",
			"h2h_proj_num",
			"h2h_proj_title",
			"h2h_transfer_from",
			"h2h_transfer_to",
			"h2h_amount",
			"workflow_state",
			"docstatus",
			"creation",
			"modified",
		],
		order_by="creation desc",
		limit_page_length=int(limit or 50),
		limit_start=int(start or 0),
	)

	for row in rows:
		row["h2h_transfer_from_label"] = _budget_head_label(row.get("h2h_transfer_from"))
		row["h2h_transfer_to_label"] = _budget_head_label(row.get("h2h_transfer_to"))

	return {"records": rows, "count": len(rows)}


@frappe.whitelist()
def get_pending_acc_head_to_head_fund_transfers(limit=50, start=0):
	"""Requests waiting on the current user — i.e. sitting in a state the user's
	roles hold a transition out of. Drives the approver inbox."""
	workflow = _active_workflow()
	if not workflow:
		return {"records": [], "count": 0, "states": []}

	user_roles = frappe.get_roles(frappe.session.user)
	states = list(
		dict.fromkeys(t.state for t in workflow.transitions if t.allowed in user_roles)
	)
	if not states:
		return {"records": [], "count": 0, "states": []}

	result = list_acc_head_to_head_fund_transfers(
		applicant="all", workflow_state=states, limit=limit, start=start
	)
	result["states"] = states
	return result


@frappe.whitelist()
def delete_acc_head_to_head_fund_transfer(docname):
	"""Delete a draft request. Submitted documents must be cancelled first."""
	try:
		if not frappe.db.exists(DOCTYPE, docname):
			return {"status": "error", "message": _("Document not found.")}

		doc = frappe.get_doc(DOCTYPE, docname)
		if doc.docstatus == 1:
			return {"status": "error", "message": _("Cancel the submitted request before deleting it.")}

		doc.flags.ignore_permissions = True
		doc.delete()
		frappe.db.commit()
		return {"status": "success", "docname": docname}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "H2H Fund Transfer Delete Error")
		return {"status": "error", "message": str(e)}


# ----------------------------------------------------------------------------
# Workflow
# ----------------------------------------------------------------------------


@frappe.whitelist()
def get_acc_head_to_head_fund_transfer_workflow_actions(docname):
	"""Workflow actions available to the current user at the doc's current state.
	Returns [] when no workflow is configured for the doctype yet."""
	if not frappe.db.exists(DOCTYPE, docname):
		return []

	workflow = _active_workflow()
	if not workflow:
		return []

	doc = frappe.get_doc(DOCTYPE, docname)
	current_state = doc.workflow_state or DEFAULT_STATE

	user_roles = frappe.get_roles(frappe.session.user)
	actions = [
		t.action for t in workflow.transitions if t.state == current_state and t.allowed in user_roles
	]
	return list(dict.fromkeys(actions))


@frappe.whitelist()
def perform_acc_head_to_head_fund_transfer_action(docname, action):
	"""Execute a workflow transition. Writes workflow_state + docstatus directly so
	API callers (who lack desk roles) are not rejected by validate_workflow."""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.workflow_state or DEFAULT_STATE

		workflow = _active_workflow()
		if not workflow:
			frappe.throw(_("Workflow not found for {0}.").format(DOCTYPE))

		allowed_actions = get_acc_head_to_head_fund_transfer_workflow_actions(docname)
		if action not in allowed_actions:
			frappe.throw(
				_("You are not permitted to perform '{0}' from state '{1}'.").format(
					action, current_state
				)
			)

		next_state = None
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				break

		if not next_state:
			frappe.throw(
				_("No valid transition for action '{0}' from state '{1}'.").format(
					action, current_state
				)
			)

		next_state_row = next((s for s in workflow.states if s.state == next_state), None)
		new_docstatus = int(next_state_row.doc_status or 0) if next_state_row else 0

		workflow_field = workflow.workflow_state_field or "workflow_state"
		update_fields = {workflow_field: next_state}
		if new_docstatus != int(doc.docstatus):
			update_fields["docstatus"] = new_docstatus

		if (
			next_state_row
			and getattr(next_state_row, "update_field", None)
			and next_state_row.update_field != workflow_field
			and next_state_row.update_value is not None
		):
			update_fields[next_state_row.update_field] = next_state_row.update_value

		frappe.db.set_value(DOCTYPE, docname, update_fields, update_modified=True)

		doc.reload()
		doc.add_comment("Workflow", _(next_state))
		frappe.db.commit()

		return {
			"status": "success",
			"message": _("Action '{0}' completed. New State: {1}").format(action, next_state),
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_acc_head_to_head_fund_transfer_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "H2H Fund Transfer Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_acc_head_to_head_fund_transfer(docname):
	"""Move a draft request out of Draft via the workflow's Submit/Forward action.

	Only `Permanent Employee` (the PI) holds the Draft -> Submit transition in
	h2h_workflow, so an applicant who is not the PI gets a clear error rather than
	a document silently pushed past the approval chain."""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		if doc.docstatus == 1:
			return {"status": "success", "message": _("Already submitted."), "docname": docname}

		actions = get_acc_head_to_head_fund_transfer_workflow_actions(docname)
		for candidate in ("Submit", "Forward", "Apply"):
			if candidate in actions:
				return perform_acc_head_to_head_fund_transfer_action(docname, candidate)

		if _active_workflow():
			# Never bypass an active workflow with a raw docstatus submit.
			return {
				"status": "error",
				"message": _(
					"You are not permitted to submit this request from state '{0}'. "
					"Available actions: {1}"
				).format(doc.workflow_state or DEFAULT_STATE, ", ".join(actions) or _("none")),
			}

		doc.flags.ignore_permissions = True
		doc.submit()
		frappe.db.commit()
		return {"status": "success", "docname": doc.name, "workflow_state": doc.workflow_state}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "H2H Fund Transfer Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_amount_in_words(amount, currency=None):
	"""Convert an amount to words for the form's read-only display field."""
	if not amount:
		return ""
	try:
		return money_in_words(flt(amount), currency)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "H2H Fund Transfer amount_in_words Error")
		return ""
