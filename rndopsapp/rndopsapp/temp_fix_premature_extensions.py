import frappe


PREMATURE = {
	# extension_name: (ps_details_name, bad_tenure_row_name, old_joining, old_completion, old_basic)
	"lm91io4tjt": ("4emu8rkhca", "abmoso754s", "2026-03-09", "2026-09-08", 35000),
	"hr2jisqcks": ("633mhc6vdm", "fgt5hu2a79", "2026-03-25", "2026-09-24", 56000),
	"41ep0jup0h": ("08s46fqku7", "ifbsfc9lpl", "2024-12-22", "2026-10-23", 28500),
}

ALREADY_CORRECT = [
	"ves0lu7t1t", "qonnua77a5", "ue6f4ik3ln", "4fifvrssfa", "quos2fkrrt",
	"vdstf9jpkq", "3ds2pdo8pj", "rm3s3n0qab", "csjgem1nkq", "uumpeoltgc",
	"oulokupnhj", "ac7m1fv2ip", "927odsfhvu",
]


def run():
	for ext_name, (ps_name, bad_row, old_join, old_comp, old_basic) in PREMATURE.items():
		ps = frappe.get_doc("Project Staff Details", ps_name)
		ps.set("table_ymed", [r for r in ps.table_ymed if r.name != bad_row])
		ps.ps_joining_date = old_join
		ps.ps_term_completion_date = old_comp
		ps.ps_basic_salary = old_basic
		ps.flags.ignore_permissions = True
		ps.save()

		ext = frappe.get_doc("Project Staff Extension", ext_name)
		ext.db_set("tenure_row_created", 0)
		print(f"Reverted {ps_name} ({ext_name}) to term {old_join} -> {old_comp}")

	for ext_name in ALREADY_CORRECT:
		ext = frappe.get_doc("Project Staff Extension", ext_name)
		ext.db_set("tenure_row_created", 1)
		print(f"Flagged {ext_name} as already applied")

	frappe.db.commit()
	print("Done.")
