# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Whitelisted API for the project ledger page's "Ledger Notes".

Endpoints (all under rndopsapp.rndopsapp.ledger_notes_api):
    get_ledger_notes(project_no)
    save_ledger_note(project_no, content, transaction_id=None, reference_summary=None, modified=None)
    delete_ledger_note(name)

Anyone with read permission on the "Ledger Note" DocType can read; only users holding the
"staff, RnD" role can save or delete. The role is enforced here, not just in the UI.
"""

import frappe
from frappe import _
from frappe.utils.html_utils import clean_html

STAFF_ROLE = "staff, RnD"
NOTE_FIELDS = ["name", "transaction_id", "reference_summary", "content", "modified", "modified_by"]


def _require_staff():
	if STAFF_ROLE not in frappe.get_roles(frappe.session.user):
		frappe.throw(
			_("Only users with the role {0} can create, edit or delete ledger notes.").format(STAFF_ROLE),
			frappe.PermissionError,
		)


def _find_project(project_no):
	"""Project Registration name for `project_no`, or None. Accepts either the document
	name or the human-readable project_no, since the ledger page works with the latter
	and the Link field stores the former."""
	project_no = (project_no or "").strip()
	if not project_no:
		return None
	return frappe.db.get_value("Project Registration", project_no, "name") or frappe.db.get_value(
		"Project Registration", {"project_no": project_no}, "name"
	)


def _serialize(row):
	out = dict(row)
	out["modified"] = str(out["modified"]) if out.get("modified") else None
	return out


@frappe.whitelist()
def get_ledger_notes(project_no):
	"""All notes of a project, oldest first."""
	frappe.has_permission("Ledger Note", "read", throw=True)

	project = _find_project(project_no)
	if not project:
		return []

	rows = frappe.get_list(
		"Ledger Note",
		filters={"project_no": project},
		fields=NOTE_FIELDS,
		order_by="creation asc",
		limit_page_length=0,
	)
	return [_serialize(r) for r in rows]


@frappe.whitelist()
def save_ledger_note(project_no, content, transaction_id=None, reference_summary=None, modified=None):
	"""Create or update the note for (project, transaction_id). Safe to call repeatedly
	(auto-save): a save that changes nothing does not write or bump `modified`.

	`modified` is the timestamp the client loaded; if the stored note has moved on,
	frappe.TimestampMismatchError is raised instead of overwriting.
	"""
	_require_staff()

	project = _find_project(project_no)
	if not project:
		frappe.throw(_("Project {0} does not exist.").format(project_no), frappe.DoesNotExistError)

	transaction_id = (transaction_id or "").strip()

	existing = frappe.get_all(
		"Ledger Note",
		filters={"project_no": project, "transaction_id": transaction_id},
		pluck="name",
		limit=1,
	)

	if existing:
		doc = frappe.get_doc("Ledger Note", existing[0])
		doc.flags.client_modified = modified

		new_content = clean_html(content or "")
		new_summary = doc.reference_summary if reference_summary is None else reference_summary
		if new_content == (doc.content or "") and (new_summary or "") == (doc.reference_summary or ""):
			doc.check_client_modified()
			return {"name": doc.name, "modified": str(doc.modified)}

		doc.content = content
		doc.reference_summary = new_summary
		doc.save()
	else:
		if modified:
			# The client had a note open, but it no longer exists (deleted by someone else).
			# Re-creating it silently would undo that delete.
			frappe.throw(
				_("This note was deleted by someone else since you opened it. Reload and try again."),
				frappe.TimestampMismatchError,
			)
		doc = frappe.get_doc(
			{
				"doctype": "Ledger Note",
				"project_no": project,
				"transaction_id": transaction_id,
				"reference_summary": reference_summary,
				"content": content,
			}
		)
		doc.insert()

	return {"name": doc.name, "modified": str(doc.modified)}


@frappe.whitelist()
def delete_ledger_note(name):
	_require_staff()

	if not name or not frappe.db.exists("Ledger Note", name):
		frappe.throw(_("Ledger Note {0} does not exist.").format(name), frappe.DoesNotExistError)

	frappe.delete_doc("Ledger Note", name)
	return {"name": name}
