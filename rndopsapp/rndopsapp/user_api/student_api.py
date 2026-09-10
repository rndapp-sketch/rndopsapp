# START Student Dashboard - Add Student API - 2026-06-19
# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
API for the PI-side "Add Student" flow.

A PI (Permanent Employee) enters a student's email id, the student's
academic details are pulled from the Academic API, the PI attaches one or
more of *their own* projects, and on submit the student is created as a
Frappe `User` (empclass = ST-Student, PI = piheadmentor_user_id) and the
student <-> project links are recorded in `studentdetails_`.

Endpoints:
  - get_student_by_email(email)        : fetch academic details for a student
  - get_pi_projects()                  : list the calling PI's projects
  - add_student(email, projects)       : create the User + studentdetails_ rows
"""

import json

import frappe
import requests
from frappe import _

from rndopsapp.static_config import ACADEMIC_API_BASE, INSTITUTE_EMAIL_DOMAIN

from .academic_department_dto import map_academic_department

# Employee Class assigned to every student created through this flow.
# `empclass` is a Link to `employeeclass_prornd`; the stored value is the
# record's id (hash), not the readable label. This id is the "ST-Student" class.
STUDENT_EMPCLASS = "5ucn86a636"

# Students authenticate through AD just like project staff / PIs. To do so the
# Frappe User must exist, be enabled, be a System User (the type used by the
# React frontend) and carry the baseline app role(s).
STUDENT_USER_TYPE = "System User"
STUDENT_ROLES = ["All_ProRnd_User", "project staff"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email_prefix(email):
	"""Return the local part of an email (the part before '@')."""
	if not email:
		return ""
	return str(email).strip().split("@")[0].strip().lower()


def _build_login_email(email):
	"""Return a full institute email, appending the domain if missing."""
	email = str(email or "").strip().lower()
	if "@" in email:
		return email
	return f"{email}@{INSTITUTE_EMAIL_DOMAIN}"


def _split_name(full_name):
	"""Split a full name into (first, middle, last)."""
	parts = [p for p in str(full_name or "").strip().split() if p]
	if not parts:
		return "", "", ""
	if len(parts) == 1:
		return parts[0], "", ""
	if len(parts) == 2:
		return parts[0], "", parts[1]
	return parts[0], " ".join(parts[1:-1]), parts[-1]


def _to_frappe_date(value):
	"""Convert a 'DD-MM-YYYY' academic-API date to Frappe's 'YYYY-MM-DD'."""
	if not value:
		return None
	value = str(value).strip()
	for sep in ("-", "/"):
		if sep in value:
			parts = value.split(sep)
			if len(parts) == 3 and len(parts[0]) == 2:
				dd, mm, yyyy = parts
				return f"{yyyy}-{mm}-{dd}"
	return value


def _fetch_academic_data(email):
	"""Call the Academic API and return the first matching student dict."""
	prefix = _email_prefix(email)
	if not prefix:
		frappe.throw(_("A student email is required."))

	url = f"{ACADEMIC_API_BASE}/{prefix}"
	try:
		resp = requests.get(url, timeout=(5, 15))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Academic API Error")
		frappe.throw(_("Could not reach the Academic API. Please try again."))

	if resp.status_code == 404:
		frappe.throw(_("No student found for email '{0}'.").format(prefix))

	try:
		resp.raise_for_status()
		payload = resp.json()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Academic API Error")
		frappe.throw(_("Could not fetch student details from the Academic API. Please try again."))

	if not payload.get("success") or not payload.get("data"):
		frappe.throw(_("No student found for email '{0}'.").format(prefix))

	return payload["data"][0]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_by_email(email):
	"""Return academic details for a student so the PI can preview them."""
	data = _fetch_academic_data(email)
	return {"status": "success", "data": data}


@frappe.whitelist()
def get_pi_projects():
	"""Return the calling PI's own projects (for the project picker)."""
	pi = frappe.session.user
	projects = frappe.get_all(
		"Project Registration",
		filters={"pi_webmail": pi},
		fields=["name", "project_title"],
		order_by="modified desc",
		limit_page_length=0,
	)
	return {"status": "success", "data": projects}


