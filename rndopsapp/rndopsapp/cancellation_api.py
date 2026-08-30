# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Cancellation API Module

Provides whitelisted API endpoints for:
1. Fetching all pending applications for the current user ("My Applications" / "Form Application")
2. Creating cancellation requests that clone the original module's workflow
3. Checking cancellation status for a given document
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

# ─── Terminal/final workflow states that should NOT appear in "Form Application" ───
TERMINAL_STATES = {
	"approved",
	"cancelled",
	"rejected",
	"sanction approved",
	"endorsement approved",
	"completed",
	"closed",
}


def _is_terminal_state(state):
	"""Check if a workflow state is a terminal (final) state."""
	if not state:
		return False
	return state.strip().lower() in TERMINAL_STATES


# ──────────────────────────────────────────────────────────────────────────────
# 1. GET MY APPLICATIONS
# ──────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_my_applications():
	"""
	Fetch all applications/forms created by the current user that are still in a
	pending (non-terminal) workflow state.

	Returns all rndopsapp module doctypes where:
	- owner = current user
	- workflow_state is NOT in a terminal state (Approved, Cancelled, Rejected, etc.)
	- docstatus < 2 (not cancelled via Frappe)

	Response format:
	{
		"success": True,
		"user": "user@example.com",
		"total_applications": 5,
		"results": [
			{
				"doctype": "Reimbursement",
				"count": 2,
				"records": [
					{
						"name": "REIMB-0001",
						"title": "...",
						"status": "PI Submitted",
						"creation": "...",
						"modified": "...",
						"has_pending_cancellation": false
					}
				]
			}
		]
	}
	"""
	current_user = frappe.session.user

	if current_user in ["Administrator", "Guest"]:
		return {"success": False, "message": "Invalid user", "results": []}

	# Get all doctypes in the rndopsapp module (non-child-table, non-single)
	rndops_doctypes = frappe.get_all(
		"DocType",
		filters=[["module", "like", "%rndopsapp%"]],
		fields=["name", "module"],
	)

	if not rndops_doctypes:
		# Fallback exact match
		rndops_doctypes = frappe.get_all(
			"DocType",
			filters={"module": "Rndopsapp"},
			fields=["name", "module"],
		)

	results = []

	for dt_info in rndops_doctypes:
		dt_name = dt_info.name

		# Skip the Cancellation Request doctype itself
		if dt_name == "Cancellation Request":
			continue

		if not frappe.db.exists("DocType", dt_name):
			continue

		meta = frappe.get_meta(dt_name)

		# Skip child tables, single doctypes, and virtual doctypes
		if meta.istable or meta.issingle:
			continue

		# Must have a workflow_state field (meaning it's a workflow-enabled form)
		status_field = None
		for field_name in ["workflow_state", "status", "state"]:
			if meta.has_field(field_name):
				status_field = field_name
				break

		if not status_field:
			continue

		# Check read permission
		try:
			if not frappe.has_permission(dt_name, "read"):
				continue
		except Exception:
			continue

		# Fetch documents owned strictly by the current user
		try:
			fields_to_fetch = ["name", "creation", "modified", "owner", "docstatus"]
			if status_field:
				fields_to_fetch.append(status_field)

			# Get title field
			title_field = (
				meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name")
			)
			if title_field != "name" and title_field not in fields_to_fetch:
				fields_to_fetch.append(title_field)

			records = frappe.get_list(
				dt_name,
				filters={
					"owner": current_user,
					"docstatus": ["<", 2],  # Exclude Frappe-cancelled
				},
				fields=fields_to_fetch,
				order_by="modified desc",
				limit_page_length=200,
			)

			# Filter out records in terminal states, except approved states
			pending_records = []
			for record in records:
				state_value = record.get(status_field, "")
				if _is_terminal_state(state_value):
					if not state_value or state_value.strip().lower() not in [
						"approved",
						"sanction approved",
						"endorsement approved",
					]:
						continue

				# Also skip "Draft" state — these haven't been submitted yet
				if state_value and state_value.strip().lower() == "draft":
					continue

				pending_records.append(record)

			if not pending_records:
				continue

			# Check for pending cancellation requests for each record
			pending_cancel_names = set()
			cancel_info = {}
			try:
				cancellations = frappe.get_all(
					"Cancellation Request",
					filters={
						"reference_doctype": dt_name,
						"reference_name": ["in", [r.name for r in pending_records]],
						"docstatus": ["<", 2],
					},
					fields=["name", "reference_name", "status", "workflow_state", "creation"],
					order_by="creation desc",
				)
				for c in cancellations:
					# Newest first, so the first one seen per document wins.
					cancel_info.setdefault(
						c.reference_name,
						{
							"name": c.name,
							"status": c.status,
							"workflow_state": c.workflow_state,
							"creation": str(c.creation),
						},
					)
					if (c.status or "").strip().lower() == "pending":
						pending_cancel_names.add(c.reference_name)
			except Exception:
				# Cancellation Request doctype might not exist yet
				pass

			# Map records to response format
			mapped = []
			for r in pending_records:
				title_value = r.get(title_field, r.name) if title_field != "name" else r.name
				mapped.append(
					{
						"name": r.name,
						"title": title_value or r.name,
						"status": r.get(status_field, "Unknown"),
						"creation": r.creation,
						"modified": r.modified,
						"owner": r.owner,
						"docstatus": r.docstatus,
						"has_pending_cancellation": r.name in pending_cancel_names,
						"cancellation": cancel_info.get(r.name),
					}
				)

			if mapped:
				results.append(
					{
						"doctype": dt_name,
						"count": len(mapped),
						"records": mapped,
					}
				)

		except Exception as e:
			# Skip doctypes that cause errors (schema mismatches, etc.)
			frappe.log_error(
				f"Error fetching {dt_name} for user {current_user}: {str(e)}",
				"get_my_applications error",
			)
			continue

	# Sort by doctype name
	results.sort(key=lambda x: x["doctype"])

	return {
		"success": True,
		"user": current_user,
		"total_applications": sum(r["count"] for r in results),
		"results": results,
	}


