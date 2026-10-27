import frappe


def resolve_budget_head(value):
	"""
	Return the Budget Head docname for `value`, which may already be a docname
	("h1lhg99vfq") or the head's label ("Overhead"). Project budget breakups and
	the Other-PI picker only carry labels, while Link fields to Budget Head need
	the docname — assigning a label fails link validation with
	"Could not find Account Head: Overhead". Returns `value` unchanged when
	nothing matches, so Frappe still reports a genuinely invalid head.
	"""
	value = (value or "").strip()
	if not value or frappe.db.exists("Budget Head", value):
		return value
	return frappe.db.get_value("Budget Head", {"budget_head": value}, "name") or value
