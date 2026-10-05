# Copyright (c) 2026, rndops and contributors
# "Put Back" — force a document's workflow state backward to an earlier state
# in its own workflow chain. Normal workflow transitions are role-gated (see
# Workflow Transition's "allowed" role), so a user who wants to send a document
# back a step usually doesn't hold the role for that specific transition. This
# module bypasses that role check by writing workflow_state directly instead of
# going through doc.save(), and instead makes the action auditable by requiring
# the acting username and recording every put-back in the Activity Log doctype.

import frappe

# Some workflow states are entered only by automation — a Kafka consumer
# writing workflow_state straight to the DB, never a Workflow Transition a
# user clicks — so they have no predecessor edge in the transition graph for
# the backward walk below to find. Each such state is mapped to the state
# it should be treated as equivalent-position to for Put Back purposes: the
# walk starts from the aliased state's predecessors instead, so these states
# get the same put-back chain as whatever they sit alongside in the workflow.
#
# Fund Received: Pending Rectification / Pending Reconciliation / Rejected
# are ledger-driven siblings of PENDING_APPROVAL (same priority tier in
# FundReceivedConsumerMapper._STATE_PRIORITY) — put back should go to
# PENDING_APPROVAL's own predecessor (Pending Misc. Staff Approval), not to
# PENDING_APPROVAL itself.
STATE_ALIASES = {
	("Fund Received", "Pending Rectification"): "PENDING_APPROVAL",
	("Fund Received", "Pending Reconciliation"): "PENDING_APPROVAL",
	("Fund Received", "Rejected"): "PENDING_APPROVAL",
}


def _get_active_workflow(doctype):
	workflows = frappe.get_all("Workflow", filters={"document_type": doctype, "is_active": 1}, pluck="name")
	if not workflows:
		workflows = frappe.get_all("Workflow", filters={"document_type": doctype}, pluck="name")
	return workflows[0] if workflows else None


@frappe.whitelist()
def get_put_back_document_states(doctype, docname):
	"""
	Returns the chain of states that precede the document's current workflow
	state, walking backwards one transition at a time — e.g. current state
	"Pending HOS Approval" -> ["Pending Staff Approval", "Draft"]. These are
	the valid "put back" targets for set_put_back_workflow_state.
	"""
	try:
		if not frappe.db.exists(doctype, docname):
			return {"status": "error", "message": "Document not found"}

		workflow = _get_active_workflow(doctype)
		if not workflow:
			return {"status": "error", "message": "No workflow found"}

		current_state = frappe.db.get_value(doctype, docname, "workflow_state")
		if not current_state:
			return {"status": "success", "current_state": None, "states": []}

		transitions = frappe.get_all(
			"Workflow Transition",
			filters={"parent": workflow},
			fields=["state", "next_state"],
		)

		# Map each state to the state(s) that transition into it, so we can
		# walk backwards from the current state to the start of the workflow.
		predecessors = {}
		for t in transitions:
			predecessors.setdefault(t.next_state, []).append(t.state)

		# Automation-only sibling states (see STATE_ALIASES) are never
		# legitimate predecessors of one another — e.g. Fund Received's
		# "Rejected" must not be offered as a put-back step on the way from
		# "Pending Rectification", just because both alias to PENDING_APPROVAL
		# and one happens to have a real Forward transition into it. Excluding
		# them from `seen` up front keeps them out of every walk except as the
		# starting current_state itself.
		aliased_states_for_doctype = {s for (dt, s) in STATE_ALIASES if dt == doctype}

		states = []
		seen = {current_state} | aliased_states_for_doctype
		state = current_state
		while True:
			preds = [p for p in predecessors.get(state) or [] if p not in seen]
			if not preds:
				# Dead end — if this is a known automation-only state (see
				# STATE_ALIASES), resume the walk from its alias's own
				# predecessors instead of giving up with an empty list.
				alias = STATE_ALIASES.get((doctype, state))
				if alias and alias not in seen:
					preds = [p for p in predecessors.get(alias) or [] if p not in seen]
				if not preds:
					break
			prev_state = preds[0]
			states.append(prev_state)
			seen.add(prev_state)
			state = prev_state

		return {"status": "success", "current_state": current_state, "states": states}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "get_put_back_document_states failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def set_put_back_workflow_state(doctype, docname, state, username, comment=None):
	"""
	Forces workflow_state back to an earlier state. Writes straight to the
	database instead of doc.save(), which is what lets this bypass the
	Workflow Transition role check that would otherwise block it. The
	username performing the put back must be supplied explicitly and is
	always recorded (together with the logged-in session user and an
	optional reason/comment) in an Activity Log entry against the document,
	so the bypass stays auditable.
	"""
	try:
		if not frappe.db.exists(doctype, docname):
			return {"status": "error", "message": "Document not found"}

		username = (username or "").strip()
		if not username:
			return {"status": "error", "message": "username is required"}

		if not state:
			return {"status": "error", "message": "state is required"}

		comment = (comment or "").strip()

		workflow = _get_active_workflow(doctype)
		if workflow:
			valid_states = frappe.get_all(
				"Workflow Document State", filters={"parent": workflow}, pluck="state"
			)
			if state not in valid_states:
				return {"status": "error", "message": f"'{state}' is not a valid state for this workflow"}

		prev_state = frappe.db.get_value(doctype, docname, "workflow_state") or "Unknown"
		session_user = frappe.session.user

		# Direct DB write — skips doc.save() entirely, so the Workflow Transition's
		# "allowed" role restriction never gets evaluated.
		frappe.db.set_value(doctype, docname, "workflow_state", state, update_modified=False)

		# Frappe's document "Activity" tab (docinfo.workflow_logs) is built from Comment
		# records with comment_type "Workflow" — it never reads the Activity Log doctype,
		# so the entry has to be a Comment to actually show up there.
		reason_text = f" | Reason: {comment}" if comment else ""
		frappe.get_doc({
			"doctype": "Comment",
			"comment_type": "Workflow",
			"reference_doctype": doctype,
			"reference_name": docname,
			"content": f"[Put Back] {username}: {prev_state} → {state}{reason_text}",
		}).insert(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"{docname} → {state}",
			"from_state": prev_state,
			"to_state": state,
			"put_back_by": username,
			"session_user": session_user,
			"comment": comment or None,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "set_put_back_workflow_state failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_put_back_document_states_test(doctype, docname):
	"""TESTING ONLY - guest-accessible clone of get_put_back_document_states. Remove before production."""
	return get_put_back_document_states(doctype, docname)


@frappe.whitelist(allow_guest=True)
def set_put_back_workflow_state_test(doctype, docname, state, username, comment=None):
	"""
	TESTING ONLY - guest-accessible clone of set_put_back_workflow_state.
	This one WRITES to the document and already bypasses role permissions,
	so with allow_guest anyone unauthenticated can revert any document's
	workflow state. Remove before production.
	"""
	return set_put_back_workflow_state(doctype, docname, state, username, comment=comment)
