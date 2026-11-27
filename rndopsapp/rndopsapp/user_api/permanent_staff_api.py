# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Self-registration for permanent staff.

The applicant has no Frappe User yet, so these endpoints allow Guest. Identity is
proven against the external auth service (see external_auth.py): a User is only
created when the service accepts the email's username and password, and no User
already exists for that email, username or Employee ID.

Endpoints (prefix: /api/method/rndopsapp.rndopsapp.user_api.permanent_staff_api.):
  - get_permanent_staff_registration_options() : departments + designations
  - get_department_head(department)            : head to auto-fill
  - check_employee_id(employee_id)             : realtime duplicate check
  - check_pi_initials(pi_initials)             : realtime duplicate check
  - register_permanent_staff(...)              : verify and create the User
"""

import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from rndopsapp.external_auth import check_test_login_password, is_test_login, verify_external_user
from rndopsapp.static_config import INSTITUTE_EMAIL_DOMAIN

# `empclass` links to EmployeeClass_prornd, whose ids are hashes.
PERMANENT_EMPCLASS = "5r4emiig95"  # "P - Permanent Employee"
PERMANENT_USER_TYPE = "System User"
PERMANENT_ROLE = "Permanent Employee"
DESIGNATION_TYPE = "Permanent Staff"

EMPLOYEE_ID_PATTERN = re.compile(r"^[A-Za-z0-9/_-]{1,20}$")
# Project numbers use exactly 4 characters; a digit is only for resolving duplicates.
PI_INITIALS_PATTERN = re.compile(r"^[A-Z]{3}[A-Z0-9]$")
EMAIL_LOCAL_PATTERN = re.compile(r"^[a-z0-9._-]+$")


def _clean(value):
	return str(value or "").strip()


def _employee_id_error(employee_id):
	"""Return why an Employee ID cannot be used, or None if it is free."""
	if not employee_id:
		return _("Employee ID is required.")
	if not EMPLOYEE_ID_PATTERN.match(employee_id):
		return _("Employee ID may contain only letters, numbers, '/', '_' and '-' (max 20).")
	if frappe.db.exists("User", {"employee_id": employee_id}):
		return _("Employee ID {0} is already registered.").format(employee_id)
	return None


def _pi_initials_error(pi_initials):
	"""Return why upper-cased PI Initials cannot be used, or None if they are free."""
	if not pi_initials:
		return _("PI Initials are required.")
	if not PI_INITIALS_PATTERN.match(pi_initials):
		return _("PI Initials must be 4 characters: letters A-Z, with only the last allowed to be a digit.")
	if frappe.db.exists("User", {"pi_initials": pi_initials}):
		return _("PI Initials {0} are already taken.").format(pi_initials)
	return None


def _department_head(department):
	"""Return {user, full_name} for an enabled department head, else None."""
	head = frappe.db.get_value("Department_prornd", department, "dept_head")
	if not head:
		return None
	user = frappe.db.get_value("User", {"name": head, "enabled": 1}, ["name", "full_name"], as_dict=True)
	if not user:
		return None
	return {"user": user.name, "full_name": user.full_name}


def _institute_email(email):
	"""
	Normalise and validate the email, returning (email, username).

	The domain check is essential: the auth service only sees the part before
	'@', so any other domain could be registered with institute credentials.
	"""
	username, _sep, domain = _clean(email).lower().partition("@")
	if domain != INSTITUTE_EMAIL_DOMAIN or not EMAIL_LOCAL_PATTERN.match(username):
		frappe.throw(_("Please use your @{0} email address.").format(INSTITUTE_EMAIL_DOMAIN))
	return f"{username}@{domain}", username


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_permanent_staff_registration_options():
	"""Dropdown options for the registration form."""
	departments = frappe.get_all(
		"Department_prornd",
		fields=["name as value", "dept_name as label"],
		order_by="dept_name asc",
		limit_page_length=0,
	)
	designations = frappe.get_all(
		"Designation_prornd",
		filters={"designation_type": DESIGNATION_TYPE},
		fields=["name as value", "designation_prornd as label"],
		order_by="designation_prornd asc",
		limit_page_length=0,
	)
	return {"status": "success", "departments": departments, "designations": designations}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_department_head(department=None):
	"""Head of the selected department; `data` is null when none is assigned."""
	department = _clean(department)
	if not department or not frappe.db.exists("Department_prornd", department):
		frappe.throw(_("Please select a valid department."))
	return {"status": "success", "data": _department_head(department)}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def check_employee_id(employee_id=None):
	"""Realtime duplicate check. Reveals availability only, never who holds an ID."""
	error = _employee_id_error(_clean(employee_id))
	return {"status": "success", "available": not error, "message": error or _("Employee ID is available.")}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def check_pi_initials(pi_initials=None):
	"""Realtime duplicate check. Reveals availability only, never who holds them."""
	error = _pi_initials_error(_clean(pi_initials).upper())
	return {"status": "success", "available": not error, "message": error or _("PI Initials are available.")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60)
def register_permanent_staff(
	email=None,
	password=None,
	first_name=None,
	employee_id=None,
	department_name=None,
	designation_name=None,
	middle_name=None,
	last_name=None,
	pi_initials=None,
):
	"""
	Create the User for a permanent staff member.

	`password` is the institute password. It is only forwarded to the external
	auth service and is never stored. The head (`piheadmentor_user_id`) is always
	derived from the department, not taken from the request.
	"""
	email, username = _institute_email(email)
	first_name = _clean(first_name)
	employee_id = _clean(employee_id)
	department_name = _clean(department_name)
	designation_name = _clean(designation_name)
	pi_initials = _clean(pi_initials).upper()

	required = {
		_("Password"): password,
		_("First Name"): first_name,
		_("Employee ID"): employee_id,
		_("Department"): department_name,
		_("Designation"): designation_name,
	}
	missing = [label for label, value in required.items() if not value]
	if missing:
		frappe.throw(_("Please fill all required fields: {0}").format(", ".join(missing)))

	if not frappe.db.exists("Department_prornd", department_name):
		frappe.throw(_("Please select a valid department."))
	if not frappe.db.exists(
		"Designation_prornd", {"name": designation_name, "designation_type": DESIGNATION_TYPE}
	):
		frappe.throw(_("Please select a valid permanent staff designation."))

	# Authenticate before the duplicate checks, so unauthenticated callers
	# cannot use this endpoint to discover which accounts exist.
	if is_test_login(email):
		verified = check_test_login_password(password)
	else:
		verified = verify_external_user(username, password)
	if not verified:
		frappe.throw(
			_("Could not verify your institute credentials. Please check your password and try again."),
			frappe.AuthenticationError,
		)

	# `username` is checked too because login falls back to matching on it.
	if frappe.db.exists("User", email) or frappe.db.exists("User", {"username": username}):
		frappe.throw(_("A user is already registered for {0}.").format(email), frappe.DuplicateEntryError)

	error = _employee_id_error(employee_id)
	if not error and pi_initials:
		error = _pi_initials_error(pi_initials)
	if error:
		frappe.throw(error)

	head = _department_head(department_name)

	user = frappe.new_doc("User")
	user.update(
		{
			"email": email,
			"username": username,
			"first_name": first_name,
			"middle_name": _clean(middle_name),
			"last_name": _clean(last_name),
			"enabled": 1,
			"user_type": PERMANENT_USER_TYPE,
			"send_welcome_email": 0,
			"employee_id": employee_id,
			# NULL rather than "": the column is unique.
			"pi_initials": pi_initials or None,
			"empclass": PERMANENT_EMPCLASS,
			"department_name": department_name,
			"designation_name": designation_name,
			"piheadmentor_user_id": head["user"] if head else None,
		}
	)
	user.append("roles", {"role": PERMANENT_ROLE})
	user.insert(ignore_permissions=True)

	return {
		"status": "success",
		"docname": user.name,
		"department_head": head,
		"message": _("Registration successful. You can now log in."),
	}
