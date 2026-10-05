# Copyright (c) 2026, rndops and contributors
# Shared logic for the "staff, RnD" post-submit field-update endpoints exposed
# by each of the 7 deposit slip doctypes (Deposit slip, Research Deposit Slip,
# T Testing / D Consultancy / Other Event / E Non Routine / Research
# Consultancy Deposit Slip). See DEPOSIT_SLIP_STAFF_POST_SUBMIT_UPDATE_PLAN.md
# at the app root for the design this implements.

import json

import frappe
from frappe import _

STAFF_ROLE = "staff, RnD"
BYPASS_ROLES = {STAFF_ROLE, "System Manager"}

# Fields no caller of this endpoint may ever touch, regardless of role.
# workflow_state/workflow_action are owned by the *_workflow_action endpoints;
# fund_received_ref is the Kafka producer/consumer pairing key (see
# kafka/producer/deposit_slip/, kafka/consumer/deposit_slip/) and must not be
# repointed after the fact.
PROTECTED_FIELDS = {
	"name", "owner", "creation", "modified", "modified_by", "doctype",
	"docstatus", "idx", "amended_from", "workflow_state", "workflow_action",
	"fund_received_ref",
}

TABLE_TYPES = {"Table", "Table MultiSelect"}
SKIP_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"}


def ensure_staff_or_manager():
	"""Raises frappe.PermissionError unless the caller has staff, RnD or System Manager."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not BYPASS_ROLES & roles:
		frappe.throw(
			_("Only Staff (RnD) can edit this document's fields after submission."),
			frappe.PermissionError,
		)


def _real_table_columns(doctype):
	"""
	Real DB column names, straight from information_schema. Doctype meta can
	list fields that haven't been migrated into the DB table yet (schema
	drift), so anything this module writes to or SELECTs must also be checked
	against this — same guard api.py's Doctype Explorer uses.
	"""
	try:
		return set(frappe.db.get_table_columns(doctype))
	except Exception:
		return None


def _valid_fieldnames(doctype):
	"""Real, non-table, non-structural fieldnames minus PROTECTED_FIELDS."""
	meta = frappe.get_meta(doctype)
	fieldnames = {
		df.fieldname for df in meta.fields
		if df.fieldtype not in TABLE_TYPES and df.fieldtype not in SKIP_TYPES
	} - PROTECTED_FIELDS
	columns = _real_table_columns(doctype)
	if columns is not None:
		fieldnames &= columns
	return fieldnames


def _table_fields(doctype):
	"""{fieldname: child_doctype} for this doctype's own Table fields."""
	meta = frappe.get_meta(doctype)
	return {
		df.fieldname: df.options
		for df in meta.fields
		if df.fieldtype in TABLE_TYPES and df.options
	}


def _child_valid_fieldnames(child_doctype):
	meta = frappe.get_meta(child_doctype)
	fieldnames = {
		df.fieldname for df in meta.fields
		if df.fieldtype not in TABLE_TYPES
	} - {"parent", "parentfield", "parenttype"}
	columns = _real_table_columns(child_doctype)
	if columns is not None:
		fieldnames &= columns
	return fieldnames


def _row_belongs_here(child_doctype, row_name, parent_doctype, docname, fieldname):
	owner = frappe.db.get_value(child_doctype, row_name, ["parent", "parentfield"], as_dict=True)
	return bool(owner) and owner.parent == docname and owner.parentfield == fieldname


def _apply_child_table_changes(doctype, docname, child_table_changes, table_fields):
	"""
	child_table_changes: list of
	    {"fieldname": <Table field on this doctype>,
	     "updated": [{"name": <child row name>, "changes": {field: value}}, ...],
	     "inserted": [{field: value, ...}, ...],
	     "deleted": [<child row name>, ...]}
	"""
	child_summary = []
	for entry in child_table_changes or []:
		fieldname = (entry or {}).get("fieldname")
		child_doctype = table_fields.get(fieldname)
		if not child_doctype:
			continue
		child_valid = _child_valid_fieldnames(child_doctype)

		n_updated = n_inserted = n_deleted = 0

		for row in entry.get("updated") or []:
			row_name = (row or {}).get("name")
			row_changes = (row or {}).get("changes") or {}
			if not row_name or not _row_belongs_here(child_doctype, row_name, doctype, docname, fieldname):
				continue
			for cfield, cvalue in row_changes.items():
				if cfield not in child_valid:
					continue
				frappe.db.set_value(child_doctype, row_name, cfield, cvalue, update_modified=False)
			n_updated += 1

		if entry.get("inserted"):
			max_idx = frappe.db.sql(
				f"SELECT COALESCE(MAX(idx), 0) FROM `tab{child_doctype}` WHERE parent=%s AND parentfield=%s",
				(docname, fieldname),
			)[0][0]
			for new_row in entry.get("inserted") or []:
				max_idx += 1
				row_doc = frappe.new_doc(child_doctype)
				row_doc.parent = docname
				row_doc.parenttype = doctype
				row_doc.parentfield = fieldname
				row_doc.idx = max_idx
				for cfield, cvalue in (new_row or {}).items():
					if cfield in child_valid:
						row_doc.set(cfield, cvalue)
				row_doc.insert(ignore_permissions=True)
				n_inserted += 1

		for row_name in entry.get("deleted") or []:
			if not _row_belongs_here(child_doctype, row_name, doctype, docname, fieldname):
				continue
			frappe.db.sql(f"DELETE FROM `tab{child_doctype}` WHERE name=%s", (row_name,))
			n_deleted += 1

		if n_updated or n_inserted or n_deleted:
			child_summary.append({
				"fieldname": fieldname, "updated": n_updated, "inserted": n_inserted, "deleted": n_deleted,
			})

	return child_summary


