# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import string

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import getseries
from frappe.utils import cint, now_datetime

INVOICE_PREFIX = "INVO"
SERIES_KEY = "CONSULTANCY-INVOICE"
LETTERS = string.ascii_uppercase
DIGIT_SPAN = 999  # numeric part runs 001..999, then the letters advance


def invoice_suffix(n):
	"""Running sequence: 1 -> AAA001, 2 -> AAA002, ... 999 -> AAA999, 1000 -> AAB001, ...
	3 letters (base 26) followed by 3 digits."""
	if n < 1 or n > len(LETTERS) ** 3 * DIGIT_SPAN:
		frappe.throw(_("The Consultancy Invoice number sequence is exhausted."))
	block, digits = divmod(n - 1, DIGIT_SPAN)
	letters = ""
	for _i in range(3):
		block, rem = divmod(block, len(LETTERS))
		letters = LETTERS[rem] + letters
	return f"{letters}{digits + 1:03d}"


def generate_invoice_no():
	"""INVO-YYYY-MM-DD-AAA001: today's date plus the next number of one running sequence
	(never reset, so numbers are unique across days). The counter is the database-locked
	Frappe naming series, so concurrent saves can't be given the same number."""
	n = cint(getseries(SERIES_KEY, 1))
	return f"{INVOICE_PREFIX}-{now_datetime().strftime('%Y-%m-%d')}-{invoice_suffix(n)}"


class ConsultancyInvoice(Document):
	def autoname(self):
		if not self.invoice_no:
			self.invoice_no = generate_invoice_no()
		self.name = self.invoice_no

	def validate(self):
		self.project_no = (self.project_no or "").strip()
		self.fund_received_ref = (self.fund_received_ref or "").strip()

		filters = {"project_no": self.project_no, "fund_received_ref": self.fund_received_ref}
		if not self.is_new():
			filters["name"] = ["!=", self.name]
		existing = frappe.get_all("Consultancy Invoice", filters=filters, pluck="name", limit=1)
		if existing:
			frappe.throw(
				_("An invoice ({0}) already exists for project {1} and fund received ref {2}.").format(
					existing[0], self.project_no, self.fund_received_ref
				),
				frappe.DuplicateEntryError,
			)


# ── Whitelisted API ─────────────────────────────────────────────────────────
# save_con_invoice(project_no, fund_received_ref) -> {"invoice_no": ...}
# get_con_invoice(project_no, fund_received_ref)  -> {"invoice_no": ... | None}
# The only inputs are the project and the Fund Received it is invoiced against; the
# invoice number is generated on save, and saving the same pair again returns the number
# already issued. Both need permission on the DocType ("staff, RnD" / System Manager).

def _find_project(project_no):
	"""(Project Registration name, human-readable project_no), or None. Accepts either
	identifier."""
	project_no = (project_no or "").strip()
	if not project_no:
		return None
	name = frappe.db.get_value("Project Registration", project_no, "name") or frappe.db.get_value(
		"Project Registration", {"project_no": project_no}, "name"
	)
	if not name:
		return None
	return name, (frappe.db.get_value("Project Registration", name, "project_no") or name)


def _existing_invoice(project_no, fund_received_ref):
	rows = frappe.get_all(
		"Consultancy Invoice",
		filters={"project_no": project_no, "fund_received_ref": fund_received_ref},
		pluck="invoice_no",
		limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def save_con_invoice(project_no, fund_received_ref):
	"""Issue (or return the already issued) invoice number for a project + Fund Received."""
	frappe.has_permission("Consultancy Invoice", "create", throw=True)

	fund_received_ref = (fund_received_ref or "").strip()
	if not fund_received_ref:
		frappe.throw(_("Fund Received Ref is required."))

	project = _find_project(project_no)
	if not project:
		frappe.throw(_("Project {0} does not exist.").format(project_no), frappe.DoesNotExistError)
	project_name, project_number = project

	# fund_received_ref is the Fund Received's reference number (as used by the deposit
	# slips); the document name is accepted too.
	fund = frappe.get_all(
		"Fund Received",
		or_filters=[["fund_received_ref_number", "=", fund_received_ref], ["name", "=", fund_received_ref]],
		fields=["name", "prjreg_title"],
		limit=1,
	)
	if not fund:
		frappe.throw(_("Fund Received {0} does not exist.").format(fund_received_ref), frappe.DoesNotExistError)
	if fund[0].prjreg_title != project_name:
		frappe.throw(
			_("Fund Received {0} does not belong to project {1}.").format(fund_received_ref, project_number)
		)

	invoice_no = _existing_invoice(project_number, fund_received_ref)
	if not invoice_no:
		doc = frappe.get_doc(
			{"doctype": "Consultancy Invoice", "project_no": project_number, "fund_received_ref": fund_received_ref}
		)
		doc.insert()
		invoice_no = doc.invoice_no

	return {"invoice_no": invoice_no}


@frappe.whitelist()
def get_con_invoice(project_no, fund_received_ref):
	"""The invoice number issued for this project + Fund Received, or None."""
	frappe.has_permission("Consultancy Invoice", "read", throw=True)

	project = _find_project(project_no)
	fund_received_ref = (fund_received_ref or "").strip()
	if not project or not fund_received_ref:
		return {"invoice_no": None}

	return {"invoice_no": _existing_invoice(project[1], fund_received_ref)}
