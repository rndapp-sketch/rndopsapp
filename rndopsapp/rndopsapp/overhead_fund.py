# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Overhead funds surfaced as projects — PDF (per employee) and DPF (per department).

The institute's consultancy overhead is split five ways by the Accounts service:

	PDF   Personal Development Fund      scoped by employeeId    owner: the PI
	DPF   Departmental Development Fund  scoped by departmentId  owner: the department head
	IDF / SWF / STWF                     institute-wide pools    no owner yet

Each of these is a *fund*, not a project. There is no project, sanction, fund received or
deposit slip for it on the Accounts side: the fund is credited automatically when a
consultancy deposit slip on some *other* project distributes its institute share. What
this module does is give an existing balance somewhere to stand — a pre-approved
Project Registration shell whose money resolves to `fundType` + one scope identifier.

See docs/pdf-project-implementation.md and docs/dpf-project-implementation.md in the
prornd-ui repo.

Three rules govern everything here:

  1. The scope identifier is NEVER taken from client input. `resolve_overhead_scope_for_user`
     derives it from a project the caller is entitled to, because overhead project numbers
     are guessable (PDF{employee_id} / DPF{dept_id}) and these balances are personal or
     departmental earnings, not institutional money.
  2. Overhead data never travels over the browser-side `/ledger-api` proxy, which is
     unauthenticated and would bypass rule 1 entirely.
  3. Routing (which Kafka topic a commit belongs on) must NOT be permission-checked — it
     runs at submit/approval time as whoever approved. `resolve_overhead_fund` is the
     unchecked variant, and it is the only one the producer may call.
