# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json
import os

import frappe
from frappe import _
from frappe.model.document import Document


def _student_field_order_from_json():
	"""Read the on-disk Top Up Fellowship Student JSON to get the authoritative
	field_order. Acts as a safety net against stale DocField idx values in the DB."""
	try:
		here = os.path.dirname(os.path.abspath(__file__))
		child_json = os.path.normpath(
			os.path.join(here, "..", "top_up_fellowship_student", "top_up_fellowship_student.json")
		)
		with open(child_json, "r") as fh:
			data = json.load(fh)
		return list(data.get("field_order") or [])
	except Exception:
		return []


PARENT_SIMPLE_FIELDS = [
	"project_code",
	"project_title",
	"account_head",
	"pi_webmail",
	"coordinating_pi_webmail",
	"send_to_faculty_admission",
	"faculty_admission_pdf",
	"checkbox1",
	"checkbox2",
	"checkbox3",
	"amended_from",
]

STUDENT_ROW_FIELDS = [
	"email_of_student",
	"roll_number",
	"dept_centre",
	"programme",
	"contact_number",
	"period_from",
	"period_to",
	"hours_per_month",
	"rate_per_hour",
	"total_amount_per_month",
	"account_holder_name",
	"account_number",
	"bank_name",
	"ifsc",
	"branch_code",
]


class TopUpFellowship(Document):
	def before_save(self):
		# Auto-compute total_amount_per_month per student row = hours * rate,
		# but only when the user hasn't set an explicit total.
		for row in self.get("students") or []:
			try:
				if not row.total_amount_per_month:
					hours = int(row.hours_per_month or 0)
					rate = int(row.rate_per_hour or 0)
					row.total_amount_per_month = hours * rate
			except Exception:
				pass


def extract_eval_expression(expression):
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


def _get_users_with_role(role_name):
	"""Return [{value, label}] of enabled Users that hold the given role."""
	try:
		role_rows = frappe.get_all(
			"Has Role",
			filters={"role": role_name, "parenttype": "User"},
			fields=["parent"],
			limit_page_length=0,
		)
		emails = list({r.parent for r in role_rows if r.parent})
		if not emails:
			return []
		users = frappe.get_all(
			"User",
			filters={"name": ["in", emails], "enabled": 1},
			fields=["name", "full_name"],
			limit_page_length=0,
		)
		return [
			{
				"value": u.name,
				"label": f"{u.full_name} ({u.name})" if u.full_name else u.name,
			}
			for u in users
		]
	except Exception:
		return []


def _get_student_options():
	"""Return [{value, label}] of Users with role = Student."""
	return _get_users_with_role("Student")


