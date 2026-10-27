import frappe

from rndopsapp.rndopsapp.cancellation_workflow import ensure_cancellation_workflow


def execute():
	"""Rebuild the Cancellation Request Workflow without the PI stage: an
	application pending at its PI is cancelled through Staff, not a PI step."""
	if not frappe.db.exists("DocType", "Cancellation Request"):
		return

	ensure_cancellation_workflow(rebuild=True)