"""

import json
from concurrent.futures import ThreadPoolExecutor

import frappe
import requests
from frappe import _
from frappe.utils import flt

from rndopsapp.static_config import ACCOUNT_PORTAL_API

# Same host as commitPayment.LEDGER_API_BASE_URL / loan_settlement.ACCOUNTS_API_BASE_URL.
ACCOUNTS_API_BASE_URL = ACCOUNT_PORTAL_API

REQUEST_TIMEOUT = 10

# The single budget head an overhead spend is booked against. These funds have no head
# dimension — the balance is one pool — but OverheadCommit carries a real AccountHead, so
# commits need a coherent one. Budget Head id 1 is "Overhead".
OVERHEAD_ACCOUNT_HEAD_LABEL = "Overhead"
OVERHEAD_ACCOUNT_HEAD_ID = 1

# Roles allowed to view any overhead fund, not just their own — the R&D office, who
# approve and pay these applications and therefore need the project behind them.
#
# `head_approver_1` is deliberately absent. A department head approves applications from
# their department, which can include a PI's PDF spend — but letting them read the project
# would expose that colleague's personal earnings, which §5.6 exists to prevent. Their
# Pending Task / Task Registry tab is placed correctly anyway: resolveProjectCategory falls
# back to the `PDF…`/`DPF…` project-number prefix, which is already on the application they
# can see. See docs/dpf-project-implementation.md §6.4.
OVERHEAD_PRIVILEGED_ROLES = (
	"staff, RnD",
	"Hos, RnD (Head of Section, RnD)",
	"Dean, RnD",
	"Ado_RnD",
	"Director",
	"System Manager",
)

PAYABLE_COMMIT_STATUSES = ("COMMITTED", "PARTIALLY_PAID", "OVERPAYMENT")


# ---------------------------------------------------------------------------
# The fund registry — the one place a fund type's scoping is described
# ---------------------------------------------------------------------------
#
# Adding IDF / SWF / STWF means adding a row here with scope_key=None; nothing else in
# this module, in the producer, or on the frontend needs to know about it.

FUND_TYPES = {
	"PDF": {
		"label": "Personal Development Fund",
		# The query parameter the Accounts service scopes this fund by.
		"scope_key": "employeeId",
		# Scope identifiers are strings for PDF (employee ids like "1411") and ints for
		# DPF (their DTO types departmentId as a number). Coerced on the way out.
		"scope_cast": str,
		"credit_balance_path": "/credit-distributions/fund-balance/pdf/employee/{scope_id}",
	},
	"DPF": {
		"label": "Departmental Development Fund",
		"scope_key": "departmentId",
		"scope_cast": int,
		"credit_balance_path": "/credit-distributions/fund-balance/dpf/department/{scope_id}",
	},
}

OVERHEAD_FUND_TYPES = tuple(FUND_TYPES)


def project_no_for(fund_type, scope_id):
	"""The project number for an overhead fund, e.g. PDF1411 / DPF4."""
	return f"{fund_type}{scope_id}"


def _scope_params(fund_type, scope_id):
	"""The query parameters that address one fund on the Accounts service."""
	spec = FUND_TYPES.get(fund_type)
	if not spec:
		return {}
	if not spec["scope_key"]:
		# An institute-wide pool takes no identifier.
		return {}
	try:
		value = spec["scope_cast"](scope_id)
	except (TypeError, ValueError):
		value = scope_id
	return {spec["scope_key"]: value}


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _overhead_project_row(project_number):
	"""
	The Project Registration row behind an overhead project number, or None.

	`project_number` may be EITHER the docname or the project_no. Callers are
	inconsistent — the commit staging payload carries the docname, which the reimbursement
	mapper only converts to project_no later — and matching just one silently sent every
	overhead commit to the wrong Kafka topic. Accepting both is what makes routing work
	from every call site.

	Falls back to the legacy is_pdf_project / pdf_employee_id pair so a PDF project minted
	before the generic fields existed still resolves, whether or not the backfill patch has
	run yet.
	"""
	if not project_number:
		return None

	fields = [
		"name", "pi_webmail", "project_no", "implementation_department",
		"is_overhead_project", "overhead_fund_type", "overhead_scope_id",
		"is_pdf_project", "pdf_employee_id",
	]
	row = frappe.db.get_value(
		"Project Registration", {"project_no": project_number}, fields, as_dict=True
	) or frappe.db.get_value(
		"Project Registration", {"name": project_number}, fields, as_dict=True
	)
	if not row:
		return None

	fund_type = (row.get("overhead_fund_type") or "").strip().upper()
	scope_id = row.get("overhead_scope_id")

	# Legacy PDF projects: the generic pair is empty, the PDF pair is not.
	if not fund_type and row.get("is_pdf_project") and row.get("pdf_employee_id"):
		fund_type, scope_id = "PDF", row["pdf_employee_id"]

	if not fund_type or fund_type not in FUND_TYPES:
		return None
	if FUND_TYPES[fund_type]["scope_key"] and not scope_id:
		# A scoped fund with no identifier cannot address anything.
		return None

	row["_fund_type"] = fund_type
	row["_scope_id"] = scope_id
	return row


def resolve_overhead_fund(project_number):
	"""
	The overhead fund a project's money belongs to, or None for an ordinary project.

	Returns ``(fund_type, scope, row)`` where `scope` holds exactly the one identifier that
	fund type is scoped by, so a caller never has to know which is which.

	**No permission check.** This is the routing primitive — it decides which Kafka topic a
	commit belongs on, and it runs at approval time as whoever approved, who is usually not
	the fund's owner. Whitelisted reads must use `resolve_overhead_scope_for_user` instead.
	"""
	row = _overhead_project_row(project_number)
	if not row:
		return None
	fund_type = row["_fund_type"]
	return fund_type, _scope_params(fund_type, row["_scope_id"]), row


def is_overhead_project(project_number) -> bool:
	"""True when this project number belongs to an overhead fund (no permission check)."""
	return resolve_overhead_fund(project_number) is not None


def _may_access(row):
	"""
	Whether the session user is entitled to this fund.

	The PI / department head recorded on the project is the owner. For DPF the live
	`Department_prornd.dept_head` also counts: a department's head rotates, and a head who
	took over yesterday must be able to read the fund today even if `pi_webmail` has not
	been reconciled yet (it is, on the next ensure — but not before).
	"""
	user = frappe.session.user
	if row.get("pi_webmail") == user:
		return True
	if any(r in frappe.get_roles(user) for r in OVERHEAD_PRIVILEGED_ROLES):
		return True
	if row["_fund_type"] == "DPF" and row.get("_scope_id"):
		heads = frappe.get_all(
			"Department_prornd",
			filters={"dept_id": str(row["_scope_id"]), "dept_head": user},
			limit=1,
		)
		if heads:
			return True
	return False


def resolve_overhead_scope_for_user(project_number, raise_on_denied=True):
	"""
	``(fund_type, scope)`` for an overhead project — but only if the caller is entitled.

	Returns None when `project_number` is not an overhead project at all, which is how
	callers tell "carry on with the normal project path" from "this is overhead".

	The project number arrives from the client and is trivially guessable, so ownership is
	checked here rather than assumed. This is the only place a scope identifier is allowed
	to originate for a client-facing read.
	"""
	resolved = resolve_overhead_fund(project_number)
	if not resolved:
		return None
	fund_type, scope, row = resolved

	if not _may_access(row):
		if raise_on_denied:
			frappe.throw(_("You are not permitted to view this fund."), frappe.PermissionError)
		return None

	return fund_type, scope


# ---------------------------------------------------------------------------
# Accounts service reads
# ---------------------------------------------------------------------------

def get_overhead_summary(fund_type, scope):
	"""
	Live balance for one overhead fund.

	Deliberately returns the same keys as commitPayment.get_project_available_amounts so
	every existing caller — the module unlock, the balance cards, the commit form — works
	unchanged. `netFundAvailable` is the only field that needs renaming.
	"""
	response = requests.get(
		f"{ACCOUNTS_API_BASE_URL}/overhead-transactions/{fund_type}/summary",
		params=scope,
		timeout=REQUEST_TIMEOUT,
	)
	response.raise_for_status()
	data = response.json() or {}

	# The endpoint answers 200 with an {"error": ...} body when the scope is missing.
	if data.get("error"):
		frappe.throw(_("Accounts service: {0}").format(data["error"]))

	scope_id = next(iter(scope.values()), "")
	return {
		"status": "success",
		"data": {
			"projectNumber": project_no_for(fund_type, scope_id),
			"totalFundReceived": flt(data.get("netFundAvailable")),
			"totalCommitted": flt(data.get("totalCommitted")),
			"totalPaid": flt(data.get("totalPaid")),
			"availableCommitAmount": flt(data.get("availableCommitAmount")),
			"availablePaymentAmount": flt(data.get("availablePaymentAmount")),
			# Display aliases, matching the project path exactly.
			"actualBalance": flt(data.get("availablePaymentAmount")),
			"committable": flt(data.get("availableCommitAmount")),
			# Loans are not permitted against PDF or DPF, so this is reported for
			# completeness and deliberately not surfaced in the UI.
			"outstandingLoan": flt(data.get("outstandingLoan")),
			"fundType": fund_type,
		},
	}


def get_overhead_credit_balance(fund_type, scope_id):
	"""
	Credited / loaned / balance for one scope, straight from the credit distribution.

	Used as the cheap "has this fund ever moved?" probe when minting — see
	has_fund_activity. Never call the un-sliced /fund-balance/{fund}: that returns the
	institute-wide pool plus a per-scope breakdown of everyone else's money.
	"""
	spec = FUND_TYPES.get(fund_type)
	if not spec or not spec.get("credit_balance_path"):
		return {}
	response = requests.get(
		ACCOUNTS_API_BASE_URL + spec["credit_balance_path"].format(scope_id=scope_id),
		timeout=REQUEST_TIMEOUT,
	)
	response.raise_for_status()
	return response.json() or {}


def has_fund_activity(balance):
	"""
	Whether this fund has ever moved — the test that decides if a project is minted.

	Deliberately NOT `balance > 0`. A fund spent down to exactly zero, or overdrawn, is
	precisely the one its owner most needs to see: hiding it makes their own spending
	history vanish and leaves an overdraft invisible. Only a fund that has never been
	credited at all stays hidden, because that project would show nothing but locked
	modules and read as broken.

	`/credit-distributions/fund-balance/...` never 404s — an unknown id comes back as
	`{"credited": 0, "loaned": 0, "balance": 0}` — so "has a record" cannot be used to tell
	the two apart. Any non-zero figure is the only available signal of real activity.
	"""
	if not balance:
		return False
	return any(
		flt(balance.get(key)) != 0
		for key in ("credited", "loaned", "balance")
	)


def _normalise_log_rows(rows):
	"""
	The Accounts transaction log, in the shape the project ledger UI already renders.

	Two renames reconcile it with /commit-payment-transactions: overhead uses
	`referenceNumber` where the project rows use `refDetails`, and has no `balance` field
	(its `paymentBalance` is the running balance).

	Plus one piece of real mapping: an overhead fund can carry LOAN_ISSUED and LOAN_SETTLED
	rows, which have no equivalent on the project side. From the fund's point of view a loan
	issued is money out and a settlement is money back in, so they are folded into the
	payment / received columns — otherwise those rows render as all-zero lines with a
	balance that moves for no visible reason. The raw amounts are left on the row too.
	"""
	normalised = []
	for row in rows or []:
		received = flt(row.get("fundReceivedAmount")) + flt(row.get("settlementAmount"))
		paid = flt(row.get("paymentAmount")) + flt(row.get("loanAmount"))
		normalised.append({
			**row,
			"refDetails": row.get("referenceNumber"),
			"balance": flt(row.get("paymentBalance")),
			"fundReceivedAmount": received,
			"paymentAmount": paid,
			# Kept so the UI can label a row precisely if it wants to.
			"rawLoanAmount": flt(row.get("loanAmount")),
			"rawSettlementAmount": flt(row.get("settlementAmount")),
		})
	return normalised


def fetch_overhead_logs(fund_type, scope, from_date=None, to_date=None):
	"""Raw transaction rows for one fund. Returns a list, or raises."""
	params = dict(scope)
	if from_date:
		params["fromDate"] = from_date
	if to_date:
		params["toDate"] = to_date

	response = requests.get(
		f"{ACCOUNTS_API_BASE_URL}/overhead-transactions/{fund_type}/logs",
		params=params,
		timeout=REQUEST_TIMEOUT,
	)
	response.raise_for_status()
	return response.json()


# ---------------------------------------------------------------------------
# Whitelisted endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_overhead_balance(project_number):
	"""Balance for an overhead project. Ownership-checked; takes a project, never a scope id."""
	resolved = resolve_overhead_scope_for_user(project_number)
	if not resolved:
		frappe.throw(_("{0} is not an overhead fund project.").format(project_number))
	fund_type, scope = resolved

	try:
		return get_overhead_summary(fund_type, scope)
	except frappe.PermissionError:
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"{fund_type} Fund - Summary Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_overhead_ledger(project_number, from_date=None, to_date=None):
	"""Transaction log for an overhead project, normalised to the project ledger shape."""
	resolved = resolve_overhead_scope_for_user(project_number)
	if not resolved:
		frappe.throw(_("{0} is not an overhead fund project.").format(project_number))
	fund_type, scope = resolved

	try:
		rows = fetch_overhead_logs(fund_type, scope, from_date, to_date)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"{fund_type} Fund - Logs Failed")
		return {"status": "error", "message": str(e), "data": []}

	if isinstance(rows, dict):
		# The endpoint answers 200 with {"error": ...} rather than a list on bad input.
		return {"status": "error", "message": rows.get("error") or "Unexpected response", "data": []}

	return {"status": "success", "data": _normalise_log_rows(rows)}


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

def _mint(project_no, project_title, project_type, fund_type, scope_id, pi_webmail,
          department, designation, legacy_pdf_employee_id=None):
	"""
	Create one pre-approved overhead project, bypassing the registration workflow.

	Shared by both funds because only the five values above differ between them.
	"""
	doc_fields = {
		"doctype": "Project Registration",
		"project_title": project_title,
		"project_type": project_type,
		"implementation_department": department,
		"applicant_department": department,
		"designation": designation or "",
		"pi_webmail": pi_webmail,
		"project_no": project_no,
		"is_overhead_project": 1,
		"overhead_fund_type": fund_type,
		"overhead_scope_id": str(scope_id),
	}
	if legacy_pdf_employee_id is not None:
		# Still written so anything reading the old pair keeps working; the generic fields
		# above are what every branch actually tests.
		doc_fields["is_pdf_project"] = 1
		doc_fields["pdf_employee_id"] = legacy_pdf_employee_id

	doc = frappe.get_doc(doc_fields)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_workflow = True
	doc.flags.ignore_mandatory = True
	doc.insert()

	# Approved + docstatus 1 is what the full project view expects (ProjectsView routes on
	# workflow_state === "Approved"). Set both at the DB layer rather than through
	# doc.submit(): an overhead project is pre-approved by definition and never passes
	# through the registration workflow, so the engine rightly refuses a Draft → Approved
	# jump. Same escape hatch project_registration.py already uses to roll a state back.
	frappe.db.set_value(
		"Project Registration",
		doc.name,
		{"workflow_state": "Approved", "docstatus": 1},
		update_modified=False,
	)
	return doc.name


def _department_context(department):
	"""The fields a DPF project needs from Department_prornd, by docname."""
	return frappe.db.get_value(
		"Department_prornd", department, ["name", "dept_id", "dept_name", "dept_head"], as_dict=True
	)


def create_dpf_project_for_department(department, force=False):
	"""
	Create the DPF project for one department, pre-approved, bypassing the workflow.

	`department` is a Department_prornd docname. Returns the docname of the project, or
	None when the department cannot or should not have one. Safe to call repeatedly — an
	existing project is returned (and its head reconciled) rather than duplicated.

	`force=True` skips the "has this fund ever moved?" probe. Without it, only departments
	whose fund has seen activity get a project — a balance of exactly 0, or a negative one,
	still counts (see has_fund_activity). Only a fund that was never credited at all is
	skipped, since that project would show nothing but locked modules.
	"""
	dept = _department_context(department)
	if not dept:
		return None
	if not dept.get("dept_id"):
		frappe.log_error(f"No dept_id on Department_prornd {department}", "DPF Fund - Cannot Mint")
		return None
	if not dept.get("dept_head"):
		# Nobody to own it. A DPF project with no head would be invisible to everyone.
		return None

	head = frappe.db.get_value(
		"User", dept["dept_head"], ["name", "enabled", "designation_name"], as_dict=True
	)
	if not head or not head.get("enabled"):
		return None

	dept_id = str(dept["dept_id"]).strip()
	project_no = project_no_for("DPF", dept_id)

	existing = frappe.db.get_value(
		"Project Registration", {"project_no": project_no}, ["name", "pi_webmail"], as_dict=True
	)
	if existing:
		# A department's head rotates. Keep the project pointing at the current one,
		# otherwise the outgoing head keeps seeing the fund in their list and the incoming
		# head never does — the list query is `pi_webmail = currentUser`.
		if existing.get("pi_webmail") != dept["dept_head"]:
			frappe.db.set_value(
				"Project Registration", existing["name"],
				{"pi_webmail": dept["dept_head"]}, update_modified=False,
			)
		return existing["name"]

	if not force:
		try:
			balance = get_overhead_credit_balance("DPF", dept_id)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "DPF Fund - Balance Probe Failed")
			return None
		if not has_fund_activity(balance):
			return None

	return _mint(
		project_no=project_no,
		project_title=f"Departmental Development Fund — {dept.get('dept_name') or dept_id}",
		project_type="DPF",
		fund_type="DPF",
		scope_id=dept_id,
		pi_webmail=dept["dept_head"],
		department=dept["name"],
		designation=head.get("designation_name") or "Head of Department",
	)


@frappe.whitelist()
def ensure_dpf_project(user=None):
	"""
	Make sure the current user's departments each have a DPF project.

	Called from the project list. The departments are resolved from
	`Department_prornd.dept_head = user` — never from client input, and never from
	`User.department_name`, which records where someone works rather than what they head.

	A head can run several departments (one user heads six today), so this returns a list.
	Cheap and idempotent: once the projects exist this is one indexed lookup each.
	"""
	user = user or frappe.session.user

	if user != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("You are not permitted to do this."), frappe.PermissionError)

	departments = frappe.get_all(
		"Department_prornd", filters={"dept_head": user}, fields=["name", "dept_id"]
	)
	if not departments:
		return {"status": "success", "data": []}

	projects, created = [], []
	for dept in departments:
		if not dept.get("dept_id"):
			continue
		# Checked before minting so the caller can tell "already had one" from "just got
		# one", and only refetch its project list in the second case.
		existed = frappe.db.exists(
			"Project Registration",
			{"project_no": project_no_for("DPF", str(dept["dept_id"]).strip())},
		)
		try:
			name = create_dpf_project_for_department(dept["name"])
		except Exception:
			# Never block the project list because minting failed.
			frappe.log_error(frappe.get_traceback(), "DPF Fund - Mint Failed")
			continue
		if name:
			projects.append(name)
			if not existed:
				created.append(name)

	if created:
		frappe.db.commit()
	return {"status": "success", "data": projects, "created": created}


@frappe.whitelist()
def ensure_overhead_projects(user=None):
	"""
	Mint whatever overhead projects the current user is entitled to, in one round trip.

	The project list calls this once per session rather than one endpoint per fund type.
	Each fund is independent: a failure to mint one never prevents the other.
	"""
	from rndopsapp.rndopsapp.pdf_fund import ensure_pdf_project

	result = {"pdf": None, "dpf": []}
	created = False

	try:
		# ensure_pdf_project returns the project whether or not it already existed, so
		# "was one minted just now?" is answered by checking first.
		had_pdf = bool(_existing_pdf_project(user or frappe.session.user))
		result["pdf"] = (ensure_pdf_project(user) or {}).get("data")
		created = created or (bool(result["pdf"]) and not had_pdf)
	except frappe.PermissionError:
		raise
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Overhead Fund - Ensure PDF Failed")

	try:
		dpf = ensure_dpf_project(user) or {}
		result["dpf"] = dpf.get("data") or []
		created = created or bool(dpf.get("created"))
	except frappe.PermissionError:
		raise
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Overhead Fund - Ensure DPF Failed")

	return {"status": "success", "created": created, "data": result}


def _existing_pdf_project(user):
	"""The user's PDF project docname, if they already have one."""
	employee_id = frappe.db.get_value("User", user, "employee_id")
	if not employee_id:
		return None
	return frappe.db.get_value(
		"Project Registration",
		{"project_no": project_no_for("PDF", str(employee_id).strip())},
		"name",
	)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

