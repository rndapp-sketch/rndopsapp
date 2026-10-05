# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ModuleRegistry(Document):
	pass


# -=-=-=-=-=
import frappe
from frappe.model.document import Document

# Roles allowed to see cross-user task/history views (get_task_registry,
# get_document_touch_history). Kept in one place so the two endpoints can't
# drift out of sync with each other.
RNDOPS_HISTORY_ROLES = [
	"staff, RnD",
	"project staff",
	"Hos, RnD (Head of Section, RnD)",
	"Dean, RnD",
	"Ado_RnD",
	"HoD (Head of Department)",
	"HoS (Head of School)",
	"HoC (Head of Center)",
	"head_department_center_school",
	"Director",
	"RnD Accounts",
	"RnD Administration",
	"RnD HR",
	"RnD Purchase",
	"System Manager",  # Always allow System Manager for admin access
]

# Reference doctypes that carry the applicant's department but no explicit
# head/approver field — their Cancellation Requests must still be scoped to
# the head of that department instead of being shown to every head.
DEPT_FIELD_MAP = {
	"Travel": "department_travel",
	"Reimbursement": "applicant_department",
	"Indent General Form": "igf_department_centre_section",
	"Indent Cum Sanction Sheet": "icss_applicant_department__centre__section",
	"Direct Purchase": "applicant_department",
	"Temporary Advance": "applicant_department",
}

# "Pending Head Approval" must be visible only to the specific head whose email
# is stored on the document. Field name varies per doctype.
HEAD_FIELD_MAP = {
	"Recruitment Adhoc Contractual": "head",
	"Project Registration": "head_approver",
	"Rate Contract": "current_approver",
}

# Some states must be scoped to a single specific user (not just a role) whose
# email is stored on the document, e.g. Reimbursement's Other-PI route parks
# the form at 'Pending PI Approval' for the chosen PI only.
SPECIFIC_APPROVER_MAP = {
	"Reimbursement": ("Pending PI Approval", "reimbursement_for_id"),
	"Travel": ("Pending Other PI", "travel_other_pi_id"),
	"Indent General Form": ("Pending Other PI", "igf_other_pi_id"),
	"Indent Cum Sanction Sheet": ("Pending Other PI", "icss_other_pi_id"),
	"Rate Contract": ("Pending Other PI", "other_pi_email"),
	"Direct Purchase": ("Pending Other PI", "dp_other_pi_id"),
}

# Kept in one place, referenced by name in get_pending_task and reused by
# rndopsapp.dashboard.track_application so the two endpoints can't drift apart
# on "which field names the actual approver on each doctype".


