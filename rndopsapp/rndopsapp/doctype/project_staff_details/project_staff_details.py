

# -========================bhasker update

# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json
import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow, get_transitions


def _extract_eval(expression):
	if not expression:
		return None
	expression = str(expression).strip()
	return expression[5:].strip() if expression.startswith("eval:") else expression


class ProjectStaffDetails(Document):
	# Employee ID is allocated when the staff submits the joining form
	# (see `submit_project_staff_details`), not at draft-insert time, so
	# abandoned drafts don't burn numbers in the series.
	def on_update(self):
		self._allocate_leave_if_approved()

	def on_submit(self):
		self._allocate_leave_if_approved()

	def on_update_after_submit(self):
		self._allocate_leave_if_approved()

	def _allocate_leave_if_approved(self):
		if (self.workflow_state or "").strip() != "Approved":
			return

		if getattr(frappe.flags, "allocating_project_staff_leave", False):
			return

		frappe.flags.allocating_project_staff_leave = True
		try:
			_allocate_leave_data_on_approval(self)
		finally:
			frappe.flags.allocating_project_staff_leave = False

	def get_date_of_last_extension(self):
		"""
		Calculates the Date of Last Extension based on the child table `table_ymed` (tenure details).
		Gets the pstd_joining_date from the newest/latest row.
		"""
		tenures = self.get("table_ymed") or []
		valid_tenures = [t for t in tenures if t.pstd_joining_date]

		if not valid_tenures:
			return None

		from frappe.utils import getdate

		sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))
		return sorted_tenures[-1].pstd_joining_date


def generate_emp_id():
	"""
	Allocate the next Employee ID for the current calendar year in the format
	YYYYTS0001 (e.g. 2026TS0001, 2026TS0002 ...).

	Uses Frappe's `make_autoname` which atomically increments the underlying
	`tabSeries` row, so two concurrent submissions can't collide on the same
	number. The series row is auto-created on first use.
	"""
	from frappe.utils import nowdate
	from frappe.model.naming import make_autoname

	year = nowdate()[:4]
	# ".####" -> 4-digit zero-padded counter scoped to the "{year}TS" prefix.
	return make_autoname(f"{year}TS.####")


@frappe.whitelist()
def get_next_emp_id():
	from frappe.utils import nowdate

	year = nowdate()[:4]
	series_key = f"{year}TS"
	current = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = %s", series_key)
	next_num = (current[0][0] if current else 0) + 1
	return f"{series_key}{str(next_num).zfill(4)}"


@frappe.whitelist()
def get_project_staff_details_fields(doc_name=None):
	"""
	Returns field metadata, prefill data (if doc_name provided), and link options.
	"""
	meta = frappe.get_meta("Project Staff Details")

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
			"description": f.description,
			"default": f.default,
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			"depends_on_eval": _extract_eval(f.depends_on),
			"mandatory_depends_on_eval": _extract_eval(f.mandatory_depends_on),
			"read_only_depends_on_eval": _extract_eval(f.read_only_depends_on),
		}
		if f.fieldtype == "Table" and f.options:
			child_meta = frappe.get_meta(f.options)
			field_data["child_fields"] = [
				{
					"fieldname": cf.fieldname,
					"label": cf.label,
					"fieldtype": cf.fieldtype,
					"options": cf.options,
					"mandatory": cf.reqd,
					"hidden": cf.hidden,
					"read_only": cf.read_only,
					"in_list_view": cf.in_list_view,
				}
				for cf in child_meta.get("fields")
			]
		fields.append(field_data)

	prefill_data = {}
	link_options = {}

	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'")
		doc = frappe.get_doc("Project Staff Details", doc_name)
		prefill_data = doc.as_dict()

	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": "Project Staff Details", "enabled": 1},
			fields=["name", "script", "view"],
		)
		for script in scripts:
			client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
	}


