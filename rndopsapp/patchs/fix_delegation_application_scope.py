import json

import frappe

_APPLICATION_DOCTYPES = [
	"Travel",
	"TA DA Settlement",
	"Temporary Advance",
	"Advance Settlement",
	"Reimbursement",
	"Direct Purchase",
	"Disbursal of Consultancy",
	"Disbursal of Honorarium",
	"Loan Request",
	"Indent General Form",
	"Indent Cum Sanction Sheet",
	"Recruitment Adhoc Contractual",
]


def execute():
	"""Migrate User Delegation.applications from a flat array of doc names to
	[{"doctype": ..., "name": ...}, ...] pairs, so list/detail scope checks can
	tell which doctype a name belongs to. See
	docs/delegate_user/application_level_delegation_backend_plan.md."""
	if not frappe.db.exists("DocType", "User Delegation"):
		return

	rows = frappe.get_all(
		"User Delegation",
		filters={"scope_type": "application"},
		fields=["name", "applications"],
	)

	for row in rows:
		if not row.applications:
			continue
		try:
			names = json.loads(row.applications)
		except Exception:
			continue
		if not isinstance(names, list) or not names:
			continue
		if isinstance(names[0], dict):
			# Already migrated.
			continue

		resolved = []
		for doc_name in names:
			doctype = next(
				(d for d in _APPLICATION_DOCTYPES if frappe.db.exists(d, doc_name)),
				None,
			)
			if doctype:
				resolved.append({"doctype": doctype, "name": doc_name})
			else:
				frappe.log_error(
					f"Could not resolve doctype for application '{doc_name}' "
					f"in User Delegation {row.name} during migration.",
					"fix_delegation_application_scope",
				)

		frappe.db.set_value("User Delegation", row.name, "applications", json.dumps(resolved))
