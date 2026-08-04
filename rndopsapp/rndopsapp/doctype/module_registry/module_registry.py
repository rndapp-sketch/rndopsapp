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

	# Find departments this user heads — used for Travel "Pending Head Approval" filtering
	_head_depts = frappe.db.sql(
		"SELECT name FROM `tabDepartment_prornd` WHERE dept_head = %s",
		current_user,
		as_dict=True,
	)
	dept_head_values = {d.name for d in _head_depts}

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

		# "Pending Head Approval" must be visible only to the specific head
		# whose email is stored on the document. Field name varies per doctype.
		head_field_map = {
			"Recruitment Adhoc Contractual": "head",
			"Project Registration": "head_approver",
			"Rate Contract": "current_approver",
		}
		head_field = head_field_map.get(dt)
		if head_field and not meta.has_field(head_field):
			head_field = None

		# Some states must be scoped to a single specific user (not just a role)
		# whose email is stored on the document, e.g. Reimbursement's Other-PI
		# route parks the form at 'Pending PI Approval' for the chosen PI only.
		specific_approver_map = {
			"Reimbursement": ("Pending PI Approval", "reimbursement_for_id"),
			"Travel": ("Pending Other PI", "travel_other_pi_id"),
			"Indent General Form": ("Pending Other PI", "igf_other_pi_id"),
			"Indent Cum Sanction Sheet": ("Pending Other PI", "icss_other_pi_id"),
			"Rate Contract": ("Pending Other PI", "other_pi_email"),
		}
		sa_state = sa_field = None
		sa = specific_approver_map.get(dt)
		if sa and meta.has_field(sa[1]):
			sa_state, sa_field = sa

		extra_fields = [head_field] if head_field else []
		if sa_field and sa_field not in extra_fields:
			extra_fields.append(sa_field)
		if dt == "Travel" and meta.has_field("department_travel") and "department_travel" not in extra_fields:
			extra_fields.append("department_travel")
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
				if ref_dt and ref_name and frappe.db.exists(ref_dt, ref_name):
					ref_doc = frappe.db.get_value(ref_dt, ref_name, "*", as_dict=True)
					if ref_doc:
						curr_status = r.get(status_field)

						# A) Head Approval filtering for the underlying reference document
						if curr_status == "Pending Head Approval":
							if ref_dt == "Travel":
								doc_dept = (ref_doc.get("department_travel") or "").strip()
								if doc_dept not in dept_head_values:
									continue
							elif ref_dt in head_field_map:
								h_field = head_field_map[ref_dt]
								h_email = (ref_doc.get(h_field) or "").strip().lower()
								if h_email and h_email != current_user.lower():
									continue
							else:
								h_email = (
									ref_doc.get("head")
									or ref_doc.get("head_approver")
									or ref_doc.get("department_head")
									or ref_doc.get("dept_head")
									or ""
								).strip().lower()
								if h_email and h_email != current_user.lower():
									continue

						# B) Specific Approver / Other PI filtering for reference document
						ref_sa = specific_approver_map.get(ref_dt)
						if ref_sa:
							ref_sa_state, ref_sa_field = ref_sa
							if curr_status == ref_sa_state:
								appr_email = (ref_doc.get(ref_sa_field) or "").strip().lower()
								if appr_email and appr_email != current_user.lower():
									continue

						# C) Pending PI Approval filtering for reference document
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
							if pi_email and pi_email != current_user.lower():
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

			# Travel: filter "Pending Head Approval" to the dept head of the document's department
			if (
				dt == "Travel"
				and r.get(status_field) == "Pending Head Approval"
				and not is_system_manager
			):
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
	Each record is tagged with "doctype" so callers can tell the two apart.
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

	records = sorted(leave_records + extension_records, key=lambda r: r["modified"], reverse=True)

	return {"user": current_user, "results": records}


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
		field_names = [c["field"] for c in field_changes]
		detail = f"Edited: {', '.join(field_names)}" if field_names else "Edited document"
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
		role_suffix = f" (as {w.completed_by_role})" if w.completed_by_role else ""
		detail = f"Completed workflow action → {w.workflow_state}{role_suffix}"
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