# ──────────────────────────────────────────────────────────────────────────────
# 2. CREATE CANCELLATION REQUEST
# ──────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_my_cancellation_requests():
	"""
	Every cancellation request raised by the current user, newest first —
	whatever state it is in. Backs the "Cancellation Requests" tab, so a
	requester can see what they asked to cancel and how far it has got.
	"""
	current_user = frappe.session.user

	rows = frappe.get_all(
		"Cancellation Request",
		filters={"requested_by": current_user},
		fields=[
			"name",
			"reference_doctype",
			"reference_name",
			"cancellation_reason",
			"status",
			"workflow_state",
			"request_date",
			"creation",
			"modified",
			"docstatus",
		],
		order_by="creation desc",
	)

	# Resolve the current state of each referenced document in one query per
	# doctype rather than one per row.
	by_doctype = {}
	for r in rows:
		by_doctype.setdefault(r.reference_doctype, []).append(r.reference_name)

	ref_states = {}
	for dt, names in by_doctype.items():
		try:
			meta = frappe.get_meta(dt)
			field = "workflow_state" if meta.has_field("workflow_state") else None
			if not field:
				continue
			for d in frappe.get_all(
				dt, filters={"name": ["in", names]}, fields=["name", field]
			):
				ref_states[(dt, d.name)] = d.get(field)
		except Exception:
			continue

	for r in rows:
		r["reference_state"] = ref_states.get((r.reference_doctype, r.reference_name))

	return {"success": True, "user": current_user, "count": len(rows), "requests": rows}


