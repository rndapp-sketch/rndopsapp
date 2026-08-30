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
		# AMC value is entered either as a percentage of the PO's Basic Value (BV)
		# or as a direct amount, depending on amc_value_type.
		if self.get("amc_value_type") == "Percentage":
			computed_value = flt(self.get("basic_value_bv_of_the_po")) * flt(self.get("amc_value_percentage")) / 100
		else:
			computed_value = flt(self.get("amc_value"))
		self.amc_computed_value = computed_value

		self.amc_grand_total = (
			computed_value
			+ flt(self.get("amc_other_charges"))
			+ flt(self.get("amc_gst"))
		)
