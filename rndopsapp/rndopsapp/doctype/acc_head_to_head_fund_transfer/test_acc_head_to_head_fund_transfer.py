# Copyright (c) 2026, rndops and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

DOCTYPE = "Acc Head to Head Fund Transfer"


class TestAccHeadtoHeadFundTransfer(FrappeTestCase):
	def _new_doc(self, **kwargs):
		doc = frappe.new_doc(DOCTYPE)
		doc.update(kwargs)
		return doc

	def test_same_source_and_destination_head_rejected(self):
		doc = self._new_doc(
			h2h_transfer_from="HEAD-A",
			h2h_transfer_to="HEAD-A",
			h2h_amount=1000,
		)
		with self.assertRaises(frappe.ValidationError):
			doc.validate_transfer()

	def test_non_positive_amount_rejected(self):
		doc = self._new_doc(
			h2h_transfer_from="HEAD-A",
			h2h_transfer_to="HEAD-B",
			h2h_amount=0,
		)
		with self.assertRaises(frappe.ValidationError):
			doc.validate_transfer()

	def test_amount_in_words_is_set(self):
		doc = self._new_doc(h2h_amount=1500)
		doc.set_amount_in_words()
		self.assertTrue(doc.h2h_amount_in_words)
