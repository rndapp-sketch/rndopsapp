"""Whitelisted wrapper around the importer, so an admin upload page can reuse it."""

import os

import frappe
from frappe import _

from rndopsapp.legacy.importer import import_legacy_mapping

DEFAULT_FILENAMES = (
	"Pragati_Migration_Mapping.xlsx",
	"PROJECT_Excel_Info.xlsx",
	"RNDOPS_PROJECTS_REMOTE_Excel_Info.xlsx",
)


def resolve_paths(mapping_path=None, proman_index_path=None, rndops_index_path=None):
	"""Fall back to `legacy_import_dir` in site_config for any path not given."""
	given = (mapping_path, proman_index_path, rndops_index_path)
	if all(given):
		return given

	import_dir = frappe.conf.get("legacy_import_dir")
	if not import_dir:
		frappe.throw(
			_("Provide all three workbook paths, or set 'legacy_import_dir' in site_config.json")
		)

	return tuple(
		path or os.path.join(import_dir, name) for path, name in zip(given, DEFAULT_FILENAMES)
	)


@frappe.whitelist()
def run_import(mapping_path=None, proman_index_path=None, rndops_index_path=None, dry_run=0):
	frappe.only_for("System Manager")
	paths = resolve_paths(mapping_path, proman_index_path, rndops_index_path)
	return import_legacy_mapping(*paths, dry_run=frappe.utils.cint(dry_run))
