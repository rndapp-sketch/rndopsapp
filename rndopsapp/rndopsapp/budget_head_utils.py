import frappe


def resolve_budget_head(value):
	"""
	Return the Budget Head docname for `value`, whatever form the caller sent:

	  * the docname itself              "h1lhg99vfq"
	  * the head's label, exactly       "Overhead"
	  * the label with other casing / extra spaces   " overhead  "
	  * the head's numeric id           "22"

	Project budget breakups and the account-head pickers only carry labels, while Link
	fields to Budget Head need the docname — assigning a label fails link validation with
	"Could not find Account Head: <label>". Returns `value` unchanged when nothing matches,
	or when more than one head matches (never guess), so Frappe still reports a genuinely
	invalid head.
	"""
	value = (value or "").strip() if isinstance(value, str) else value
	if not value:
		return value
	value = str(value)

	if frappe.db.exists("Budget Head", value):
		return value

	exact = frappe.db.get_value("Budget Head", {"budget_head": value}, "name")
	if exact:
		return exact

	# Same label with different case or spacing.
	wanted = " ".join(value.split()).lower()
	matches = [
		h.name
		for h in frappe.get_all("Budget Head", fields=["name", "budget_head"], limit_page_length=0)
		if " ".join((h.budget_head or "").split()).lower() == wanted
	]
	if len(matches) == 1:
		return matches[0]

	# Numeric Budget Head id.
	if value.isdigit() and not matches:
		by_id = frappe.get_all("Budget Head", filters={"id": int(value)}, pluck="name", limit_page_length=2)
		if len(by_id) == 1:
			return by_id[0]

	return value


def resolve_budget_head_links(doc, method=None):
	"""
	doc_events hook: turn a Budget Head label into its docname on every Link-to-Budget-Head
	field of `doc` and of its child rows, before Frappe's link validation runs.

	The project account-head pickers return labels ("Overhead") while these Links need the
	docname ("h1lhg99vfq"); see resolve_budget_head. Values that match nothing are left
	alone so a genuinely invalid head still fails with Frappe's own message.
	"""
	def fix(target, link_fields):
		for df in link_fields:
			value = target.get(df.fieldname)
			if value:
				target.set(df.fieldname, resolve_budget_head(value))

	meta = frappe.get_meta(doc.doctype)
	fix(doc, [df for df in meta.get_link_fields() if df.options == "Budget Head"])

	for table_df in meta.get_table_fields():
		child_links = [
			df for df in frappe.get_meta(table_df.options).get_link_fields() if df.options == "Budget Head"
		]
		if not child_links:
			continue
		for row in doc.get(table_df.fieldname) or []:
			fix(row, child_links)
