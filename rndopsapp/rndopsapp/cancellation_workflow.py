# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Independent workflow for Cancellation Request.

The cancellation workflow is NOT a copy of the original document's workflow.
It is one fixed workflow, "Cancellation Request Workflow":

	Draft -> [Head] -> Staff -> HoS -> Dean -> Approved

plus three single-stage entries for applications still waiting on the
applicant side of the chain (Mentor, PI, Other PI).

How far a given request travels is decided once, when it is filed, from the
state the application is in (see resolve_cancellation_path) and stored on the
request as `stop_stage` / `stage_path`. The workflow's transition conditions
read those two fields, so the same workflow serves every doctype.

See docs/cancellation_request/CANCELLATION_WORKFLOW.md.
"""

import frappe
from frappe import _

WORKFLOW_NAME = "Cancellation Request Workflow"

# Doctypes whose own workflow has a Head approval before Staff. Only these get
# a Head stage in front of Staff when the cancellation has to reach Staff or
# beyond.
HEAD_APPROVAL_DOCTYPES = {"Top Up Fellowship", "Recruitment Adhoc Contractual", "Travel"}

# The linear approval chain, in order. Head is only included for
# HEAD_APPROVAL_DOCTYPES.
CHAIN = ["Head", "Staff", "HoS", "Dean"]

# Stages an application can be waiting at on the applicant side. A cancellation
# for such an application is a single stage: that approver approves it and the
# cancellation is done.
SINGLE_STAGES = ["Mentor", "Other PI"]

ALL_STAGES = SINGLE_STAGES + CHAIN

# stage -> (workflow state name, roles allowed to approve at that stage).
# Roles are the ones the live workflows already use for the same stage.
STAGE_STATES = {
	"Mentor": ("Pending Mentor Approval", ["Mentor"]),
	"Other PI": ("Pending Other PI", ["Other PI"]),
	"Head": ("Pending Head Approval", ["head_approver_1"]),
	"Staff": ("Pending Staff Approval", ["staff, RnD"]),
	"HoS": ("Pending HoS Approval", ["Hos, RnD (Head of Section, RnD)"]),
	"Dean": ("Pending Dean Approval", ["Dean, RnD"]),
}

# Application states that cannot be cancelled: the application is not waiting
# on any approver (back with the applicant, or already dead).
_NOT_CANCELLABLE_MARKERS = ("correction", "rectification", "reject", "cancel", "acknowledg")


def _normalize(state):
	return (state or "").strip().lower()


def stage_for_application_state(state):
	"""
	Map an application's workflow_state to the cancellation stage it ends at.

	Returns a stage name from ALL_STAGES, or None when the application is not
	cancellable (Draft, rejected, needs-correction, already cancelled).

	Anything that is not a recognised "pending <approver>" state — Approved,
	Sanction Approved, Pending PO Generation, Pending Staff Verification, ... —
	is past the approval chain, so the cancellation runs the full chain and
	ends at Dean.
	"""
	s = _normalize(state)
	if not s or s == "draft" or any(m in s for m in _NOT_CANCELLABLE_MARKERS):
		return None

	# Applicant-side stages.
	if "mentor" in s:
		return "Mentor"
	if "other pi" in s:
		return "Other PI"
	# An application waiting on its PI has no PI stage in the cancellation: the
	# PI is skipped and the cancellation goes straight to Staff.
	if "pi approval" in s:
		return "Staff"

	# Chain stages. Associate Dean / Director are above HoS, so they share the
	# Dean stage — the cancellation chain has nothing above Dean.
	if "head approval" in s or "hod approval" in s:
		return "Head"
	if "staff approval" in s:
		return "Staff"
	if "hos approval" in s:
		return "HoS"
	if "dean" in s or "director" in s:
		return "Dean"

	# Approved or any later (post-approval) state.
	return "Dean"


def resolve_cancellation_path(reference_doctype, application_state):
	"""
	Work out the stages a cancellation has to pass through.

	Returns (stop_stage, path) where `path` is the ordered list of stages from
	the first approver to `stop_stage`. Raises frappe.ValidationError when the
	application cannot be cancelled.
	"""
	stage = stage_for_application_state(application_state)
	if not stage:
		frappe.throw(
			_("A document in state '{0}' cannot be cancelled. It is not waiting for any approval.").format(
				application_state or _("Draft")
			)
		)

	# Applicant-side stages and a Head stage are single-stage cancellations.
	if stage in SINGLE_STAGES or stage == "Head":
		return stage, [stage]

	chain = [s for s in CHAIN if s != "Head" or reference_doctype in HEAD_APPROVAL_DOCTYPES]
	return stage, chain[: chain.index(stage) + 1]


def encode_path(path):
	"""['Staff', 'HoS'] -> '|Staff|HoS|' — delimited so a transition condition can test membership."""
	return "|" + "|".join(path) + "|"


# ──────────────────────────────────────────────────────────────────────────────
# Workflow definition
# ──────────────────────────────────────────────────────────────────────────────


def _transition_rows():
	"""
	Every transition of the cancellation workflow, with the condition that
	decides whether it applies to a given request.

	Conditions read `doc.stage_path` ('|Staff|HoS|') and `doc.stop_stage` and
	are evaluated by Frappe itself, so the form buttons and apply_workflow
	both only offer the transitions that belong to this request's route.
	"""
	rows = []

	# Draft -> first stage of the request's path. Whoever files the request submits it.
	for stage in ALL_STAGES:
		state_name = STAGE_STATES[stage][0]
		rows.append(
			{
				"state": "Draft",
				"action": "Submit",
				"next_state": state_name,
				"allowed": ["All"],
				"condition": f'(doc.stage_path or "").startswith("|{stage}|")',
			}
		)

	for stage in ALL_STAGES:
		state_name, roles = STAGE_STATES[stage]

		# Forward to the next stage of the chain, unless this is where the request stops.
		if stage in CHAIN and stage != CHAIN[-1]:
			next_stage = CHAIN[CHAIN.index(stage) + 1]
			rows.append(
				{
					"state": state_name,
					"action": "Approve",
					"next_state": STAGE_STATES[next_stage][0],
					"allowed": roles,
					"condition": f'"|{next_stage}|" in (doc.stage_path or "")',
				}
			)

		# Stop here: approving at the stop stage finishes the cancellation.
		rows.append(
			{
				"state": state_name,
				"action": "Approve",
				"next_state": "Approved",
				"allowed": roles,
				"condition": f'doc.stop_stage == "{stage}"',
			}
		)

		rows.append(
			{
				"state": state_name,
				"action": "Reject",
				"next_state": "Rejected",
				"allowed": roles,
				"condition": None,
			}
		)

	return rows


def ensure_cancellation_workflow(rebuild=False):
	"""
	Create the Cancellation Request Workflow if it does not exist (or rebuild
	it from the definition above) and make it the active workflow.

	Idempotent: a normal call is a no-op when the workflow is already there.
	"""
	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		if not rebuild:
			return WORKFLOW_NAME
		frappe.delete_doc("Workflow", WORKFLOW_NAME, ignore_permissions=True, force=True)

	# Role links are validated on insert. A role that does not exist on this site
	# is dropped, but a stage left with no approver role at all is an error.
	existing_roles = set(frappe.get_all("Role", pluck="name"))
	for stage, (_state, roles) in STAGE_STATES.items():
		if not [r for r in roles if r in existing_roles]:
			frappe.throw(_("No role exists for cancellation stage {0}: {1}").format(stage, ", ".join(roles)))

	rows = _transition_rows()
	state_names = ["Draft", "Approved", "Rejected"] + [STAGE_STATES[s][0] for s in ALL_STAGES]
	action_names = {"Submit", "Approve", "Reject"}

	# Workflow Transition.action / Workflow Document State.state are Links.
	for action in action_names:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)
	for state in state_names:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}).insert(
				ignore_permissions=True
			)

	workflow = frappe.new_doc("Workflow")
	workflow.workflow_name = WORKFLOW_NAME
	workflow.document_type = "Cancellation Request"
	workflow.workflow_state_field = "workflow_state"
	workflow.is_active = 1
	workflow.send_email_alert = 0

	workflow.append("states", {"state": "Draft", "doc_status": "0", "allow_edit": "All"})
	for stage in ALL_STAGES:
		state_name, roles = STAGE_STATES[stage]
		# One row per role: allow_edit is a Link -> Role holding exactly one role.
		for role in [r for r in roles if r in existing_roles]:
			workflow.append("states", {"state": state_name, "doc_status": "0", "allow_edit": role})
	workflow.append("states", {"state": "Approved", "doc_status": "0", "allow_edit": "System Manager"})
	workflow.append("states", {"state": "Rejected", "doc_status": "0", "allow_edit": "System Manager"})

	for row in rows:
		# Same one-row-per-role expansion for transitions.
		for role in [r for r in row["allowed"] if r in existing_roles]:
			workflow.append(
				"transitions",
				{
					"state": row["state"],
					"action": row["action"],
					"next_state": row["next_state"],
					"allowed": role,
					"allow_self_approval": 1,
					"condition": row["condition"],
				},
			)

	workflow.flags.ignore_permissions = True
	workflow.insert()
	frappe.clear_cache(doctype="Cancellation Request")
	return WORKFLOW_NAME