@frappe.whitelist()
def save_project_staff_details_data(data):
	"""
	Creates a new Project Staff Details record or updates an existing one.
	"""
	from frappe.utils.file_manager import save_file

	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("Project Staff Details", doc_name)
			if doc.docstatus == 2:
				frappe.throw(_("Cannot edit a cancelled document."))
			if doc.docstatus == 1:
				frappe.throw(_("Cannot edit a submitted document. Use the workflow action endpoint instead."))
		else:
			# Enforce a single Joining Form per candidate. If a Project Staff Details
			# already exists for this candidate (application_id), do not create a
			# second one — the existing record must be opened instead.
			application_id = data.get("application_id")
			if application_id:
				existing = frappe.db.get_value(
					"Project Staff Details",
					{"application_id": application_id},
					["name", "workflow_state"],
					as_dict=True,
				)
				if existing:
					frappe.throw(
						_(
							"A Joining Form already exists for this candidate ({0}). Open the existing record instead of creating a new one."
						).format(existing.name)
					)
			doc = frappe.new_doc("Project Staff Details")

		# NOTE: ps_emp_id is intentionally NOT in this list. It is server-owned
		# and gets allocated exactly once on the first successful Submit (see
		# `submit_project_staff_details`). Accepting it from the client caused
		# the preview value (e.g. 2026TS0001) to be persisted on save, which
		# then short-circuited the real allocation at submit time and made
		# every candidate end up with the same ID.
		field_mapping = [
			"scr_id",
			"pi_id",
			"application_id",
			"project_no",
			"ps_first_name",
			"ps_middle_name",
			"ps_last_name",
			"ps_gender",
			"ps_email_id",
			"ps_phone_number",
			"ps_department",
			"ps_designation",
			"ps_date_of_birth",
			"ps_joining_date",
			"ps_term_completion_date",
			"ps_fathers_name",
			"ps_present_address",
			"ps_permanent_address",
			"ps_pan",
			"ps_aadhar_number",
			"ps_blood_group",
			"ps_maritial_status",
			"ps_basic_salary",
			"ps_hra",
			"ps_ma",
			"ps_ta",
			"ps_ta_amount",
			"ps_hostel",
			"ps_citizenship",
			"ps_aon",
			"ps_mro",
			"ps_jrn",
			"bank_account_number",
			"erp_mail",
			"workflow_state",
			"amended_from",
		]

		for field in field_mapping:
			if field in data and data[field] not in [None, ""]:
				doc.set(field, data[field])

		# Attach fields: frontend sends either an existing file URL (str)
		# or a {file_name, file_data} base64 payload (dict, handled after the
		# doc has a name).
		attach_fields = ["ps_photo", "ps_signature", "ps_medical_certificate"]
		for field in attach_fields:
			value = data.get(field)
			if isinstance(value, str) and value:
				doc.set(field, value)

		# Handle tenure details child table
		tenure_rows = data.get("table_ymed", [])
		if tenure_rows is not None:
			doc.set("table_ymed", [])
			child_fields = [
				"pstd_joining_date",
				"pstd_term_completion_date",
				"pstd_basic_salary",
				"pstd_increment",
				"pstd_hra",
				"pstd_extension_sought",
				"pstd_joining_number",
				"pstd_pi_extension_sought",
				"pstd_staff_extension_sought",
				"pstd_tentative_joining_date",
			]
			for row in tenure_rows:
				doc.append(
					"table_ymed", {f: row.get(f) for f in child_fields if row.get(f) not in [None, ""]}
				)

		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)

		# Now that the doc has a name, save any base64 file uploads and link them.
		# Frontend sends `file_data` as pure base64 (no data URL prefix). One bad
		# attachment must not abort the entire save — log and continue.
		attachments_updated = False
		for field in attach_fields:
			value = data.get(field)
			if not (isinstance(value, dict) and value.get("file_data")):
				continue

			file_data = value["file_data"]
			# Defensive: strip a `data:<mime>;base64,` prefix in case an older
			# client sends a data URL. save_file(decode=True) cannot handle it.
			if isinstance(file_data, str) and file_data.startswith("data:") and "," in file_data:
				file_data = file_data.split(",", 1)[1]

			try:
				saved_file = save_file(
					value.get("file_name", "attachment"),
					file_data,
					"Project Staff Details",
					doc.name,
					decode=True,
					is_private=1,
					df=field,
				)
				doc.set(field, saved_file.file_url)
				attachments_updated = True
			except Exception as upload_err:
				frappe.log_error(
					frappe.get_traceback(),
					f"PSD attach upload failed for field {field} on {doc.name}",
				)
				# Surface as a non-fatal message; keep going with the save.
				frappe.msgprint(
					_("Could not save attachment for {0}: {1}").format(field, upload_err),
					indicator="orange",
				)

		if attachments_updated:
			doc.save(ignore_permissions=True)

		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Save Error")
		frappe.throw(_("Failed to save Project Staff Details: {0}").format(str(e)))


