import frappe

from rndopsapp.rndopsapp.cancellation_workflow import ensure_cancellation_workflow


def execute():
	"""Create the independent Cancellation Request Workflow (see
	docs/cancellation_request/CANCELLATION_WORKFLOW.md).

	The old per-doctype `cancel_*` workflows are left in place, inactive, so
	requests filed before this change can still be read; they are no longer
	created, rebuilt or activated.
	"""
	if not frappe.db.exists("DocType", "Cancellation Request"):
		return

	ensure_cancellation_workflow()