@frappe.whitelist()
def create_cancellation_request(reference_doctype, reference_name, cancellation_reason):
	"""
	Create a new Cancellation Request document.

	The cancellation request will:
	1. Reference the original document
	2. Store the user's cancellation reason
	3. Be assigned the same workflow as the original doctype
	4. Start moving through the approval chain

	Args:
		reference_doctype (str): The doctype of the document being cancelled
		reference_name (str): The name of the document being cancelled
		cancellation_reason (str): The user's reason for cancellation

	Returns:
		dict: Success/error status and the created cancellation request name
	"""
	try:
		current_user = frappe.session.user

		# Validate inputs
		if not reference_doctype or not reference_name:
			frappe.throw(_("Reference document is required."))
		if not cancellation_reason or not cancellation_reason.strip():
			frappe.throw(_("Cancellation reason is required."))

		# Verify the referenced document exists
		if not frappe.db.exists(reference_doctype, reference_name):
			frappe.throw(_("Document {0} ({1}) does not exist.").format(reference_name, reference_doctype))

		# Verify the user owns the document, is System Manager, or is designated Head/PI for the document
		ref_doc = frappe.get_doc(reference_doctype, reference_name)
		user_roles = frappe.get_roles(current_user)
		if ref_doc.owner != current_user and "System Manager" not in user_roles:
			_head_depts = frappe.db.sql(
				"SELECT name FROM `tabDepartment_prornd` WHERE dept_head = %s",
				current_user,
				as_dict=True,
			)
			dept_head_values = {d.name for d in _head_depts}
			doc_dept = (
				getattr(ref_doc, "department_travel", None)
				or getattr(ref_doc, "department", None)
				or getattr(ref_doc, "dept", None)
			)
			is_dept_head = bool(doc_dept and doc_dept in dept_head_values)

			associated_fields = [
				"head",
				"head_approver",
				"department_head",
				"current_approver",
				"reimbursement_for_id",
				"travel_other_pi_id",
				"igf_other_pi_id",
				"icss_other_pi_id",
				"other_pi_email",
				"pi_id",
				"pi",
				"pi_webmail",
				"pi_mentor_user",
				"pi_userid",
			]
			is_head_or_pi = any(
				getattr(ref_doc, f, None)
				and str(getattr(ref_doc, f)).strip().lower() == current_user.lower()
				for f in associated_fields
			)
			if not (is_dept_head or is_head_or_pi):
				frappe.throw(_("You can only cancel documents that you own or head."))

		# Check the document is not already in a terminal state, unless it is approved
		ref_state = getattr(ref_doc, "workflow_state", None)
		if _is_terminal_state(ref_state):
			is_approved_state = ref_state and ref_state.strip().lower() in [
				"approved",
				"sanction approved",
				"endorsement approved",
			]
			if not is_approved_state:
				frappe.throw(
					_("This document is already in a final state ({0}) and cannot be cancelled.").format(
						ref_state
					)
				)

		# Check for existing pending cancellation request
		existing = frappe.get_all(
			"Cancellation Request",
			filters={
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"status": "Pending",
				"docstatus": ["<", 2],
			},
			limit=1,
		)
		if existing:
			frappe.throw(
				_("A pending cancellation request already exists for this document ({0}).").format(
					existing[0].name
				)
			)

		# Find the workflow for the reference doctype
		source_workflow = frappe.get_value("Workflow", {"document_type": reference_doctype}, "name")

		# Setup and activate the workflow before insertion so that insert() runs under it
		if source_workflow:
			_setup_cancellation_workflow(source_workflow)
			target_wf = f"cancel_{source_workflow}"
			if frappe.db.exists("Workflow", target_wf):
				frappe.db.sql(
					"""
					UPDATE `tabWorkflow`
					SET is_active = (CASE WHEN name = %s THEN 1 ELSE 0 END)
					WHERE document_type = 'Cancellation Request'
				""",
					(target_wf,),
				)
				frappe.clear_cache(doctype="Cancellation Request")

		# Create the Cancellation Request
		cancel_doc = frappe.new_doc("Cancellation Request")
		cancel_doc.reference_doctype = reference_doctype
		cancel_doc.reference_name = reference_name
		cancel_doc.reference_owner = ref_doc.owner
		cancel_doc.cancellation_reason = cancellation_reason.strip()
		cancel_doc.requested_by = current_user
		cancel_doc.request_date = now_datetime()
		cancel_doc.source_workflow = source_workflow or ""
		cancel_doc.status = "Pending"

		# Generate short doctype name for auto-naming
		words = reference_doctype.replace("_", " ").split()
		if len(words) == 1:
			cancel_doc.reference_doctype_short = words[0][:4].upper()
		else:
			cancel_doc.reference_doctype_short = "".join(w[0].upper() for w in words[:4])

		cancel_doc.flags.ignore_permissions = True
		cancel_doc.insert()

		# If a workflow exists for the reference doctype, we need to set up the
		# cancellation request's workflow. We do this by creating/reusing a
		# workflow for "Cancellation Request" that mirrors the source workflow.
		if source_workflow:
			_setup_cancellation_workflow(source_workflow)

			# Move the cancellation request from "Draft" to the first submitted/pending state
			try:
				wf_doc = frappe.get_doc("Workflow", f"cancel_{source_workflow}")
				action = _get_first_transition_action(wf_doc)
				if action:
					from frappe.model.workflow import apply_workflow

					# Since the document was just inserted as Draft, we apply the workflow action
					# to move it to the first submitted/pending state.
					cancel_doc.flags.ignore_permissions = True
					apply_workflow(cancel_doc, action)
					cancel_doc.reload()

				# The first state may be "Pending Head Approval"; skip it when the
				# head cannot act on it (is the requester / is not configured).
				_maybe_bypass_head_approval(cancel_doc, ref_doc, current_user, wf_doc)
			except Exception as e:
				frappe.log_error(
					frappe.get_traceback(),
					_("Error moving cancellation request {0} to next state: {1}").format(
						cancel_doc.name, str(e)
					),
				)

		frappe.db.commit()

		# Add audit comment on the original document
		try:
			ref_doc.add_comment(
				"Info",
				_("Cancellation requested by {0}. Reason: {1}. Request ID: {2}").format(
					current_user, cancellation_reason.strip(), cancel_doc.name
				),
			)
		except Exception:
			pass

		return {
			"status": "success",
			"message": _("Cancellation request created successfully."),
			"cancellation_request": cancel_doc.name,
			"workflow_state": getattr(cancel_doc, "workflow_state", "Pending"),
		}

	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Create Cancellation Request Error")
		return {"status": "error", "message": str(e)}


