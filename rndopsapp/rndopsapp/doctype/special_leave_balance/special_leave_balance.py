# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, getdate, nowdate


class special_leave_balance(Document):
	def before_save(self):
		"""Auto-compute available_balance = total_credited - utilized_balance."""
		self.available_balance = max(0, (self.total_credited or 0) - (self.utilized_balance or 0))


# ---------------------------------------------------------------------------
# Public helpers used by travel.py and the scheduler
# ---------------------------------------------------------------------------

def get_or_create_balance_record(employee, year):
	"""
	Return the special_leave_balance doc for (employee, year).
	Creates a new record with 0 balance if it does not exist yet.
	"""
	name = f"{employee}-{year}"
	if frappe.db.exists("special_leave_balance", name):
		return frappe.get_doc("special_leave_balance", name)

	doc = frappe.new_doc("special_leave_balance")
	doc.employee = employee
	doc.year = year
	doc.total_credited = 0
	doc.utilized_balance = 0
	doc.available_balance = 0
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


def credit_leaves(employee, year, days, remarks=""):
	"""
	Add `days` to total_credited for the given employee/year.
	Appends an entry to the SCL log.
	"""
	doc = get_or_create_balance_record(employee, year)
	doc.total_credited = (doc.total_credited or 0) + days
	doc.last_credit_date = today()
	doc.append("scl_log", {
		"transaction_date": today(),
		"transaction_type": "Credit",
		"days": days,
		"remarks": remarks,
	})
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def deduct_leaves(employee, year, days, reference_doctype="Travel", reference_name="", remarks=""):
	"""
	Deduct `days` from the balance. Returns True on success, False if balance insufficient.
	Does NOT raise an exception — callers decide whether to block or warn.
	"""
	doc = get_or_create_balance_record(employee, year)
	available = (doc.total_credited or 0) - (doc.utilized_balance or 0)

	if days > available:
		return False  # insufficient balance — caller handles this

	doc.utilized_balance = (doc.utilized_balance or 0) + days
	doc.append("scl_log", {
		"transaction_date": today(),
		"transaction_type": "Deduction",
		"days": days,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"remarks": remarks or f"Deducted on approval of {reference_name}",
	})
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return True


def reverse_leaves(employee, year, days, reference_doctype="Travel", reference_name="", remarks=""):
	"""
	Reverse a previous deduction (e.g., Travel cancelled).
	Reduces utilized_balance by `days`.
	"""
	doc = get_or_create_balance_record(employee, year)
	doc.utilized_balance = max(0, (doc.utilized_balance or 0) - days)
	doc.append("scl_log", {
		"transaction_date": today(),
		"transaction_type": "Reversal",
		"days": days,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"remarks": remarks or f"Reversed on cancellation of {reference_name}",
	})
	doc.save(ignore_permissions=True)
	frappe.db.commit()


# ---------------------------------------------------------------------------
# Whitelisted API consumed by the Travel React form
# ---------------------------------------------------------------------------

_PERMANENT_CLASS_PREFIX = "PI - Principal Investigator"


def _is_permanent_employee(employee):
	"""Return True if the user's empclass is the Permanent Employee class."""
	empclass = frappe.db.get_value("User", employee, "empclass")
	if not empclass:
		return False
	empclass_name = frappe.db.get_value("EmployeeClass_prornd", empclass, "empclass_name")
	return empclass_name == _PERMANENT_CLASS_PREFIX


@frappe.whitelist()
def get_special_leave_balance(employee=None):
	"""
	Returns SCL balance info for the given employee (defaults to current user).
	Response shape:
	  {
	    employee, year, total_credited, utilized_balance,
	    available_balance, is_eligible
	  }
	"""
	if not employee:
		employee = frappe.session.user

	if employee == "Guest":
		return {"is_eligible": False, "error": "Not logged in"}

	# Only permanent employees are eligible for SCL
	if not _is_permanent_employee(employee):
		return {
			"employee": employee,
			"is_eligible": False,
			"reason": "Not a permanent employee",
		}

	year = getdate(nowdate()).year

	name = f"{employee}-{year}"
	if frappe.db.exists("special_leave_balance", name):
		doc = frappe.get_doc("special_leave_balance", name)
		return {
			"employee": employee,
			"year": year,
			"total_credited": doc.total_credited or 0,
			"utilized_balance": doc.utilized_balance or 0,
			"available_balance": max(0, (doc.total_credited or 0) - (doc.utilized_balance or 0)),
			"is_eligible": True,
		}

	# Permanent employee but no credit record yet (backfill pending)
	return {
		"employee": employee,
		"year": year,
		"total_credited": 0,
		"utilized_balance": 0,
		"available_balance": 0,
		"is_eligible": True,
	}
