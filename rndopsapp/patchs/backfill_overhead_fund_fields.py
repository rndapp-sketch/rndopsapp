# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Backfill the generic overhead fields onto PDF projects minted before they existed.

PDF was the first overhead fund to be surfaced as a project, and it carried its own pair
of fields: `is_pdf_project` / `pdf_employee_id`. DPF made that shape untenable — a second
fund would have meant a second pair and a second branch everywhere — so the pair was
generalised to `is_overhead_project` / `overhead_fund_type` / `overhead_scope_id`.

This copies the old pair into the new one. It is idempotent, and the resolution code
falls back to the old pair anyway, so a site that has not run it yet still works — this
just means every read takes the fast path and the payment queue picks these projects up
from the primary query rather than the legacy top-up.

The old fields are deliberately left populated: anything still reading them keeps working.
"""

import frappe


def execute():
	rows = frappe.get_all(
		"Project Registration",
		filters={"is_pdf_project": 1},
		fields=["name", "pdf_employee_id", "is_overhead_project", "overhead_fund_type"],
	)

	updated = 0
	for row in rows:
		if row.get("is_overhead_project") and row.get("overhead_fund_type"):
			continue
		if not row.get("pdf_employee_id"):
			# Nothing to scope by; leave it alone rather than writing a fund that cannot
			# address anything on the Accounts side.
			frappe.log_error(
				f"PDF project {row['name']} has no pdf_employee_id — not backfilled",
				"Overhead Backfill - Skipped",
			)
			continue

		frappe.db.set_value(
			"Project Registration",
			row["name"],
			{
				"is_overhead_project": 1,
				"overhead_fund_type": "PDF",
				"overhead_scope_id": str(row["pdf_employee_id"]).strip(),
			},
			update_modified=False,
		)
		updated += 1

	frappe.db.commit()
	print(f"Overhead backfill: {updated} PDF project(s) given generic fund fields.")