@frappe.whitelist()
def get_pending_task(page_name="pending-task"):
	"""
	Fetch docs where the CURRENT USER has a pending action.
	FIXED: Handles Role names that contain commas (e.g. "staff, RnD").
	"""

	# 1. Get Current User Roles
	current_user = frappe.session.user
	user_roles = frappe.get_roles(current_user)
	is_system_manager = "System Manager" in user_roles

	# Find departments this user heads — used for "Pending Head Approval" filtering.
	# Both the link ID and the readable name are kept: some doctypes store the
	# department as a Link (ID), others as plain Data (the department name).
	_head_depts = frappe.db.sql(
		"SELECT name, dept_name FROM `tabDepartment_prornd` WHERE dept_head = %s",
		current_user,
		as_dict=True,
	)
	dept_head_values = {d.name for d in _head_depts}
	dept_head_names = {(d.dept_name or "").strip().lower() for d in _head_depts if d.dept_name}

	def _heads_this_department(value):
		"""True when `value` (a Department_prornd ID *or* its name) is a
		department the current user heads."""
		v = (value or "").strip()
		if not v:
			return False
		return v in dept_head_values or v.lower() in dept_head_names

	dept_field_map = DEPT_FIELD_MAP

	# 2. Get Parent Module Registry
	parent = frappe.get_all(
		"Module Registry", filters={"page_name": page_name}, fields=["name"], limit_page_length=1
	)

	if not parent:
		return {"results": []}

	parent_doc = frappe.get_doc("Module Registry", parent[0].name)

	child_rows = getattr(parent_doc, "doctype_name", []) or []
	# Extract both doctype_name and mod_vis
	doctype_data = [(row.doctype_name, row.mod_vis) for row in child_rows if row.doctype_name]

	results = []

	# --- 4. Iterate Doctypes ---
	for dt, mod_vis in doctype_data:
		if not frappe.db.exists("DocType", dt):
			continue
		if not frappe.has_permission(dt, "read"):
			continue

		# --- WORKFLOW SELECTION ---
		wf_names = []
		if dt == "Project Registration":
			wf_names = ["pending_approval_prjReg"]
		elif dt == "Cancellation Request":
			workflows = frappe.get_all(
				"Workflow", filters={"document_type": "Cancellation Request"}, fields=["name"]
			)
			wf_names = [w.name for w in workflows]
		else:
			wf_name = frappe.get_value("Workflow", {"document_type": dt}, "name")
			if wf_name:
				wf_names = [wf_name]

		# --- DETERMINE ACTIONABLE STATES ---

		# A) Special Case: Advance Settlement (No Workflow)
		if dt == "Advance Settlement" and not wf_names:
			# Fetch "Submitted" documents (docstatus=1)
			records = frappe.get_list(
				dt,
				filters={"docstatus": 1},
				fields=["name", "creation", "modified", "owner", "docstatus"],
				order_by="modified desc",
				limit_page_length=1000,
				ignore_permissions=True,
			)

			mapped = []
			for r in records:
				mapped.append(
					{
						"name": r.name,
						"title": r.name,
						"status": "Submitted",
						"creation": r.creation,
						"modified": r.modified,
						"owner": r.owner,
						"docstatus": r.docstatus,
					}
				)

			if mapped:
				results.append({"doctype": dt, "mod_vis": mod_vis, "records": mapped})

			continue

		# B) Standard Case: Workflow
		if not wf_names:
			continue

		status_field = "workflow_state"
		actionable_states = set()

		# --- SMARTER ROLE CHECK FUNCTION ---
		def check_roles(config_raw):
			"""
			Determines if the user has permission based on the workflow string.
			Handles cases where role names contain commas.
			"""
			if not config_raw:
				return False
			if is_system_manager:
				return True

			raw_str = str(config_raw).strip()

			# STRATEGY 1: Check Exact Match (Handles "staff, RnD")
			if raw_str in user_roles:
				return True

			# STRATEGY 2: Check Newline Split
			for part in raw_str.split("\n"):
				if part.strip() in user_roles:
					return True

			# STRATEGY 3: Check Comma Split
			for part in raw_str.split(","):
				if part.strip() in user_roles:
					return True

			return False

		has_valid_wf = False
		for wfn in wf_names:
			if frappe.db.exists("Workflow", wfn):
				has_valid_wf = True
				wf_doc = frappe.get_doc("Workflow", wfn)
				status_field = wf_doc.workflow_state_field or status_field

				# A) Check States table (Allow Edit)
				for state_row in wf_doc.states:
					if check_roles(state_row.allow_edit):
						actionable_states.add(state_row.state)

				# B) Check Transitions table (Allowed Action)
				for transition_row in wf_doc.transitions:
					if check_roles(transition_row.allowed):
						actionable_states.add(transition_row.state)

		if not has_valid_wf:
			continue

		# Exclude states that are universally terminal (no transition can ever follow).
		# "Sanction Approved" is intentionally NOT excluded here — some doctypes
		# (e.g. Direct Purchase) have further transitions from that state, so the
		# workflow transitions table already determines whether it is actionable.
		for excluded in ("Draft", "Endorsement Approved"):
			actionable_states.discard(excluded)

		# Ado_RnD: restrict strictly to Associate-Dean pending states so the
		# inbox doesn't pick up transitions that merely share the role.
		if "Ado_RnD" in user_roles and not is_system_manager:
			ado_states = {"Pending Associate Dean", "Pending Associate Dean Approval"}
			actionable_states &= ado_states

		if not actionable_states:
			continue

		# --- DATA FETCHING ---
		meta = frappe.get_meta(dt)

		# Safeguard constraint: The doctype MUST have the status_field in its schema
		if not meta.has_field(status_field):
			continue

		title_field = (
			meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name")
		)

		head_field_map = HEAD_FIELD_MAP
		head_field = head_field_map.get(dt)
		if head_field and not meta.has_field(head_field):
			head_field = None

		specific_approver_map = SPECIFIC_APPROVER_MAP
		sa_state = sa_field = None
		sa = specific_approver_map.get(dt)
		if sa and meta.has_field(sa[1]):
			sa_state, sa_field = sa

		extra_fields = [head_field] if head_field else []
		if sa_field and sa_field not in extra_fields:
			extra_fields.append(sa_field)
		if dt == "Travel" and meta.has_field("department_travel") and "department_travel" not in extra_fields:
			extra_fields.append("department_travel")
		if dt == "Travel" and meta.has_field("travel_head_approver_id") and "travel_head_approver_id" not in extra_fields:
			extra_fields.append("travel_head_approver_id")
		if dt == "Cancellation Request":
			for f in ["reference_doctype", "reference_name"]:
				if f not in extra_fields:
					extra_fields.append(f)

		try:
			records = frappe.get_list(
				dt,
				filters={status_field: ["in", list(actionable_states)], "docstatus": ["<", 2]},
				fields=["name", title_field, status_field, "modified", "owner", "docstatus", "creation"]
				+ extra_fields,
				order_by="modified desc",
				limit_page_length=1000,
				ignore_permissions=True,
			)
		except Exception as e:
			frappe.log_error(
				f"Error fetching pending tasks for {dt}", f"get_pending_task API Error: {str(e)}"
			)
			print(f"Skipping {dt} due to error: {str(e)}")
			continue

		mapped = []
		for r in records:
			# print("r:",r)
			if dt == "Cancellation Request" and not is_system_manager:
				ref_dt = r.get("reference_doctype")
				ref_name = r.get("reference_name")
				curr_status = r.get(status_field)
				ref_doc = None
				if ref_dt and ref_name and frappe.db.exists(ref_dt, ref_name):
					ref_doc = frappe.db.get_value(ref_dt, ref_name, "*", as_dict=True)

				# Reference document missing/deleted/unreadable: these states can
				# only be scoped by reading a field off that document, so without
				# it we can't verify who the intended approver is. Fail CLOSED
				# (skip) rather than show it to everyone the broad role check let in.
				if not ref_doc:
					if curr_status in ("Pending Head Approval", "Pending Other PI", "Pending PI Approval"):
						continue
				else:
					# A) Head Approval filtering for the underlying reference document
					if curr_status == "Pending Head Approval":
						# Travel Other-PI: the head step is re-pointed to the
						# funding PI's department head, so honour that first.
						travel_head = (ref_doc.get("travel_head_approver_id") or "").strip().lower()
						if ref_dt == "Travel" and travel_head:
							if travel_head != current_user.lower():
								continue
						elif ref_dt in dept_field_map:
							if not _heads_this_department(ref_doc.get(dept_field_map[ref_dt])):
								continue
						elif ref_dt in head_field_map:
							h_field = head_field_map[ref_dt]
							h_email = (ref_doc.get(h_field) or "").strip().lower()
							if h_email != current_user.lower():
								continue
						else:
							h_email = (
								ref_doc.get("head")
								or ref_doc.get("head_approver")
								or ref_doc.get("department_head")
								or ref_doc.get("dept_head")
								or ""
							).strip().lower()
							if h_email:
								if h_email != current_user.lower():
									continue
							else:
								# No head field and no known department field:
								# fall back to any department-looking value so
								# the request is not exposed to every head.
								dept_val = (
									ref_doc.get("applicant_department")
									or ref_doc.get("department")
									or ""
								)
								if not _heads_this_department(dept_val):
									continue

					# B) Specific Approver / Other PI filtering for reference document.
					# Fail CLOSED: if no approver is recorded on the reference doc,
					# don't fall through to "visible to everyone with the role" —
					# these states are only ever meant for one specific person.
					ref_sa = specific_approver_map.get(ref_dt)
					if ref_sa:
						ref_sa_state, ref_sa_field = ref_sa
						if curr_status == ref_sa_state:
							appr_email = (ref_doc.get(ref_sa_field) or "").strip().lower()
							if appr_email != current_user.lower():
								continue

					# C) Pending PI Approval filtering for reference document (fail closed, as above).
					if curr_status == "Pending PI Approval":
						pi_email = (
							ref_doc.get("reimbursement_for_id")
							or ref_doc.get("pi_id")
							or ref_doc.get("pi_webmail")
							or ref_doc.get("pi")
							or ref_doc.get("pi_email")
							or ref_doc.get("pi_mentor_user")
							or ""
						).strip().lower()
						if pi_email != current_user.lower():
							continue

			if head_field and r.get(status_field) == "Pending Head Approval" and not is_system_manager:
				head_email = (r.get(head_field) or "").strip().lower()
				if head_email != current_user.lower():
					continue

			# Specific-approver states (e.g. Reimbursement "Pending PI Approval")
			# are visible only to the exact user stored on the document.
			if sa_field and r.get(status_field) == sa_state and not is_system_manager:
				approver_email = (r.get(sa_field) or "").strip().lower()
				if approver_email != current_user.lower():
					continue

			# Travel: filter "Pending Head Approval" to the correct dept head.
			# For an Other-PI form the head is re-pointed to the FUNDING PI's
			# department head (stored on travel_head_approver_id); otherwise it
			# falls back to the head of the applicant's own department.
			if (
				dt == "Travel"
				and r.get(status_field) == "Pending Head Approval"
				and not is_system_manager
			):
				head_override = (r.get("travel_head_approver_id") or "").strip().lower()
				if head_override:
					if head_override != current_user.lower():
						continue
				else:
					doc_dept = (r.get("department_travel") or "").strip()
					if doc_dept not in dept_head_values:
						continue

			mapped.append(
				{
					"name": r.get("name"),
					"title": r.get(title_field),
					"status": r.get(status_field),
					"creation": r.get("creation"),
					"modified": r.get("modified"),
					"owner": r.get("owner"),
					"docstatus": r.get("docstatus"),
				}
			)

		if mapped:
			results.append(
				{
					"doctype": dt,
					"mod_vis": mod_vis,  # Added mod_vis field
					"records": mapped,
				}
			)
			# print("results:", results)

	return {"page": page_name, "user": current_user, "results": results}