def get_permission_query_conditions(user=None):
	"""
	Hide overhead projects from everyone but their own owner.

	A PDF balance is a person's own consultancy earnings and a DPF balance is one
	department's. `Permanent Employee` has read-all on Project Registration, and Project
	Search queries the doctype with no owner restriction — so without this, one search
	would expose every colleague's personal fund project (and its guessable project
	number). Applied via hooks.permission_query_conditions.

	Both the generic flag and the legacy PDF flag are tested, so a project minted before
	the backfill patch ran is still hidden.
	"""
	user = user or frappe.session.user
	if not user or user == "Administrator":
		return ""
	if any(r in frappe.get_roles(user) for r in OVERHEAD_PRIVILEGED_ROLES):
		return ""

	safe_user = frappe.db.escape(user)
	return (
		"((ifnull(`tabProject Registration`.`is_overhead_project`, 0) = 0"
		" and ifnull(`tabProject Registration`.`is_pdf_project`, 0) = 0)"
		f" or `tabProject Registration`.`pi_webmail` = {safe_user})"
	)


def project_registration_permission_query(user=None):
	"""
	The `permission_query_conditions` hook for Project Registration.

	Project Registration already had a hook — delegate_user's, which *expands* list
	visibility to a delegator's records. This one *restricts* it, hiding other people's
	overhead fund projects. Both must apply, so they are composed here with AND rather than
	one replacing the other in hooks.py (a dict literal would silently drop the first).

	Delegation returns "" whenever it has nothing to add, which is the common case, so this
	usually reduces to the overhead condition alone.
	"""
	from rndopsapp.rndopsapp.delegate_user.delegate_user import (
		project_registration_permission_query as delegation_query,
	)

	parts = [c for c in (delegation_query(user=user), get_permission_query_conditions(user)) if c]
	if not parts:
		return ""
	return " and ".join(f"({c})" for c in parts)