def _setup_cancellation_workflow(source_workflow_name):
	"""
	Set up workflow for the Cancellation Request by creating/reusing a
	workflow that mirrors the source workflow.

	The cancellation workflow will have the same states and transitions
	as the original document's workflow, allowing it to go through the
	same approval chain.
	"""
	try:
		cancel_wf_name = f"cancel_{source_workflow_name}"

		source_wf = frappe.get_doc("Workflow", source_workflow_name)

		# Check if cancellation workflow already exists
		if frappe.db.exists("Workflow", cancel_wf_name):
			if source_wf.document_type == "Reimbursement":
				frappe.delete_doc("Workflow", cancel_wf_name, ignore_permissions=True)
				frappe.clear_cache(doctype="Cancellation Request")
			else:
				return

		new_wf = frappe.new_doc("Workflow")
		new_wf.workflow_name = cancel_wf_name
		new_wf.document_type = "Cancellation Request"
		new_wf.is_active = 1
		new_wf.workflow_state_field = "workflow_state"

		# Copy all states from the source workflow
		for state in source_wf.states:
			new_wf.append(
				"states",
				{
					"state": state.state,
					"doc_status": state.doc_status,
					"allow_edit": state.allow_edit,
					"is_optional_state": getattr(state, "is_optional_state", 0),
				},
			)

		# Copy all transitions from the source workflow
		for transition in source_wf.transitions:
			next_state = transition.next_state
			action = transition.action
			if (
				source_wf.document_type == "Reimbursement"
				and transition.state == "Pending Staff Approval"
				and transition.action in ["Verify (With Hardcopy)", "Approve"]
			):
				# Find the terminal approved state name from the source workflow
				approved_state_name = "Approved"
				for s in source_wf.states:
					if s.state and s.state.strip().lower() in [
						"approved",
						"sanction approved",
						"endorsement approved",
					]:
						approved_state_name = s.state
						break
				next_state = approved_state_name
				action = "Approve"

			new_wf.append(
				"transitions",
				{
					"state": transition.state,
					"action": action,
					"next_state": next_state,
					"allowed": transition.allowed,
					"allow_self_approval": getattr(transition, "allow_self_approval", 1),
				},
			)

		new_wf.flags.ignore_permissions = True
		new_wf.insert()

	except Exception as e:
		frappe.log_error(
			frappe.get_traceback(), f"Error setting up cancellation workflow for {source_workflow_name}"
		)
		# Even if workflow setup fails, the cancellation request is still created
		# It just won't have automated workflow transitions


def _get_first_submitted_state(workflow_doc):
	"""
	Get the first state after Draft in the workflow.
	This is the state the cancellation should start at (simulating submission).
	"""
	# Look for the transition from Draft
	for transition in workflow_doc.transitions:
		if transition.state and transition.state.strip().lower() == "draft":
			return transition.next_state

	# Fallback: return the second state in the states list (first is usually Draft)
	if len(workflow_doc.states) > 1:
		return workflow_doc.states[1].state

	# Final fallback
	return workflow_doc.states[0].state if workflow_doc.states else None