@frappe.whitelist()
def get_pending_application():
	"""
	Returns applications pending the current user's approval as PI, combining:
	- Leave Module: filtered by pi == frappe.session.user, workflow_state == "Pending PI Approval".
	- Project Staff Extension: has no "pi" field, so instead matched via whichever
	  of these identifies the applicant as this PI's staff (ex_emp_id is free text
	  and often left blank, so the owner-based check is the reliable path):
	    a) ex_emp_id against Project Staff Details.pi_id / User.piheadmentor_user_id
	    b) the document's owner being a User whose piheadmentor_user_id == current user
	- Other-PI forms (Travel, Indent General Form, Indent Cum Sanction Sheet,
	  Reimbursement, Direct Purchase): the applicant charged the form to a project owned by
	  this user, so it is parked with them ("Pending Other PI", or "Pending PI
	  Approval" for Reimbursement) until they pick the funding project/account
	  head. Without this the designated PI has no inbox for them, since the
	  Pending Task page is not shown to Permanent Employees.
	- Cancellation Request, any pending state: "Pending Other PI" / "Pending PI
	  Approval" is scoped to the specific PI recorded on the referenced
	  document (same as the Other-PI forms above); every other pending state
	  (Staff, HoS, Associate Dean, Dean, Head, Director, ...) is scoped to
	  whoever holds that state's role on the cancellation's own workflow.
	Each record is tagged with "doctype" so callers can tell the sources apart.
	"""

	current_user = frappe.session.user

	leave_records = frappe.get_list(
		"Leave Module",
		filters={
			"pi": current_user,
			"workflow_state": "Pending PI Approval",
			"docstatus": 0,
		},
		fields=["name", "username", "pi", "leave_type", "workflow_state", "modified", "owner", "docstatus", "creation"],
		order_by="modified desc",
		limit_page_length=10000,
	)
	for r in leave_records:
		r["doctype"] = "Leave Module"

	pi_users = frappe.get_all(
		"User",
		filters={"piheadmentor_user_id": current_user},
		fields=["name", "employee_id"],
	)
	pi_owner_emails = [u.name for u in pi_users]

	pi_emp_ids_from_details = frappe.get_all(
		"Project Staff Details",
		filters={"pi_id": current_user},
		pluck="ps_emp_id",
	)
	pi_emp_ids_from_user = [u.employee_id for u in pi_users]
	pi_emp_ids = {e for e in (pi_emp_ids_from_details + pi_emp_ids_from_user) if e}

	extension_records = []
	if pi_emp_ids or pi_owner_emails:
		or_filters = []
		if pi_emp_ids:
			or_filters.append(["ex_emp_id", "in", list(pi_emp_ids)])
		if pi_owner_emails:
			or_filters.append(["owner", "in", pi_owner_emails])

		extension_records = frappe.get_list(
			"Project Staff Extension",
			filters={
				"workflow_state": "Pending PI Approval",
				"docstatus": 1,
			},
			or_filters=or_filters,
			fields=["name", "ex_name", "ex_proj_name", "ex_proj_no", "ex_emp_id", "workflow_state", "modified", "owner", "docstatus", "creation"],
			order_by="modified desc",
			limit_page_length=10000,
			ignore_permissions=True,
		)
		for r in extension_records:
			r["doctype"] = "Project Staff Extension"

	# Project Staff Resignation: same no-"pi"-field situation as Extension above,
	# matched the same way via applicant_emp_id / owner. Unlike Extension, this
	# doctype stays at docstatus 0 all the way through "Pending PI Approval"
	# (it only reaches docstatus 1 once Dean-approved), so the docstatus filter
	# here is 0, not 1.
	resignation_records = []
	if pi_emp_ids or pi_owner_emails:
		or_filters = []
		if pi_emp_ids:
			or_filters.append(["applicant_emp_id", "in", list(pi_emp_ids)])
		if pi_owner_emails:
			or_filters.append(["owner", "in", pi_owner_emails])

		resignation_records = frappe.get_list(
			"Project Staff Resignation",
			filters={
				"workflow_state": "Pending PI Approval",
				"docstatus": 0,
			},
			or_filters=or_filters,
			fields=["name", "applicant_name", "applicant_prj_num", "applicant_emp_id", "workflow_state", "modified", "owner", "docstatus", "creation"],
			order_by="modified desc",
			limit_page_length=10000,
			ignore_permissions=True,
		)
		for r in resignation_records:
			r["doctype"] = "Project Staff Resignation"

	records = leave_records + extension_records + resignation_records

	# doctype -> (other-PI field, state it waits in, applicant-name field)
	other_pi_sources = {
		"Travel": ("travel_other_pi_id", "Pending Other PI", "applicant_name_travel"),
		"Indent General Form": ("igf_other_pi_id", "Pending Other PI", "igf_indenter"),
		"Indent Cum Sanction Sheet": ("icss_other_pi_id", "Pending Other PI", "icss_applicant_name"),
		"Reimbursement": ("reimbursement_for_id", "Pending PI Approval", "applicant_webmail"),
		"Direct Purchase": ("dp_other_pi_id", "Pending Other PI", "applicant_name"),
	}

	for dt, (pi_field, state, name_field) in other_pi_sources.items():
		try:
			meta = frappe.get_meta(dt)
			if not meta.has_field(pi_field):
				continue
			fields = ["name", "workflow_state", "modified", "owner", "docstatus", "creation"]
			if meta.has_field(name_field):
				fields.append(name_field)
			rows = frappe.get_list(
				dt,
				filters={pi_field: current_user, "workflow_state": state},
				fields=fields,
				order_by="modified desc",
				limit_page_length=10000,
				ignore_permissions=True,
			)
			for r in rows:
				r["doctype"] = dt
				r["pi"] = current_user
				r["username"] = r.get(name_field) or r.get("owner")
				records.append(r)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"get_pending_application: {dt} lookup failed")

	# Cancellation Request: was showing every pending cancellation to every
	# user, regardless of state. Scope each one the same way its *own* state
	# is scoped on the source doctype:
	#   - "Pending Other PI" / "Pending PI Approval" -> the specific PI/other-PI
	#     recorded on the referenced document (other_pi_sources above).
	#   - every other "Pending ..." step (Staff, HoS, Associate Dean, Dean,
	#     Head, Director, ...) -> whoever holds that state's `allow_edit` role
	#     on the cancellation's own workflow (cancel_<source_workflow>), same
	#     as a normal role-gated approval step.
	try:
		user_roles = frappe.get_roles(current_user)
		is_system_manager = "System Manager" in user_roles

		cancel_records = frappe.get_list(
			"Cancellation Request",
			filters={"docstatus": ["<", 2]},
			fields=[
				"name", "reference_doctype", "reference_name", "workflow_state",
				"source_workflow", "modified", "owner", "docstatus", "creation",
			],
			order_by="modified desc",
			limit_page_length=10000,
			ignore_permissions=True,
		)

		_allow_edit_cache = {}

		def _allow_edit_role(source_workflow, state):
			key = (source_workflow, state)
			if key not in _allow_edit_cache:
				role = None
				if source_workflow:
					role = frappe.db.get_value(
						"Workflow Document State",
						{"parent": f"cancel_{source_workflow}", "state": state},
						"allow_edit",
					)
				_allow_edit_cache[key] = role
			return _allow_edit_cache[key]

		for r in cancel_records:
			state = r.get("workflow_state") or ""
			if "pending" not in state.lower():
				# Draft / Approved / Rejected / *Generated / *Printed etc. — not
				# awaiting anyone's action.
				continue

			ref_dt = r.get("reference_doctype")
			ref_name = r.get("reference_name")
			src = other_pi_sources.get(ref_dt)

			if src and src[1] == state:
				# PI-specific step: same scoping as the non-cancellation records above.
				pi_field, _expected_state, name_field = src
				if not ref_name or not frappe.db.exists(ref_dt, ref_name):
					continue
				approver = (frappe.db.get_value(ref_dt, ref_name, pi_field) or "").strip()
				if approver.lower() != current_user.lower():
					continue
				r["pi"] = current_user
				r["username"] = frappe.db.get_value(ref_dt, ref_name, name_field) or r.get("owner")
			elif not is_system_manager:
				role = _allow_edit_role(r.get("source_workflow"), state)
				if not role or role not in user_roles:
					continue

			r["doctype"] = "Cancellation Request"
			records.append(r)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_pending_application: Cancellation Request lookup failed")

	records.sort(key=lambda r: r.get("modified") or "", reverse=True)

	return {"user": current_user, "results": records}


