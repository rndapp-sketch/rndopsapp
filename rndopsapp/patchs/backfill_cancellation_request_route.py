import frappe

from rndopsapp.rndopsapp.cancellation_workflow import (
	CHAIN,
	HEAD_APPROVAL_DOCTYPES,
	STAGE_STATES,
	encode_path,
	resolve_cancellation_path,
)

FINAL_STATES = ("Approved", "Rejected", "Draft")


def execute():
	"""
	Cancellation Requests filed before stop_stage / stage_path existed have no
	route, so none of the workflow's Approve transitions match and only Reject
	is offered. Give every open request a route.
	"""
	state_to_stage = {v[0]: k for k, v in STAGE_STATES.items()}
	rows = frappe.get_all(
		"Cancellation Request",
		filters={"workflow_state": ["not in", FINAL_STATES]},
		or_filters={"stop_stage": ["is", "not set"], "stage_path": ["is", "not set"]},
		fields=["name", "reference_doctype", "reference_name", "workflow_state"],
	)
	for r in rows:
		try:
			app_state = frappe.db.get_value(r.reference_doctype, r.reference_name, "workflow_state")
			stop_stage, path = resolve_cancellation_path(r.reference_doctype, app_state)
		except Exception:
			# Application is no longer in a cancellable state: stop at the stage the request is at now.
			stage = state_to_stage.get(r.workflow_state)
			if not stage:
				continue
			chain = [s for s in CHAIN if s != "Head" or r.reference_doctype in HEAD_APPROVAL_DOCTYPES]
			stop_stage, path = stage, ([stage] if stage not in chain else chain[: chain.index(stage) + 1])

		# The request is already past the earlier stages of its path, so the route must contain the current one.
		current = state_to_stage.get(r.workflow_state)
		if current and current not in path:
			path = [current]
			stop_stage = current
		frappe.db.set_value(
			"Cancellation Request", r.name, {"stop_stage": stop_stage, "stage_path": encode_path(path)},
			update_modified=False,
		)
	frappe.db.commit()
