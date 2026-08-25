"""Endpoints backing the Legacy Records tab on the project overview page."""

import mimetypes
import os

import frappe
from frappe import _

from rndopsapp.legacy.file_source import LegacyFileError, read_legacy_file
from rndopsapp.legacy.workbook import MAX_ROWS, parse_workbook

UNREACHABLE = "The legacy file server could not be reached. Please try again later."


def _check_project_permission(docname):
	if not docname:
		frappe.throw(_("docname is required"))
	if not frappe.db.exists("Project Registration", docname):
		frappe.throw(_("Project {0} not found").format(docname), frappe.DoesNotExistError)
	# Routes through the app's has_permission hook, so delegated access works too.
	if not frappe.has_permission("Project Registration", "read", doc=docname):
		raise frappe.PermissionError


def _get_mapping(docname):
	if not frappe.db.exists("Legacy Project Mapping", docname):
		return None
	return frappe.get_doc("Legacy Project Mapping", docname)


def _resolve_file(docname, rel_path):
	"""Return (mapping, file_row) for a path that genuinely belongs to this project."""
	mapping = _get_mapping(docname)
	if not mapping:
		frappe.throw(_("No legacy record is mapped to this project"), frappe.DoesNotExistError)

	for row in mapping.files:
		if row.rel_path == rel_path:
			return mapping, row

	# Refusing unlisted paths stops this endpoint being used to read arbitrary files.
	raise frappe.PermissionError


def _read(mapping, file_row):
	try:
		return read_legacy_file(mapping.source_system, file_row.rel_path)
	except FileNotFoundError:
		frappe.throw(
			_("{0} is no longer present on the {1} file server").format(
				file_row.file_name, mapping.source_system
			),
			frappe.DoesNotExistError,
		)
	except LegacyFileError as exc:
		frappe.throw(_(str(exc)))
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Legacy file read failed: {file_row.rel_path}")
		frappe.throw(_(UNREACHABLE))


@frappe.whitelist()
def get_legacy_files(docname):
	"""Legacy mapping and available files for one Project Registration."""
	_check_project_permission(docname)
	mapping = _get_mapping(docname)

	if not mapping:
		return {"has_mapping": False, "files": []}

	return {
		"has_mapping": True,
		"mapping": {
			"source_system": mapping.source_system,
			"old_project_number": mapping.old_project_number,
			"old_project_title": mapping.old_project_title,
			"old_pi_name": mapping.old_pi_name,
			"old_status": mapping.old_status,
			"match_method": mapping.match_method,
			"title_similarity": mapping.title_similarity,
			"last_imported_on": mapping.last_imported_on,
		},
		"files": [
			{"file_name": row.file_name, "rel_path": row.rel_path, "file_ext": row.file_ext}
			for row in mapping.files
		],
	}


@frappe.whitelist()
def get_legacy_file_data(docname, rel_path, max_rows=MAX_ROWS):
	"""Parse one legacy workbook into JSON rows for table rendering."""
	_check_project_permission(docname)
	mapping, file_row = _resolve_file(docname, rel_path)
	raw = _read(mapping, file_row)

	try:
		max_rows = max(1, min(int(max_rows), MAX_ROWS))
	except (TypeError, ValueError):
		max_rows = MAX_ROWS

	try:
		sheets = parse_workbook(raw, file_row.file_name, max_rows=max_rows)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Legacy workbook parse failed: {rel_path}")
		frappe.throw(
			_("{0} could not be read as a spreadsheet. Try downloading it instead.").format(
				file_row.file_name
			)
		)

	return {
		"file_name": file_row.file_name,
		"source_system": mapping.source_system,
		"size": len(raw),
		"sheets": sheets,
	}


@frappe.whitelist()
def download_legacy_file(docname, rel_path):
	"""Stream the original legacy file through Frappe as a download."""
	_check_project_permission(docname)
	mapping, file_row = _resolve_file(docname, rel_path)
	raw = _read(mapping, file_row)

	frappe.response["filename"] = os.path.basename(file_row.file_name)
	frappe.response["filecontent"] = raw
	frappe.response["type"] = "download"
	frappe.response["content_type"] = (
		mimetypes.guess_type(file_row.file_name)[0] or "application/vnd.ms-excel"
	)