@frappe.whitelist()
def get_top_up_fellowship_fields(doc_name=None):
	"""
	Return Top Up Fellowship field metadata + prefill data.
	- doc_name: Project Registration.name (optional). Used to prefill project info.
	"""
	meta = frappe.get_meta("Top Up Fellowship")
	fields = [_serialize_field(f) for f in meta.get("fields")]

	# Child table fields for "Top Up Fellowship Student"
	# Sort by the on-disk JSON's field_order so renames/reorders show up
	# correctly without needing a full reload-doctype to fix DocField idx.
	child_table_fields = {}
	try:
		child_meta = frappe.get_meta("Top Up Fellowship Student")
		field_by_name = {cf.fieldname: cf for cf in child_meta.get("fields")}
		ordered_names = _student_field_order_from_json()
		# Append any DB fields not in the JSON order at the end (graceful fallback)
		for fn in field_by_name:
			if fn not in ordered_names:
				ordered_names.append(fn)
		child_table_fields["students"] = [
			_serialize_field(field_by_name[fn]) for fn in ordered_names if fn in field_by_name
		]
	except Exception:
		child_table_fields["students"] = []

	prefill_data = {}
	link_options = {}
	related_project_data = {}

	# Note: pi_webmail (Supervisor / Faculty Adviser) is NOT prefilled.
	# Staff/PI selects from the Permanent Employee dropdown.

	# Department link options (used by child row dept_centre)
	try:
		depts = frappe.get_all(
			"Department_prornd",
			fields=["name", "dept_name"],
			limit_page_length=500,
		)
		link_options["dept_centre"] = [
			{"value": d.name, "label": d.dept_name or d.name} for d in depts
		]
	except Exception:
		pass

	# Student options for child row email_of_student
	link_options["email_of_student"] = _get_student_options()

	# Permanent Employee options for pi_webmail (Supervisor / Faculty Adviser)
	link_options["pi_webmail"] = _get_users_with_role("Permanent Employee")

	# Budget Head options for account_head (label = actual budget_head name)
	try:
		heads = frappe.get_all(
			"Budget Head",
			fields=["name", "budget_head"],
			limit_page_length=500,
		)
		link_options["account_head"] = [
			{"value": h.name, "label": h.budget_head or h.name} for h in heads
		]
	except Exception:
		pass

	# Project Registration options for project_code (label shows the code, not the title)
	try:
		projects = frappe.get_all(
			"Project Registration",
			fields=["name", "project_title"],
			limit_page_length=500,
		)
		link_options["project_code"] = [
			{
				"value": p.name,
				"label": p.name if not p.project_title else f"{p.name} — {p.project_title}",
			}
			for p in projects
		]
	except Exception:
		pass

	# If a project is provided via URL, prefill project_code/title.
	# The URL param can be the PR's doc name OR the human-readable project_no —
	# try both so the form works no matter which is passed.
	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'").strip()
		try:
			project = frappe.db.get_value(
				"Project Registration",
				doc_name,
				["name", "project_title", "project_no", "pi_webmail"],
				as_dict=True,
			)
			if not project:
				# Try resolving as project_no instead
				match = frappe.get_all(
					"Project Registration",
					filters={"project_no": doc_name},
					fields=["name", "project_title", "project_no", "pi_webmail"],
					limit_page_length=1,
				)
				project = match[0] if match else None

			if project:
				related_project_data = project
				prefill_data["project_code"] = project.get("name")
				prefill_data["project_title"] = project.get("project_title") or ""
				if project.get("pi_webmail"):
					prefill_data["coordinating_pi_webmail"] = project["pi_webmail"]
		except Exception:
			pass

	return {
		"fields": fields,
		"child_table_fields": child_table_fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_project_data": related_project_data,
	}


@frappe.whitelist()
def save_top_up_fellowship_data(data):
	"""Save (insert or update) a Top Up Fellowship document. Expects JSON string or dict."""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		docname = data.get("name")
		if docname:
			doc = frappe.get_doc("Top Up Fellowship", docname)
		else:
			doc = frappe.new_doc("Top Up Fellowship")

		for field in PARENT_SIMPLE_FIELDS:
			if field in data:
				val = data[field]
				if field.startswith("checkbox"):
					doc.set(field, 1 if val in [1, "1", True, "True"] else 0)
				else:
					doc.set(field, val if val != "null" else None)

		# Child table: students
		students_data = data.get("students", [])
		if isinstance(students_data, str):
			students_data = json.loads(students_data)

		if students_data is not None:
			doc.set("students", [])
			for row in students_data:
				clean = {k: row.get(k) for k in STUDENT_ROW_FIELDS if k in row}
				doc.append("students", clean)

		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_student_details(email):
	"""Return roll number (employee_id) and department for a student User."""
	try:
		if not email:
			return {}
		user = frappe.db.get_value(
			"User",
			email,
			["employee_id", "department_name", "full_name"],
			as_dict=True,
		)
		if not user:
			return {}
		return {
			"roll_number": user.get("employee_id") or "",
			"dept_centre": user.get("department_name") or "",
			"full_name": user.get("full_name") or "",
		}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship get_student_details")
		return {}


MONTHLY_CAP_PER_STUDENT = 25000


def _parse_amount(val):
	try:
		if val in (None, ""):
			return 0.0
		return float(val)
	except (TypeError, ValueError):
		return 0.0


