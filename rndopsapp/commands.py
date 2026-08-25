import click
import frappe
from frappe.commands import get_site, pass_context


@click.command("import-legacy-mapping")
@click.argument("mapping_path", required=False)
@click.argument("proman_index_path", required=False)
@click.argument("rndops_index_path", required=False)
@click.option("--dry-run", is_flag=True, default=False, help="Report what would change without writing.")
@pass_context
def import_legacy_mapping(
	context, mapping_path=None, proman_index_path=None, rndops_index_path=None, dry_run=False
):
	"""Import the Proman / R&D OPS migration mapping into Legacy Project Mapping.

	Paths default to `legacy_import_dir` in site_config.json when omitted.
	"""
	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		from rndopsapp.legacy.importer import import_legacy_mapping as run
		from rndopsapp.legacy.importer_api import resolve_paths

		stats = run(*resolve_paths(mapping_path, proman_index_path, rndops_index_path), dry_run=dry_run)
		warnings = stats.pop("warnings", [])

		for key, value in stats.items():
			click.echo(f"{key:<20} {value}")
		if warnings:
			click.echo(f"\n{len(warnings)} warning(s):")
			for warning in warnings[:20]:
				click.echo(f"  - {warning}")
			if len(warnings) > 20:
				click.echo(f"  ... and {len(warnings) - 20} more")
	finally:
		frappe.destroy()


commands = [import_legacy_mapping]
