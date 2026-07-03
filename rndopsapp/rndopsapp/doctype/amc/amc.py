# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class AMC(Document):
	def validate(self):
		if not self.flags.get("skip_total_calculation"):
			self._compute_totals()

	def _compute_totals(self):
		# amc_value, amc_other_charges, amc_gst are Data fields (user-entered amounts).
		# amc_grand_total = value + other charges + gst amount.
		total = (
			flt(self.get("amc_value"))
			+ flt(self.get("amc_other_charges"))
			+ flt(self.get("amc_gst"))
		)
		self.amc_grand_total = total