def _format_value(v):
	return "(empty)" if v in (None, "") else str(v)


def _log_post_submit_edit(doctype, docname, updated_fields, child_summary, before, after, user):
	"""
	frappe.db.set_value doesn't create a Version log the way doc.save() does,
	so a post-submit correction would otherwise be invisible. Leave a plain
	Comment on the document instead — cheapest option that still gives a
	readable trail in the desk timeline. Best-effort: never allowed to roll
	back the field update that already succeeded.
	"""
	if not updated_fields and not child_summary:
		return
	lines = [f"Staff post-submit edit by {user} on {frappe.utils.now()}:"]
	for field in updated_fields:
		lines.append(f"- {field}: {_format_value(before.get(field))} -> {_format_value(after.get(field))}")
	for c in child_summary:
		parts = []
		if c["updated"]:
			parts.append(f"{c['updated']} updated")
		if c["inserted"]:
			parts.append(f"{c['inserted']} inserted")
		if c["deleted"]:
			parts.append(f"{c['deleted']} deleted")
		lines.append(f"- {c['fieldname']}: {', '.join(parts)}")
	try:
		frappe.get_doc(doctype, docname).add_comment("Comment", "\n".join(lines))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Deposit Slip post-submit audit comment failed")


def update_locked_deposit_slip(doctype, docname, changes=None, child_table_changes=None):
	"""
	Core implementation shared by every deposit-slip doctype's
	update_<doctype>_fields(docname, changes, child_table_changes) endpoint.
	Writes only the fields/rows present in the payload via frappe.db.set_value
	(bypassing UpdateAfterSubmitError) — every other field is left untouched.
	Restricted to `staff, RnD` / System Manager.
	"""
	ensure_staff_or_manager()

	if isinstance(changes, str):
		changes = json.loads(changes) if changes else {}
	if isinstance(child_table_changes, str):
		child_table_changes = json.loads(child_table_changes) if child_table_changes else []

	if not docname or not frappe.db.exists(doctype, docname):
		return {"status": "error", "message": f"'{docname}' not found in {doctype}."}

	try:
		valid_fieldnames = _valid_fieldnames(doctype)
		table_fields = _table_fields(doctype)
		requested_fields = [f for f in (changes or {}) if f in valid_fieldnames]

		before = {}
		if requested_fields:
			before = frappe.db.get_value(doctype, docname, requested_fields, as_dict=True) or {}

		updated_fields = []
		for field in requested_fields:
			frappe.db.set_value(doctype, docname, field, changes[field], update_modified=False)
			updated_fields.append(field)

		child_summary = _apply_child_table_changes(doctype, docname, child_table_changes, table_fields)

		if not updated_fields and not child_summary:
			return {
				"status": "success", "doctype": doctype, "docname": docname,
				"updated_fields": [], "child_tables": [],
			}

		now = frappe.utils.now()
		user = frappe.session.user
		frappe.db.set_value(doctype, docname, {"modified": now, "modified_by": user}, update_modified=False)

		after = {}
		if updated_fields:
			after = frappe.db.get_value(doctype, docname, updated_fields, as_dict=True) or {}
		_log_post_submit_edit(doctype, docname, updated_fields, child_summary, before, after, user)

		frappe.db.commit()

		return {
			"status": "success", "doctype": doctype, "docname": docname,
			"updated_fields": updated_fields, "child_tables": child_summary,
			"modified": now, "modified_by": user,
		}
	except frappe.PermissionError:
		raise
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"update_locked_deposit_slip failed ({doctype})")
		return {"status": "error", "message": str(e)}