@frappe.whitelist()
def get_students_monthly_summary(emails, month, year, exclude_docname=None):
	"""
	Return per-student totals (honorarium + top-up) for the given month/year.
	- emails: JSON array (or list) of student emails.
	- month, year: ints (1-12, e.g. 2026).
	- exclude_docname: optional Top Up Fellowship docname to skip (when editing the same doc).

	Returns: {
		"cap": 25000,
		"summary": {
			"<email>": {
				"honorarium": <float>,
				"top_up": <float>,
				"total": <float>,
				"remaining": <float>,
			},
			...
		}
	}
	"""
	if isinstance(emails, str):
		try:
			emails = json.loads(emails)
		except Exception:
			emails = [emails]
	emails = [e for e in (emails or []) if e]
	try:
		month = int(month)
		year = int(year)
	except (TypeError, ValueError):
		return {"cap": MONTHLY_CAP_PER_STUDENT, "summary": {}}

	summary = {e: {"honorarium": 0.0, "top_up": 0.0} for e in emails}
	if not emails:
		return {"cap": MONTHLY_CAP_PER_STUDENT, "summary": {}}

	# Honorarium: honorarium_table rows with web_mail_id matching, where the
	# row's [from, to] range overlaps the target month. Only Submitted
	# disbursals (docstatus=1) count toward the cap.
	#
	# Overlap rule: from <= last day of month  AND  COALESCE(to, from) >= first day.
	# If `to` is null, fall back to `from` so single-day disbursals still match.
	try:
		honorarium_rows = frappe.db.sql(
			"""
			SELECT child.web_mail_id AS email, child.amount AS amount
			FROM `tabhonorarium_table` AS child
			INNER JOIN `tabDisbursal of Honorarium` AS parent
				ON child.parent = parent.name
			WHERE child.web_mail_id IN %(emails)s
				AND child.`from` IS NOT NULL
				AND child.`from` <= LAST_DAY(%(month_start)s)
				AND COALESCE(child.`to`, child.`from`) >= %(month_start)s
				AND parent.workflow_state = 'Approved'
			""",
			{
				"emails": tuple(emails),
				"month_start": f"{year:04d}-{month:02d}-01",
			},
			as_dict=True,
		)
		for r in honorarium_rows:
			if r.email in summary:
				summary[r.email]["honorarium"] += _parse_amount(r.amount)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship monthly summary (honorarium)")

	# Top Up Fellowship: child rows with email_of_student matching, where the row's
	# [period_from, period_to] overlaps the target month. `total_amount_per_month`
	# is the per-month amount, so it is counted once per overlapping month.
	# Exclude the current doc if editing.
	try:
		params = {
			"emails": tuple(emails),
			"month_start": f"{year:04d}-{month:02d}-01",
		}
		exclude_clause = ""
		if exclude_docname:
			exclude_clause = "AND parent.name != %(exclude_docname)s"
			params["exclude_docname"] = exclude_docname

		top_up_rows = frappe.db.sql(
			f"""
			SELECT child.email_of_student AS email,
				child.total_amount_per_month AS amount
			FROM `tabTop Up Fellowship Student` AS child
			INNER JOIN `tabTop Up Fellowship` AS parent
				ON child.parent = parent.name
			WHERE child.email_of_student IN %(emails)s
				AND child.period_from IS NOT NULL
				AND child.period_from <= LAST_DAY(%(month_start)s)
				AND COALESCE(child.period_to, child.period_from) >= %(month_start)s
				AND parent.workflow_state = 'Approved'
				{exclude_clause}
			""",
			params,
			as_dict=True,
		)
		for r in top_up_rows:
			if r.email in summary:
				summary[r.email]["top_up"] += _parse_amount(r.amount)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship monthly summary (top up)")

	# Compute totals and remaining headroom
	out = {}
	for e, v in summary.items():
		total = v["honorarium"] + v["top_up"]
		out[e] = {
			"honorarium": round(v["honorarium"], 2),
			"top_up": round(v["top_up"], 2),
			"total": round(total, 2),
			"remaining": round(max(0.0, MONTHLY_CAP_PER_STUDENT - total), 2),
		}

	return {"cap": MONTHLY_CAP_PER_STUDENT, "summary": out}


TOP_UP_DOCTYPE = "Top Up Fellowship"


@frappe.whitelist()
def get_top_up_fellowship_workflow_actions(docname):
	"""Available workflow actions for the current user at the doc's current state."""
	doc = frappe.get_doc(TOP_UP_DOCTYPE, docname)
	current_state = doc.workflow_state or "Draft"

	workflow_name = frappe.get_value("Workflow", {"document_type": TOP_UP_DOCTYPE}, "name")
	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	user_roles = frappe.get_roles(frappe.session.user)
	actions = [
		t.action
		for t in workflow.transitions
		if t.state == current_state and t.allowed in user_roles
	]
	# de-dup while preserving order
	return list(dict.fromkeys(actions))


