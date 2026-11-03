# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import base64
import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

DOCTYPE = "UC Request"
STAFF_ROLE = "staff, RnD"

STATE_PI_VERIFICATION = "Pending PI Verification"
STATE_REGISTRAR = "Pending Registrar Verification"

ACTION_VERIFY_PRINT = "Verify & Print"
ACTION_SEND_REGISTRAR = "Print & Send to Registrar"

# Project Registration field -> UC Request field. Filled server-side on every
# save so the project block can never be edited from the form.
PROJECT_FIELD_MAP = {
	"project_no": "project_no",
	"project_title": "project_title",
	"principal_investigator_name": "principal_investigator_name",
	"pi_webmail": "pi_webmail",
	"implementation_department": "implementation_department",
	"funding_agen": "funding_agency",
	"funding_agency_schemes": "funding_agency_scheme",
	"sanctioned_letter_no": "sanctioned_letter_no",
	"sanctioned_letter_date": "sanctioned_letter_date",
	"prj_start_date": "prj_start_date",
	"prj_end_date": "prj_end_date",
	"total_sanctioned_amount": "total_sanction_amount",
}

# Attach fields the applicant may set from the form
FORM_ATTACH_FIELDS = ("prev_uc", "uc_format")


class UCRequest(Document):
	def validate(self):
		self.fill_project_details()

	def fill_project_details(self):
		if not self.project_id:
			return
		project = frappe.db.get_value(
			"Project Registration", self.project_id, [*PROJECT_FIELD_MAP, "pi_userid"], as_dict=True
		)
		if not project:
			frappe.throw(_("Project {0} not found.").format(self.project_id))

		for src, dst in PROJECT_FIELD_MAP.items():
			self.set(dst, project.get(src))
		# Some projects carry only pi_userid
		self.pi_webmail = self.pi_webmail or project.pi_userid
		self.total_sanction_amount = flt(self.total_sanction_amount)
		self.funding_agency_name = (
			frappe.db.get_value("fundingagency_", self.funding_agency, "funding_agency_name")
			if self.funding_agency
			else None
		)


def _is_system_manager():
	return "System Manager" in frappe.get_roles(frappe.session.user)


def _is_pi(doc):
	user = (frappe.session.user or "").lower()
	return user in {(doc.get("pi_webmail") or "").lower(), (doc.get("owner") or "").lower()}


def _upload_attachment(doc, file_dict):
	"""Upload a base64 file dict from the frontend to
	Project_Registration/{project_no}/UC/{docname}/{filename}; returns the URL."""
	from rndopsapp.minio import get_rnd_file_service

	file_name = file_dict.get("file_name") or "attachment"
	file_data = file_dict.get("file_data") or ""
	if "," in file_data:
		file_data = file_data.split(",", 1)[1]
	content = base64.b64decode(file_data)

	file_service = get_rnd_file_service()
	path = f"Project_Registration/{doc.get('project_no') or 'unknown'}/UC/{doc.name}/{file_name}"
	file_service.storage.upload(path, content, file_service._mime(file_name))
	return f"/prod-rnd-files/{path}"


def _apply_attachments(doc, data, fieldnames):
	"""Set URL values as-is; upload base64 file dicts (doc must already have a name)."""
	for field in fieldnames:
		if field not in data:
			continue
		value = data.get(field)
		if isinstance(value, dict) and value.get("file_data"):
			frappe.db.set_value(DOCTYPE, doc.name, field, _upload_attachment(doc, value))
		elif isinstance(value, str) or value is None:
			frappe.db.set_value(DOCTYPE, doc.name, field, value or None)


def _get_workflow():
	name = frappe.db.get_value("Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name")
	return frappe.get_doc("Workflow", name) if name else None


def _transition_applies(transition, doc):
	if not transition.condition:
		return True
	from frappe.model.workflow import get_workflow_safe_globals

	return bool(frappe.safe_eval(transition.condition, get_workflow_safe_globals(), {"doc": doc.as_dict()}))


def _allowed_transitions(doc):
	"""Transitions the current user may take from the document's current state,
	with conditions (Audited UC branch) evaluated."""
	workflow = _get_workflow()
	if not workflow:
		return []
	current_state = doc.get("workflow_state") or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)
	is_sm = "System Manager" in user_roles

	# PI stages belong to this project's PI, not to every Permanent Employee
	if current_state in ("Draft", STATE_PI_VERIFICATION) and not is_sm and not _is_pi(doc):
		return []

	return [
		t
		for t in workflow.transitions
		if t.state == current_state and (is_sm or t.allowed in user_roles) and _transition_applies(t, doc)
	]


@frappe.whitelist()
def get_uc_request_fields(doc_name=None):
	meta = frappe.get_meta(DOCTYPE)
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
			"default": f.default,
			"fetch_from": f.fetch_from,
			"depends_on": f.depends_on,
		}
		for f in meta.get("fields")
	]

	prefill_data = {}
	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'")
		if frappe.db.exists(DOCTYPE, doc_name):
			prefill_data = frappe.get_doc(DOCTYPE, doc_name).as_dict()

	return {"fields": fields, "prefill_data": prefill_data, "link_options": {}, "child_table_fields": {}}


@frappe.whitelist()
def get_project_details_for_uc(project):
	"""Project block for a new UC Request. Accepts the Project Registration
	name or its project_no."""
	name = (
		project
		if frappe.db.exists("Project Registration", project)
		else frappe.db.get_value("Project Registration", {"project_no": project}, "name")
	)
	if not name:
		return {"status": "error", "message": f"Project '{project}' not found."}
	doc = frappe.new_doc(DOCTYPE)
	doc.project_id = name
	doc.fill_project_details()
	fields = ["project_id", *PROJECT_FIELD_MAP.values(), "funding_agency_name"]
	return {"status": "success", "data": {f: doc.get(f) for f in fields}}


