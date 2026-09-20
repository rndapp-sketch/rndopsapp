import frappe


def execute():
	"""Indent General Form.igf_account_head changed from a hardcoded Select
	("Consumable"/"Contingency"/"Equipments"/"Other") to a Link -> Budget Head.
	Existing rows store the old label text, which is not a Budget Head docname,
	so rewrite them to the matching Budget Head record."""
	if not frappe.db.exists("DocType", "Indent General Form") or not frappe.db.exists(
		"DocType", "Budget Head"
	):
		return

	rows = frappe.get_all(
		"Indent General Form",
		filters={"igf_account_head": ["not in", ["", None]]},
		fields=["name", "igf_account_head"],
	)

	for row in rows:
		budget_head_name = frappe.db.get_value(
			"Budget Head", {"budget_head": row.igf_account_head}, "name"
		)
		if budget_head_name and budget_head_name != row.igf_account_head:
			frappe.db.set_value(
				"Indent General Form", row.name, "igf_account_head", budget_head_name
			)
		elif not budget_head_name:
			frappe.log_error(
				f"No Budget Head record matches label '{row.igf_account_head}' "
				f"for Indent General Form {row.name} during migration.",
				"migrate_igf_account_head_to_link",
			)