@frappe.whitelist()
def get_project_staff_details_list(filters=None, limit=100000):
	"""
	Returns a paginated list of Project Staff Details records.
	"""
	try:
		parsed_filters = {}
		if filters:
			parsed_filters = json.loads(filters) if isinstance(filters, str) else filters

		records = frappe.get_all(
			"Project Staff Details",
			filters=parsed_filters,
			fields=[
				"name",
				"scr_id",
				"pi_id",
				"project_no",
				"ps_emp_id",
				"ps_first_name",
				"ps_middle_name",
				"ps_last_name",
				"ps_gender",
				"ps_email_id",
				"ps_phone_number",
				"ps_department",
				"ps_designation",
				"ps_date_of_birth",
				"ps_joining_date",
				"ps_term_completion_date",
				"ps_aon",
				"ps_jrn",
				"bank_account_number",
				"erp_mail",
				"workflow_state",
				"docstatus",
				"modified",
				"creation",
			],
			order_by="modified desc",
			limit=int(limit),
		)
		return {"status": "success", "data": records}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Staff Details List Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_joining_by_application(application_id):
	"""
	Returns the existing Joining Form (Project Staff Details) for a candidate,
	identified by application_id, or None. Used by the form to load the existing
	record (view/edit) instead of creating a duplicate.
	"""
	if not application_id:
		return {"status": "success", "data": None}

	rec = frappe.db.get_value(
		"Project Staff Details",
		{"application_id": application_id},
		["name", "workflow_state", "docstatus"],
		as_dict=True,
	)
	# A doc is considered "submitted" (view-only) once it has moved past Draft.
	is_submitted = bool(rec) and (
		int(rec.docstatus or 0) >= 1 or (rec.workflow_state or "").strip().lower() not in ("", "draft")
	)
	return {
		"status": "success",
		"data": (
			{
				"docname": rec.name,
				"workflow_state": rec.workflow_state,
				"docstatus": rec.docstatus,
				"is_submitted": is_submitted,
			}
			if rec
			else None
		),
	}