def _categorize_task_results(doctype_groups):
	"""
	Buckets every record across `doctype_groups` (the common {doctype, records:
	[{name, title, status, creation, owner, ...}]} shape shared by
	get_pending_task's and get_task_registry's `results`) into research /
	consultancy / others, resolving each record's linked Project Registration
	via DOCTYPE_PR_LINKS (project_type_links.py) with two batched queries
	(Project Registration by name, by project_no) instead of one query per
	record or a client-side bulk fetch of every Project Registration.
	"""
	from rndopsapp.rndopsapp.doctype.module_registry.project_type_links import (
		DOCTYPE_PR_LINKS,
		DEPOSIT_SLIP_DOCTYPES,
		HARDCODED_CONSULTANCY_DOCTYPES,
		pr_link_fields,
		resolve_project_category,
		resolve_project_no,
	)

	buckets = {"research": [], "consultancy": [], "others": []}

	# 1. Batch-fetch the PR-link field(s) (plus, for Fund Received, its own
	# reference number; for Cancellation Request, the reference_doctype/
	# reference_name it points at — get_task_registry doesn't fetch those by
	# default, so they're re-fetched here regardless of source) each doctype
	# needs beyond what's already on the record.
	for group in doctype_groups:
		dt = group.get("doctype")
		records = group.get("records") or []
		if not records or not frappe.db.exists("DocType", dt):
			continue

		wanted = set(pr_link_fields(dt))
		if dt == "Fund Received":
			wanted.add("fund_received_ref_number")
		if dt == "Cancellation Request":
			wanted |= {"reference_doctype", "reference_name"}

		fetch_fields = [f for f in wanted if frappe.db.has_column(dt, f)]

		extra_by_name = {}
		if fetch_fields:
			names = [r.get("name") for r in records if r.get("name")]
			if names:
				rows = frappe.get_all(
					dt,
					filters={"name": ["in", names]},
					fields=["name"] + fetch_fields,
					ignore_permissions=True,
				)
				extra_by_name = {row["name"]: row for row in rows}

		for r in records:
			r["_extra"] = extra_by_name.get(r.get("name"), {})

	# 1b. Cancellation Request has no Project Registration link of its own —
	# it cancels some other application (Travel, Reimbursement, Project
	# Registration itself, ...) named by reference_doctype/reference_name.
	# Resolve each Cancellation Request row to that underlying application's
	# (doctype, record) pair instead, batch-fetching the referenced doctype's
	# own PR-link field(s) the same way step 1 does for a direct doctype, so
	# a cancellation is bucketed by the project it actually cancels against.
	logical_target = {}  # Cancellation Request name -> (logical_dt, logical_record)
	cr_group = next((g for g in doctype_groups if g.get("doctype") == "Cancellation Request"), None)
	if cr_group:
		by_ref_dt = {}
		for r in cr_group.get("records") or []:
			extra = r.get("_extra", {})
			ref_dt, ref_name = extra.get("reference_doctype"), extra.get("reference_name")
			if ref_dt and ref_name:
				by_ref_dt.setdefault(ref_dt, set()).add(ref_name)

		ref_extra = {}  # (ref_dt, ref_name) -> fetched field dict
		for ref_dt, ref_names in by_ref_dt.items():
			if not frappe.db.exists("DocType", ref_dt):
				continue
			fields = [f for f in pr_link_fields(ref_dt) if frappe.db.has_column(ref_dt, f)]
			rows = frappe.get_all(
				ref_dt,
				filters={"name": ["in", list(ref_names)]},
				fields=["name"] + fields,
				ignore_permissions=True,
			)
			for row in rows:
				ref_extra[(ref_dt, row["name"])] = row

		for r in cr_group.get("records") or []:
			extra = r.get("_extra", {})
			ref_dt, ref_name = extra.get("reference_doctype"), extra.get("reference_name")
			if not ref_dt or not ref_name:
				continue
			fetched = ref_extra.get((ref_dt, ref_name), {"name": ref_name})
			logical_target[r.get("name")] = (ref_dt, {**fetched, "name": ref_name})

	def _logical(dt, r, merged):
		"""(doctype, record) to actually resolve project links against."""
		if dt == "Cancellation Request" and r.get("name") in logical_target:
			return logical_target[r["name"]]
		return dt, merged

	# 2. Collect every PR `name` / `project_no` referenced in this batch, to
	# resolve project_type in two queries instead of one per record.
	pr_names, pr_nos = set(), set()
	for group in doctype_groups:
		dt = group.get("doctype")
		for r in group.get("records") or []:
			merged = {**r, **r.get("_extra", {})}
			logical_dt, logical_record = _logical(dt, r, merged)
			mapping = DOCTYPE_PR_LINKS.get(logical_dt)
			if logical_dt in HARDCODED_CONSULTANCY_DOCTYPES or not mapping:
				continue
			for strategy in (mapping.get("primary"), mapping.get("fallback")):
				if not strategy:
					continue
				kind, field = strategy
				if kind == "self":
					if logical_record.get("name"):
						pr_names.add(logical_record["name"])
				elif kind == "pr_name" and logical_record.get(field):
					pr_names.add(logical_record[field])
				elif kind == "pr_project_no" and logical_record.get(field):
					pr_nos.add(logical_record[field])

	pr_name_to_type, pr_name_to_no = {}, {}
	if pr_names:
		rows = frappe.get_all(
			"Project Registration",
			filters={"name": ["in", list(pr_names)]},
			fields=["name", "project_type", "project_no"],
			ignore_permissions=True,
		)
		for row in rows:
			pr_name_to_type[row["name"]] = row.get("project_type")
			pr_name_to_no[row["name"]] = row.get("project_no")

	pr_no_to_type = {}
	if pr_nos:
		rows = frappe.get_all(
			"Project Registration",
			filters={"project_no": ["in", list(pr_nos)]},
			fields=["project_no", "project_type"],
			ignore_permissions=True,
		)
		for row in rows:
			pr_no_to_type[row["project_no"]] = row.get("project_type")

	# 3. Batch-resolve the "Deposit: RES-DS-..." sub-line for Fund Received rows
	# — every deposit-slip doctype stores `fund_received_ref` == the parent
	# Fund Received's own `fund_received_ref_number`.
	deposit_by_ref = {}
	fr_group = next((g for g in doctype_groups if g.get("doctype") == "Fund Received"), None)
	if fr_group:
		refs = list({
			r["_extra"].get("fund_received_ref_number")
			for r in fr_group.get("records") or []
			if r.get("_extra", {}).get("fund_received_ref_number")
		})
		if refs:
			for ds_dt in DEPOSIT_SLIP_DOCTYPES:
				if not frappe.db.exists("DocType", ds_dt):
					continue
				rows = frappe.get_all(
					ds_dt,
					filters={"fund_received_ref": ["in", refs]},
					fields=["name", "fund_received_ref"],
					ignore_permissions=True,
				)
				for row in rows:
					deposit_by_ref.setdefault(row["fund_received_ref"], row["name"])

	# 4. Flatten every doctype's records into one row shape, bucketed by category.
	for group in doctype_groups:
		dt = group.get("doctype")
		for r in group.get("records") or []:
			extra = r.get("_extra", {})
			merged = {**r, **extra}
			logical_dt, logical_record = _logical(dt, r, merged)

			category = resolve_project_category(logical_record, logical_dt, pr_name_to_type, pr_no_to_type)
			project_no = resolve_project_no(logical_record, logical_dt, pr_name_to_no)

			# mod_vis is passed through unfiltered, exactly as get_pending_task's
			# own results already do (it's None for get_task_registry, which has
			# no such concept). Neither this field nor the HoS bypass for
			# mod_vis=0 groups on "Pending HoS Approval" records is filtered
			# here — that logic has always lived in the frontend, not in
			# get_pending_task, and this endpoint intentionally leaves it there
			# too rather than guessing at a rule it can't see.
			row = {
				"status": r.get("status"),
				"module": dt,
				"title": r.get("title"),
				"project_no": project_no,
				"date": str(r.get("creation"))[:10] if r.get("creation") else None,
				"owner": r.get("owner"),
				"doctype": dt,
				"name": r.get("name"),
				"mod_vis": group.get("mod_vis"),
			}

			if dt == "Fund Received":
				deposit_slip = deposit_by_ref.get(extra.get("fund_received_ref_number"))
				if deposit_slip:
					row["deposit_slip"] = deposit_slip

			buckets[category].append(row)

	return buckets