# ---------------------------------------------------------------------------
# "Pending Head Approval" bypass
# ---------------------------------------------------------------------------
# Cancellation requests for permanent employees are routed Draft -> Pending Head
# Approval -> Pending Staff Approval. That deadlocks when the head is the person
# asking for the cancellation (nobody else can move it) or when the document's
# department has no dept_head set at all.
#
# Mode "always"   skips the head stage for every cancellation request.
# Mode "deadlock" skips it only in the two cases above.
#
# Set to "always": a cancellation never waits on a department head. The head
# already approved the original document; requiring them again only to undo it
# was pure delay, and it deadlocked outright whenever the head was the
# requester or no dept_head was configured.
CANCELLATION_HEAD_BYPASS_MODE = "always"

HEAD_STATE = "Pending Head Approval"

# Department field varies by source doctype.
_DEPT_FIELDS = (
	"department_travel",
	"applicant_department",
	"department",
	"dept",
	"department_name",
)


def _resolve_document_head(ref_doc):
	"""Return (department, dept_head_user) for the document being cancelled."""
	doc_dept = None
	for f in _DEPT_FIELDS:
		val = getattr(ref_doc, f, None)
		if val and str(val).strip():
			doc_dept = str(val).strip()
			break

	if not doc_dept:
		return None, None

	head = frappe.db.get_value("Department_prornd", doc_dept, "dept_head")
	return doc_dept, (head or None)


def _next_state_after_head(wf_doc):
	"""
	The state the head would forward to. Resolved from the workflow rather than
	hardcoded, because each cancel_* workflow mirrors a different source flow.
	"""
	rejecting = ("reject", "return", "send back", "put back", "cancel")
	fallback = None
	for t in wf_doc.transitions:
		if not t.state or t.state.strip().lower() != HEAD_STATE.lower():
			continue
		action = (t.action or "").strip().lower()
		if any(word in action for word in rejecting):
			continue
		if action in ("forward", "approve"):
			return t.next_state
		fallback = fallback or t.next_state
	return fallback


def _maybe_bypass_head_approval(cancel_doc, ref_doc, requester, wf_doc):
	"""
	Skip the head stage when it cannot meaningfully act. Returns the reason the
	bypass was applied, or None if the request was left at the head.
	"""
	if (cancel_doc.workflow_state or "").strip().lower() != HEAD_STATE.lower():
		return None

	doc_dept, head = _resolve_document_head(ref_doc)

	if CANCELLATION_HEAD_BYPASS_MODE == "always":
		reason = _("head approval is not required for cancellation requests")
	elif not head:
		reason = _("no department head is configured for {0}").format(doc_dept or _("this document"))
	elif head.strip().lower() == (requester or "").strip().lower():
		reason = _("the requester {0} is the head of {1}").format(requester, doc_dept)
	else:
		return None

	next_state = _next_state_after_head(wf_doc)
	if not next_state:
		return None

	cancel_doc.db_set("workflow_state", next_state, update_modified=False)
	cancel_doc.reload()

	try:
		cancel_doc.add_comment(
			"Info",
			_("Head approval skipped automatically because {0}. Moved to {1}.").format(
				reason, next_state
			),
		)
	except Exception:
		pass

	return reason


def _get_first_transition_action(workflow_doc):
	"""
	Get the action name that transitions the document from Draft.
	"""
	for transition in workflow_doc.transitions:
		if transition.state and transition.state.strip().lower() == "draft":
			return transition.action

	# Fallback: check if there's any transition at all
	if workflow_doc.transitions:
		return workflow_doc.transitions[0].action

	return None


# ──────────────────────────────────────────────────────────────────────────────
# 3. GET CANCELLATION STATUS
# ──────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_cancellation_status(reference_doctype, reference_name):
	"""
	Check if a cancellation request exists for a given document.

	Returns:
		dict: {
			"has_cancellation": True/False,
			"cancellation_requests": [...],
		}
	"""
	try:
		cancellations = frappe.get_all(
			"Cancellation Request",
			filters={
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"docstatus": ["<", 2],
			},
			fields=[
				"name",
				"status",
				"cancellation_reason",
				"requested_by",
				"request_date",
				"workflow_state",
				"creation",
				"modified",
			],
			order_by="creation desc",
		)

		return {
			"has_cancellation": len(cancellations) > 0,
			"has_pending": any(c.status == "Pending" for c in cancellations),
			"cancellation_requests": cancellations,
		}

	except Exception:
		# Cancellation Request doctype might not exist yet
		return {
			"has_cancellation": False,
			"has_pending": False,
			"cancellation_requests": [],
		}


