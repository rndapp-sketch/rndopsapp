# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Personal Development Fund (PDF) — the per-employee overhead fund, surfaced as a project.

**The implementation lives in `overhead_fund.py`.** PDF was the first overhead fund to get
a screen; DPF (per department) followed, and the two differ only in which identifier the
Accounts service is addressed by. Everything general moved there rather than being
duplicated, and this module is now:

  - PDF-specific minting (`create_pdf_project_for_user`, `ensure_pdf_project`), which needs
    the User record rather than a Department_prornd row;
  - the PDF-named entry points the frontend and `commitPayment` already call, kept working
    so nothing had to change at those call sites.

New code should call `overhead_fund` directly. See docs/pdf-project-implementation.md and
docs/dpf-project-implementation.md in the prornd-ui repo.
"""

import frappe
from frappe import _
from frappe.utils import flt

from rndopsapp.rndopsapp.overhead_fund import (
	ACCOUNTS_API_BASE_URL,
	OVERHEAD_ACCOUNT_HEAD_ID,
	OVERHEAD_ACCOUNT_HEAD_LABEL,
	OVERHEAD_PRIVILEGED_ROLES,
	PAYABLE_COMMIT_STATUSES,
	REQUEST_TIMEOUT,
	_mint,
	attach_module_ids,
	get_overhead_balance,
	get_overhead_commits,
	get_overhead_credit_balance,
	has_fund_activity,
	get_overhead_ledger,
	get_overhead_summary,
	get_permission_query_conditions,
	project_no_for as _project_no_for,
	project_registration_permission_query,
	resolve_overhead_fund,
	resolve_overhead_scope_for_user,
)

# Kept under their old names: commitPayment and the overhead Kafka producer import these.
PDF_ACCOUNT_HEAD_LABEL = OVERHEAD_ACCOUNT_HEAD_LABEL
PDF_ACCOUNT_HEAD_ID = OVERHEAD_ACCOUNT_HEAD_ID
PDF_PRIVILEGED_ROLES = OVERHEAD_PRIVILEGED_ROLES

__all__ = [
	"ACCOUNTS_API_BASE_URL",
	"REQUEST_TIMEOUT",
	"PDF_ACCOUNT_HEAD_ID",
	"PDF_ACCOUNT_HEAD_LABEL",
	"PDF_PRIVILEGED_ROLES",
	"PAYABLE_COMMIT_STATUSES",
	"attach_module_ids",
	"create_pdf_project_for_user",
	"ensure_pdf_project",
	"get_pdf_balance",
	"get_pdf_commits",
	"get_pdf_credit_balance",
	"get_pdf_ledger",
	"get_pdf_summary",
	"has_fund_activity",
	"get_permission_query_conditions",
	"is_pdf_project",
	"project_no_for",
	"project_registration_permission_query",
	"_resolve_pdf_employee_id",
]


def project_no_for(employee_id):
	"""The PDF project number for an employee. One PDF project per PI, by definition."""
	return _project_no_for("PDF", employee_id)


# ---------------------------------------------------------------------------
# PDF-named entry points (thin wrappers — the logic is in overhead_fund)
# ---------------------------------------------------------------------------

def _resolve_pdf_employee_id(project_number, raise_on_denied=True):
	"""
	The employee id behind a PDF project — but only if the caller is entitled to it.

	Returns None when `project_number` is not a PDF project, which is how `commitPayment`
	tells "carry on with the normal project path" from "this is PDF".

	Note it returns None for a *DPF* project too: that is deliberate, because a caller
	asking for an employee id has no use for a department. `commitPayment` routes on
	`resolve_overhead_scope_for_user` instead, which handles both.
	"""
	resolved = resolve_overhead_scope_for_user(project_number, raise_on_denied=raise_on_denied)
	if not resolved:
		return None
	fund_type, scope = resolved
	if fund_type != "PDF":
		return None
	return scope.get("employeeId")


def is_pdf_project(project_number):
	"""True when this project number belongs to a PDF project (no permission check)."""
	resolved = resolve_overhead_fund(project_number)
	return bool(resolved and resolved[0] == "PDF")


def get_pdf_summary(employee_id):
	"""Live PDF balance for an employee, in get_project_available_amounts' shape."""
	return get_overhead_summary("PDF", {"employeeId": str(employee_id)})