@frappe.whitelist()
def get_categorized_pending_task(page_name="pending-task"):
	"""
	Endpoint: /api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_categorized_pending_task

	Same records as get_pending_task(page_name) — that function's permission,
	workflow-state and role/department-head scoping is reused as-is, not
	duplicated — but pre-bucketed into {"research": [...], "consultancy": [...],
	"others": [...]} so the frontend no longer needs to bulk-fetch every
	Project Registration and resolve DOCTYPE_PR_LINKS client-side.
	"""
	base = get_pending_task(page_name=page_name)
	return _categorize_task_results(base.get("results") or [])


def _module_registry_doctypes(page_name):
	"""
	The set of doctype names registered under Module Registry(page_name) —
	the same curated "application" list get_pending_task(page_name) scopes
	itself to. get_task_registry, unlike get_pending_task, has no such
	restriction of its own: it walks every doctype in the whole Rndopsapp
	module (internal logs like Staff Activity Log / Kafka *, deposit-slip
	doctypes that aren't user-facing applications like D Consultancy Deposit
	Slip, etc. included). get_categorized_task_registry uses this to narrow
	its output back down to real "pending task" modules only.
	"""
	if not frappe.db.exists("Module Registry", page_name):
		return set()
	return set(
		frappe.get_all(
			"Module Registry Item", filters={"parent": page_name}, pluck="doctype_name"
		)
	)


