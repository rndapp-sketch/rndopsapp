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