# ──────────────────────────────────────────────────────────────────────────────
# 4. GET CANCELLATION REQUEST DETAILS (for the approver view)
# ──────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_cancellation_request_details(cancellation_name):
	"""
	Get full details of a cancellation request for the approver view.

	Args:
		cancellation_name (str): Name of the Cancellation Request document

	Returns:
		dict: Full cancellation request details including original document info
	"""
	try:
		cancel_doc = frappe.get_doc("Cancellation Request", cancellation_name)

		# Self-healing: ensure the cancellation workflow is updated/recreated with latest rules
		if cancel_doc.source_workflow:
			_setup_cancellation_workflow(cancel_doc.source_workflow)

		# Get reference document details
		ref_details = {}
		try:
			ref_doc = frappe.get_doc(cancel_doc.reference_doctype, cancel_doc.reference_name)
			ref_details = {
				"name": ref_doc.name,
				"doctype": cancel_doc.reference_doctype,
				"owner": ref_doc.owner,
				"workflow_state": getattr(ref_doc, "workflow_state", "Unknown"),
				"creation": ref_doc.creation,
				"modified": ref_doc.modified,
			}
			# Try to get title
			meta = frappe.get_meta(cancel_doc.reference_doctype)
			title_field = meta.title_field or ("title" if meta.has_field("title") else "name")
			ref_details["title"] = getattr(ref_doc, title_field, ref_doc.name)
		except Exception:
			ref_details = {
				"name": cancel_doc.reference_name,
				"doctype": cancel_doc.reference_doctype,
				"error": "Could not fetch reference document details",
			}

		# Get available workflow actions for the current user
		workflow_actions = []
		try:
			from rndopsapp.workflow_pipeline import get_available_workflow_actions

			actions = get_available_workflow_actions(cancellation_name, "Cancellation Request")
			workflow_actions = actions if isinstance(actions, list) else []
		except Exception:
			pass

		# Get requester details
		requester_info = {}
		try:
			user_doc = frappe.get_doc("User", cancel_doc.requested_by)
			requester_info = {
				"email": user_doc.email,
				"full_name": user_doc.full_name,
			}
		except Exception:
			requester_info = {"email": cancel_doc.requested_by}

		return {
			"success": True,
			"cancellation_request": {
				"name": cancel_doc.name,
				"reference_doctype": cancel_doc.reference_doctype,
				"reference_name": cancel_doc.reference_name,
				"cancellation_reason": cancel_doc.cancellation_reason,
				"requested_by": cancel_doc.requested_by,
				"requester_info": requester_info,
				"request_date": cancel_doc.request_date,
				"status": cancel_doc.status,
				"workflow_state": getattr(cancel_doc, "workflow_state", None),
				"source_workflow": cancel_doc.source_workflow,
				"creation": cancel_doc.creation,
				"modified": cancel_doc.modified,
			},
			"reference_document": ref_details,
			"available_actions": workflow_actions,
		}

	except frappe.DoesNotExistError:
		return {"success": False, "message": "Cancellation request not found."}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Cancellation Details Error")
		return {"success": False, "message": str(e)}


def validate_original_document_not_locked(doc, method=None):
	"""
	Prevent any updates or workflow progression on the original document
	if there is a pending cancellation request for it.
	"""
	if doc.doctype == "Cancellation Request":
		return

	try:
		if frappe.db.exists("DocType", "Cancellation Request"):
			pending_cancel = frappe.db.exists(
				"Cancellation Request",
				{
					"reference_doctype": doc.doctype,
					"reference_name": doc.name,
					"status": "Pending",
					"docstatus": ["<", 2],
				},
			)
			if pending_cancel:
				frappe.throw(
					_(
						"This application is locked because a cancellation request ({0}) is pending approval."
					).format(pending_cancel)
				)
	except Exception:
		pass


@frappe.whitelist()
def get_original_commitment(reference_doctype, reference_name):
	"""
	Retrieve the original commitment details from Kafka Commit Staging.
	Only allowed if the user has read access to the original document.
	"""
	if not reference_doctype or not reference_name:
		frappe.throw(_("Reference Doctype and Reference Name are required."))

	# Verify user has read permission on the original document
	if not frappe.has_permission(reference_doctype, "read", doc=reference_name):
		frappe.throw(
			_("You do not have permission to view this document's commitment details."),
			frappe.PermissionError,
		)

	# Fetch the staging record bypassing standard user permission filters
	records = frappe.get_all(
		"Kafka Commit Staging",
		filters={"reference_name": reference_name},
		fields=["*"],
		limit=1,
	)

	return records[0] if records else None