@frappe.whitelist()
def get_categorized_task_registry(debug=0, page_name="pending-task"):
	"""
	Endpoint: /api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_categorized_task_registry

	Same records as get_task_registry(debug) — that function's role gating and
	document-discovery logic is reused as-is, not duplicated — but narrowed to
	only the doctypes registered in Module Registry(page_name) (the same
	"pending task" module list get_categorized_pending_task is scoped to —
	see _module_registry_doctypes) and pre-bucketed into {"research": [...],
	"consultancy": [...], "others": [...]} the same way
	get_categorized_pending_task is.
	"""
	base = get_task_registry(debug=debug)
	if not base.get("success"):
		return base

	allowed = _module_registry_doctypes(page_name)
	scoped_results = [g for g in (base.get("results") or []) if g.get("doctype") in allowed]

	grouped = _categorize_task_results(scoped_results)
	grouped["success"] = True
	return grouped


@frappe.whitelist()
def get_task_registry(debug=0):
	"""
	Endpoint: /api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_task_registry

	Returns all documents that were processed/moved/approved by the current user.
	Only accessible by roles: staff, hos, dean, adornd, head of department.

	Pass ?debug=1 to include per-doctype diagnostics (why each doctype was
	kept/dropped, plus per-method hit counts: modified_by / Version / Workflow Action).
	"""

	try:
		debug_flag = bool(int(debug))
	except (TypeError, ValueError):
		debug_flag = bool(debug)

	# 1. Get Current User and Roles
	current_user = frappe.session.user
	user_roles = frappe.get_roles(current_user)

	# Check if user has any of the allowed roles
	has_allowed_role = any(role in RNDOPS_HISTORY_ROLES for role in user_roles)

	if not has_allowed_role:
		return {
			"success": False,
			"message": "Access denied. Only authorized RnD roles (staff, HoS, Dean, Ado_RnD, HoD, HoS, HoC, Director, RnD Accounts/Admin/HR/Purchase) can access this endpoint.",
			"results": [],
		}

	print(f"\n--- DEBUG: get_task_registry for user '{current_user}' ---")
	print(f"User Roles: {user_roles}")

	# 2. Get all doctypes from the rndopsapp module (case-insensitive)
	rndops_doctypes = frappe.get_all(
		"DocType", filters=[["module", "like", "%rndopsapp%"]], fields=["name", "module"]
	)

	if not rndops_doctypes:
		# Try exact match as fallback
		rndops_doctypes = frappe.get_all(
			"DocType", filters={"module": "Rndopsapp"}, fields=["name", "module"]
		)

	doctype_names = [dt.name for dt in rndops_doctypes]
	print(f"Doctypes in Rndopsapp module ({len(doctype_names)}): {doctype_names}")

	skipped_info = []  # Track why doctypes are skipped
	debug_info = []  # Populated only when debug_flag is True

	def _dbg(entry):
		if debug_flag:
			debug_info.append(entry)

	results = []

	# 3. For each doctype, find documents modified by the current user
	# where workflow_state has been changed (meaning they performed an action)
	for dt_name in doctype_names:
		# Skip child tables and non-workflow doctypes
		if not frappe.db.exists("DocType", dt_name):
			_dbg({"doctype": dt_name, "reason": "doctype row missing"})
			continue

		meta = frappe.get_meta(dt_name)

		# Skip child tables
		if meta.istable:
			_dbg({"doctype": dt_name, "reason": "child table (istable=1)"})
			continue

		# Check read permission
		if not frappe.has_permission(dt_name, "read"):
			skipped_info.append({"doctype": dt_name, "reason": "no read permission"})
			_dbg({"doctype": dt_name, "reason": "no read permission"})
			continue

		# Determine status field - can be workflow_state, status, or state
		status_field = None
		for field_name in ["workflow_state", "status", "state"]:
			if meta.has_field(field_name):
				status_field = field_name
				break

		try:
			# Method 1: Get documents modified by user (simple approach)
			# This finds docs where the user was the last one to modify
			fields_to_fetch = ["name", "modified", "owner", "creation", "docstatus"]
			if status_field:
				fields_to_fetch.append(status_field)

			modified_docs = frappe.get_list(
				dt_name,
				filters={
					"modified_by": current_user,
					"docstatus": ["<", 2],  # Exclude cancelled
				},
				fields=fields_to_fetch,
				order_by="modified desc",
				limit_page_length=1000,
				ignore_permissions=True,
			)

			# Method 2: Also get docs from Version/Activity Log where user performed workflow action
			# Query the Version doctype to find workflow state changes by this user
			version_docs = []
			try:
				versions = frappe.get_all(
					"Version",
					filters={"ref_doctype": dt_name, "owner": current_user},
					fields=["docname", "creation", "data"],
					order_by="creation desc",
					limit_page_length=100,
				)

				# Filter versions that contain workflow_state changes
				for v in versions:
					if v.data and "workflow_state" in v.data:
						if v.docname not in [d.name for d in modified_docs]:
							# Get the document details
							if frappe.db.exists(dt_name, v.docname):
								doc_data = frappe.get_value(dt_name, v.docname, fields_to_fetch, as_dict=True)
								if doc_data and doc_data.docstatus < 2:
									version_docs.append(doc_data)
			except Exception as e:
				print(f"Version query error for {dt_name}: {str(e)}")

			# Method 3: Get docs from Workflow Action (where user completed an action)
			# This is crucial for doctypes without track_changes enabled (like Reimbursement)
			wf_action_docs = []
			try:
				wf_actions = frappe.get_all(
					"Workflow Action",
					filters={
						"reference_doctype": dt_name,
						"status": "Completed",
						"completed_by": current_user,
					},
					fields=[
						"reference_name",
						"creation",
					],  # creation here is when action was requested/completed
					order_by="creation desc",
					limit_page_length=100,
				)

				processed_names = {w.reference_name for w in wf_actions}

				# Filter out docs we already found to avoid double fetching
				existing_names = set(d.name for d in modified_docs)
				# Note: version_docs aren't fully resolved to names yet in scope, but we check duplicates later

				# Fetch details for these docs
				if processed_names:
					# Batch fetch
					placeholders = ", ".join(["%s"] * len(processed_names))
					fetched_wf_docs = frappe.db.sql(
						f"""
						SELECT {", ".join(fields_to_fetch)}
						FROM `tab{dt_name}`
						WHERE name IN ({placeholders}) AND docstatus < 2
					""",
						tuple(processed_names),
						as_dict=True,
					)

					wf_action_docs = fetched_wf_docs
			except Exception as e:
				print(f"Workflow Action query error for {dt_name}: {str(e)}")

			# Method 4: Workflow Comments — catches cases where Frappe left the
			# Workflow Action as "Open"/no completed_by (known Frappe gap) but still
			# wrote a Workflow-type Comment when the user triggered the transition.
			wf_comment_docs = []
			try:
				wf_comments = frappe.get_all(
					"Comment",
					filters={
						"reference_doctype": dt_name,
						"comment_type": "Workflow",
						"owner": current_user,
					},
					fields=["reference_name"],
					limit_page_length=100,
					ignore_permissions=True,
				)

				comment_names = {c.reference_name for c in wf_comments}
				if comment_names:
					placeholders = ", ".join(["%s"] * len(comment_names))
					wf_comment_docs = frappe.db.sql(
						f"""
						SELECT {", ".join(fields_to_fetch)}
						FROM `tab{dt_name}`
						WHERE name IN ({placeholders}) AND docstatus < 2
					""",
						tuple(comment_names),
						as_dict=True,
					)
			except Exception as e:
				print(f"Workflow Comment query error for {dt_name}: {str(e)}")

			# Combine and deduplicate
			all_doc_names = set()
			combined_docs = []

			for doc in modified_docs:
				if doc.name not in all_doc_names:
					all_doc_names.add(doc.name)
					combined_docs.append(doc)

			for doc in version_docs:
				if doc.name not in all_doc_names:
					all_doc_names.add(doc.name)
					combined_docs.append(doc)

			for doc in wf_action_docs:
				if doc.name not in all_doc_names:
					all_doc_names.add(doc.name)
					combined_docs.append(doc)

			for doc in wf_comment_docs:
				if doc.name not in all_doc_names:
					all_doc_names.add(doc.name)
					combined_docs.append(doc)

			# Diagnostics: per-method counts for this doctype
			has_workflow = bool(frappe.db.exists("Workflow", {"document_type": dt_name}))
			method_counts = {
				"method1_modified_by": len(modified_docs),
				"method2_versions": len(version_docs),
				"method3_workflow_action": len(wf_action_docs),
				"method4_workflow_comment": len(wf_comment_docs),
				"combined_unique": len(combined_docs),
			}

			if not combined_docs:
				_dbg(
					{
						"doctype": dt_name,
						"reason": "no matching records for this user",
						"status_field": status_field,
						"has_workflow": has_workflow,
						"track_changes": bool(getattr(meta, "track_changes", 0)),
						"counts": method_counts,
					}
				)
				continue

			# Get title field for better display
			title_field = (
				meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name")
			)

			# Fetch full details for display
			mapped = []
			for doc in combined_docs:
				doc_state = doc.get(status_field) if status_field else None

				# Get title value if different from name
				title_value = doc.name
				if title_field != "name":
					title_value = frappe.get_value(dt_name, doc.name, title_field) or doc.name

				mapped.append(
					{
						"name": doc.name,
						"title": title_value,
						"status": doc_state,
						"creation": doc.creation,
						"modified": doc.modified,
						"owner": doc.owner,
						"docstatus": doc.docstatus,
					}
				)

			# Sort by modified date descending
			mapped.sort(key=lambda x: x["modified"] if x["modified"] else "", reverse=True)

			if mapped:
				results.append({"doctype": dt_name, "count": len(mapped), "records": mapped})
				_dbg(
					{
						"doctype": dt_name,
						"reason": "included",
						"status_field": status_field,
						"has_workflow": has_workflow,
						"track_changes": bool(getattr(meta, "track_changes", 0)),
						"counts": method_counts,
					}
				)
				print(f"Found {len(mapped)} documents in {dt_name} processed by user")

		except Exception as e:
			print(f"Error processing {dt_name}: {str(e)}")
			_dbg({"doctype": dt_name, "reason": "exception", "error": str(e)})
			continue

	# Sort results by doctype name for consistent ordering
	results.sort(key=lambda x: x["doctype"])

	response = {
		"success": True,
		"user": current_user,
		"roles": user_roles,
		"doctypes_in_module": len(doctype_names),
		"total_doctypes_with_data": len(results),
		"total_documents": sum(r["count"] for r in results),
		"skipped": skipped_info,
		"results": results,
	}

	if debug_flag:
		response["debug"] = {
			"all_doctypes_in_module": sorted(doctype_names),
			"per_doctype": sorted(debug_info, key=lambda x: x.get("doctype", "")),
		}

	return response