# ---------------------------------------------------------------------------
# Payable commits (staff, RnD payment queue)
# ---------------------------------------------------------------------------

def _overhead_projects_for_queue():
	"""
	Every overhead project the staff payment queue fans out over.

	Includes PDF projects minted before the generic fields existed: the backfill patch sets
	them, but a site that has not run it yet would otherwise drop them from the queue.
	"""
	projects = frappe.get_all(
		"Project Registration",
		filters={"is_overhead_project": 1},
		fields=["project_no", "overhead_fund_type", "overhead_scope_id"],
	)
	for row in frappe.get_all(
		"Project Registration",
		filters={"is_pdf_project": 1, "is_overhead_project": 0},
		fields=["project_no", "pdf_employee_id"],
	):
		if row.get("pdf_employee_id"):
			projects.append({
				"project_no": row["project_no"],
				"overhead_fund_type": "PDF",
				"overhead_scope_id": row["pdf_employee_id"],
			})

	return [
		p for p in projects
		if p.get("overhead_fund_type") in FUND_TYPES and p.get("overhead_scope_id")
	]


@frappe.whitelist()
def get_overhead_commits(statuses=None):
	"""
	Overhead commits awaiting payment, shaped like the project-side CommitRecord.

	Feeds the Payments page's "Pending Commits" list, which today gets project commits from
	/account-head-commit/by-status/{status}. Overhead has no by-status endpoint, so COMMIT
	rows are read from each fund's transaction log and filtered here — a handful of rows per
	fund, not a table scan.

	**Deliberately aggregates across funds and owners**, unlike every other read in this
	module. Staff process payments on everyone's behalf, so the payment queue has to show
	every pending commit whoever's fund it belongs to — the same visibility project commits
	already have on that page. The exception is bounded by the role check below: a PI or a
	department head still cannot reach another's balance, ledger or project.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not any(r in roles for r in OVERHEAD_PRIVILEGED_ROLES):
		frappe.throw(_("You are not permitted to view the payment queue."), frappe.PermissionError)

	if isinstance(statuses, str):
		try:
			statuses = json.loads(statuses)
		except ValueError:
			statuses = [statuses]
	wanted = {s.upper() for s in (statuses or PAYABLE_COMMIT_STATUSES)}

	projects = _overhead_projects_for_queue()
	if not projects:
		return {"status": "success", "data": []}

	def _commits_for(project):
		fund_type = project["overhead_fund_type"]
		scope = _scope_params(fund_type, project["overhead_scope_id"])
		try:
			rows = fetch_overhead_logs(fund_type, scope)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Overhead Fund - Commit List Failed ({project['project_no']})",
			)
			return []

		if not isinstance(rows, list):
			return []

		out = []
		for row in rows:
			if row.get("transactionType") != "COMMIT":
				continue
			if (row.get("status") or "").upper() not in wanted:
				continue
			out.append({
				# transactionId IS the overheadCommitId a payment must reference.
				"transactionCommitNumber": row.get("transactionId"),
				"projectNumber": project["project_no"],
				"accountHeadId": OVERHEAD_ACCOUNT_HEAD_ID,
				"transactionReceivedRefNumber": None,
				"commitDate": row.get("transactionDate"),
				"commitParticular": row.get("particulars") or "",
				"refDetails": row.get("referenceNumber") or "",
				"commitAmount": flt(row.get("commitAmount")),
				"status": row.get("status"),
				"billAmount": None,
				"moduleId": row.get("moduleId"),
				"frapAppId": row.get("frapAppId"),
				"fundType": fund_type,
			})
		return out

	with ThreadPoolExecutor(max_workers=8) as executor:
		results = list(executor.map(_commits_for, projects))

	commits = [c for group in results for c in group]
	attach_module_ids(commits)
	commits.sort(key=lambda c: c.get("commitDate") or "", reverse=True)
	return {"status": "success", "data": commits}


@frappe.whitelist()
def get_overhead_payments(statuses=None):
	"""
	Payments already raised against overhead commits, shaped like the ledger's payment rows.

	The Payments page swaps a commit's **Pay** button for *Payment Pending* + **View** as
	soon as a payment exists against it — it builds that from `getAllPayments()`, which hits
	`/account-head-payments` and therefore only ever knew about *project* payments. An
	overhead payment lives in the Accounts overhead tables, so the page never saw one and
	kept offering **Pay** on a commit that had already been paid. Staff could submit a
	second payment against the same commit.

	Role-gated exactly like `get_overhead_commits`: this aggregates across every fund, which
	is the staff payment queue's job and nobody else's.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not any(r in roles for r in OVERHEAD_PRIVILEGED_ROLES):
		frappe.throw(_("You are not permitted to view the payment queue."), frappe.PermissionError)

	if isinstance(statuses, str):
		try:
			statuses = json.loads(statuses)
		except ValueError:
			statuses = [statuses]
	wanted = {s.upper() for s in statuses} if statuses else None

	projects = _overhead_projects_for_queue()
	if not projects:
		return {"status": "success", "data": []}

	def _payments_for(project):
		fund_type = project["overhead_fund_type"]
		scope = _scope_params(fund_type, project["overhead_scope_id"])
		try:
			rows = fetch_overhead_logs(fund_type, scope)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Overhead Fund - Payment List Failed ({project['project_no']})",
			)
			return []
		if not isinstance(rows, list):
			return []

		# A PAYMENT row carries no parent commit id — the only link back to its COMMIT is
		# the frapAppId both share (the application docname). Build that map first.
		commit_by_frap = {}
		for row in rows:
			if row.get("transactionType") == "COMMIT" and row.get("frapAppId"):
				# An application can be re-committed; the newest commit is the live one.
				commit_by_frap[row["frapAppId"]] = row.get("transactionId")

		out = []
		for row in rows:
			if row.get("transactionType") != "PAYMENT":
				continue
			if wanted and (row.get("status") or "").upper() not in wanted:
				continue
			out.append({
				"transactionPaymentNumber": row.get("transactionId"),
				"transactionCommitNumber": commit_by_frap.get(row.get("frapAppId")),
				"projectNumber": project["project_no"],
				"accountHeadId": row.get("accountHeadId") or OVERHEAD_ACCOUNT_HEAD_ID,
				"paymentDate": row.get("transactionDate"),
				"paymentParticular": row.get("particulars") or "",
				"paymentAmount": flt(row.get("paymentAmount")),
				"paymentStatus": row.get("status"),
				"bmr": row.get("bmr"),
				"bankTransactionNumber": row.get("bankTransactionNumber"),
				"bankTransactionDate": row.get("bankTransactionDate"),
				"remarks": row.get("remarks"),
				"frapAppId": row.get("frapAppId"),
				"moduleId": row.get("moduleId"),
				"fundType": fund_type,
			})
		return out

	with ThreadPoolExecutor(max_workers=8) as executor:
		results = list(executor.map(_payments_for, projects))

	payments = [p for group in results for p in group]
	attach_module_ids(payments)
	payments.sort(key=lambda p: p.get("paymentDate") or "", reverse=True)
	return {"status": "success", "data": payments}


