import os
import re

import frappe

TEMPLATES_ROOT = os.path.join(
	frappe.get_app_path("rndopsapp"), "rndopsapp", "templates", "emails"
)

# A few filenames don't title-case nicely on their own (dp_po -> "Dp Po").
# Cosmetic only — template_name is just a human label now that Email
# Manager links to a template explicitly instead of matching doctype names.
_LABEL_OVERRIDES = {
	"dp_po": "DP PO",
	"niq": "NIQ",
	"amc": "AMC",
	"uc_request": "UC Request",
	"ta_da_settlement": "TA DA Settlement",
	"p_11_form": "P 11 Form",
	"ipr_invention_disclosure": "IPR Invention Disclosure",
	"myprojects": "Myprojects",
}

_CATEGORY_LABELS = {
	"purchase": "Purchase",
	"financial": "Financial",
	"project": "Project",
	"hr_staff": "HR / Staff",
	"deposits": "Deposits",
	"travel": "Travel",
	"ipr": "IPR",
	"other": "Other",
}


def _label_for(slug: str) -> str:
	if slug in _LABEL_OVERRIDES:
		return _LABEL_OVERRIDES[slug]
	return re.sub(r"\bOf\b", "of", slug.replace("_", " ").title())


def execute():
	"""One-time migration: load the 43 static HTML email templates
	(rndopsapp/rndopsapp/templates/emails/<category>/<slug>.html) into
	Email Notification Template records, so they become editable/addable
	from the Email Manager admin page instead of living only as files on
	disk. Idempotent — skips any template_name that already exists."""
	if not os.path.isdir(TEMPLATES_ROOT):
		return

	created = 0
	for category_dir in sorted(os.listdir(TEMPLATES_ROOT)):
		category_path = os.path.join(TEMPLATES_ROOT, category_dir)
		if not os.path.isdir(category_path):
			continue

		for filename in sorted(os.listdir(category_path)):
			if not filename.endswith(".html"):
				continue

			slug = filename[: -len(".html")]
			template_name = _label_for(slug)

			if frappe.db.exists("Email Notification Template", template_name):
				continue

			with open(os.path.join(category_path, filename), encoding="utf-8") as f:
				content = f.read()

			frappe.get_doc(
				{
					"doctype": "Email Notification Template",
					"template_name": template_name,
					"category": _CATEGORY_LABELS.get(category_dir, category_dir),
					"is_active": 1,
					"content": content,
				}
			).insert(ignore_permissions=True)
			created += 1

	if created:
		frappe.db.commit()

	# Backfill the one existing Email Manager config (Project Registration)
	# now that `template` is a required field — it predates this field.
	if frappe.db.exists("Email Manager", "Project Registration") and frappe.db.exists(
		"Email Notification Template", "Project Registration"
	):
		if not frappe.db.get_value("Email Manager", "Project Registration", "template"):
			frappe.db.set_value(
				"Email Manager", "Project Registration", "template", "Project Registration", update_modified=False
			)
			frappe.db.commit()