@frappe.whitelist()
def get_rndopsapp_doctypes():
	"""
	Endpoint: /api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_rndopsapp_doctypes

	Returns the sorted list of non-child doctype names in the Rndopsapp
	module, for populating the DocType filter dropdown on doc_history.html.
	"""

	current_user = frappe.session.user
	user_roles = frappe.get_roles(current_user)

	if not any(role in RNDOPS_HISTORY_ROLES for role in user_roles):
		return {"success": False, "message": "Access denied.", "doctypes": []}

	doctype_names = frappe.get_all("DocType", filters=[["module", "like", "%rndopsapp%"]], pluck="name")

	doctypes = []
	for dt in sorted(doctype_names):
		if not frappe.db.exists("DocType", dt):
			continue
		if frappe.get_meta(dt).istable:
			continue
		doctypes.append(dt)

	return {"success": True, "doctypes": doctypes}


@frappe.whitelist()
def get_document_touch_history(docname, doctype=None):
	"""
	Endpoint: /api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_document_touch_history

	Given a document id, return every user who ever touched it (edited a
	field, completed a workflow action, or left a workflow/comment note),
	merged into one chronological timeline, plus a per-user summary.

	If `doctype` isn't given, every non-child doctype in the Rndopsapp
	module is checked for a matching name — names are usually unique per
	doctype (REC_..., SAN_..., project registration numbers, etc.) but if
	more than one doctype has a document with this exact name, all of them
	are returned so the caller can disambiguate.
	"""

	current_user = frappe.session.user
	user_roles = frappe.get_roles(current_user)

	if not any(role in RNDOPS_HISTORY_ROLES for role in user_roles):
		return {
			"success": False,
			"message": "Access denied. Only authorized RnD roles can access this endpoint.",
			"matches": [],
		}

	docname = (docname or "").strip()
	if not docname:
		return {"success": False, "message": "Document ID is required.", "matches": []}

	if doctype:
		if not frappe.db.exists("DocType", doctype):
			return {"success": False, "message": f"DocType '{doctype}' not found.", "matches": []}
		candidate_doctypes = [doctype]
	else:
		candidate_doctypes = frappe.get_all(
			"DocType", filters=[["module", "like", "%rndopsapp%"]], pluck="name"
		)

	matches = []
	for dt in candidate_doctypes:
		if not frappe.db.exists("DocType", dt):
			continue

		meta = frappe.get_meta(dt)
		if meta.istable:
			continue

		if not frappe.db.exists(dt, docname):
			continue

		if not frappe.has_permission(dt, "read"):
			continue

		matches.append(_build_document_touch_history(dt, docname, meta))

	if not matches:
		return {
			"success": True,
			"docname": docname,
			"matches": [],
			"message": f"No document named '{docname}' found in any Rndopsapp doctype you can read.",
		}

	return {"success": True, "docname": docname, "matches": matches}


