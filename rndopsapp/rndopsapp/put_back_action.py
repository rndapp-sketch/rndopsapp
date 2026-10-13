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

# Hardcoded put-back target list for specific (doctype, state) pairs, used
# in place of the generic backward walk below. Recruitment Adhoc Contractual
# can't express "Pending Staff Approval -> Draft" as a real Workflow
# Transition (Draft's Doc Status is 0/unsubmitted, Pending Staff Approval's
# is 1/submitted, and Frappe's Workflow doctype hard-blocks any transition
# from a submitted state to an unsubmitted one) — this is exactly the gap
# this module's direct-DB-write exists to cover. The generic walk would also
# offer "Pending Head Approval" as an intermediate hop before reaching
# "Draft"; staff, RnD should only be offered "Draft" itself.
PUT_BACK_STATE_OVERRIDES = {
	("Recruitment Adhoc Contractual", "Pending Staff Approval"): ["Draft"],
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

		override = PUT_BACK_STATE_OVERRIDES.get((doctype, current_state))
		if override is not None:
			return {"status": "success", "current_state": current_state, "states": override}

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


@frappe.whitelist()
def get_put_back_states_for_role(doctype, role):
	"""
	Returns every state that sits below a given ROLE's own approval level in
	the doctype's workflow — same backward walk as get_put_back_document_states,
	but anchored to wherever `role` is the "allowed" role on a transition,
	instead of a specific document's current state.

	e.g. for "staff, RnD" (the approver at "Pending Staff Approval") this
	returns just ["Draft"]; for "Dean, RnD" (approver further along, at
	"Pending Dean Approval") it returns every state before that — "Pending
	Staff Approval", "Pending HoD Approval", "Draft", etc. — since a more
	senior role's level sits below more of the chain.
	"""
	try:
		workflow = _get_active_workflow(doctype)
		if not workflow:
			return {"status": "error", "message": "No workflow found"}

		transitions = frappe.get_all(
			"Workflow Transition",
			filters={"parent": workflow},
			fields=["state", "next_state", "allowed"],
		)

		# The role's own level(s): every state from which a transition lets
		# this role act. A role can be the approver at more than one state.
		role_states = sorted({t.state for t in transitions if t.allowed == role})
		if not role_states:
			return {"status": "success", "role": role, "role_states": [], "states": []}

		# Map each state to the state(s) that transition into it, so we can
		# walk backwards from the role's level(s) to the start of the workflow.
		predecessors = {}
		for t in transitions:
			predecessors.setdefault(t.next_state, []).append(t.state)

		# Automation-only sibling states (see STATE_ALIASES) are never
		# legitimate predecessors — same exclusion as get_put_back_document_states.
		aliased_states_for_doctype = {s for (dt, s) in STATE_ALIASES if dt == doctype}

		states = []
		seen = set(role_states) | aliased_states_for_doctype
		queue = list(role_states)
		while queue:
			state = queue.pop(0)
			for prev_state in predecessors.get(state) or []:
				if prev_state in seen:
					continue
				states.append(prev_state)
				seen.add(prev_state)
				queue.append(prev_state)

		return {"status": "success", "role": role, "role_states": role_states, "states": states}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "get_put_back_states_for_role failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_workflow_history_trace(doctype, docname):
	"""
	Returns a chronological trace of every workflow-state hop a document has
	been through: from_state -> to_state, who did it, and which role they did
	it under (resolved by intersecting the actor's current roles against the
	"allowed" role(s) on that exact (state, next_state) Workflow Transition).

	Two sources are merged, since this app writes workflow_state two ways:
	  - "Workflow Action" rows: created automatically by Frappe's workflow
	    engine whenever a document with an active workflow is saved/submitted
	    through the normal doc.save()/doc.submit() path (which is how every
	    *forward* transition in this app's *_action.py modules happens).
	  - "Comment" rows with comment_type "Workflow": this is also where
	    set_put_back_workflow_state's audit trail lands (see its own
	    docstring) — it writes workflow_state via a direct DB write, which
	    bypasses doc.save() entirely, so those hops never create a Workflow
	    Action row and would otherwise be invisible to this trace.
	"""
	try:
		if not frappe.db.exists(doctype, docname):
			return {"status": "error", "message": "Document not found"}

		workflow = _get_active_workflow(doctype)
		transitions = []
		if workflow:
			transitions = frappe.get_all(
				"Workflow Transition",
				filters={"parent": workflow},
				fields=["state", "next_state", "allowed"],
			)

		def _roles_for_hop(from_state, to_state, actor):
			candidates = [
				t.allowed for t in transitions
				if t.state == from_state and t.next_state == to_state and t.allowed
			]
			actor_roles = set(frappe.get_roles(actor)) if actor else set()
			matched = next((r for r in candidates if r in actor_roles), None)
			return matched, sorted(set(candidates))

		# Forward hops: each "Workflow Action" row names the state the
		# document was WAITING in, and (once Completed) who advanced it out
		# of that state. Ordered by creation, row[i]'s state -> row[i+1]'s
		# state is the hop row[i].completed_by performed at row[i].modified.
		wf_actions = frappe.get_all(
			"Workflow Action",
			filters={"reference_doctype": doctype, "reference_name": docname},
			fields=["workflow_state", "status", "completed_by", "creation", "modified"],
			order_by="creation asc",
		)

		steps = []
		for i in range(len(wf_actions) - 1):
			cur, nxt = wf_actions[i], wf_actions[i + 1]
			if cur.status != "Completed" or not cur.completed_by:
				continue
			matched_role, candidate_roles = _roles_for_hop(cur.workflow_state, nxt.workflow_state, cur.completed_by)
			steps.append({
				"from_state": cur.workflow_state,
				"to_state": nxt.workflow_state,
				"performed_by": cur.completed_by,
				"role": matched_role,
				"candidate_roles": candidate_roles,
				"timestamp": cur.modified,
				"source": "workflow_action",
			})

		# Put-back hops: set_put_back_workflow_state's Comment audit trail —
		# "[Put Back] username: <from> → <to> | Reason: <text>". These bypass
		# doc.save(), so they never appear in Workflow Action above.
		import re
		put_back_comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": doctype,
				"reference_name": docname,
				"comment_type": "Workflow",
				"content": ["like", "[Put Back]%"],
			},
			fields=["content", "creation"],
			order_by="creation asc",
		)
		pattern = re.compile(r"^\[Put Back\] (.+?): (.+?) → (.+?)(?: \| Reason: (.*))?$")
		for c in put_back_comments:
			m = pattern.match(c.content or "")
			if not m:
				continue
			username, from_state, to_state, reason = m.groups()
			matched_role, candidate_roles = _roles_for_hop(from_state, to_state, username)
			steps.append({
				"from_state": from_state,
				"to_state": to_state,
				"performed_by": username,
				"role": matched_role,
				"candidate_roles": candidate_roles,
				"timestamp": c.creation,
				"reason": reason,
				"source": "put_back",
			})

		steps.sort(key=lambda s: s["timestamp"])

		# "Started from" — the very first forward hop out of the workflow's
		# entry state, i.e. who submitted it and under which role.
		started = steps[0] if steps and steps[0]["source"] == "workflow_action" else None

		current_state = frappe.db.get_value(doctype, docname, "workflow_state")

		return {
			"status": "success",
			"doctype": doctype,
			"docname": docname,
			"current_state": current_state,
			"started_from_state": started["from_state"] if started else (wf_actions[0].workflow_state if wf_actions else None),
			"started_by": started["performed_by"] if started else frappe.db.get_value(doctype, docname, "owner"),
			"started_role": started["role"] if started else None,
			"trace": steps,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "get_workflow_history_trace failed")
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
