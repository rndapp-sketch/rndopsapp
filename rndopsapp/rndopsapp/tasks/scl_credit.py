# Copyright (c) 2026, rndops and contributors
# Scheduled tasks for Special Casual Leave (SCL) balance credit.
#
# Registered in hooks.py under scheduler_events["cron"]:
#   "0 0 1 1 *"  -> credit_january_scl   (Jan 1  - creates new year record, credits 15)
#   "0 0 1 7 *"  -> credit_july_scl      (Jul 1  - adds 15 to existing record)

import frappe
from frappe.utils import getdate, nowdate

from rndopsapp.rndopsapp.doctype.special_leave_balance.special_leave_balance import (
	credit_leaves,
	get_or_create_balance_record,
)

_CREDIT_DAYS = 15

# Name of the EmployeeClass_prornd record for permanent staff.
# Matched by empclass_name prefix so minor label changes don't break it.
_PERMANENT_CLASS_PREFIX = "PI - Principal Investigator"


def _get_permanent_employee_class_id():
	"""Return the `name` (ID) of the Permanent Employee class record."""
	result = frappe.db.get_value(
		"EmployeeClass_prornd",
		{"empclass_name": _PERMANENT_CLASS_PREFIX},
		"name",
	)
	if not result:
		frappe.log_error(
			f"[SCL] EmployeeClass_prornd record '{_PERMANENT_CLASS_PREFIX}' not found. "
			"No employees will be credited.",
			"SCL Credit - Missing Employee Class"
		)
	return result


def _get_all_eligible_employees():
	"""
	Return a list of User email IDs eligible for SCL.
	Only permanent employees (empclass = 'P - Permanent Employee') are eligible.
	"""
	permanent_class_id = _get_permanent_employee_class_id()
	if not permanent_class_id:
		return []

	users = frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"empclass": permanent_class_id,
			"name": ["not in", ["Guest", "Administrator"]],
		},
		pluck="name",
	)
	return users


def credit_january_scl():
	"""
	Runs on Jan 1.
	- Creates a fresh special_leave_balance record for the new year.
	- Credits 15 days as the first half-year allotment.
	"""
	year = getdate(nowdate()).year
	frappe.logger().info(f"[SCL] credit_january_scl triggered for year {year}")

	employees = _get_all_eligible_employees()
	credited = 0

	for emp in employees:
		try:
			# Ensure a clean record for the new year (get_or_create starts at 0)
			doc = get_or_create_balance_record(emp, year)

			# Guard: do not double-credit if Jan credit was already applied
			if doc.total_credited >= _CREDIT_DAYS:
				frappe.logger().info(f"[SCL] Skipping Jan credit for {emp} {year} — already credited {doc.total_credited}")
				continue

			credit_leaves(emp, year, _CREDIT_DAYS, remarks=f"January credit {year}")
			credited += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"[SCL] credit_january_scl failed for {emp}")

	frappe.logger().info(f"[SCL] January credit complete. Credited {credited}/{len(employees)} employees.")


def credit_july_scl():
	"""
	Runs on Jul 1.
	- Adds 15 days to the existing year record (total becomes 30).
	"""
	year = getdate(nowdate()).year
	frappe.logger().info(f"[SCL] credit_july_scl triggered for year {year}")

	employees = _get_all_eligible_employees()
	credited = 0

	for emp in employees:
		try:
			doc = get_or_create_balance_record(emp, year)

			# Guard: do not double-credit if July credit was already applied
			if doc.total_credited >= (_CREDIT_DAYS * 2):
				frappe.logger().info(f"[SCL] Skipping July credit for {emp} {year} — already at {doc.total_credited}")
				continue

			credit_leaves(emp, year, _CREDIT_DAYS, remarks=f"July credit {year}")
			credited += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"[SCL] credit_july_scl failed for {emp}")

	frappe.logger().info(f"[SCL] July credit complete. Credited {credited}/{len(employees)} employees.")


# ---------------------------------------------------------------------------
# Manual trigger — call from bench console for backfill / testing
# ---------------------------------------------------------------------------

@frappe.whitelist()
def manual_credit(employee, year, half):
	"""
	Manually credit SCL for a single employee.
	  half = "january" | "july"
	Call from bench: bench execute rndopsapp.rndopsapp.tasks.scl_credit.manual_credit
	                   --kwargs '{"employee":"user@example.com","year":2026,"half":"january"}'
	"""
	if half == "january":
		credit_leaves(employee, int(year), _CREDIT_DAYS, remarks=f"Manual January credit {year}")
	elif half == "july":
		credit_leaves(employee, int(year), _CREDIT_DAYS, remarks=f"Manual July credit {year}")
	else:
		frappe.throw("half must be 'january' or 'july'")

	return {"status": "success", "employee": employee, "year": year, "half": half, "days": _CREDIT_DAYS}