_DOCSTATUS_TRANSITIONS = {
	(0, 1): "Submitted the application",
	(1, 2): "Cancelled the application",
	(0, 2): "Discarded the draft",
}


def _humanize_field_label(meta, fieldname):
	label = meta.get_label(fieldname)
	if not label or label == "No Label":
		label = frappe.unscrub(fieldname)
	return label


def _humanize_field_changes(meta, status_field, field_changes):
	"""
	Turns a raw Version diff into one sentence a non-technical user can read,
	instead of a fieldname dump like "Edited: workflow_state, workflow_state".
	Also de-dupes repeat entries for the same field within one Version row
	(Frappe's own diff can list the same field twice in one save).
	"""
	deduped = {}
	order = []
	for c in field_changes:
		fn = c["field"]
		if fn not in deduped:
			order.append(fn)
		deduped[fn] = c
	field_changes = [deduped[fn] for fn in order]

	if not field_changes:
		return "Edited document", field_changes

	if len(field_changes) == 1:
		c = field_changes[0]
		fn = c["field"]

		if fn == "docstatus":
			verb = _DOCSTATUS_TRANSITIONS.get((c["old"], c["new"]))
			if verb:
				return verb, field_changes

		if status_field and fn == status_field:
			if c["old"]:
				return f'Status changed from "{c["old"]}" to "{c["new"]}"', field_changes
			return f'Status set to "{c["new"]}"', field_changes

		label = _humanize_field_label(meta, fn)
		if not c["old"] and c["new"]:
			return f'Set "{label}" to "{c["new"]}"', field_changes
		return f'Updated "{label}"', field_changes

	labels = [_humanize_field_label(meta, c["field"]) for c in field_changes]
	return f"Updated {', '.join(labels)}", field_changes


def _build_document_touch_history(dt, docname, meta):
	status_field = None
	for field_name in ["workflow_state", "status", "state"]:
		if meta.has_field(field_name):
			status_field = field_name
			break

	fields = ["name", "owner", "creation", "modified", "modified_by", "docstatus"]
	if status_field:
		fields.append(status_field)

	doc = frappe.db.get_value(dt, docname, fields, as_dict=True)

	title_field = meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name")
	title = docname
	if title_field != "name":
		title = frappe.get_value(dt, docname, title_field) or docname

	timeline = [
		{
			"user": doc.owner,
			"timestamp": doc.creation,
			"source": "Created",
			"detail": f"Created this {dt}",
		}
	]

	# Version log — every saved edit, with which fields changed
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": dt, "docname": docname},
		fields=["owner", "creation", "data"],
		order_by="creation asc",
	)
	for v in versions:
		field_changes = []
		if v.data:
			try:
				for c in frappe.parse_json(v.data).get("changed") or []:
					if not c or not c[0]:
						continue
					field_changes.append(
						{
							"field": c[0],
							"old": c[1] if len(c) > 1 else None,
							"new": c[2] if len(c) > 2 else None,
						}
					)
			except Exception:
				pass
		detail, field_changes = _humanize_field_changes(meta, status_field, field_changes)
		timeline.append(
			{
				"user": v.owner,
				"timestamp": v.creation,
				"source": "Version",
				"detail": detail,
				"changes": field_changes,
			}
		)

	# Workflow Action — completed transitions
	wf_actions = frappe.get_all(
		"Workflow Action",
		filters={"reference_doctype": dt, "reference_name": docname, "status": "Completed"},
		fields=["completed_by", "completed_by_role", "workflow_state", "creation"],
		order_by="creation asc",
	)
	for w in wf_actions:
		if not w.completed_by:
			continue
		# NOTE: `workflow_state` on a completed Workflow Action is the state the
		# document was sitting in WHILE this action was open — i.e. the step this
		# user just acted on, not the state it moved to. Phrase it that way so it
		# doesn't read as "moved to Pending Head Approval" when it's the opposite.
		role_suffix = f" (as {w.completed_by_role})" if w.completed_by_role else ""
		detail = f'Actioned the "{w.workflow_state}" step{role_suffix}'
		timeline.append(
			{"user": w.completed_by, "timestamp": w.creation, "source": "Workflow Action", "detail": detail}
		)

	# Comments — includes both Workflow-type transition notes and plain comments
	comments = frappe.get_all(
		"Comment",
		filters={"reference_doctype": dt, "reference_name": docname},
		fields=["comment_type", "owner", "creation", "content"],
		order_by="creation asc",
	)
	for c in comments:
		raw = (c.content or "").replace("<br>", "\n").replace("</strong>", "</strong> ").replace("</div>", "</div> ")
		content = " ".join(frappe.utils.strip_html(raw).split())
		source = "Workflow Note" if c.comment_type == "Workflow" else "Comment"
		timeline.append(
			{"user": c.owner, "timestamp": c.creation, "source": source, "detail": content or source}
		)

	timeline.sort(key=lambda e: e["timestamp"] or "")

	users_summary = {}
	for event in timeline:
		u = event["user"]
		if not u:
			continue
		entry = users_summary.setdefault(
			u, {"user": u, "touches": 0, "first_touch": event["timestamp"], "last_touch": event["timestamp"], "sources": set()}
		)
		entry["touches"] += 1
		entry["last_touch"] = event["timestamp"]
		entry["sources"].add(event["source"])

	users = sorted(
		(
			{
				"user": info["user"],
				"touches": info["touches"],
				"first_touch": info["first_touch"],
				"last_touch": info["last_touch"],
				"sources": sorted(info["sources"]),
			}
			for info in users_summary.values()
		),
		key=lambda x: x["last_touch"] or "",
		reverse=True,
	)

	return {
		"doctype": dt,
		"docname": docname,
		"title": title,
		"owner": doc.owner,
		"current_status": doc.get(status_field) if status_field else None,
		"creation": doc.creation,
		"modified": doc.modified,
		"modified_by": doc.modified_by,
		"docstatus": doc.docstatus,
		"timeline": timeline,
		"users": users,
	}