@frappe.whitelist()
def add_student(email, projects=None):
	"""
	Create (or update) a student User and link them to the PI's projects.

	Args:
		email:    the student's email / email-prefix entered by the PI.
		projects: list (or JSON string) of Project Registration names. Each
		          must belong to the calling PI.
	"""
	try:
		pi = frappe.session.user

		# --- Normalise projects input ---
		if isinstance(projects, str):
			projects = json.loads(projects) if projects.strip() else []
		projects = projects or []
		if not projects:
			frappe.throw(_("Please attach at least one project to the student."))

		# --- Ensure every project belongs to the calling PI ---
		owned = set(
			frappe.get_all(
				"Project Registration",
				filters={"pi_webmail": pi, "name": ["in", projects]},
				pluck="name",
			)
		)
		invalid = [p for p in projects if p not in owned]
		if invalid:
			frappe.throw(_("These projects are not yours: {0}").format(", ".join(invalid)))

		# --- Fetch academic details ---
		student = _fetch_academic_data(email)
		login_email = _build_login_email(student.get("email_id") or email)
		username = _email_prefix(login_email)
		first, middle, last = _split_name(student.get("sname"))
		gender = (student.get("sex") or "").strip().title() or None
		dob = _to_frappe_date(student.get("dob"))

		# --- Create or update the User ---
		if frappe.db.exists("User", login_email):
			user = frappe.get_doc("User", login_email)
		else:
			user = frappe.new_doc("User")
			user.email = login_email
			user.send_welcome_email = 0

		user.username = username
		user.first_name = first
		user.middle_name = middle
		user.last_name = last
		user.full_name = (student.get("sname") or "").strip()
		user.enabled = 1
		user.user_type = STUDENT_USER_TYPE
		user.empclass = STUDENT_EMPCLASS
		user.piheadmentor_user_id = pi
		mapped_department = map_academic_department(student.get("d_name"))
		if mapped_department:
			user.department_name = mapped_department

		# Grant the baseline roles so the student can log in via AD and use the
		# app like project staff (without clobbering any roles already present).
		existing_roles = {r.role for r in (user.get("roles") or [])}
		for role in STUDENT_ROLES:
			if role not in existing_roles and frappe.db.exists("Role", role):
				user.append("roles", {"role": role})

		user.flags.ignore_permissions = True
		user.flags.ignore_links = True
		user.save(ignore_permissions=True)

		# --- Record student <-> project links in studentdetails_ ---
		for project in projects:
			existing = frappe.get_all(
				"studentdetails_",
				filters={"email_id": login_email, "project_number": project},
				limit=1,
			)
			if existing:
				continue
			detail = frappe.new_doc("studentdetails_")
			detail.student_id = username
			detail.pi_employee_id = _email_prefix(pi)
			detail.project_number = project
			detail.email_id = login_email
			detail.roll_no = student.get("roll_no")
			detail.designation_or_program = student.get("d_name")
			detail.dob = dob
			detail.gender = gender
			detail.flags.ignore_permissions = True
			detail.flags.ignore_links = True
			detail.insert(ignore_permissions=True)

		frappe.db.commit()
		return {
			"status": "success",
			"docname": user.name,
			"message": _("Student '{0}' added successfully.").format(user.full_name or username),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Add Student Error")
		frappe.throw(_("Failed to add student: {0}").format(str(e)))


# ---------------------------------------------------------------------------
# Student self-service profile
# ---------------------------------------------------------------------------
# A student added by a PI can log in immediately, but must complete their own
# details before using the app. The PI-controlled part of `studentdetails_`
# (project, dates, pay, allowances) is deliberately NOT part of this — the
# student only fills the "Basic Details" section.

STUDENT_PROFILE_FIELDS = [
	"dob",
	"gender",
	"contact_number",
	"qualification",
	"permanent_address",
	"present_address",
	"blood_group",
	"account_number",
	"pan",
	"aadhar_number",
	"father_name",
	"maritial_status",
	"citizenship",
]

# Everything above is required before the student is let through.
STUDENT_PROFILE_REQUIRED = list(STUDENT_PROFILE_FIELDS)


def _is_student(user=None):
	"""True when the given (or session) user carries the ST-Student class."""
	user = user or frappe.session.user
	return frappe.db.get_value("User", user, "empclass") == STUDENT_EMPCLASS


def _student_profile_row(user=None):
	"""Return the studentdetails_ docname for a user, or None."""
	user = user or frappe.session.user
	username = _email_prefix(user)
	rows = frappe.get_all(
		"studentdetails_", filters={"student_id": username}, pluck="name", limit=1
	)
	return rows[0] if rows else None


@frappe.whitelist()
def get_my_student_profile():
	"""
	Profile state for the logged-in user.

	Returns is_student / is_complete / missing so the frontend can decide
	whether to force the student onto the profile form.
	"""
	user = frappe.session.user
	if not _is_student(user):
		return {"is_student": False, "is_complete": True, "data": {}, "missing": []}

	name = _student_profile_row(user)
	data = {}
	if name:
		doc = frappe.get_doc("studentdetails_", name)
		data = {f: doc.get(f) for f in STUDENT_PROFILE_FIELDS}

	missing = [f for f in STUDENT_PROFILE_REQUIRED if not (data.get(f) or "")]
	return {
		"is_student": True,
		"is_complete": not missing,
		"missing": missing,
		"data": data,
		"fields": STUDENT_PROFILE_FIELDS,
	}


@frappe.whitelist()
def save_my_student_profile(data):
	"""Create or update the logged-in student's own profile row."""
	user = frappe.session.user
	if not _is_student(user):
		frappe.throw(_("Only students can update a student profile."), frappe.PermissionError)

	if isinstance(data, str):
		data = json.loads(data or "{}")
	data = data or {}

	missing = [f for f in STUDENT_PROFILE_REQUIRED if not str(data.get(f) or "").strip()]
	if missing:
		frappe.throw(_("Please fill all required fields: {0}").format(", ".join(missing)))

	name = _student_profile_row(user)
	if name:
		doc = frappe.get_doc("studentdetails_", name)
	else:
		doc = frappe.new_doc("studentdetails_")
		doc.student_id = _email_prefix(user)

	# Only ever write the student-owned fields; never the PI/pay section.
	for field in STUDENT_PROFILE_FIELDS:
		if field in data:
			doc.set(field, data.get(field) or None)

	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"status": "success", "docname": doc.name, "message": _("Profile saved.")}


# END Student Dashboard - Add Student API - 2026-06-19