@frappe.whitelist()
def update_joining_report_number(docname, ps_jrn):
	"""
	Update only the joining report number (ps_jrn) on a Project Staff Details doc.
	Uses db.set_value so it works even when the document is submitted, mirroring
	the appointment/medical report number update endpoints on Selection Candidate
	Details.
	"""
	if not docname:
		return {"status": "error", "message": "docname is required"}

	if not frappe.db.exists("Project Staff Details", docname):
		return {"status": "error", "message": f"Document '{docname}' not found"}

	try:
		frappe.db.set_value("Project Staff Details", docname, "ps_jrn", ps_jrn)
		frappe.db.commit()
		return {"status": "success", "docname": docname, "ps_jrn": ps_jrn}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"update ps_jrn failed for {docname}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def delete_project_staff_details(docname):
	"""
	Deletes a Project Staff Details document (only Draft records).
	"""
	try:
		doc = frappe.get_doc("Project Staff Details", docname)

		if doc.docstatus == 1:
			frappe.throw(_("Cannot delete a submitted document. Cancel it first."))

		frappe.delete_doc("Project Staff Details", docname, ignore_permissions=True)
		frappe.db.commit()
		return {"status": "success", "message": _("Record '{0}' deleted successfully.").format(docname)}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Delete Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_project_staff_details_workflow_actions(docname):
	"""
	Returns the workflow actions available to the current user for this doc,
	based on its current workflow_state and the user's roles.
	"""
	try:
		doc = frappe.get_doc("Project Staff Details", docname)
		transitions = get_transitions(doc)
		actions = list(dict.fromkeys([t.get("action") for t in transitions]))
		return {
			"status": "success",
			"workflow_state": doc.workflow_state,
			"docstatus": doc.docstatus,
			"actions": actions,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Workflow Actions Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def perform_project_staff_details_action(docname, action):
	"""
	Applies a workflow action (Submit / Forward / Approve / Reject / Put Back ...)
	to a Project Staff Details document. Uses Frappe's apply_workflow which
	handles state transition, permission check, and docstatus updates.
	"""
	try:
		doc = frappe.get_doc("Project Staff Details", docname)
		updated = apply_workflow(doc, action)

		# On ADO, RnD approval, create / update the corresponding Frappe User.
		if action == "Approve" and "Ado_RnD" in frappe.get_roles():
			_sync_project_staff_to_user(updated)

		# Once the document reaches the 'Approved' state, capture a tenure row
		# (joining date / term completion date / basic salary) in the child table.
		if (updated.workflow_state or "").strip() == "Approved":
			_populate_tenure_on_approval(updated)
			_allocate_leave_data_on_approval(updated)

		frappe.db.commit()

		return {
			"status": "success",
			"message": _("Action '{0}' completed. New state: {1}").format(action, updated.workflow_state),
			"docname": docname,
			"workflow_state": updated.workflow_state,
			"docstatus": updated.docstatus,
			"next_actions": get_project_staff_details_workflow_actions(docname).get("actions", []),
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Action Error")
		return {"status": "error", "message": str(e)}


def _populate_tenure_on_approval(doc):
	"""
	On approval, add a row to the 'Project Staff Tenure Details' (table_ymed)
	child table capturing the joining date, term completion date and basic salary
	from the parent. Other child fields are left blank. Idempotent: skips if a row
	with the same joining date already exists.
	"""
	joining_date = doc.get("ps_joining_date")
	term_completion_date = doc.get("ps_term_completion_date")
	basic_salary = doc.get("ps_basic_salary")

	# Nothing meaningful to record.
	if not (joining_date or term_completion_date or basic_salary):
		return

	# Avoid duplicating the row if approval is re-triggered.
	for row in doc.get("table_ymed") or []:
		if str(row.pstd_joining_date or "") == str(joining_date or "") and str(
			row.pstd_basic_salary or ""
		) == str(basic_salary or ""):
			return

	doc.append(
		"table_ymed",
		{
			"pstd_joining_date": joining_date,
			"pstd_term_completion_date": term_completion_date,
			"pstd_basic_salary": basic_salary,
		},
	)
	doc.save(ignore_permissions=True)


def round_up_to_half(value):
	return math.ceil(value * 2) / 2


def get_tenure_months(joining_date, term_completion_date):
	if not joining_date or not term_completion_date:
		return 0
	from frappe.utils import getdate

	j_date = getdate(joining_date)
	c_date = getdate(term_completion_date)
	if c_date < j_date:
		return 0
	# Calculate days difference inclusively
	days_diff = (c_date - j_date).days + 1
	# Standard average days per month is 30.437
	return int(round(days_diff / 30.437))


def _allocate_leave_data_on_approval(doc):
	try:
		# Always reload key fields from DB — the in-memory doc may predate the
		# ps_emp_id assignment that happens at Submit time.
		ps_data = frappe.db.get_value(
			"Project Staff Details",
			doc.name,
			[
				"ps_emp_id",
				"erp_mail",
				"ps_joining_date",
				"ps_term_completion_date",
				"ps_department",
			],
			as_dict=True,
		)

		if not ps_data:
			frappe.log_error(
				f"Cannot allocate leave for Project Staff Details {doc.name}: record not found in DB.",
				"Leave Allocation Error",
			)
			return

		emp_id = ps_data.ps_emp_id

		if not emp_id:
			frappe.log_error(
				f"Cannot allocate leave for Project Staff Details {doc.name}: ps_emp_id is not set.",
				"Leave Allocation Error",
			)
			return

		joining_date = ps_data.ps_joining_date or doc.ps_joining_date
		term_completion_date = ps_data.ps_term_completion_date or doc.ps_term_completion_date

		tenure_months = get_tenure_months(joining_date, term_completion_date)

		if tenure_months <= 0:
			frappe.log_error(
				f"Cannot allocate leave for Project Staff Details {doc.name}: "
				f"tenure_months={tenure_months} "
				f"(joining={joining_date}, completion={term_completion_date}).",
				"Leave Allocation Error",
			)
			return

		# Round up to the next 0.5
		cl = round_up_to_half(tenure_months * 8.0 / 11.0)
		el = round_up_to_half(max(0, (tenure_months - 1) * 2.5))

		# emp_username derived from erp_mail; optional — leave blank if not yet set.
		erp_mail = (ps_data.erp_mail or "").strip()
		emp_username = erp_mail.split("@", 1)[0] if "@" in erp_mail else ""

		department = ps_data.ps_department or doc.ps_department or ""

		# Check by both document name (autoname=field:emp_id) and by field value
		# to handle any existing records that may have been named differently.
		existing_name = frappe.db.get_value("Leave Data", {"emp_id": emp_id}, "name")

		if existing_name:
			leave_data_doc = frappe.get_doc("Leave Data", existing_name)

			if emp_username:
				leave_data_doc.emp_username = emp_username

			leave_data_doc.emp_class = "Project Staff"
			leave_data_doc.department = department
			leave_data_doc.cl = cl
			leave_data_doc.el = el

			leave_data_doc.save(ignore_permissions=True)

		else:
			leave_data_doc = frappe.new_doc("Leave Data")
			leave_data_doc.emp_id = emp_id
			leave_data_doc.emp_username = emp_username
			leave_data_doc.emp_class = "Project Staff"
			leave_data_doc.department = department
			leave_data_doc.cl = cl
			leave_data_doc.el = el

			leave_data_doc.insert(ignore_permissions=True)

	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Failed to allocate leave for Project Staff Details {doc.name}",
		)


def _sync_project_staff_to_user(doc):
	"""
	Creates (or updates) a Frappe User from an approved Project Staff Details doc.
	Field mapping:
	  email                -> erp_mail               (full ERP mail address)
	  username             -> erp_mail.split('@')[0] (local part of ERP mail)
	  first/middle/last    -> ps_first_name / ps_middle_name / ps_last_name
	  full_name            -> first + middle + last
	  employee_id          -> ps_emp_id
	  department_name      -> ps_department
	  designation_name     -> ps_designation
	  piheadmentor_user_id -> pi_id
	"""
	from rndopsapp.rndopsapp.user_api.user_api import save_user_data

	erp_mail = (doc.erp_mail or "").strip()
	if not erp_mail or "@" not in erp_mail:
		frappe.log_error(
			"Project Staff Details {0} has no valid erp_mail; skipping User creation.".format(doc.name),
			"Project Staff User Sync",
		)
		return

	full_name = " ".join(p for p in [doc.ps_first_name, doc.ps_middle_name, doc.ps_last_name] if p)

	roles = ["project staff"]
	if frappe.db.exists("User", erp_mail):
		existing_roles = [r.role for r in frappe.get_doc("User", erp_mail).roles]
		for r in existing_roles:
			if r not in roles:
				roles.append(r)

	payload = {
		"email": erp_mail,
		"username": erp_mail.split("@", 1)[0],
		"first_name": doc.ps_first_name,
		"middle_name": doc.ps_middle_name,
		"last_name": doc.ps_last_name,
		"full_name": full_name,
		"employee_id": doc.ps_emp_id,
		"department_name": doc.ps_department,
		"designation_name": doc.ps_designation,
		"piheadmentor_user_id": doc.pi_id,
		"enabled": 1,
		"roles": roles,
	}

	save_user_data(payload)


def _update_single_field(docname, fieldname, value):
	"""Internal helper: update exactly one field on a Project Staff Details doc."""
	if not docname:
		return {"status": "error", "message": "docname is required"}

	if not frappe.db.exists("Project Staff Details", docname):
		return {"status": "error", "message": f"Document '{docname}' not found"}

	try:
		frappe.db.set_value("Project Staff Details", docname, fieldname, value)
		frappe.db.commit()
		return {"status": "success", "docname": docname, fieldname: value}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"update {fieldname} failed for {docname}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_joining_report_number(docname, joining_report_number):
	"""Update only the ps_jrn (Joining Report Number) field."""
	return _update_single_field(docname, "ps_jrn", joining_report_number)


@frappe.whitelist()
def submit_project_staff_details(docname):
	"""
	Staff-facing submit endpoint. Triggers the 'Submit' workflow action
	(Draft -> Pending HoS Approval) and, on the *first* submit, allocates a
	fresh Employee ID for the candidate (idempotent: re-submitting an already
	allotted record reuses the existing ps_emp_id rather than burning a new
	one from the series).

	Returns the allotted `ps_emp_id` alongside the workflow result so the UI
	can surface it in the post-submit confirmation alert without an extra
	round trip.
	"""
	if not docname:
		return {"status": "error", "message": "docname is required"}

	if not frappe.db.exists("Project Staff Details", docname):
		return {"status": "error", "message": f"Document '{docname}' not found"}

	# Capture the workflow state BEFORE we attempt the transition. We only
	# allocate a fresh Employee ID when this call is the doc's first Submit
	# (was Draft / blank going in). Doing the allocation AFTER apply_workflow
	# succeeds means a failed/forbidden transition can't burn a series number.
	before_state = (
		(frappe.db.get_value("Project Staff Details", docname, "workflow_state") or "").strip().lower()
	)

	result = perform_project_staff_details_action(docname, "Submit")

	if isinstance(result, dict) and result.get("status") == "success":
		if before_state in ("", "draft"):
			# First successful Submit — allocate a fresh ID, overwriting any
			# stale preview value (e.g. "2026TS0001") that earlier client builds
			# may have written into ps_emp_id via the save handler.
			emp_id = generate_emp_id()
			frappe.db.set_value("Project Staff Details", docname, "ps_emp_id", emp_id)
			frappe.db.commit()
		else:
			emp_id = frappe.db.get_value("Project Staff Details", docname, "ps_emp_id")
		result["ps_emp_id"] = emp_id

		if (result.get("workflow_state") or "").strip() == "Approved":
			_allocate_leave_data_on_approval(frappe.get_doc("Project Staff Details", docname))
			frappe.db.commit()
	return result


@frappe.whitelist()
def get_my_project_staff_details():
	"""
	Return the Project Staff Details row whose `erp_mail` matches the
	logged-in user's email. Uses session user server-side so the client
	does not need List permission on Project Staff Details.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)

	rows = frappe.get_all(
		"Project Staff Details",
		filters={"erp_mail": user},
		fields=[
			"name",
			"erp_mail",
			"ps_first_name",
			"ps_middle_name",
			"ps_last_name",
			"ps_department",
			"ps_designation",
			"project_no",
			"bank_account_number",
			"ps_aadhar_number",
			"ps_pan",
			"ps_joining_date",
			"ps_term_completion_date",
		],
		limit=1,
		ignore_permissions=True,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def get_my_basic_details():
	"""
	Return Basic Details for the currently logged-in user by joining the
	User doctype's `username` against the part of `erp_mail` before '@'
	in Project Staff Details.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)

	rows = frappe.db.sql(
		"""
		SELECT
			psd.name,
			psd.erp_mail,
			psd.ps_first_name,
			psd.ps_middle_name,
			psd.ps_last_name,
			psd.ps_fathers_name,
			psd.ps_gender,
			psd.ps_date_of_birth,
			psd.ps_blood_group,
			psd.ps_maritial_status,
			psd.ps_citizenship,
			psd.ps_phone_number,
			psd.ps_email_id,
			psd.ps_present_address,
			psd.ps_permanent_address,
			psd.ps_department,
			COALESCE(dept.dept_name, psd.ps_department) AS ps_department_name,
			psd.ps_designation,
			psd.ps_emp_id,
			psd.project_no,
			pr.project_title AS project_name,
			psd.ps_joining_date,
			psd.ps_term_completion_date,
			psd.ps_basic_salary,
			psd.bank_account_number,
			psd.ps_aadhar_number,
			psd.ps_pan,
			psd.ps_photo,
			u.username,
			u.full_name,
			u.email
		FROM `tabProject Staff Details` psd
		INNER JOIN `tabUser` u
			ON u.username = SUBSTRING_INDEX(psd.erp_mail, '@', 1)
		LEFT JOIN `tabDepartment_prornd` dept
			ON dept.name = psd.ps_department
		LEFT JOIN `tabProject Registration` pr
			ON pr.project_no = psd.project_no
		WHERE u.name = %(user)s
		LIMIT 1
		""",
		{"user": user},
		as_dict=True,
	)
	if not rows:
		return None

	res = dict(rows[0])

	# Fetch Date of Last Extension
	doc = frappe.get_doc("Project Staff Details", res["name"])
	res["ex_last_ex_date"] = doc.get_date_of_last_extension()

	# Fetch latest tenure details from the child table
	tenures = doc.get("table_ymed") or []
	valid_tenures = [t for t in tenures if t.pstd_joining_date]
	res["tenures"] = []
	if valid_tenures:
		from frappe.utils import getdate

		sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))
		latest_tenure = sorted_tenures[-1]

		# Preserve original parent ps_joining_date and ps_term_completion_date.
		# Expiry of present tenure is fetched from the latest tenure's completion date.
		res["ex_date_of_expiry"] = latest_tenure.pstd_term_completion_date
		res["ps_basic_salary"] = latest_tenure.pstd_basic_salary

		# Full tenure history (each term's joining + completion + basic), oldest first.
		res["tenures"] = [
			{
				"joining_date": str(t.pstd_joining_date) if t.pstd_joining_date else None,
				"term_completion_date": str(t.pstd_term_completion_date) if t.pstd_term_completion_date else None,
				"basic_salary": t.pstd_basic_salary,
			}
			for t in sorted_tenures
		]

	j_date = res.get("ps_joining_date")
	if j_date:
		from frappe.utils import getdate, today

		jd = getdate(j_date)
		cd = getdate(today())
		if cd >= jd:
			days_diff = (cd - jd).days + 1
			months = int(days_diff / 30.437)
			if months < 1:
				res["no_of_months_worked"] = 0
				res["no_of_days_worked"] = days_diff
			else:
				res["no_of_months_worked"] = months
				res["no_of_days_worked"] = 0
		else:
			res["no_of_months_worked"] = 0
			res["no_of_days_worked"] = 0
	else:
		res["no_of_months_worked"] = 0
		res["no_of_days_worked"] = 0

	return res