def get_pdf_credit_balance(employee_id):
	"""Credited / loaned / balance for one employee — the mint probe."""
	return get_overhead_credit_balance("PDF", employee_id)


@frappe.whitelist()
def get_pdf_balance(project_number):
	"""Balance for a PDF project. Ownership-checked; takes a project, never an employee."""
	return get_overhead_balance(project_number)


@frappe.whitelist()
def get_pdf_ledger(project_number, from_date=None, to_date=None):
	"""Transaction log for a PDF project, normalised to the project ledger shape."""
	return get_overhead_ledger(project_number, from_date, to_date)


@frappe.whitelist()
def get_pdf_commits(statuses=None):
	"""Overhead commits awaiting payment, shaped like the project-side CommitRecord."""
	return get_overhead_commits(statuses)


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

def _employee_context(user):
	"""The fields a PDF project needs from the User record."""
	# department_name / designation_name, not department / designation — this install's
	# User doctype has no plain `department` column, and department_name already holds a
	# Department_prornd docname.
	return frappe.db.get_value(
		"User",
		user,
		["name", "full_name", "employee_id", "enabled", "department_name", "designation_name"],
		as_dict=True,
	)


def _pick_department(user_doc):
	"""
	Department for the shell project.

	Both department fields on Project Registration are Links to Department_prornd, so an
	unresolvable value has to be dropped rather than guessed — the project is a container,
	and a wrong department would misreport it in every departmental view.
	"""
	dept = user_doc.get("department_name")
	if dept and frappe.db.exists("Department_prornd", dept):
		return dept
	return None


def create_pdf_project_for_user(user, force=False):
	"""
	Create the PDF project for one user, pre-approved, bypassing the workflow.

	Returns the docname, or None when the user cannot or should not have one. Safe to call
	repeatedly — an existing project is returned rather than duplicated.

	`force=True` skips the "has this fund ever moved?" probe. Without it, only employees
	whose fund has seen activity get a project — a balance of exactly 0, or a negative one,
	still counts (see has_fund_activity). Only a fund that was never credited at all is
	skipped, since that project would show nothing but locked modules.
	"""
	u = _employee_context(user)
	if not u:
		return None
	if not u.get("enabled"):
		return None
	if not u.get("employee_id"):
		frappe.log_error(f"No employee_id on User {user}", "PDF Fund - Cannot Mint")
		return None

	employee_id = str(u["employee_id"]).strip()
	project_no = project_no_for(employee_id)

	existing = frappe.db.get_value("Project Registration", {"project_no": project_no}, "name")
	if existing:
		return existing

	if not force:
		try:
			balance = get_pdf_credit_balance(employee_id)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "PDF Fund - Balance Probe Failed")
			return None
		if not has_fund_activity(balance):
			return None

	return _mint(
		project_no=project_no,
		project_title=f"Personal Development Fund — {u.get('full_name') or user}",
		project_type="PDF",
		fund_type="PDF",
		scope_id=employee_id,
		pi_webmail=user,
		department=_pick_department(u),
		designation=u.get("designation_name"),
		legacy_pdf_employee_id=employee_id,
	)


@frappe.whitelist()
def ensure_pdf_project(user=None):
	"""
	Make sure the current user's PDF project exists, minting it on first credited balance.

	Called from the project list. Cheap and idempotent: once the project exists this is a
	single indexed lookup, and users with no PDF credit never get one.
	"""
	user = user or frappe.session.user

	if user != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("You are not permitted to do this."), frappe.PermissionError)

	employee_id = frappe.db.get_value("User", user, "employee_id")
	if not employee_id:
		return {"status": "success", "data": None}

	existing = frappe.db.get_value(
		"Project Registration", {"project_no": project_no_for(str(employee_id).strip())}, "name"
	)
	if existing:
		return {"status": "success", "data": existing}

	try:
		name = create_pdf_project_for_user(user)
	except Exception:
		# Never block the project list because minting failed.
		frappe.log_error(frappe.get_traceback(), "PDF Fund - Mint Failed")
		return {"status": "success", "data": None}

	if name:
		frappe.db.commit()
	return {"status": "success", "data": name}