@frappe.whitelist()
def perform_top_up_fellowship_action(docname, action):
	"""Execute a workflow transition. Writes workflow_state + docstatus directly
	to bypass validate_workflow (API callers lack desk roles so the standard
	doc.save()/doc.submit() path would reject the transition)."""
	try:
		doc = frappe.get_doc(TOP_UP_DOCTYPE, docname)
		current_state = doc.workflow_state or "Draft"

		workflow_name = frappe.get_value("Workflow", {"document_type": TOP_UP_DOCTYPE}, "name")
		if not workflow_name:
			frappe.throw(f"Workflow not found for {TOP_UP_DOCTYPE}.")

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				break

		if not next_state:
			frappe.throw(f"No valid transition for action '{action}' from state '{current_state}'.")

		# Gate: R&D Staff cannot Forward from Pending Staff Approval until they
		# have (1) sent the application to Faculty Admission for signing and
		# (2) uploaded the signed PDF that came back.
		if current_state == "Pending Staff Approval" and action.lower() == "forward":
			if not doc.send_to_faculty_admission:
				frappe.throw(
					"Send the application to Faculty Admission first (download PDF)."
				)
			if not (doc.faculty_admission_pdf and str(doc.faculty_admission_pdf).strip()):
				frappe.throw(
					"Upload the Faculty Admission signed PDF before forwarding to HoS."
				)
			# (3) a commit must have been submitted (Kafka Commit Staging row exists)
			has_commit = frappe.db.exists(
				"Kafka Commit Staging",
				{
					"reference_doctype": TOP_UP_DOCTYPE,
					"reference_name": docname,
					"status": ["in", ["PENDING_APPROVAL", "FAILED", "PUBLISHED"]],
				},
			)
			if not has_commit:
				frappe.throw(
					"Submit the commit (budget head + amount) before forwarding to HoS."
				)

		next_state_row = next(
			(s for s in workflow.states if s.state == next_state), None
		)
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

		frappe.db.set_value(TOP_UP_DOCTYPE, docname, update_fields, update_modified=True)

		doc.reload()
		doc.add_comment("Workflow", _(next_state))

		# Kafka publish on final approval. perform_*_action uses frappe.db.set_value
		# (bypasses ORM), so the on_update hook check_workflow_and_publish doesn't
		# fire — we must publish staged commits explicitly here.
		if next_state == "Approved":
			try:
				from rndopsapp.rndopsapp.kafka.producer.reimbursement import (
					publish_commit as kafka_publish_commit,
				)

				staging_docs = frappe.get_all(
					"Kafka Commit Staging",
					filters={
						"reference_doctype": TOP_UP_DOCTYPE,
						"reference_name": docname,
						"status": ["in", ["PENDING_APPROVAL", "FAILED"]],
					},
				)
				frappe.logger().info(
					f"[Top Up Kafka] Approval triggered for {docname}. "
					f"Found {len(staging_docs)} staged commit(s)."
				)
				for st in staging_docs:
					staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
					try:
						payload = json.loads(staging_doc.payload)
						success = kafka_publish_commit(
							doc=doc,
							commit_amount=payload.get("commit_amount"),
							budget_head=payload.get("budget_head"),
							project_name=payload.get("project_name"),
							bmr=payload.get("bmr"),
							bill_amount=payload.get("bill_amount"),
							frap_app_id=payload.get("frap_app_id"),
							ref_details=payload.get("ref_details"),
						)
						if success:
							staging_doc.db_set("status", "PUBLISHED")
						else:
							staging_doc.db_set("status", "FAILED")
							staging_doc.db_set(
								"error_message", "kafka_publish_commit returned False"
							)
					except Exception as e:
						frappe.log_error(
							frappe.get_traceback(),
							f"[Top Up Kafka] Error publishing staging {staging_doc.name} for {docname}",
						)
						staging_doc.db_set("status", "FAILED")
						staging_doc.db_set("error_message", str(e))
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					f"[Top Up Kafka] Outer failure processing staged commits for {docname}",
				)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_top_up_fellowship_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_top_up_fellowship_commit_details(docname):
	"""Return commit-related fields for the Staff Commit form.
	Frontend should call commitPayment.submit_commit_data + perform_top_up_fellowship_action('Forward')."""
	if not frappe.db.exists(TOP_UP_DOCTYPE, docname):
		frappe.throw(_("Top Up Fellowship document not found."))

	doc = frappe.get_doc(TOP_UP_DOCTYPE, docname)

	# Project number — resolve from Project Registration (project_code holds the doc id)
	project_number = None
	if doc.project_code:
		project_number = frappe.db.get_value(
			"Project Registration", doc.project_code, "project_no"
		)

	# Sum of all students' per-month totals (defensive: coerce to float)
	total_amount = 0.0
	for row in doc.get("students") or []:
		try:
			total_amount += float(row.total_amount_per_month or 0)
		except (TypeError, ValueError):
			pass

	return {
		"docname": docname,
		"workflow_state": doc.workflow_state,
		"project_code": doc.project_code,
		"project_number": project_number,
		"project_title": doc.project_title,
		"account_head": doc.account_head,
		"pi_webmail": doc.pi_webmail,
		"coordinating_pi_webmail": doc.coordinating_pi_webmail,
		"total_amount": total_amount,
		"student_count": len(doc.get("students") or []),
	}