@frappe.whitelist()
def save_uc_request(doc_data):
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data

		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc(DOCTYPE, doc_name)
			if (doc.workflow_state or "Draft") != "Draft" or doc.docstatus != 0:
				return {"status": "info", "message": "Only a Draft UC Request can be edited."}
			if not _is_pi(doc) and not _is_system_manager():
				frappe.throw(_("Only the applicant can edit this UC Request."), frappe.PermissionError)
		else:
			doc = frappe.new_doc(DOCTYPE)
			doc.workflow_state = "Draft"

		for field in ("project_id", "pi_name", "uc_type", "uc_comment_if_any"):
			if field in data and data[field] is not None:
				doc.set(field, data[field])

		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)

		_apply_attachments(doc, data, FORM_ATTACH_FIELDS)
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "UC Request Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_uc_request(docname):
	doc = frappe.get_doc(DOCTYPE, docname)
	current_state = doc.get("workflow_state") or "Draft"
	if current_state != "Draft":
		return {
			"status": "info",
			"message": f"UC Request '{docname}' is already in state '{current_state}'.",
			"docname": docname,
			"workflow_state": current_state,
		}
	if not doc.uc_type:
		return {"status": "error", "message": "Please select the UC Type before submitting."}
	return perform_uc_request_action(docname, "Submit")


@frappe.whitelist()
def get_uc_request_workflow_actions(docname):
	doc = frappe.get_doc(DOCTYPE, docname)
	return list(dict.fromkeys(t.action for t in _allowed_transitions(doc)))


@frappe.whitelist()
def perform_uc_request_action(docname, action):
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.get("workflow_state") or "Draft"

		transition = next((t for t in _allowed_transitions(doc) if t.action == action), None)
		if not transition:
			frappe.throw(
				_("No valid transition found for action '{0}' from state '{1}'.").format(action, current_state)
			)

		# Audited UC: the Registrar-verified copy must be on file before HoS forwards
		if (
			current_state == STATE_REGISTRAR
			and action != "Reject"
			and not (doc.get("registrar_signed_uc") or "").strip()
		):
			frappe.throw(_("Cannot forward: the Registrar-verified UC has not been uploaded by R&D Staff yet."))

		next_state = transition.next_state
		updates = {"workflow_state": next_state}
		if action == ACTION_VERIFY_PRINT:
			updates.update(pi_verified_by=frappe.session.user, pi_verified_on=now_datetime())
		elif action == ACTION_SEND_REGISTRAR:
			updates["hos_printed_on"] = now_datetime()

		state_doc = next((s for s in _get_workflow().states if s.state == next_state), None)
		if state_doc and int(state_doc.doc_status or 0) == 1 and doc.docstatus == 0:
			doc.update(updates)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_workflow = True
			doc.submit()
		else:
			doc.db_set(updates, update_modified=True)

		frappe.db.commit()
		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_uc_request_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "UC Request Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_uc_request_staff_section(doc_data):
	"""R&D Staff attaches the prepared UC / remarks while the request is with them."""
	try:
		if STAFF_ROLE not in frappe.get_roles(frappe.session.user) and not _is_system_manager():
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		doc = frappe.get_doc(DOCTYPE, data.get("name"))
		if not (doc.workflow_state or "").startswith("Pending Staff"):
			frappe.throw(_("R&D Office details can only be updated while the request is pending with Staff."))

		if "staff_remarks" in data:
			frappe.db.set_value(DOCTYPE, doc.name, "staff_remarks", data.get("staff_remarks") or None)
		_apply_attachments(doc, data, ("staff_prepared_uc",))
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "UC Request Staff Update Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def attach_registrar_signed_uc(docname, file_url):
	"""Staff binds an already-uploaded file URL to registrar_signed_uc.
	Replacing an existing copy is allowed."""
	if STAFF_ROLE not in frappe.get_roles(frappe.session.user) and not _is_system_manager():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not file_url:
		frappe.throw(_("file_url is required"))
	if not frappe.db.exists(DOCTYPE, docname):
		frappe.throw(_("Document not found"))
	if (frappe.db.get_value(DOCTYPE, docname, "workflow_state") or "") != STATE_REGISTRAR:
		frappe.throw(
			_("The Registrar copy can only be attached while the request is in '{0}'.").format(STATE_REGISTRAR)
		)

	frappe.db.set_value(DOCTYPE, docname, "registrar_signed_uc", file_url)
	frappe.db.commit()
	return {"status": "success", "docname": docname, "registrar_signed_uc": file_url}


@frappe.whitelist()
def get_pending_registrar_uploads():
	"""UC Requests awaiting the Registrar-verified copy, shaped for the
	Director-Signed PDF Upload page (registrar_signed_uc -> director_signed_pdf)."""
	docs = frappe.get_all(
		DOCTYPE,
		filters={"workflow_state": STATE_REGISTRAR, "docstatus": 0},
		fields=[
			"name",
			"project_no",
			"project_title",
			"principal_investigator_name",
			"implementation_department",
			"uc_type",
			"registrar_signed_uc",
			"modified",
			"workflow_state",
		],
		order_by="modified desc",
	)
	for d in docs:
		d["director_signed_pdf"] = d.pop("registrar_signed_uc")
	return {"status": "success", "data": docs}