def attach_module_ids(commits):
	"""
	Fill in each commit's moduleId from our own staging records.

	The Accounts transaction log does not return `moduleId` — the field is simply absent
	from a COMMIT row, even though we send it. Without it the Payments page cannot split
	Miscellaneous Commit (module 25) and Recruitment (11) out of the main Pending Commits
	list, so overhead commits would all pile into one tab.

	We published these commits, so the module is knowable on our side. `Kafka Commit
	Staging` holds the original request keyed by the same frapAppId; one query for the
	whole batch, then two ways to read a module out of it:

	  1. the staged payload's own module override, present only when a caller deliberately
	     passed one (ICSS PO re-commit sends 14);
	  2. otherwise the staging row's `reference_doctype`, mapped through the very same
	     Module Registry lookup the producer used to derive `moduleId` at publish time.

	(2) is what makes this work at all for an ordinary commit. Nothing writes a module into
	the staged payload unless it is an override, so relying on (1) alone left `moduleId`
	null on every normal commit and collapsed the Payments tabs into one.
	"""
	frap_ids = [c["frapAppId"] for c in commits if c.get("frapAppId")]
	if not frap_ids:
		return

	from rndopsapp.rndopsapp.kafka.producer.overhead.producer import _module_id_for_doctype

	rows = frappe.get_all(
		"Kafka Commit Staging",
		filters={"reference_name": ["in", frap_ids]},
		fields=["reference_name", "payload", "reference_doctype"],
	)

	module_by_frap = {}
	# One Module Registry lookup per distinct doctype, not per commit.
	module_by_doctype = {}
	for row in rows:
		payload = row.get("payload")
		if isinstance(payload, str):
			try:
				payload = json.loads(payload)
			except ValueError:
				payload = None
		module_id = (payload or {}).get("moduleId") or (payload or {}).get("module_id")

		if module_id in (None, ""):
			doctype = row.get("reference_doctype")
			if doctype:
				if doctype not in module_by_doctype:
					module_by_doctype[doctype] = _module_id_for_doctype(doctype)
				module_id = module_by_doctype[doctype]

		if module_id not in (None, ""):
			module_by_frap[row["reference_name"]] = str(module_id)

	for c in commits:
		if not c.get("moduleId"):
			c["moduleId"] = module_by_frap.get(c.get("frapAppId"))