@frappe.whitelist()
def get_pending_faculty_admission_uploads():
	"""Return Top Up Fellowship docs that R&D Staff need to handle: those that
	the Staff has already marked 'Send to Faculty Admission' (the PDF was
	downloaded for signing) and are currently in 'Pending Staff Approval'.
	Includes already-uploaded docs so Staff can replace the PDF if needed."""
	filters = {
		"send_to_faculty_admission": 1,
		"docstatus": 0,
	}
	fields = [
		"name",
		"project_code",
		"project_title",
		"pi_webmail",
		"coordinating_pi_webmail",
		"send_to_faculty_admission",
		"faculty_admission_pdf",
		"modified",
	]
	if frappe.db.has_column(TOP_UP_DOCTYPE, "workflow_state"):
		filters["workflow_state"] = "Pending Staff Approval"
		fields.append("workflow_state")

	docs = frappe.get_all(
		TOP_UP_DOCTYPE,
		filters=filters,
		fields=fields,
		order_by="modified desc",
	)
	return {"status": "success", "data": docs}


@frappe.whitelist()
def mark_send_to_faculty_admission(docname):
	"""Set send_to_faculty_admission=1 on a Top Up Fellowship document.
	Called by R&D Staff when they download the PDF to send for signing."""
	try:
		if not docname:
			return {"status": "error", "message": "Missing docname."}
		frappe.db.set_value(
			TOP_UP_DOCTYPE,
			docname,
			{"send_to_faculty_admission": 1},
			update_modified=True,
		)
		frappe.db.commit()
		return {"status": "success", "docname": docname}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship mark_send_to_faculty_admission")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def attach_faculty_admission_pdf(docname, file_url):
	"""Bind an already-uploaded file (file_url from /api/method/upload_file) to the
	faculty_admission_pdf field of the given Top Up Fellowship document."""
	try:
		if not docname or not file_url:
			return {"status": "error", "message": "Missing docname or file_url."}
		frappe.db.set_value(
			TOP_UP_DOCTYPE,
			docname,
			{"faculty_admission_pdf": file_url},
			update_modified=True,
		)
		frappe.db.commit()
		return {"status": "success", "docname": docname, "file_url": file_url}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship attach_faculty_admission_pdf")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_top_up_fellowship(docname):
	"""Submit a Top Up Fellowship document by triggering the workflow's 'Submit'
	action from Draft. This ensures the doc transitions into the correct
	'Pending …' state instead of going straight to docstatus=1."""
	try:
		doc = frappe.get_doc(TOP_UP_DOCTYPE, docname)
		current_state = doc.workflow_state or "Draft"

		if current_state != "Draft":
			return {
				"status": "info",
				"message": f"Top Up Fellowship '{docname}' is already in state '{current_state}'.",
				"docname": docname,
				"workflow_state": current_state,
			}

		return perform_top_up_fellowship_action(docname, "Submit")

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship Submit Error")
		return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Dynamic Put-Back Engine (mirrors Indent General Form's approach)
# ---------------------------------------------------------------------------
# Replaces N duplicated "Put Back to X" rows in the Workflow Transition table.
# Forward transitions stay in the Workflow doc; put-back is driven entirely
# from this compact config.

TUF_DOCTYPE = "Top Up Fellowship"

PUT_BACK_TARGETS = {
	# target_key -> next_state
	"Submitter": "Draft",
	"PI":        "Pending PI Approval",
	"Head":      "Pending Head Approval",
	"Staff":     "Pending Staff Approval",
	"HoS":       "Pending HoS Approval",
}

PUT_BACK_RULES = {
	# current_state -> { who can do it, which targets are reachable }
	"Pending PI Approval": {
		"role": "head_approver_1",
		"targets": ["Submitter"],
	},
	"Pending Head Approval": {
		"role": "head_approver_1",
		"targets": ["PI", "Submitter"],
	},
	"Pending Staff Approval": {
		"role": "staff, RnD",
		"targets": ["Head", "PI", "Submitter"],
	},
	"Pending HoS Approval": {
		"role": "Hos, RnD (Head of Section, RnD)",
		"targets": ["Staff", "Head", "PI", "Submitter"],
	},
	"Pending Dean Approval": {
		"role": "Dean, RnD",
		"targets": ["HoS", "Staff", "Head", "PI", "Submitter"],
	},
}


def _tuf_user_has_role(required_role):
	roles = frappe.get_roles(frappe.session.user)
	return required_role in roles or "Administrator" in roles


def _tuf_submitter_is_student(docname):
	"""The 'PI' put-back target only exists when the form was submitted by a
	Student — that's the only flow path that includes Pending PI Approval.
	For Permanent-Employee-submitted forms the PI IS the submitter, so PI
	collapses to Submitter and we hide the redundant button."""
	owner = frappe.db.get_value(TUF_DOCTYPE, docname, "owner")
	if not owner:
		return False
	owner_roles = frappe.get_roles(owner)
	return "Student" in owner_roles


def _tuf_filter_targets_for_doc(targets, docname):
	if _tuf_submitter_is_student(docname):
		return targets
	# Permanent Employee submission → PI == Submitter, drop the duplicate.
	return [t for t in targets if t != "PI"]


@frappe.whitelist()
def get_available_back_actions(docname):
	"""Return the list of put-back actions the current user can perform
	on this Top Up Fellowship doc, given its current workflow_state."""
	if not frappe.db.exists(TUF_DOCTYPE, docname):
		return {"actions": [], "error": "Document not found"}

	current_state = frappe.db.get_value(TUF_DOCTYPE, docname, "workflow_state")
	rule = PUT_BACK_RULES.get(current_state)
	if not rule or not _tuf_user_has_role(rule["role"]):
		return {"actions": [], "current_state": current_state}

	targets = _tuf_filter_targets_for_doc(rule["targets"], docname)
	actions = [
		{
			"target": t,
			"label": f"Put Back to {t}",
			"next_state": PUT_BACK_TARGETS[t],
		}
		for t in targets
		if t in PUT_BACK_TARGETS
	]
	return {"actions": actions, "current_state": current_state}


@frappe.whitelist()
def put_back(docname, target, comment=None):
	"""Apply a put-back action. Validates role + from-state + target."""
	if target not in PUT_BACK_TARGETS:
		frappe.throw(f"Unknown put-back target: {target}")

	if not frappe.db.exists(TUF_DOCTYPE, docname):
		frappe.throw("Document not found")

	current_state = frappe.db.get_value(TUF_DOCTYPE, docname, "workflow_state")
	rule = PUT_BACK_RULES.get(current_state)
	if not rule:
		frappe.throw(f"No put-back actions allowed from state '{current_state}'")

	allowed_targets = _tuf_filter_targets_for_doc(rule["targets"], docname)
	if target not in allowed_targets:
		frappe.throw(f"Cannot put back to '{target}' from '{current_state}' for this submission type")

	if not _tuf_user_has_role(rule["role"]):
		frappe.throw(f"Role '{rule['role']}' required to put back from '{current_state}'")

	next_state = PUT_BACK_TARGETS[target]

	# Bypass Frappe's workflow transition validator — the put-back is governed
	# by PUT_BACK_RULES, not by Workflow Transition rows.
	frappe.db.set_value(TUF_DOCTYPE, docname, "workflow_state", next_state, update_modified=True)

	# Audit trail
	body = f"Put back to {target} ({next_state}) by {frappe.session.user} from {current_state}"
	if comment:
		body += f"\n\nComment: {comment}"

	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Workflow",
		"reference_doctype": TUF_DOCTYPE,
		"reference_name": docname,
		"content": body,
	}).insert(ignore_permissions=True)

	frappe.db.commit()

	return {
		"status": "success",
		"from": current_state,
		"to": next_state,
		"target": target,
	}
